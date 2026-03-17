# Performance optimization modules
"""
性能优化模块

提供缓存管理、数据加载优化、启动优化等功能
"""

__version__ = "1.0.0"
__author__ = "Pre-Analysis Team"

# 暴露主要的类和函数
from .cache.cache_manager import CacheManager, cache, cached
from .loaders.data_loader_optimized import get_defect_data, preload_defect_data

__all__ = [
    'CacheManager',
    'cache',
    'cached',
    'get_defect_data',
    'preload_defect_data'
] 