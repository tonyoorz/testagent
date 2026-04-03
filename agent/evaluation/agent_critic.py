from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional


_STRONG_CONFIDENT_PATTERNS = [
    r"\bdefinitely\b",
    r"\bcertainly\b",
    r"\bguaranteed\b",
    r"\bprove(?:s|d|n)?\b",
    r"必然",
    r"一定",
    r"完全证明",
    r"毫无疑问",
    r"可以确定",
    r"已被证明",
]


def contains_strong_confident_language(text: str) -> bool:
    draft = str(text or "").strip()
    if not draft:
        return False
    for pattern in _STRONG_CONFIDENT_PATTERNS:
        if re.search(pattern, draft, flags=re.IGNORECASE):
            return True
    return False


@dataclass(frozen=True)
class CriticFinding:
    level: str
    message: str


@dataclass(frozen=True)
class CriticResult:
    findings: List[CriticFinding]
    should_refuse: bool = False
    refusal_reason: str = ""


class BaseCritic:
    name: str = "base"

    def critique(
        self,
        question: str,
        context: Dict[str, Any],
        execution_results: List[Dict[str, Any]],
        draft_text: str,
    ) -> CriticResult:
        raise NotImplementedError


class RuleBasedCritic(BaseCritic):
    name = "rule_based"

    @staticmethod
    def _collect_evidence_gaps(context: Dict[str, Any], execution_results: List[Dict[str, Any]]) -> List[str]:
        bundles: List[Dict[str, Any]] = []
        for candidate in [
            context.get("critic_evidence_bundle"),
            context.get("evidence_bundle"),
        ]:
            if isinstance(candidate, dict):
                bundles.append(candidate)

        for row in (execution_results or []):
            if not isinstance(row, dict):
                continue
            tool_output = row.get("result") if isinstance(row.get("result"), dict) else {}
            nested_result = tool_output.get("result") if isinstance(tool_output.get("result"), dict) else {}
            for candidate in [
                row.get("evidence_bundle"),
                tool_output.get("evidence_bundle"),
                nested_result.get("evidence_bundle"),
            ]:
                if isinstance(candidate, dict):
                    bundles.append(candidate)

        gaps: List[str] = []
        seen = set()
        for bundle in bundles:
            for gap in (bundle.get("evidence_gap") if isinstance(bundle.get("evidence_gap"), list) else []):
                text = str(gap or "").strip()
                key = text.lower()
                if text and key not in seen:
                    seen.add(key)
                    gaps.append(text)
        return gaps

    def critique(
        self,
        question: str,
        context: Dict[str, Any],
        execution_results: List[Dict[str, Any]],
        draft_text: str,
    ) -> CriticResult:
        findings: List[CriticFinding] = []

        warnings = context.get("validation_warnings") or []
        if warnings and ("风险提示" not in (draft_text or "")):
            findings.append(CriticFinding(level="warning", message="存在已识别的数据/口径风险，但输出未显式提示风险。"))

        q = (question or "").lower()
        if any(k in (draft_text or "") for k in ["必然", "证明", "一定"]) and (
            ("trend" in (context.get("intents") or [])) or ("comparison" in (context.get("intents") or []))
        ):
            findings.append(CriticFinding(level="warning", message="结论措辞偏强，建议降级为“倾向/可能”，并补充样本量与时间跨度。"))

        evidence_gaps = self._collect_evidence_gaps(context, execution_results)
        has_strong_claim = contains_strong_confident_language(draft_text)
        if evidence_gaps and has_strong_claim:
            findings.append(
                CriticFinding(
                    level="warning",
                    message="检测到高置信断言且证据存在缺口，相关结论应明确改为未确认状态。",
                )
            )

        failed_tools = []
        for r in execution_results:
            tool_output = r.get("result") or {}
            if tool_output.get("success") is False:
                failed_tools.append(str(r.get("tool") or "unknown"))
        if failed_tools:
            findings.append(CriticFinding(level="warning", message=f"部分工具执行失败（{', '.join(failed_tools[:5])}），相关结论需要回避或说明缺口。"))

        refusal = context.get("refusal") or {}
        if refusal.get("should_refuse") is True:
            return CriticResult(findings=findings, should_refuse=True, refusal_reason=str(refusal.get("reason") or "数据不足"))

        if evidence_gaps and has_strong_claim:
            reason = f"检测到高置信断言但证据存在缺口，当前无法确认结论（{evidence_gaps[0]}）"
            return CriticResult(findings=findings, should_refuse=True, refusal_reason=reason)

        return CriticResult(findings=findings, should_refuse=False, refusal_reason="")


class CriticPipeline:
    def __init__(self, critics: Optional[List[BaseCritic]] = None):
        self._critics: List[BaseCritic] = list(critics or [])

    def register(self, critic: BaseCritic) -> None:
        self._critics.append(critic)

    def run(
        self,
        question: str,
        context: Dict[str, Any],
        execution_results: List[Dict[str, Any]],
        draft_text: str,
    ) -> List[CriticResult]:
        results: List[CriticResult] = []
        for c in self._critics:
            results.append(c.critique(question, context, execution_results, draft_text))
        return results

    @staticmethod
    def render(results: List[CriticResult]) -> str:
        findings: List[CriticFinding] = []
        for r in results:
            findings.extend(r.findings or [])
        findings = [f for f in findings if f and f.message]
        if not findings:
            return ""
        lines = ["\n**校验与质疑**\n"]
        for f in findings[:8]:
            lines.append(f"- [{f.level}] {f.message}\n")
        return "".join(lines)
