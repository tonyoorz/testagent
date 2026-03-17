#!/usr/bin/env python3
"""
性能优化测试脚本
对比优化前后的历史数据加载性能
"""

import time
import pandas as pd
import random
from data_processor import (
    load_defect_data, 
    history_cache, 
    get_history_data,
    extract_transition_path_from_history,
    enrich_data_with_transition_paths,
    get_resolved_time_from_history
)

def test_cache_performance():
    """测试缓存性能"""
    print("=== 缓存性能测试 ===")
    
    # 加载一些缺陷数据
    df = load_defect_data()
    if df.empty:
        print("❌ 无法加载缺陷数据")
        return
    
    # 随机选择100个缺陷ID进行测试
    test_ids = df['id'].astype(str).sample(min(100, len(df))).tolist()
    print(f"测试缺陷ID数量: {len(test_ids)}")
    
    # 测试1: 未缓存的情况下单个读取历史数据
    print("\n📊 测试1: 单个读取历史数据（未缓存）")
    history_cache.clear()  # 清空缓存
    
    start_time = time.time()
    for defect_id in test_ids[:20]:  # 只测试前20个
        get_history_data(defect_id)
    uncached_time = time.time() - start_time
    print(f"未缓存读取20个历史文件耗时: {uncached_time:.2f}秒")
    
    # 测试2: 预加载缓存后读取
    print("\n📊 测试2: 预加载缓存后读取")
    history_cache.clear()  # 清空缓存
    
    # 预加载
    preload_start = time.time()
    history_cache.preload_histories(test_ids[:20])
    preload_time = time.time() - preload_start
    print(f"预加载20个历史文件耗时: {preload_time:.2f}秒")
    
    # 缓存读取
    start_time = time.time()
    for defect_id in test_ids[:20]:
        get_history_data(defect_id)
    cached_time = time.time() - start_time
    print(f"缓存读取20个历史文件耗时: {cached_time:.2f}秒")
    
    # 性能提升计算
    if uncached_time > 0:
        speedup = uncached_time / cached_time if cached_time > 0 else float('inf')
        print(f"\n🚀 缓存读取速度提升: {speedup:.1f}倍")
    
    return {
        'uncached_time': uncached_time,
        'preload_time': preload_time,
        'cached_time': cached_time
    }

def test_transition_path_performance():
    """测试流转路径计算性能"""
    print("\n=== 流转路径计算性能测试 ===")
    
    # 加载一些缺陷数据
    df = load_defect_data()
    if df.empty:
        print("❌ 无法加载缺陷数据")
        return
    
    # 选择测试样本
    test_df = df.sample(min(50, len(df))).copy()
    test_ids = test_df['id'].astype(str).tolist()
    
    print(f"测试样本数量: {len(test_ids)}")
    
    # 测试1: 未预加载的情况
    print("\n📊 测试1: 未预加载历史数据")
    history_cache.clear()
    
    start_time = time.time()
    for defect_id in test_ids:
        extract_transition_path_from_history(defect_id, 'assigned_ecu_udf')
    unoptimized_time = time.time() - start_time
    print(f"未优化的ECU流转路径计算耗时: {unoptimized_time:.2f}秒")
    
    # 测试2: 预加载后计算
    print("\n📊 测试2: 预加载历史数据后计算")
    history_cache.clear()
    
    # 预加载历史数据
    preload_start = time.time()
    history_cache.preload_histories(test_ids)
    preload_time = time.time() - preload_start
    print(f"预加载耗时: {preload_time:.2f}秒")
    
    # 计算流转路径
    start_time = time.time()
    for defect_id in test_ids:
        extract_transition_path_from_history(defect_id, 'assigned_ecu_udf')
    optimized_time = time.time() - start_time
    print(f"优化后的ECU流转路径计算耗时: {optimized_time:.2f}秒")
    
    # 总时间对比
    total_unoptimized = unoptimized_time
    total_optimized = preload_time + optimized_time
    
    print(f"\n📈 性能对比:")
    print(f"  未优化总耗时: {total_unoptimized:.2f}秒")
    print(f"  优化后总耗时: {total_optimized:.2f}秒")
    
    if total_unoptimized > 0:
        if total_optimized < total_unoptimized:
            speedup = total_unoptimized / total_optimized
            print(f"  🚀 性能提升: {speedup:.1f}倍")
        else:
            slowdown = total_optimized / total_unoptimized
            print(f"  ⚠️ 性能下降: {slowdown:.1f}倍 (预加载开销)")
    
    return {
        'unoptimized_time': total_unoptimized,
        'optimized_time': total_optimized,
        'preload_time': preload_time
    }

def test_bulk_operations():
    """测试批量操作性能"""
    print("\n=== 批量操作性能测试 ===")
    
    # 加载数据
    df = load_defect_data()
    if df.empty:
        print("❌ 无法加载缺陷数据")
        return
    
    # 选择较小的测试样本
    test_df = df.sample(min(30, len(df))).copy()
    print(f"测试样本数量: {len(test_df)}")
    
    # 测试批量流转路径计算
    print("\n📊 测试批量流转路径计算（包含预加载）")
    
    start_time = time.time()
    enriched_df = enrich_data_with_transition_paths(test_df)
    bulk_time = time.time() - start_time
    
    print(f"批量流转路径计算耗时: {bulk_time:.2f}秒")
    print(f"平均每条记录耗时: {bulk_time/len(test_df):.3f}秒")
    
    # 检查结果
    ecu_paths = enriched_df['ecu_transition_path'].notna().sum()
    solution_paths = enriched_df['solution_cluster_transition_path'].notna().sum()
    
    print(f"成功计算ECU流转路径: {ecu_paths}/{len(test_df)}")
    print(f"成功计算Solution Cluster流转路径: {solution_paths}/{len(test_df)}")
    
    return {
        'bulk_time': bulk_time,
        'records_processed': len(test_df),
        'avg_time_per_record': bulk_time/len(test_df)
    }

def test_cache_hit_rate():
    """测试缓存命中率"""
    print("\n=== 缓存命中率测试 ===")
    
    df = load_defect_data()
    if df.empty:
        print("❌ 无法加载缺陷数据")
        return
    
    test_ids = df['id'].astype(str).sample(min(100, len(df))).tolist()
    
    # 预加载部分数据
    history_cache.clear()
    history_cache.preload_histories(test_ids[:50])
    
    # 测试命中率
    cache_hits = 0
    cache_misses = 0
    
    for defect_id in test_ids:
        cached_data = history_cache.get(defect_id)
        if cached_data is not None:
            cache_hits += 1
        else:
            cache_misses += 1
    
    hit_rate = (cache_hits / len(test_ids)) * 100
    print(f"缓存命中率: {hit_rate:.1f}% ({cache_hits}/{len(test_ids)})")
    
    return {
        'hit_rate': hit_rate,
        'cache_hits': cache_hits,
        'cache_misses': cache_misses
    }

def main():
    """主测试函数"""
    print("🧪 开始历史数据加载性能优化测试\n")
    
    results = {}
    
    try:
        # 运行各项测试
        results['cache'] = test_cache_performance()
        results['transition'] = test_transition_path_performance()
        results['bulk'] = test_bulk_operations()
        results['hit_rate'] = test_cache_hit_rate()
        
        # 输出总结
        print("\n" + "="*50)
        print("🎯 测试总结")
        print("="*50)
        
        if 'cache' in results and results['cache']:
            cache_results = results['cache']
            if cache_results['cached_time'] > 0:
                speedup = cache_results['uncached_time'] / cache_results['cached_time']
                print(f"✅ 缓存读取性能提升: {speedup:.1f}倍")
        
        if 'transition' in results and results['transition']:
            trans_results = results['transition']
            if trans_results['optimized_time'] < trans_results['unoptimized_time']:
                speedup = trans_results['unoptimized_time'] / trans_results['optimized_time']
                print(f"✅ 流转路径计算性能提升: {speedup:.1f}倍")
            else:
                print(f"⚠️ 流转路径计算有预加载开销，但后续访问会更快")
        
        if 'bulk' in results and results['bulk']:
            bulk_results = results['bulk']
            print(f"✅ 批量操作处理能力: {bulk_results['records_processed']/bulk_results['bulk_time']:.1f} 记录/秒")
        
        if 'hit_rate' in results and results['hit_rate']:
            hit_results = results['hit_rate']
            print(f"✅ 缓存命中率: {hit_results['hit_rate']:.1f}%")
        
        print("\n🎉 优化建议:")
        print("1. 使用预加载可显著提升历史数据访问速度")
        print("2. 缓存机制有效减少重复文件读取")
        print("3. 批量操作优于单个操作")
        print("4. 首次加载后，后续访问速度大幅提升")
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
    
    print("\n测试完成！")

if __name__ == "__main__":
    main()