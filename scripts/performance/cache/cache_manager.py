#!/usr/bin/env python3
"""
缓存管理器

提供内存缓存和装饰器功能，支持Windows兼容性
"""

import os
import time
import pickle
import hashlib
from functools import wraps
from typing import Any, Dict, Optional, Callable
from pathlib import Path


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = "cache", max_size: int = 1000):
        self.cache_dir = Path(cache_dir)
        self.max_size = max_size
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        
        # 确保缓存目录存在
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"警告：无法创建缓存目录 {cache_dir}: {e}")
    
    def _generate_key(self, key: str) -> str:
        """生成缓存键"""
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        cache_key = self._generate_key(key)
        
        # 先检查内存缓存
        if cache_key in self._memory_cache:
            cache_data = self._memory_cache[cache_key]
            if time.time() - cache_data['timestamp'] < cache_data['timeout']:
                return cache_data['value']
            else:
                # 过期删除
                del self._memory_cache[cache_key]
        
        # 检查文件缓存
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    if time.time() - cache_data['timestamp'] < cache_data['timeout']:
                        # 加载到内存缓存
                        self._memory_cache[cache_key] = cache_data
                        return cache_data['value']
                    else:
                        # 过期删除文件
                        cache_file.unlink(missing_ok=True)
            except Exception as e:
                print(f"读取缓存文件失败: {e}")
                cache_file.unlink(missing_ok=True)
        
        return None
    
    def set(self, key: str, value: Any, timeout: int = 3600):
        """设置缓存值"""
        cache_key = self._generate_key(key)
        cache_data = {
            'value': value,
            'timestamp': time.time(),
            'timeout': timeout
        }
        
        # 存储到内存缓存
        self._memory_cache[cache_key] = cache_data
        
        # 清理内存缓存大小
        if len(self._memory_cache) > self.max_size:
            # 删除最旧的缓存
            oldest_key = min(self._memory_cache.keys(), 
                           key=lambda k: self._memory_cache[k]['timestamp'])
            del self._memory_cache[oldest_key]
        
        # 存储到文件缓存
        try:
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            print(f"写入缓存文件失败: {e}")
    
    def clear(self):
        """清空所有缓存"""
        # 清空内存缓存
        self._memory_cache.clear()
        
        # 清空文件缓存
        try:
            for cache_file in self.cache_dir.glob("*.pkl"):
                cache_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"清空文件缓存失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        memory_count = len(self._memory_cache)
        file_count = len(list(self.cache_dir.glob("*.pkl"))) if self.cache_dir.exists() else 0
        
        return {
            'memory_cache_count': memory_count,
            'file_cache_count': file_count,
            'cache_dir': str(self.cache_dir),
            'max_size': self.max_size
        }


# 全局缓存管理器实例
_cache_manager = CacheManager()


def cache(key: str, timeout: int = 3600) -> Any:
    """缓存装饰器（简单版本）"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}_{key}_{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存获取
            cached_result = _cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            _cache_manager.set(cache_key, result, timeout)
            return result
        return wrapper
    return decorator


def cached(key_prefix: str, timeout: int = 3600) -> Callable:
    """缓存装饰器（带前缀）"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}_{func.__name__}_{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存获取
            cached_result = _cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            _cache_manager.set(cache_key, result, timeout)
            return result
        return wrapper
    return decorator


# 导出缓存管理器实例（保持类名不变）
default_cache_manager = _cache_manager