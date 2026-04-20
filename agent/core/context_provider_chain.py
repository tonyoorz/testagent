from typing import Any, Dict, Iterable, Optional


class RequestContextProvider:
    def apply(self, context: Dict[str, Any], *, request: Optional[Dict[str, Any]] = None, **_: Any) -> Dict[str, Any]:
        if isinstance(request, dict) and request:
            context['request'] = dict(request)
        return context


class PageContextProvider:
    def apply(self, context: Dict[str, Any], *, page_context: Optional[Dict[str, Any]] = None, **_: Any) -> Dict[str, Any]:
        if isinstance(page_context, dict) and page_context:
            payload = dict(page_context)
            context['page_context'] = payload
            dashboard_type = str(payload.get('dashboard_type') or '').strip()
            if dashboard_type:
                context['dashboard_type'] = dashboard_type
        return context


class RuntimeConfigProvider:
    def apply(self, context: Dict[str, Any], *, runtime_config: Optional[Dict[str, Any]] = None, **_: Any) -> Dict[str, Any]:
        if isinstance(runtime_config, dict) and runtime_config:
            context['runtime'] = dict(runtime_config)
        return context


class ContextProviderChain:
    def __init__(self, providers: Optional[Iterable[Any]] = None):
        self.providers = list(providers or [])

    def apply(self, context: Dict[str, Any], **payload: Any) -> Dict[str, Any]:
        resolved = dict(context or {})
        for provider in self.providers:
            resolved = provider.apply(resolved, **payload)
        return resolved