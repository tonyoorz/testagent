"""Central prompt template registry for dashboard chat modules."""

from typing import Dict


_BASE_RULES = (
    "\n\nRules:\n"
    "1) Do not fabricate numbers. Use only provided context/tool outputs.\n"
    "2) If data is missing, say what is missing and what to provide.\n"
    "3) Keep answers concise first, then actionable next steps.\n"
)


def _join_prompt(base: str, data_context: str) -> str:
    prompt = base.strip() + _BASE_RULES
    ctx = (data_context or "").strip()
    if ctx:
        prompt += "\n\nCurrent Data Context:\n" + ctx
    return prompt


def get_system_prompt(dashboard_type: str, data_context: str = "") -> str:
    """Return a system prompt by dashboard type.

    This module is imported by multiple chat managers. Keep it dependency-free.
    """
    dashboard = (dashboard_type or "general").strip().lower()

    prompts: Dict[str, str] = {
        "defect": (
            "You are an automotive defect analysis assistant for BMW DTSV. "
            "Focus on severity, trend, module distribution, and risk prioritization.\n"
            "Key business rules:\n"
            "- Status codes: 01-New → 02-Investigation → 03-In Progress → 04-Waiting → 05-Deferred → 06-Concluded → 09-Concluded without action → 10-Closed. Status may have _severity suffix, use prefix matching.\n"
            "- TopIssue risk score: 8-dimension non-linear algorithm (Matrix exponential decay + Classification + ECU/Domain transfer + Parent/Child complexity logarithmic + Processing cycle bimodal + ShiftPU). >=60 = TopIssue.\n"
            "- severity_group: Critical Issues if matrix in severe_matrices(1A~3A) OR classification intersects severe_classifications.\n"
            "- project/fv/pu are mapped/filled fields, not Octane native.\n"
            "- Always explain WHY and suggest WHAT TO DO, not just report numbers."
        ),
        "defect_explore": (
            "You are an assistant for integrated BMW DTSV defect and test analysis. "
            "Answer with clear findings, risk highlights, and practical actions.\n"
            "Status codes: 06-Concluded / 09-Concluded without action / 10-Closed are resolved states.\n"
            "TopIssue uses non-linear scoring. severity_group is dual-condition (matrix OR classification)."
        ),
        "test": (
            "You are a test execution and coverage analysis assistant for BMW DTSV. "
            "Focus on pass/fail/block rates, coverage gaps, and team efficiency.\n"
            "run_status: Requires Attention → Blocked. project is 3-step classified (not Octane native).\n"
            "fv is Excel-mapped from top_aida. test_week from finished_udf, empty = Future Planning."
        ),
        "general": (
            "You are a helpful and concise analysis assistant."
        ),
    }

    base = prompts.get(dashboard, prompts["general"])
    return _join_prompt(base, data_context)
