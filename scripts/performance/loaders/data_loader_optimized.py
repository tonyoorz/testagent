import os
import pandas as pd
from ..cache.cache_manager import cache, cached
from data_processor import load_defect_data, enrich_ddf_with_master_info
import threading
import time

class OptimizedDataLoader:
    def __init__(self):
        self._data = None
        self._loading = False
        self._last_updated = None
        self._lock = threading.Lock()
    
    @cached("defect_data_full", timeout=3600)
    def _load_and_process_data(self):
        """加载和处理数据的核心逻辑"""
        print("开始加载和处理数据...")
        start_time = time.time()
        
        # 加载基础缺陷数据（加载所有年份）
        df = load_defect_data("defect/*_defect.json")
        
        # 丰富主票信息
        df = enrich_ddf_with_master_info(df)
        
        load_time = time.time() - start_time
        print(f"数据加载完成，耗时: {load_time:.2f}秒")
        
        return df
    
    def get_data(self, force_reload=False):
        """获取数据，支持缓存和强制重新加载"""
        with self._lock:
            if force_reload:
                cache.clear("defect_data_full")
                self._data = None
            
            if self._data is None or force_reload:
                if not self._loading:
                    self._loading = True
                    try:
                        self._data = self._load_and_process_data()
                        self._last_updated = time.time()
                    finally:
                        self._loading = False
            
            return self._data
    
    def is_loading(self):
        """检查是否正在加载数据"""
        return self._loading
    
    def get_last_updated(self):
        """获取最后更新时间"""
        return self._last_updated
    
    def preload_data(self):
        """预加载数据（后台任务）"""
        def background_load():
            print("后台预加载数据...")
            self.get_data()
        
        thread = threading.Thread(target=background_load, daemon=True)
        thread.start()
        return thread

# 全局数据加载器实例
data_loader = OptimizedDataLoader()

def get_defect_data(force_reload=False):
    """获取缺陷数据的简化接口（直接使用优化加载器）"""
    return data_loader.get_data(force_reload=force_reload)

def preload_defect_data():
    """预加载缺陷数据"""
    return data_loader.preload_data()

# 分页数据获取
def get_paginated_data(df, page=1, page_size=50, filters=None):
    """获取分页数据"""
    if filters:
        # 应用筛选器
        filtered_df = df.copy()
        for column, values in filters.items():
            if values and column in filtered_df.columns:
                if isinstance(values, list):
                    filtered_df = filtered_df[filtered_df[column].isin(values)]
                else:
                    filtered_df = filtered_df[filtered_df[column] == values]
    else:
        filtered_df = df
    
    # 计算分页
    total_records = len(filtered_df)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    paginated_df = filtered_df.iloc[start_idx:end_idx]
    
    return {
        'data': paginated_df,
        'total_records': total_records,
        'total_pages': (total_records + page_size - 1) // page_size,
        'current_page': page,
        'page_size': page_size
    } 