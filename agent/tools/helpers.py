import importlib
from typing import Any


def build_legacy_tool(tool_class_name: str, *args: Any, **kwargs: Any) -> Any:
    legacy_agent = importlib.import_module('agent.core.intelligent_agent')
    tool_cls = getattr(legacy_agent, tool_class_name)
    return tool_cls(*args, **kwargs)
