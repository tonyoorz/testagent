#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from data_processor import load_defect_data
import pandas as pd

def analyze_unmatched_vins():
    print("正在加载缺陷数据...")
    ddf = load_defect_data()
    
    # 获取未分配tproject的缺陷
    empty_tproject = ddf[ddf['ecu'] == '']
    
    # 获取有效但未匹配的VIN
    valid_but_unmatched = empty_tproject[
        (~empty_tproject['vin_udf'].isnull()) & 
        (empty_tproject['vin_udf'] != '') & 
        (empty_tproject['vin_udf'] != 'nan')
    ]
    
    unique_unmatched_vins = valid_but_unmatched['vin_udf'].dropna().unique()
    
    print(f"\n未匹配VIN分析:")
    print(f"总计未匹配VIN数量: {len(unique_unmatched_vins)}")
    
    # 识别测试/特殊值VIN
    test_vins = [v for v in unique_unmatched_vins if v in ['TEST', '1111111111111', 'M715225', 'NONE']]
    print(f"测试/特殊值VIN: {test_vins}")
    
    # 有效VIN
    valid_vins = [v for v in unique_unmatched_vins if v not in test_vins]
    print(f"有效VIN数量: {len(valid_vins)}")
    print(f"测试VIN数量: {len(test_vins)}")
    
    # 分析VIN前缀
    print("\n有效但未匹配的VIN前缀分析:")
    prefixes = {}
    for v in valid_vins:
        if len(v) >= 3:
            prefix = v[:3]
            if prefix not in prefixes:
                prefixes[prefix] = []
            prefixes[prefix].append(v)
    
    for prefix, vins in sorted(prefixes.items()):
        print(f"{prefix}: {len(vins)} 个VIN")
        if len(vins) <= 3:
            for vin in vins:
                print(f"  - {vin}")
    
    # 分析每个测试VIN的缺陷数量
    print("\n测试VIN的缺陷分布:")
    for test_vin in test_vins:
        count = len(valid_but_unmatched[valid_but_unmatched['vin_udf'] == test_vin])
        print(f"{test_vin}: {count} 个缺陷")
    
    print("\n有效VIN的缺陷分布:")
    for prefix, vins in sorted(prefixes.items()):
        total_defects = 0
        for vin in vins:
            count = len(valid_but_unmatched[valid_but_unmatched['vin_udf'] == vin])
            total_defects += count
        print(f"{prefix} 前缀: {total_defects} 个缺陷 ({len(vins)} 个VIN)")

if __name__ == "__main__":
    analyze_unmatched_vins()