from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
