#!/usr/bin/env python3
"""
单例数据管理器
确保整个应用只加载一次数据，避免重复加载
"""

import threading
import time
import os
from typing import Optional, Dict, Any

class DataManager:
    """单例数据管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DataManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._data_cache = {}
        self._loading_status = {}
        self._load_times = {}
        self._access_counts = {}
        self._data_lock = threading.Lock()
    
    def is_reloader_process(self) -> bool:
        """检查是否为Flask/Dash的reloader进程"""
        return os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    
    def get_data(self, data_key: str, loader_func=None, force_reload: bool = False) -> Optional[Any]:
        """
        获取数据，支持缓存和延迟加载
        
        Args:
            data_key: 数据键名
            loader_func: 数据加载函数
            force_reload: 是否强制重新加载
        
        Returns:
            缓存的数据或新加载的数据
        """
        with self._data_lock:
            # 增加访问计数
            self._access_counts[data_key] = self._access_counts.get(data_key, 0) + 1
            
            # 如果是reloader进程且不是强制重载，跳过加载
            if self.is_reloader_process() and not force_reload:
                print(f"[DataManager] Reloader进程跳过数据加载: {data_key}")
                return None
            
            # 检查缓存
            if not force_reload and data_key in self._data_cache:
                cache_age = time.time() - self._load_times.get(data_key, 0)
                print(f"[DataManager] 返回缓存数据: {data_key} (缓存时长: {cache_age:.1f}秒, 访问次数: {self._access_counts[data_key]})")
                return self._data_cache[data_key]
            
            # 检查是否正在加载中
            if data_key in self._loading_status and self._loading_status[data_key]:
                print(f"[DataManager] 数据正在加载中，等待完成: {data_key}")
                return self._data_cache.get(data_key)
            
            # 开始加载数据
            if loader_func is None:
                print(f"[DataManager] 没有提供加载函数: {data_key}")
                return None
            
            print(f"[DataManager] 开始加载数据: {data_key}")
            self._loading_status[data_key] = True
            
            try:
                start_time = time.time()
                data = loader_func()
                load_time = time.time() - start_time
                
                if data is not None:
                    self._data_cache[data_key] = data
                    self._load_times[data_key] = time.time()
                    print(f"[DataManager] 数据加载成功: {data_key} (耗时: {load_time:.2f}秒)")
                else:
                    print(f"[DataManager] 数据加载失败: {data_key}")
                
                return data
                
            except Exception as e:
                print(f"[DataManager] 数据加载异常: {data_key} - {e}")
                return None
                
            finally:
                self._loading_status[data_key] = False
    
    def clear_cache(self, data_key: Optional[str] = None):
        """清空缓存"""
        with self._data_lock:
            if data_key is None:
                self._data_cache.clear()
                self._load_times.clear()
                self._access_counts.clear()
                print("[DataManager] 已清空所有缓存")
            else:
                self._data_cache.pop(data_key, None)
                self._load_times.pop(data_key, None)
                self._access_counts.pop(data_key, None)
                print(f"[DataManager] 已清空缓存: {data_key}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        with self._data_lock:
            info = {
                'cached_keys': list(self._data_cache.keys()),
                'cache_sizes': {key: len(str(data)) for key, data in self._data_cache.items()},
                'load_times': self._load_times.copy(),
                'access_counts': self._access_counts.copy(),
                'loading_status': self._loading_status.copy()
            }
            return info
    
    def preload_data(self, data_configs: Dict[str, callable]):
        """预加载多个数据源"""
        print(f"[DataManager] 开始预加载 {len(data_configs)} 个数据源...")
        
        def load_in_background():
            for data_key, loader_func in data_configs.items():
                try:
                    self.get_data(data_key, loader_func)
                except Exception as e:
                    print(f"[DataManager] 预加载失败: {data_key} - {e}")
        
        # 后台线程预加载
        thread = threading.Thread(target=load_in_background, daemon=True)
        thread.start()
        return thread

# 全局数据管理器实例
data_manager = DataManager()

def get_managed_data(data_key: str, loader_func=None, force_reload: bool = False):
    """获取管理的数据的简化接口"""
    return data_manager.get_data(data_key, loader_func, force_reload)

def clear_data_cache(data_key: Optional[str] = None):
    """清空数据缓存的简化接口"""
    data_manager.clear_cache(data_key)

def get_cache_info():
    """获取缓存信息的简化接口"""
    return data_manager.get_cache_info()

def preload_all_data():
    """预加载所有应用数据"""
    try:
        from data_processor import load_defect_data
        from scripts.performance.loaders.data_loader_optimized import get_defect_data
        
        data_configs = {
            'defect_data': get_defect_data,
            'raw_defect_data': load_defect_data,
        }
        
        return data_manager.preload_data(data_configs)
        
    except ImportError as e:
        print(f"[DataManager] 预加载失败，模块导入错误: {e}")
        return None

if __name__ == "__main__":
    # 测试数据管理器
    print("测试数据管理器...")
    
    def dummy_loader():
        time.sleep(1)  # 模拟加载时间
        return {"test": "data", "timestamp": time.time()}
    
    # 第一次加载
    data1 = get_managed_data("test_data", dummy_loader)
    print(f"第一次加载: {data1}")
    
    # 第二次加载（应该从缓存获取）
    data2 = get_managed_data("test_data", dummy_loader)
    print(f"第二次加载: {data2}")
    
    # 查看缓存信息
    info = get_cache_info()
    print(f"缓存信息: {info}")
    
    print("数据管理器测试完成！")