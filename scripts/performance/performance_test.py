#!/usr/bin/env python3
"""
简化的性能测试模块
集成最重要的性能测试功能
"""

import time
import random
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_cache_performance():
    """测试缓存性能"""
    print("=== 缓存性能测试 ===")
    
    try:
        from data_processor import load_defect_data, history_cache, get_history_data
        
        # 加载测试数据
        df = load_defect_data()
        if df.empty:
            print("❌ 无法加载缺陷数据")
            return {}
        
        # 随机选择测试ID
        test_ids = df['id'].astype(str).sample(min(20, len(df))).tolist()
        print(f"测试样本: {len(test_ids)} 个")
        
        # 测试未缓存读取
        history_cache.clear()
        start_time = time.time()
        for defect_id in test_ids:
            get_history_data(defect_id)
        uncached_time = time.time() - start_time
        
        # 测试预加载+缓存读取
        history_cache.clear()
        preload_start = time.time()
        history_cache.preload_histories(test_ids)
        preload_time = time.time() - preload_start
        
        start_time = time.time()
        for defect_id in test_ids:
            get_history_data(defect_id)
        cached_time = time.time() - start_time
        
        # 计算提升
        speedup = uncached_time / cached_time if cached_time > 0 else float('inf')
        
        print(f"✅ 未缓存读取: {uncached_time:.3f}秒")
        print(f"✅ 预加载耗时: {preload_time:.3f}秒") 
        print(f"✅ 缓存读取: {cached_time:.3f}秒")
        print(f"🚀 性能提升: {speedup:.1f}倍")
        
        return {
            'uncached_time': uncached_time,
            'cached_time': cached_time,
            'speedup': speedup
        }
        
    except Exception as e:
        print(f"❌ 缓存测试失败: {e}")
        return {}

def test_batch_operations():
    """测试批量操作性能"""
    print("\n=== 批量操作测试 ===")
    
    try:
        from data_processor import load_defect_data, enrich_data_with_transition_paths
        
        # 加载测试数据
        df = load_defect_data()
        if df.empty:
            print("❌ 无法加载缺陷数据")
            return {}
        
        # 选择小样本测试
        test_df = df.sample(min(30, len(df))).copy()
        print(f"测试样本: {len(test_df)} 条记录")
        
        # 批量流转路径计算
        start_time = time.time()
        enriched_df = enrich_data_with_transition_paths(test_df)
        batch_time = time.time() - start_time
        
        # 计算成功率
        ecu_success = enriched_df['ecu_transition_path'].notna().sum()
        solution_success = enriched_df['solution_cluster_transition_path'].notna().sum()
        
        print(f"✅ 批量处理耗时: {batch_time:.3f}秒")
        print(f"✅ 平均每条记录: {batch_time/len(test_df):.4f}秒")
        print(f"✅ ECU路径成功率: {ecu_success}/{len(test_df)}")
        print(f"✅ Solution路径成功率: {solution_success}/{len(test_df)}")
        
        return {
            'batch_time': batch_time,
            'records_processed': len(test_df),
            'throughput': len(test_df) / batch_time if batch_time > 0 else 0
        }
        
    except Exception as e:
        print(f"❌ 批量操作测试失败: {e}")
        return {}

def test_cache_hit_rate():
    """测试缓存命中率"""
    print("\n=== 缓存命中率测试 ===")
    
    try:
        from data_processor import load_defect_data, history_cache
        
        df = load_defect_data()
        if df.empty:
            print("❌ 无法加载缺陷数据")
            return {}
        
        test_ids = df['id'].astype(str).sample(min(50, len(df))).tolist()
        
        # 预加载一半数据
        history_cache.clear()
        preload_ids = test_ids[:len(test_ids)//2]
        history_cache.preload_histories(preload_ids)
        
        # 测试命中率
        cache_hits = 0
        for defect_id in test_ids:
            if history_cache.get(defect_id) is not None:
                cache_hits += 1
        
        hit_rate = (cache_hits / len(test_ids)) * 100
        print(f"✅ 缓存命中率: {hit_rate:.1f}% ({cache_hits}/{len(test_ids)})")
        
        return {'hit_rate': hit_rate, 'hits': cache_hits, 'total': len(test_ids)}
        
    except Exception as e:
        print(f"❌ 命中率测试失败: {e}")
        return {}

def run_all_tests():
    """运行所有性能测试"""
    print("🧪 开始性能测试")
    print("=" * 50)
    
    start_time = time.time()
    results = {}
    
    # 运行各项测试
    results['cache'] = test_cache_performance()
    results['batch'] = test_batch_operations()
    results['hit_rate'] = test_cache_hit_rate()
    
    total_time = time.time() - start_time
    
    # 输出总结
    print("\n" + "=" * 50)
    print("📊 测试总结")
    print("=" * 50)
    print(f"⏱️  总测试时间: {total_time:.2f}秒")
    
    if results['cache'].get('speedup', 0) > 1:
        print(f"✅ 缓存性能提升: {results['cache']['speedup']:.1f}倍")
    
    if results['batch'].get('throughput', 0) > 0:
        print(f"✅ 批量处理能力: {results['batch']['throughput']:.1f} 记录/秒")
    
    if results['hit_rate'].get('hit_rate', 0) > 0:
        print(f"✅ 缓存命中率: {results['hit_rate']['hit_rate']:.1f}%")
    
    print("\n🎉 性能优化建议:")
    print("• 预加载可显著提升访问速度")
    print("• 缓存机制有效减少重复读取")
    print("• 批量操作优于单个操作")
    
    return results

if __name__ == "__main__":
    run_all_tests()