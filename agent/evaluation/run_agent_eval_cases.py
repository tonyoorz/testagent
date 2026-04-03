import json
import os
import re
from pathlib import Path

import pandas as pd
import sys


_STRUCTURED_EVIDENCE_TEXT_MARKERS = [
    "[observed facts]",
    "observed facts",
    "observed_facts",
    "sql_used:",
    "sample_count:",
    "total_count:",
]

_NON_SQL_EVIDENCE_TERMS = [
    "趋势方向",
    "变化率",
    "总inflow",
    "总outflow",
    "净积压",
    "收敛率",
    "失败率",
    "对比项目",
    "topissue",
    "总记录数",
    "key insights",
    "observed facts",
]

_NON_SQL_EVIDENCE_TOOLS = {
    "analyze_trend",
    "compare_items",
    "defect_explore_dashboard",
    "statistical_summary",
    "analyze_risk",
    "analyze_project_recent_weeks",
}


def _has_non_sql_tool_evidence(text: str, tools_used: list) -> bool:
    if not isinstance(tools_used, list) or not any(str(t).strip() for t in tools_used):
        return False

    normalized_tools = {str(tool or "").strip() for tool in tools_used if str(tool or "").strip()}
    if not (normalized_tools & _NON_SQL_EVIDENCE_TOOLS):
        return False

    lowered = str(text or "").lower()
    has_numeric_fact = bool(re.search(r"\d", lowered))
    has_evidence_term = any(term in lowered for term in _NON_SQL_EVIDENCE_TERMS)
    return has_numeric_fact and has_evidence_term


def _is_clarification_response(text: str, context: dict, tools_used: list) -> bool:
    if not isinstance(context, dict):
        return False
    if context.get("needs_clarification") is not True:
        return False
    if isinstance(tools_used, list) and any(str(t).strip() for t in tools_used):
        return False

    lowered = str(text or "").lower()
    if not lowered.strip():
        return False

    clarification_terms = [
        "我不太确定",
        "请明确",
        "请补充",
        "you can",
        "please clarify",
    ]
    has_clarification_term = any(term in lowered for term in clarification_terms)
    has_option_list = all(marker in lowered for marker in ["1.", "2."])
    return has_clarification_term or has_option_list


def _has_structured_summary_evidence(
    text: str,
    context: dict,
    evidence_bundle: dict,
) -> bool:
    lowered_text = str(text or "").lower()
    if any(marker in lowered_text for marker in _STRUCTURED_EVIDENCE_TEXT_MARKERS):
        return True

    def _has_marker_values(payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False

        observed = payload.get("observed_facts")
        if isinstance(observed, (list, dict)) and bool(observed):
            return True
        if str(observed or "").strip():
            return True

        if str(payload.get("sql_used") or "").strip():
            return True

        for numeric_key in ["sample_count", "total_count"]:
            value = payload.get(numeric_key)
            if isinstance(value, (int, float)):
                return True
            if str(value or "").strip():
                return True

        return False

    candidate_payloads = []
    if isinstance(context, dict):
        candidate_payloads.append(context)
        for value in context.values():
            if isinstance(value, dict):
                candidate_payloads.append(value)
    if isinstance(evidence_bundle, dict):
        candidate_payloads.append(evidence_bundle)

    return any(_has_marker_values(payload) for payload in candidate_payloads)


def _has_meaningful_evidence_bundle(evidence_bundle: dict) -> bool:
    if not isinstance(evidence_bundle, dict) or not evidence_bundle:
        return False

    if str(evidence_bundle.get("sql_used") or "").strip():
        return True

    sample_count = evidence_bundle.get("sample_count")
    if isinstance(sample_count, (int, float)) and float(sample_count) > 0:
        return True

    total_count = evidence_bundle.get("total_count")
    if isinstance(total_count, (int, float)) and float(total_count) > 0:
        return True

    key_fields = evidence_bundle.get("key_fields")
    if isinstance(key_fields, list) and any(str(x or "").strip() for x in key_fields):
        return True

    return False


def _make_defects_short_window() -> pd.DataFrame:
    base = pd.Timestamp("2025-08-01")
    rows = []
    for i in range(8):
        rows.append(
            {
                "id": f"D{i+1}",
                "creation_time": base + pd.Timedelta(days=i % 10),
                "severity": "Critical" if i % 3 == 0 else "Major",
                "status_phase": "01-New" if i % 2 == 0 else "03-In Analysis",
                "project": "P1",
                "aida_english": "Propulsion",
                "matrix": "matrix-1a" if i % 4 == 0 else "matrix-2d",
                "topissue": "TopIssue" if i % 5 == 0 else "",
            }
        )
    return pd.DataFrame(rows)


def _make_defects_inflow_outflow() -> pd.DataFrame:
    base = pd.Timestamp("2025-06-01")
    rows = []
    for i in range(120):
        rows.append(
            {
                "id": f"D{i+1}",
                "creation_time": base + pd.Timedelta(days=i),
                "severity": "Major" if i % 5 else "Critical",
                "status_phase": "04-In Progress",
                "project": "P1" if i % 2 == 0 else "P2",
                "aida_english": "Digital" if i % 3 == 0 else "Driving",
                "matrix": "matrix-2d",
                "topissue": "TopIssue" if i % 10 == 0 else "",
            }
        )
    return pd.DataFrame(rows)


def _make_defects_multi_project() -> pd.DataFrame:
    base = pd.Timestamp("2025-07-01")
    rows = []
    for i in range(60):
        rows.append(
            {
                "id": f"D{i+1}",
                "creation_time": base + pd.Timedelta(days=i % 30),
                "severity": "Critical" if (i % 10 == 0) else "Minor",
                "status_phase": "04-In Progress",
                "project": "P1" if i % 3 == 0 else ("P2" if i % 3 == 1 else "P3"),
                "aida_english": "Propulsion",
                "matrix": "matrix-1b" if i % 7 == 0 else "matrix-3c",
                "topissue": "TopIssue" if i % 12 == 0 else "",
            }
        )
    return pd.DataFrame(rows)


def _make_tests_basic() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "test_case": ["C1", "C1", "C2", "C3", "C3", "C3"],
            "run_status": ["PASS", "FAIL", "FAIL", "PASS", "ERROR", "PASS"],
            "finished_udf_dt": pd.to_datetime(
                ["2025-08-12", "2025-08-12", "2025-08-12", "2025-08-12", "2025-08-12", "2025-08-12"]
            ),
            "project": ["P1", "P1", "P1", "P2", "P2", "P2"],
        }
    )


def _profile_data(profile: str):
    if profile == "defects_short_window":
        return {"defects": _make_defects_short_window()}
    if profile == "defects_inflow_outflow":
        return {"defects": _make_defects_inflow_outflow()}
    if profile == "defects_multi_project":
        return {"defects": _make_defects_multi_project()}
    if profile == "tests_basic":
        return {"tests": _make_tests_basic()}
    raise ValueError(f"unknown data_profile: {profile}")


def main():
    os.environ.setdefault("AGENT_SEMANTIC_CATALOG_ENABLED", "1")
    os.environ.setdefault("AGENT_CRITIC_ENABLED", "1")
    os.environ.setdefault("AGENT_VALIDATION_ENABLED", "1")

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import importlib
    from agent.evaluation.agent_critic import contains_strong_confident_language
    from agent.core import intelligent_agent

    importlib.reload(intelligent_agent)

    cases_path = root / "evaluation" / "agent_eval_cases.jsonl"
    out_path = root / "evaluation" / "agent_eval_report.md"

    lines = []
    lines.append("# Agent 离线评测报告\n\n")
    lines.append(f"- 用例文件：{cases_path.name}\n")
    lines.append(f"- 开关：AGENT_SEMANTIC_CATALOG_ENABLED={os.environ.get('AGENT_SEMANTIC_CATALOG_ENABLED')}, ")
    lines.append(f"AGENT_CRITIC_ENABLED={os.environ.get('AGENT_CRITIC_ENABLED')}, ")
    lines.append(f"AGENT_VALIDATION_ENABLED={os.environ.get('AGENT_VALIDATION_ENABLED')}\n\n")
    total_cases = 0
    passed_cases = 0

    for raw in cases_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        total_cases += 1
        case = json.loads(raw)
        agent = intelligent_agent.create_agent(case.get("dashboard_type") or "general")
        data = _profile_data(case["data_profile"])
        res = agent.process(case["question"], data)
        ctx = res.get("context") or {}

        lines.append(f"## {case['id']}\n\n")
        lines.append(f"- Question: {case['question']}\n")
        tools_used = res.get("tools_used") or []
        lines.append(f"- Tools: {', '.join(tools_used)}\n")
        warnings = ctx.get("validation_warnings") or []
        refusal_payload = ctx.get("refusal") if isinstance(ctx.get("refusal"), dict) else {}
        refusal = refusal_payload.get("should_refuse") is True
        refusal_reason = str(refusal_payload.get("reason") or "").strip()
        text = str(res.get("text") or "")
        evidence_bundle = ctx.get("evidence_bundle") if isinstance(ctx.get("evidence_bundle"), dict) else {}
        evidence_gaps = evidence_bundle.get("evidence_gap") if isinstance(evidence_bundle.get("evidence_gap"), list) else []
        has_structured_evidence = _has_structured_summary_evidence(
            text=text,
            context=ctx,
            evidence_bundle=evidence_bundle,
        )
        has_non_sql_evidence = _has_non_sql_tool_evidence(text, tools_used)
        has_evidence = (
            ("来源:" in text)
            or _has_meaningful_evidence_bundle(evidence_bundle)
            or has_structured_evidence
            or has_non_sql_evidence
        )

        has_strong_claim = contains_strong_confident_language(text)
        lower_reason = refusal_reason.lower()
        unsupported_claim_signal = bool(evidence_gaps) and (
            refusal or has_strong_claim or any(token in lower_reason for token in ["证据", "无法确认", "unsupported", "high-confidence"])
        )

        clarification_mode = _is_clarification_response(text=text, context=ctx, tools_used=tools_used)
        if clarification_mode:
            case_pass = (not refusal) and (not has_strong_claim)
        else:
            case_pass = (not refusal) and (not unsupported_claim_signal) and has_evidence
        if case_pass:
            passed_cases += 1
        lines.append(f"- Warnings: {len(warnings)}\n")
        lines.append(f"- Refusal: {refusal}\n\n")
        lines.append(f"- EvidenceDetected: {has_evidence}\n")
        lines.append(f"- StructuredEvidenceDetected: {has_structured_evidence}\n")
        lines.append(f"- NonSQLEvidenceDetected: {has_non_sql_evidence}\n")
        lines.append(f"- ClarificationMode: {clarification_mode}\n")
        lines.append(f"- RefusalReason: {refusal_reason or '-'}\n")
        lines.append(f"- UnsupportedClaimSignal: {unsupported_claim_signal}\n\n")
        lines.append(f"- Pass: {case_pass}\n\n")
        lines.append("### Answer\n\n")
        lines.append("```text\n")
        lines.append(text.strip() + "\n")
        lines.append("```\n\n")

    pass_rate = (passed_cases / total_cases * 100.0) if total_cases else 0.0
    lines.insert(5, f"- 汇总：passed={passed_cases}/{total_cases} ({round(pass_rate,2)}%)\n")
    out_path.write_text("".join(lines), encoding="utf-8")
    print(str(out_path))
    threshold = float(os.environ.get("AGENT_EVAL_MIN_PASS_RATE", "50") or 50)
    if total_cases > 0 and passed_cases == 0:
        raise SystemExit(2)
    if pass_rate < threshold:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
