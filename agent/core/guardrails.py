"""
Guardrails — 输入/输出护栏

输入护栏（Input Guardrails）：
1. 话题相关性检查 — 过滤与业务无关的问题
2. Prompt注入检测 — 防止恶意指令
3. 敏感信息脱敏 — 防止查询中泄露密钥/密码

输出护栏（Output Guardrails）：
1. 幻觉检测 — 检查LLM回答是否引用了实际数据
2. 数据脱敏 — 防止输出中包含敏感字段
3. 置信度标注 — 低置信度结果标记警告

默认关闭，AGENT_GUARDRAILS=1 开启。
"""

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class GuardrailAction(Enum):
    """Guardrail decision."""
    PASS = "pass"           # 放行
    WARN = "warn"           # 警告但放行
    BLOCK = "block"         # 阻止
    REPHRASE = "rephrase"   # 需要改写


@dataclass
class GuardrailResult:
    """Single guardrail check result."""
    name: str
    action: GuardrailAction
    reason: str = ""
    confidence: float = 1.0
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def should_block(self) -> bool:
        return self.action == GuardrailAction.BLOCK


class InputGuardrails:
    """Input-side guardrails: topic relevance, injection detection, PII."""

    # 与汽车测试/缺陷分析相关的关键词
    DOMAIN_KEYWORDS = {
        "zh": [
            "缺陷", "bug", "测试", "用例", "风险", "矩阵", "matrix", "topissue",
            "项目", "ecu", "aida", "严重", "severity", "趋势", "分布", "对比",
            "测试人员", "tester", "模块", "功能", "状态", "流转", "修复", "回归",
            "失败", "通过率", "覆盖率", "质量", "发布", "版本", "看板", "kpi",
            "数据", "统计", "分析", "报告", "图表", "dashboard", "策略",
            "长期", "乒乓", "热点", "top", "longrunner", "积压", "收敛",
            "fv", "feature team", "domain", "cluster", "pu",
        ],
        "en": [
            "defect", "bug", "test", "case", "risk", "matrix", "topissue",
            "project", "ecu", "aida", "severity", "trend", "distribution",
            "tester", "module", "feature", "status", "fix", "regression",
            "failure", "pass rate", "coverage", "quality", "release",
            "dashboard", "kpi", "statistic", "analysis", "report",
            "longrunner", "pingpong", "hotspot", "backlog", "convergence",
            "fv", "feature team", "domain", "cluster", "pu",
        ],
    }

    # Prompt注入特征模式
    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(?:your\s+)?(?:previous|all|above)\s+(?:instructions?|prompts?|rules)",
        r"(?i)ignore\s+(?:previous|all|above|your)\s+(?:instructions?|prompts?|rules)",
        r"(?i)forget\s+(everything|all|your\s+instructions)",
        r"(?i)you\s+are\s+now\s+a?",
        r"(?i)pretend\s+(you\s+are|to\s+be)",
        r"(?i)system\s*:\s*",
        r"(?i)<\|im_start\|>",
        r"(?i)\[INST\]",
        r"(?i)###\s*instruction",
        r"(?i)disregard\s+(your|all|previous)",
        r"(?i)override\s+(safety|security|rules)",
        r"(?i)jailbreak",
        r"(?i)reveal\s+(your|the)\s+(prompt|system|instructions)",
        r"(?i)output\s+your\s+(system|initial)\s+(prompt|message)",
    ]

    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        (r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+", "密码"),
        (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+", "API密钥"),
        (r"(?i)(secret|token)\s*[:=]\s*\S+", "密钥/令牌"),
        (r"(?i)(aws_access_key_id)\s*[:=]\s*\S+", "AWS密钥"),
        (r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "私钥"),
        (r"(?i)(Bearer\s+[A-Za-z0-9\-._~+/]+=*)", "Bearer令牌"),
        (r"\bghp_[A-Za-z0-9]{36}\b", "GitHub Token"),
        (r"\bgho_[A-Za-z0-9]{36}\b", "GitHub OAuth"),
    ]

    def check_topic_relevance(self, question: str) -> GuardrailResult:
        """检查问题是否与业务域相关。"""
        q = (question or "").strip()
        if not q:
            return GuardrailResult(
                name="topic_relevance",
                action=GuardrailAction.BLOCK,
                reason="问题为空",
                confidence=1.0,
            )

        # 短问候语放行
        greetings = ["你好", "嗨", "hi", "hello", "hey", "早上好", "下午好", "晚上好", "thanks", "谢谢"]
        if q.lower().strip() in greetings:
            return GuardrailResult(
                name="topic_relevance",
                action=GuardrailAction.PASS,
                reason="问候语",
            )

        # 帮助/关于类问题放行
        help_patterns = ["你能做什么", "帮助", "help", "功能", "怎么用", "使用说明"]
        if any(p in q.lower() for p in help_patterns):
            return GuardrailResult(
                name="topic_relevance",
                action=GuardrailAction.PASS,
                reason="帮助类问题",
            )

        # 检查关键词命中
        q_lower = q.lower()
        hit_count = 0
        for lang_keywords in self.DOMAIN_KEYWORDS.values():
            for kw in lang_keywords:
                if kw in q_lower:
                    hit_count += 1

        # 宽松匹配：命中1个就放行（业务术语很多）
        if hit_count >= 1:
            return GuardrailResult(
                name="topic_relevance",
                action=GuardrailAction.PASS,
                reason=f"命中{hit_count}个业务关键词",
            )

        # 通用分析类问题也放行
        generic_analysis = ["分析", "统计", "数据", "趋势", "对比", "分析一下", "看看"]
        if any(p in q_lower for p in generic_analysis):
            return GuardrailResult(
                name="topic_relevance",
                action=GuardrailAction.WARN,
                reason="通用分析问题，未匹配具体业务关键词",
                confidence=0.6,
            )

        # 完全不相关
        return GuardrailResult(
            name="topic_relevance",
            action=GuardrailAction.WARN,
            reason="问题可能与业务无关",
            confidence=0.5,
            details={"hit_count": hit_count},
        )

    def check_injection(self, question: str) -> GuardrailResult:
        """检测 prompt 注入攻击。"""
        q = (question or "").strip()
        if not q:
            return GuardrailResult(name="injection", action=GuardrailAction.PASS)

        matched = []
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, q):
                matched.append(pattern)

        if not matched:
            return GuardrailResult(name="injection", action=GuardrailAction.PASS)

        # 强注入特征直接阻止
        strong_patterns = [r"ignore\s+(?:your\s+)?(?:previous|all|above)", r"forget\s+everything", r"jailbreak"]
        is_strong = any(re.search(p, q, re.IGNORECASE) for p in strong_patterns)

        if is_strong:
            return GuardrailResult(
                name="injection",
                action=GuardrailAction.BLOCK,
                reason=f"检测到强 prompt 注入特征 ({len(matched)} 个匹配)",
                confidence=0.95,
                details={"matched_patterns": matched},
            )

        return GuardrailResult(
            name="injection",
            action=GuardrailAction.WARN,
            reason=f"检测到疑似注入特征 ({len(matched)} 个匹配)",
            confidence=0.7,
            details={"matched_patterns": matched},
        )

    def check_sensitive_info(self, question: str) -> GuardrailResult:
        """检测查询中的敏感信息。"""
        q = (question or "").strip()
        if not q:
            return GuardrailResult(name="sensitive_info", action=GuardrailAction.PASS)

        found = []
        for pattern, label in self.SENSITIVE_PATTERNS:
            if re.search(pattern, q):
                found.append(label)

        if not found:
            return GuardrailResult(name="sensitive_info", action=GuardrailAction.PASS)

        return GuardrailResult(
            name="sensitive_info",
            action=GuardrailAction.WARN,
            reason=f"检测到敏感信息: {', '.join(found)}",
            confidence=0.9,
            details={"found_types": found},
        )

    def check_all(self, question: str) -> List[GuardrailResult]:
        """运行所有输入检查。"""
        return [
            self.check_topic_relevance(question),
            self.check_injection(question),
            self.check_sensitive_info(question),
        ]


class OutputGuardrails:
    """Output-side guardrails: hallucination, PII, confidence."""

    # 不应在输出中出现的敏感字段
    SENSITIVE_FIELDS = {"password", "passwd", "secret", "token", "api_key", "apikey", "private_key"}

    # 幻觉特征：LLM编造的不存在的数据引用
    HALLUCINATION_INDICATORS = [
        r"(?i)根据我的知识",
        r"(?i)一般来说",
        r"(?i)通常情况下",
        r"(?i)一般来说(?!，)",
        r"(?i)我(?:认为|觉得|猜测|估计)(?!.*数据)",
        r"(?i)(?:应该|可能|也许|大概).{0,20}(?:是因为|由于)",
    ]

    def check_sensitive_output(self, text: str) -> GuardrailResult:
        """检查输出中是否包含敏感信息。"""
        if not text:
            return GuardrailResult(name="output_sensitive", action=GuardrailAction.PASS)

        text_lower = text.lower()
        found = []
        for field_name in self.SENSITIVE_FIELDS:
            if field_name in text_lower:
                found.append(field_name)

        if not found:
            return GuardrailResult(name="output_sensitive", action=GuardrailAction.PASS)

        return GuardrailResult(
            name="output_sensitive",
            action=GuardrailAction.WARN,
            reason=f"输出可能包含敏感字段: {', '.join(found)}",
            confidence=0.8,
        )

    def check_data_grounding(self, text: str, execution_results: List[Dict] = None) -> GuardrailResult:
        """检查回答是否有数据支撑（防幻觉）。

        逻辑：
        - 如果有 execution_results 且至少一个成功 → grounded
        - 如果回答很长但没有数据结果 → 可能幻觉
        """
        if not text:
            return GuardrailResult(name="data_grounding", action=GuardrailAction.PASS)

        # 有成功执行的工具结果
        has_success = False
        if execution_results:
            for r in execution_results:
                res = (r or {}).get("result") or {}
                if isinstance(res, dict) and res.get("success") is True:
                    has_success = True
                    break

        if has_success:
            return GuardrailResult(name="data_grounding", action=GuardrailAction.PASS)

        # 没有数据支撑但回答有一定长度 → 警告
        if len(text) > 20:
            # 检查是否有幻觉特征
            hallucination_hits = 0
            for pattern in self.HALLUCINATION_INDICATORS:
                if re.search(pattern, text):
                    hallucination_hits += 1

            if hallucination_hits >= 2:
                return GuardrailResult(
                    name="data_grounding",
                    action=GuardrailAction.WARN,
                    reason="回答缺乏数据支撑，可能包含推测性内容",
                    confidence=0.6,
                    details={"hallucination_indicators": hallucination_hits},
                )

        return GuardrailResult(
            name="data_grounding",
            action=GuardrailAction.PASS,
            confidence=0.8,
        )

    def check_all(self, text: str, execution_results: List[Dict] = None) -> List[GuardrailResult]:
        """运行所有输出检查。"""
        return [
            self.check_sensitive_output(text),
            self.check_data_grounding(text, execution_results),
        ]


class GuardrailPipeline:
    """完整的输入/输出护栏管道。"""

    def __init__(self):
        self.input_guardrails = InputGuardrails()
        self.output_guardrails = OutputGuardrails()

    @staticmethod
    def is_enabled() -> bool:
        return os.getenv("AGENT_GUARDRAILS", "0") == "1"

    def check_input(self, question: str) -> Tuple[bool, List[GuardrailResult]]:
        """检查输入，返回 (should_proceed, results)。"""
        results = self.input_guardrails.check_all(question)

        # 任何一个 BLOCK → 不继续
        blocked = any(r.should_block for r in results)
        return (not blocked), results

    def check_output(self, text: str, execution_results: List[Dict] = None) -> List[GuardrailResult]:
        """检查输出，返回 results。"""
        return self.output_guardrails.check_all(text, execution_results)

    def format_input_block_message(self, results: List[GuardrailResult]) -> str:
        """生成输入被拒绝时的用户友好消息。"""
        blocks = [r for r in results if r.should_block]
        warns = [r for r in results if r.action == GuardrailAction.WARN]

        parts = []
        if blocks:
            for b in blocks:
                parts.append(f"❌ {b.reason}")

        if warns:
            for w in warns:
                parts.append(f"⚠️ {w.reason}")

        if not parts:
            return "请求被安全策略阻止。"

        msg = "抱歉，无法处理您的问题：\n" + "\n".join(f"- {p}" for p in parts)
        msg += "\n\n我可以帮您分析汽车测试/缺陷相关的数据。试试问我："
        msg += "\n• 哪个项目风险最高？"
        msg += "\n• 上周的缺陷趋势怎么样？"
        msg += "\n• IDCevo的Matrix分布"
        return msg

    def format_output_warnings(self, results: List[GuardrailResult]) -> str:
        """生成输出警告的附加文本。"""
        warns = [r for r in results if r.action == GuardrailAction.WARN]
        if not warns:
            return ""

        parts = [f"⚠️ {w.reason}" for w in warns]
        return "\n\n---\n**注意**: " + "；".join(parts)
