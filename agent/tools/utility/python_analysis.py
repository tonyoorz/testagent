"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class PythonAnalysisTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="python_analysis",
            description="受限Python执行器（仅用于结构化数据分析），禁止反射与私有属性访问",
            parameters={"code": {"type": "string", "description": "Python代码，需赋值 final_answer"}},
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        datasets = data if isinstance(data, dict) else {}
        code = str(kwargs.get("code") or "").strip()
        if not code:
            return {"success": False, "tool": self.name, "error": "code 不能为空"}
        if "__" in code:
            return {"success": False, "tool": self.name, "error": "禁止 dunder/双下划线 访问"}
        if re.search(r"\._[a-zA-Z0-9]", code):
            return {"success": False, "tool": self.name, "error": "禁止访问以下划线开头的私有属性（下划线）"}
        for bad in ["getattr", "setattr", "delattr", "globals", "locals", "vars", "dir", "type(", "eval", "exec", "open(", "import ", "from "]:
            if bad in code:
                return {"success": False, "tool": self.name, "error": f"禁止调用 {bad.strip()}"}
        try:
            max_rows = int(os.getenv("AGENT_PYTHON_ANALYSIS_MAX_TOTAL_ROWS", "200000"))
        except Exception:
            max_rows = 200000
        total_rows = 0
        for v in (datasets or {}).values():
            if isinstance(v, pd.DataFrame):
                total_rows += int(len(v))
        if total_rows > max_rows:
            return {"success": False, "tool": self.name, "error": "数据量过大，拒绝执行"}
        try:
            timeout_s = int(os.getenv("AGENT_PYTHON_ANALYSIS_TIMEOUT_SECONDS", "5"))
        except Exception:
            timeout_s = 5
        timeout_s = max(1, min(timeout_s, 30))

        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(target=_python_analysis_worker, args=(q, code, datasets))
        p.daemon = True
        p.start()
        p.join(timeout_s)
        if p.is_alive():
            try:
                p.terminate()
            except Exception:
                pass
            return {"success": False, "tool": self.name, "error": "执行超时"}
        try:
            msg = q.get_nowait()
        except Exception:
            msg = {"ok": False, "error": "执行失败"}
        if not msg.get("ok"):
            return {"success": False, "tool": self.name, "error": msg.get("error") or "执行失败"}
        return {"success": True, "tool": self.name, "result": {"final_answer": msg.get("final_answer")}}
