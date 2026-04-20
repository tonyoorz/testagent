from datetime import datetime
import time
from typing import Any, Dict, Optional


_ALLOWED_EVENT_STATUS = {"running", "ok", "warn", "error", "fallback", "info"}


def init_stream_state(progress: str) -> Dict[str, Any]:
    now = time.time()
    return {
        "status": "processing",
        "reasoning": "",
        "response": "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "progress": str(progress or ""),
        "chunk_buffer": "",
        "last_update": now,
        "started_at": now,
        "events": [],
    }


def append_event(
    stream_entry: Dict[str, Any],
    *,
    kind: str,
    title: str,
    status: str = "info",
    summary: str = "",
    details: Optional[Any] = None,
    limit: int = 80,
) -> Dict[str, Any]:
    normalized = status if status in _ALLOWED_EVENT_STATUS else "info"
    events = stream_entry.setdefault("events", [])
    event = {
        "id": f"evt_{int(time.time() * 1000)}_{len(events) + 1}",
        "ts": time.time(),
        "kind": str(kind or "info"),
        "title": str(title or "事件"),
        "status": normalized,
        "summary": str(summary or ""),
        "details": details or {},
    }
    events.append(event)
    if len(events) > limit:
        del events[:-limit]
    stream_entry["last_update"] = time.time()
    return event