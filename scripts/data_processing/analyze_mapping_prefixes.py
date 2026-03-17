#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd

def analyze_mapping_prefixes():
    # 读取现有映射文件
    df = pd.read_excel('project/vin_project_mapping.xlsx')
    
    print("现有映射中的VIN前缀分布:")
    prefixes = {}
    projects_by_prefix = {}
    
    for _, row in df.iterrows():
        vin = str(row['VIN'])
        project = row['HU']
        prefix = vin[:3]
        
        # 统计前缀数量
        prefixes[prefix] = prefixes.get(prefix, 0) + 1
        
        # 统计每个前缀对应的项目
        if prefix not in projects_by_prefix:
            projects_by_prefix[prefix] = {}
        projects_by_prefix[prefix][project] = projects_by_prefix[prefix].get(project, 0) + 1
    
    # 显示前缀分布
    for prefix, count in sorted(prefixes.items()):
        print(f"{prefix}: {count} 个VIN")
        # 显示该前缀对应的项目分布
        for project, proj_count in projects_by_prefix[prefix].items():
            print(f"  - {project}: {proj_count}")
    
    print(f"\n总计: {len(df)} 个VIN映射")

if __name__ == "__main__":
    analyze_mapping_prefixes() 