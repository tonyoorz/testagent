import json
import os
from pathlib import Path

import pandas as pd
import sys


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
        lines.append(f"- Tools: {', '.join(res.get('tools_used') or [])}\n")
        warnings = ctx.get("validation_warnings") or []
        refusal = (ctx.get("refusal") or {}).get("should_refuse") is True
        text = str(res.get("text") or "")
        has_evidence = ("来源:" in text) or bool(ctx.get("evidence_bundle"))
        case_pass = (not refusal) and has_evidence
        if case_pass:
            passed_cases += 1
        lines.append(f"- Warnings: {len(warnings)}\n")
        lines.append(f"- Refusal: {refusal}\n\n")
        lines.append(f"- Pass: {case_pass}\n\n")
        lines.append("### Answer\n\n")
        lines.append("```text\n")
        lines.append(text.strip() + "\n")
        lines.append("```\n\n")

    pass_rate = (passed_cases / total_cases * 100.0) if total_cases else 0.0
    lines.insert(5, f"- 汇总：passed={passed_cases}/{total_cases} ({round(pass_rate,2)}%)\n")
    out_path.write_text("".join(lines), encoding="utf-8")
    print(str(out_path))
    threshold = float(os.environ.get("AGENT_EVAL_MIN_PASS_RATE", "0") or 0)
    if pass_rate < threshold:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
