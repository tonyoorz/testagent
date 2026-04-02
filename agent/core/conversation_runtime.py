from typing import Any, Dict, List


VALID_EXECUTION_MODES = {"rule", "agentic", "hybrid"}


def resolve_execution_mode(
    requested_mode: str,
    *,
    agentic_enabled: bool,
    internal_template_route: bool,
) -> str:
    """Resolve runtime mode with safe fallbacks.

    Rules:
    - Unknown mode defaults to ``agentic``.
    - Internal template route degrades ``agentic`` to ``hybrid``.
    - If agentic is unavailable, ``agentic`` falls back to ``rule``.
    """
    mode = str(requested_mode or "agentic").strip().lower() or "agentic"
    if mode not in VALID_EXECUTION_MODES:
        mode = "agentic"

    if mode == "agentic" and internal_template_route:
        mode = "hybrid"

    if (not agentic_enabled) and mode == "agentic":
        mode = "rule"

    return mode


def init_analysis_trace(
    mode: str,
    validation_enabled: bool,
    *,
    internal_template_route: bool,
) -> Dict[str, Any]:
    """Initialize the normalized analysis trace payload."""
    trace: Dict[str, Any] = {
        "mode": str(mode or "rule"),
        "validation_enabled": bool(validation_enabled),
        "plan": [],
        "execution": [],
    }
    if internal_template_route:
        trace["llm_route"] = "internal_template"
    return trace


def serialize_plan_trace(plan: Any) -> List[Dict[str, Any]]:
    """Normalize planner steps into a stable trace payload."""
    rows: List[Dict[str, Any]] = []
    for step in plan or []:
        if not isinstance(step, dict):
            continue
        rows.append(
            {
                "step": int(step.get("step") or 0),
                "tool": step.get("tool"),
                "description": step.get("description"),
                "params": dict(step.get("params") or {}),
            }
        )
    return rows
