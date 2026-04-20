from typing import Any, Dict, Optional


def normalize_page_context(
    dashboard_type: str,
    current_data: Any,
    conversation_state: Optional[Dict[str, Any]] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = dict(conversation_state or {})
    extras = dict(extra_context or {})

    if isinstance(current_data, dict):
        available_datasets = [str(key) for key in current_data.keys()]
    else:
        available_datasets = [] if current_data is None else ["primary"]

    page_filters = extras.get("page_filters") if isinstance(extras.get("page_filters"), dict) else {}

    return {
        "dashboard_type": str(dashboard_type or "general"),
        "selected_team": str(state.get("selected_team") or ""),
        "page_filters": page_filters,
        "available_datasets": available_datasets,
        "conversation_state": state,
    }