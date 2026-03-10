# Cache management modules
"""
缓存管理模块

提供缓存管理器、装饰器等功能
"""

from .cache_manager import CacheManager, cache, cached, default_cache_manager

__all__ = ['CacheManager', 'cache', 'cached', 'default_cache_manager']