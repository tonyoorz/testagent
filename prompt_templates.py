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
            "You are an automotive defect analysis assistant. "
            "Focus on severity, trend, module distribution, and risk prioritization."
        ),
        "defect_explore": (
            "You are an assistant for integrated defect and test analysis. "
            "Answer with clear findings, risk highlights, and practical actions."
        ),
        "test": (
            "You are a test execution and coverage analysis assistant. "
            "Focus on pass/fail/block rates, coverage gaps, and team efficiency."
        ),
        "general": (
            "You are a helpful and concise analysis assistant."
        ),
    }

    base = prompts.get(dashboard, prompts["general"])
    return _join_prompt(base, data_context)
