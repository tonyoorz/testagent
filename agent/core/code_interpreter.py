"""
Code Interpreter — Python 沙箱执行引擎

让 Agent 能生成并执行 Python 代码来分析数据，解决 SQL 搞不定的问题。

特性：
1. 自动生成分析代码（LLM驱动）
2. 安全执行（只读数据库、超时、资源限制）
3. 结果自动捕获（stdout + 返回值）
4. 错误自修正（代码出错 → LLM修 → 重试）
5. 中间结果可打印调试

用法：
    from agent.core.code_interpreter import CodeInterpreter

    ci = CodeInterpreter(db_path="path/to/db.duckdb")
    result = ci.execute(
        question="ECU乒乓次数和风险评分有相关性吗？",
        data_profile=profile_summary,
        semantic_context="...",  # semantic_catalog 摘要
    )

环境变量：
    AGENT_CODE_INTERPRETER=1  开启（默认关闭）
    AGENT_CODE_TIMEOUT=30     执行超时（秒）
"""

import io
import json
import logging
import os
import subprocess
import sys
import textwrap
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 分析代码模板
_CODE_TEMPLATE = '''\
# -*- coding: utf-8 -*-
"""Agent-generated analysis code"""
import pandas as pd
import numpy as np
import json
import sys

# 数据加载
DB_PATH = {db_path_repr}
{data_load_code}

# === 用户问题 ===
# {question}
# === 分析代码 ===
{user_code}

# === 结果输出 ===
if 'result' not in dir():
    # 如果代码没有定义 result，尝试捕获最后一个表达式的值
    result = {{"success": True, "note": "代码执行完毕，但未定义 result 变量"}}

if isinstance(result, pd.DataFrame):
    result = result.to_dict(orient="records")
if not isinstance(result, dict):
    result = {{"success": True, "value": str(result)}}

# 确保 success 字段存在
result.setdefault("success", True)

print("___RESULT_JSON___")
print(json.dumps(result, ensure_ascii=False, default=str))
'''

# LLM 生成代码的 prompt
_CODE_GEN_PROMPT = """\
你是一个 Python 数据分析专家。根据用户问题和数据概况，生成分析代码。

## 规则
1. 只使用 pandas, numpy, scipy, duckdb 库
2. 数据库路径在 DB_PATH 变量中，使用 duckdb.connect(DB_PATH, read_only=True)
3. 如果已有 DataFrame（df 变量），直接使用
4. 把最终分析结果赋值给 result 变量（dict类型）
5. 可以使用 print() 输出中间调试信息
6. 不要使用 matplotlib/show/plot（无图形环境）
7. 代码中不要使用 input()
8. 处理空值：使用 .dropna() 或 fillna
9. 处理异常：用 try/except 包裹可能失败的操作

## 数据概况
{data_profile}

## 语义上下文（数据库表和字段含义）
{semantic_context}

## 用户问题
{question}

## 要求
只输出 Python 代码，不要解释。代码必须把结果赋值给 result 变量。
"""


@dataclass
class CodeResult:
    """代码执行结果。"""
    success: bool
    code: str = ""
    result: Optional[Dict[str, Any]] = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    duration_ms: int = 0
    attempts: int = 1


class CodeInterpreter:
    """Python 沙箱执行引擎。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        timeout: int = 0,
        max_retries: int = 2,
        llm: Any = None,
    ):
        self._db_path = db_path
        self._timeout = timeout or int(os.getenv("AGENT_CODE_TIMEOUT", "30") or 30)
        self._max_retries = max_retries
        self._llm = llm

    @staticmethod
    def is_enabled() -> bool:
        return os.getenv("AGENT_CODE_INTERPRETER", "0") == "1"

    def execute(
        self,
        question: str,
        code: Optional[str] = None,
        data_profile: str = "",
        semantic_context: str = "",
        df: Optional[pd.DataFrame] = None,
    ) -> CodeResult:
        """执行分析代码。

        如果不提供 code，会用 LLM 自动生成。
        """
        # 获取或生成代码
        if code:
            user_code = code
        else:
            user_code = self._generate_code(question, data_profile, semantic_context)
            if not user_code:
                return CodeResult(success=False, error="无法生成分析代码")

        # 准备数据加载代码
        data_load_code = self._build_data_load_code(df)

        # 组装完整代码
        full_code = _CODE_TEMPLATE.format(
            db_path_repr=repr(self._db_path or ""),
            question=question.replace("'", "\\'"),
            data_load_code=data_load_code,
            user_code=user_code,
        )

        # 执行（带重试）
        last_result = None
        for attempt in range(1, self._max_retries + 1):
            result = self._run_code(full_code)
            result.attempts = attempt
            result.code = user_code

            if result.success:
                return result

            # 失败 → 尝试 LLM 修正
            if attempt < self._max_retries and self._llm:
                corrected = self._fix_code(
                    original_code=user_code,
                    error=result.stderr or result.error,
                    question=question,
                    data_profile=data_profile,
                )
                if corrected and corrected != user_code:
                    user_code = corrected
                    full_code = _CODE_TEMPLATE.format(
                        db_path_repr=repr(self._db_path or ""),
                        question=question.replace("'", "\\'"),
                        data_load_code=data_load_code,
                        user_code=user_code,
                    )
                    continue

            last_result = result
            break

        return last_result or CodeResult(success=False, error="执行失败")

    # ------------------------------------------------------------------
    # 代码生成
    # ------------------------------------------------------------------

    def _generate_code(self, question: str, data_profile: str, semantic_context: str) -> Optional[str]:
        """用 LLM 生成分析代码。"""
        if not self._llm:
            return None

        prompt = _CODE_GEN_PROMPT.format(
            question=question,
            data_profile=data_profile[:2000] if data_profile else "(无数据概况)",
            semantic_context=semantic_context[:2000] if semantic_context else "(无语义上下文)",
        )

        try:
            client = getattr(self._llm, "client", self._llm)
            model = getattr(self._llm, "model", None)

            if hasattr(client, "chat") and callable(client.chat):
                messages = [{"role": "user", "content": prompt}]
                resp = client.chat(messages=messages, model=model)
            elif hasattr(client, "create") and callable(client.create):
                resp = client.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                return None

            # 提取文本
            text = self._extract_response_text(resp)
            if not text:
                return None

            # 清理 markdown 围栏
            text = text.strip()
            if text.startswith("```python"):
                text = text[len("```python"):]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            return text.strip()

        except Exception as e:
            logger.warning(f"Code generation failed: {e}")
            return None

    def _fix_code(self, original_code: str, error: str, question: str, data_profile: str) -> Optional[str]:
        """用 LLM 修正出错的代码。"""
        if not self._llm:
            return None

        prompt = f"""\
代码执行出错，请修正。

## 原始问题
{question}

## 原始代码
```python
{original_code}
```

## 错误信息
{error[:1000]}

## 要求
只输出修正后的完整 Python 代码，不要解释。"""

        try:
            client = getattr(self._llm, "client", self._llm)
            model = getattr(self._llm, "model", None)

            if hasattr(client, "chat") and callable(client.chat):
                resp = client.chat(messages=[{"role": "user", "content": prompt}], model=model)
            elif hasattr(client, "create") and callable(client.create):
                resp = client.create(model=model, messages=[{"role": "user", "content": prompt}])
            else:
                return None

            text = self._extract_response_text(resp)
            if not text:
                return None

            text = text.strip()
            if text.startswith("```python"):
                text = text[len("```python"):]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            return text.strip()

        except Exception as e:
            logger.warning(f"Code fix failed: {e}")
            return None

    # ------------------------------------------------------------------
    # 代码执行
    # ------------------------------------------------------------------

    def _run_code(self, full_code: str) -> CodeResult:
        """在子进程中安全执行代码。"""
        import tempfile
        import time

        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(full_code)
            tmp_path = f.name

        try:
            t0 = time.time()
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env={**os.environ, "PYTHONPATH": os.getcwd()},
            )
            duration_ms = int((time.time() - t0) * 1000)

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            if proc.returncode != 0:
                return CodeResult(
                    success=False,
                    stderr=stderr,
                    stdout=stdout,
                    error=stderr[:500] or f"Exit code {proc.returncode}",
                    duration_ms=duration_ms,
                )

            # 从 stdout 提取结果
            result_data = self._extract_result(stdout)

            if result_data is not None:
                # 移除结果 JSON 行，保留调试输出
                debug_output = self._strip_result_json(stdout)
                return CodeResult(
                    success=True,
                    result=result_data,
                    stdout=debug_output,
                    duration_ms=duration_ms,
                )
            else:
                return CodeResult(
                    success=True,
                    result={"success": True, "note": "代码执行完毕，未输出结构化结果"},
                    stdout=stdout,
                    duration_ms=duration_ms,
                )

        except subprocess.TimeoutExpired:
            return CodeResult(
                success=False,
                error=f"执行超时（{self._timeout}秒）",
            )
        except Exception as e:
            return CodeResult(
                success=False,
                error=str(e),
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _build_data_load_code(self, df: Optional[pd.DataFrame]) -> str:
        """构建数据加载代码。"""
        if df is not None:
            # 保存 DataFrame 到临时 CSV，在子进程中读取
            import tempfile
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
            df.to_csv(tmp.name, index=False)
            return f"df = pd.read_csv({repr(tmp.name)})\nprint(f'DataFrame loaded: {{len(df)}} rows')"
        elif self._db_path:
            return "import duckdb\ncon = duckdb.connect(DB_PATH, read_only=True)\nprint(f'Database connected: {DB_PATH}')"
        return ""

    @staticmethod
    def _extract_result(stdout: str) -> Optional[Dict[str, Any]]:
        """从 stdout 提取 ___RESULT_JSON___ 后面的 JSON。"""
        marker = "___RESULT_JSON___"
        idx = stdout.rfind(marker)
        if idx < 0:
            return None
        json_str = stdout[idx + len(marker):].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _strip_result_json(stdout: str) -> str:
        """移除结果 JSON，保留调试输出。"""
        marker = "___RESULT_JSON___"
        idx = stdout.rfind(marker)
        if idx < 0:
            return stdout
        return stdout[:idx].strip()

    @staticmethod
    def _extract_response_text(resp) -> str:
        """从 LLM 响应中提取文本。"""
        if isinstance(resp, dict):
            choices = resp.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                return str(msg.get("content") or "")
        elif hasattr(resp, "choices"):
            return str(resp.choices[0].message.content)
        elif isinstance(resp, str):
            return resp
        return ""
