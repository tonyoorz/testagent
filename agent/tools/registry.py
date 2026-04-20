from typing import Any, Dict


def normalize_params_to_json_schema(params: Any) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    if not isinstance(params, dict):
        return {'type': 'object', 'properties': {}, 'additionalProperties': True}

    for name, spec in params.items():
        if not isinstance(spec, dict):
            properties[str(name)] = {'type': 'string'}
            continue
        item: Dict[str, Any] = {'type': str(spec.get('type') or 'string').lower() or 'string'}
        if spec.get('description'):
            item['description'] = str(spec.get('description'))
        if isinstance(spec.get('enum'), list) and spec.get('enum'):
            item['enum'] = list(spec.get('enum'))
        if item['type'] == 'array' and isinstance(spec.get('items'), dict):
            item['items'] = dict(spec.get('items'))
        properties[str(name)] = item

    return {'type': 'object', 'properties': properties, 'additionalProperties': True}


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(self, tool: Any) -> None:
        name = str(getattr(tool, 'name', '') or '').strip()
        if not name:
            return
        params = getattr(tool, 'parameters', None) if isinstance(getattr(tool, 'parameters', None), dict) else {}
        self._tools[name] = {
            'description': str(getattr(tool, 'description', '') or ''),
            'parameters': dict(params or {}),
            'json_schema': normalize_params_to_json_schema(params or {}),
        }

    def export(self, tool_name: str = None) -> Dict[str, Any]:
        if tool_name:
            return dict(self._tools.get(tool_name, {}))
        return {name: dict(payload) for name, payload in self._tools.items()}