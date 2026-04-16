"""
Prompt Registry — 统一 Prompt 管理中心

集中管理所有 system prompt，支持：
1. 按 name 查找 prompt
2. 变量注入（{{variable}}）
3. 版本标记
4. 运行时覆盖（A/B 测试、自定义 prompt）

用法：
    from agent.core.prompt_registry import PromptRegistry

    reg = PromptRegistry()
    prompt = reg.render("defect_analysis", data_context="...", user_role="engineer")
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# prompt 文件目录（YAML/JSON 格式的自定义 prompt 可以放这里）
_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "prompts")


class PromptTemplate:
    """一个 prompt 模板。"""

    __slots__ = ("name", "template", "version", "description", "variables", "tags")

    def __init__(
        self,
        name: str,
        template: str,
        version: str = "1.0",
        description: str = "",
        tags: Optional[List[str]] = None,
    ):
        self.name = name
        self.template = template
        self.version = version
        self.description = description
        self.tags = tags or []
        # 自动提取 {{variable}} 占位符
        self.variables = sorted(set(re.findall(r"\{\{(\w+)\}\}", template)))

    def render(self, **kwargs) -> str:
        """渲染模板，注入变量。未提供的变量保留原样。"""
        result = self.template
        for key, value in kwargs.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "variables": self.variables,
            "tags": self.tags,
            "template_length": len(self.template),
        }


class PromptRegistry:
    """统一 Prompt 管理中心。"""

    _instance: Optional["PromptRegistry"] = None

    def __init__(self):
        self._prompts: Dict[str, PromptTemplate] = {}
        self._overrides: Dict[str, str] = {}  # 运行时覆盖
        self._load_builtin_prompts()
        self._load_file_prompts()

    @classmethod
    def get_instance(cls) -> "PromptRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        template: str,
        version: str = "1.0",
        description: str = "",
        tags: Optional[List[str]] = None,
    ):
        """注册一个 prompt 模板。"""
        pt = PromptTemplate(name=name, template=template, version=version, description=description, tags=tags)
        self._prompts[name] = pt
        logger.debug(f"Registered prompt: {name} v{version}")

    def override(self, name: str, template: str):
        """运行时覆盖某个 prompt（用于 A/B 测试或自定义）。"""
        self._overrides[name] = template
        logger.info(f"Prompt override: {name}")

    # ------------------------------------------------------------------
    # 查询与渲染
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[PromptTemplate]:
        """获取 prompt 模板。"""
        return self._prompts.get(name)

    def render(self, name: str, **kwargs) -> str:
        """渲染指定 prompt。"""
        pt = self._prompts.get(name)
        if pt is None:
            logger.warning(f"Prompt not found: {name}")
            return ""

        # 优先使用 override
        template = self._overrides.get(name, pt.template)
        result = template
        for key, value in kwargs.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result

    def list_prompts(self, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有 prompt。"""
        prompts = list(self._prompts.values())
        if tag:
            prompts = [p for p in prompts if tag in p.tags]
        return [p.to_dict() for p in prompts]

    # ------------------------------------------------------------------
    # 内置 Prompt 定义
    # ------------------------------------------------------------------

    def _load_builtin_prompts(self):
        """注册所有内置 prompt。"""

        # === 核心 Agent Prompt ===
        self.register(
            name="defect_analysis",
            description="缺陷分析主 prompt（defect dashboard）",
            tags=["core", "defect"],
            template=(
                "You are an automotive defect analysis assistant for BMW DTSV. "
                "Focus on severity, trend, module distribution, and risk prioritization.\n"
                "Key business rules:\n"
                "- Status codes: 01-New → 02-Investigation → 03-In Progress → 04-Waiting → 05-Deferred "
                "→ 06-Concluded → 09-Concluded without action → 10-Closed. "
                "Status may have _severity suffix, use prefix matching.\n"
                "- TopIssue risk score: 8-dimension non-linear algorithm "
                "(Matrix exponential decay + Classification + ECU/Domain transfer + "
                "Parent/Child complexity logarithmic + Processing cycle bimodal + ShiftPU). >=60 = TopIssue.\n"
                "- severity_group: Critical Issues if matrix in severe_matrices(1A~3A) "
                "OR classification intersects severe_classifications.\n"
                "- project/fv/pu are mapped/filled fields, not Octane native.\n"
                "- Always explain WHY and suggest WHAT TO DO, not just report numbers.\n\n"
                "Rules:\n"
                "1) Do not fabricate numbers. Use only provided context/tool outputs.\n"
                "2) If data is missing, say what is missing and what to provide.\n"
                "3) Keep answers concise first, then actionable next steps.\n\n"
                "Current Data Context:\n{{data_context}}"
            ),
        )

        self.register(
            name="defect_explore",
            description="缺陷探索 prompt",
            tags=["core", "defect"],
            template=(
                "You are a defect exploration assistant for BMW DTSV Octane data. "
                "Help users explore defect distributions, trends, hot-spots and root causes.\n"
                "Focus areas: Matrix distribution, AIDA hotspots, TopIssue hotlist, "
                "Long-runner tracking, tester findings.\n"
                "Use the provided tool outputs; do not fabricate data.\n\n"
                "Current Data Context:\n{{data_context}}"
            ),
        )

        self.register(
            name="test_coverage",
            description="测试覆盖分析 prompt",
            tags=["core", "test"],
            template=(
                "You are a test coverage analysis assistant for BMW DTSV. "
                "Help users understand test execution status, pass/fail rates, "
                "coverage across modules/projects/FVs.\n"
                "Use only provided data; explain gaps and suggest improvements.\n\n"
                "Current Data Context:\n{{data_context}}"
            ),
        )

        self.register(
            name="general",
            description="通用分析 prompt",
            tags=["core"],
            template=(
                "You are a data analysis assistant for automotive testing and defect data. "
                "Answer questions about trends, distributions, comparisons, and risks.\n"
                "Use only the provided tool outputs and data context.\n"
                "Explain your reasoning and suggest actionable next steps.\n\n"
                "Current Data Context:\n{{data_context}}"
            ),
        )

        # === Agentic Runtime Prompt ===
        self.register(
            name="agentic_system",
            description="Agentic 模式的 system prompt",
            tags=["agentic"],
            template=(
                "你是一个专业的汽车测试数据分析专家。你可以使用工具来分析数据。\n\n"
                "重要规则：\n"
                "1. 只使用提供的工具分析数据，不要编造数据\n"
                "2. 先理解问题，再选择合适的工具\n"
                "3. 如果一个工具失败，尝试其他工具或参数\n"
                "4. 给出结论时要说明数据依据\n"
                "5. 提供可操作的建议\n\n"
                "用户问题：{{question}}\n"
                "数据概况：{{data_summary}}"
            ),
        )

        # === Task Planning Prompt ===
        self.register(
            name="task_planning",
            description="任务规划 prompt（让 LLM 选择工具和参数）",
            tags=["planning"],
            template=(
                "Based on the user's question and available data, select the best analysis tools.\n\n"
                "User question: {{question}}\n"
                "Detected intents: {{intents}}\n"
                "Primary dataset: {{dataset}}\n"
                "Data summary: {{data_summary}}\n\n"
                "Available tools:\n{{tool_list}}\n\n"
                "Return a JSON array of steps, each with 'tool', 'params', and 'description'."
            ),
        )

        # === SQL Generation Prompt ===
        self.register(
            name="sql_generation",
            description="SQL 生成 prompt",
            tags=["sql"],
            template=(
                "Generate a SQL query for the following question.\n\n"
                "Question: {{question}}\n"
                "Table: {{table_name}}\n"
                "Schema: {{schema}}\n\n"
                "Rules:\n"
                "1. Only SELECT statements\n"
                "2. Use only the columns listed in the schema\n"
                "3. Add appropriate WHERE, GROUP BY, ORDER BY as needed\n"
                "4. Return only the SQL, no explanation"
            ),
        )

        # === SQL Fix Prompt ===
        self.register(
            name="sql_fix",
            description="SQL 纠错 prompt",
            tags=["sql"],
            template=(
                "The following SQL query failed with an error. Fix it.\n\n"
                "Original SQL: {{sql}}\n"
                "Error: {{error}}\n"
                "Table schema: {{schema}}\n\n"
                "Rules:\n"
                "1. Only SELECT statements\n"
                "2. Return only the fixed SQL, no explanation"
            ),
        )

        # === Self-Correction Prompt ===
        self.register(
            name="self_correction",
            description="工具错误修正 prompt",
            tags=["correction"],
            template=(
                "你是一个数据分析工具的调试专家。一个工具执行失败了，请分析原因并返回修正后的参数。\n\n"
                "## 原始用户问题\n{{question}}\n\n"
                "## 上下文信息\n"
                "- 已识别意图：{{intents}}\n"
                "- 主要数据集：{{primary_dataset}}\n"
                "- 数据概况：{{data_summary}}\n\n"
                "## 失败的工具\n"
                "- 工具名：{{tool_name}}\n"
                "- 原始参数：{{original_params}}\n"
                "- 错误信息：{{error_message}}\n\n"
                "## 可用工具列表\n{{available_tools}}\n\n"
                "## 要求\n"
                "分析失败原因（参数错误？维度不对？数据缺失？），然后返回修正后的完整参数 JSON。\n"
                "只返回一个 JSON 对象，不要解释。如果无法修正，返回 {\"__give_up\": true, \"reason\": \"...\"}。"
            ),
        )

        # === 提票审查 Prompt ===
        self.register(
            name="defect_ticket_review",
            description="缺陷提票前置审查 prompt",
            tags=["defect", "review"],
            template=(
                "你是缺陷提票前置审查助手。你的任务是：根据用户的自然语言问题描述，"
                '在"候选缺陷列表"中找出最相似的已知问题，并给出是否建议提票的结论。\n\n'
                "规则：\n"
                "1) 只能基于提供的候选列表，不要编造不存在的ticket。\n"
                "2) 相似度评分使用 1-10（10=几乎同一个问题）。\n"
                "3) 如果最高相似度 >= 8：结论默认\"不建议提票\"，建议合并到最相似票。\n"
                "4) 如果最高相似度 <= 6：结论默认\"可以提票\"。\n\n"
                "候选缺陷列表（JSON Lines）：\n{{candidate_block}}"
            ),
        )

        # === 通用闲聊 Prompt ===
        self.register(
            name="casual_chat",
            description="非业务问题的通用回复 prompt",
            tags=["general"],
            template=(
                "你是一个简洁友好的通用助手。"
                "如果用户的问题与汽车测试/缺陷分析无关，礼貌地引导回业务话题。"
            ),
        )

    def _load_file_prompts(self):
        """从 config/prompts/ 目录加载自定义 prompt（JSON 格式）。"""
        if not os.path.isdir(_PROMPT_DIR):
            return

        for fname in os.listdir(_PROMPT_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(_PROMPT_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "name" in item and "template" in item:
                            self.register(
                                name=item["name"],
                                template=item["template"],
                                version=item.get("version", "custom"),
                                description=item.get("description", ""),
                                tags=item.get("tags"),
                            )
                elif isinstance(data, dict) and "name" in data and "template" in data:
                    self.register(
                        name=data["name"],
                        template=data["template"],
                        version=data.get("version", "custom"),
                        description=data.get("description", ""),
                        tags=data.get("tags"),
                    )
                logger.info(f"Loaded custom prompts from {fname}")
            except Exception as e:
                logger.warning(f"Failed to load prompt file {fname}: {e}")

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self._prompts)
