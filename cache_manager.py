"""
Unified cache manager for Dash callbacks.
Redis-first with in-memory fallback when Redis is unavailable.
"""

import os
import json
import pickle
import hashlib
import logging
import pandas as pd
from typing import Any, Optional, Callable
from functools import wraps

logger = logging.getLogger(__name__)

# Try import redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class UnifiedCache:
    """Redis-backed cache with in-memory fallback."""

    def __init__(self, redis_url: str = None, default_timeout: int = 300):
        self.default_timeout = default_timeout
        self._memory_cache = {}
        self._redis_client = None

        if REDIS_AVAILABLE:
            url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            try:
                self._redis_client = redis.from_url(url, socket_connect_timeout=2)
                self._redis_client.ping()
                logger.info(f"✅ Redis cache connected: {url}")
            except Exception as e:
                logger.warning(f"⚠️ Redis unavailable ({e}), using in-memory cache")
                self._redis_client = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis_client else "memory"

    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from function arguments."""
        raw = f"{prefix}:{args}:{sorted(kwargs.items())}"
        return f"dtsv:{hashlib.md5(raw.encode()).hexdigest()}"

    def _serialize(self, value: Any) -> bytes:
        """Serialize value, using pickle for DataFrames."""
        if isinstance(value, pd.DataFrame):
            return pickle.dumps(value)
        return json.dumps(value, default=str).encode()

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value, trying pickle first for DataFrames."""
        try:
            result = pickle.loads(data)
            return result
        except Exception:
            return json.loads(data)

    def get(self, key: str) -> Optional[Any]:
        if self._redis_client:
            try:
                val = self._redis_client.get(key)
                if val:
                    return self._deserialize(val)
            except Exception:
                pass
        return self._memory_cache.get(key)

    def set(self, key: str, value: Any, timeout: int = None) -> None:
        timeout = timeout or self.default_timeout
        if self._redis_client:
            try:
                self._redis_client.setex(key, timeout, self._serialize(value))
                return
            except Exception:
                pass
        self._memory_cache[key] = value

    def memoize(self, prefix: str, timeout: int = None):
        """Decorator: cache function result by arguments."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Skip cache if explicitly disabled
                if kwargs.pop('_no_cache', False):
                    return func(*args, **kwargs)

                key = self._make_key(prefix, *args, **kwargs)
                cached = self.get(key)
                if cached is not None:
                    return cached

                result = func(*args, **kwargs)
                if result is not None:
                    self.set(key, result, timeout)
                return result
            wrapper._cache_manager = self
            wrapper._cache_prefix = prefix
            return wrapper
        return decorator

    def clear_prefix(self, prefix: str) -> int:
        """Clear all cache entries with given prefix."""
        count = 0
        if self._redis_client:
            try:
                pattern = f"dtsv:*"
                keys = self._redis_client.keys(pattern)
                for k in keys:
                    self._redis_client.delete(k)
                    count += 1
            except Exception:
                pass
        else:
            count = len(self._memory_cache)
            self._memory_cache.clear()
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        info = {"backend": self.backend}
        if self._redis_client:
            try:
                info["redis_keys"] = len(self._redis_client.keys("dtsv:*"))
                info["redis_memory"] = self._redis_client.info()["used_memory_human"]
            except Exception:
                pass
        else:
            info["memory_keys"] = len(self._memory_cache)
        return info


# Global singleton
_cache_instance: Optional[UnifiedCache] = None

def get_cache(redis_url: str = None, default_timeout: int = 300) -> UnifiedCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = UnifiedCache(redis_url=redis_url, default_timeout=default_timeout)
    return _cache_instance
