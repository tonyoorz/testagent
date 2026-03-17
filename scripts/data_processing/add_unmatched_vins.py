#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import os
import shutil
from data_processor import load_defect_data

def get_unmatched_vins():
    """获取所有未匹配的VIN"""
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
    
    # 识别测试/特殊值VIN
    test_vins = [v for v in unique_unmatched_vins if v in ['TEST', '1111111111111', 'M715225', 'NONE']]
    
    # 有效VIN
    valid_vins = [v for v in unique_unmatched_vins if v not in test_vins]
    
    return valid_vins, test_vins

def assign_project_by_prefix(vin):
    """根据VIN前缀分配项目"""
    if not vin or len(vin) < 3:
        return 'MGU_02_A'  # 默认分配
    
    prefix = vin[:3].upper()
    
    # 根据现有映射的规律分配项目
    prefix_mapping = {
        'LBV': 'MGU_02_A',    # LBV前缀主要分配给MGU_02_A
        'WMW': 'MGU_02_A',    # WMW前缀全部是MGU_02_A
        'HGS': 'MGU_02_A',    # HGS前缀是MGU_02_A
        'WBA': 'MGU_02_A',    # WBA前缀主要是MGU_02_A
        'WBY': 'IDCEVO25',    # WBY前缀主要是IDCEVO25
        'SCA': 'MGU_02_L',    # SCA前缀主要是MGU_02_L
        'CK7': 'MGU_02_L'     # CK7前缀是MGU_02_L
    }
    
    return prefix_mapping.get(prefix, 'MGU_02_A')  # 默认分配给MGU_02_A

def add_unmatched_vins_to_excel():
    """添加未匹配VIN到Excel文件"""
    excel_file = 'vin_project_mapping.xlsx'
    
    # 获取未匹配的VIN
    valid_vins, test_vins = get_unmatched_vins()
    
    if not valid_vins and not test_vins:
        print("没有未匹配的VIN需要添加")
        return 0
    
    print(f"找到 {len(valid_vins)} 个有效的未匹配VIN")
    print(f"找到 {len(test_vins)} 个测试VIN")
    
    # 读取现有Excel文件
    if os.path.exists(excel_file):
        df_current = pd.read_excel(excel_file)
        current_vins = set(df_current['VIN'].astype(str).str.strip().str.upper())
        print(f'当前Excel文件中的VIN数量: {len(current_vins)}')
    else:
        print(f'Excel文件 {excel_file} 不存在')
        return 0
    
    # 收集需要添加的新VIN
    new_rows = []
    total_to_add = 0
    
    # 处理有效VIN
    prefix_counts = {}
    for vin in valid_vins:
        vin_upper = vin.strip().upper()
        if vin_upper not in current_vins:
            hu_name = assign_project_by_prefix(vin_upper)
            prefix = vin_upper[:3] if len(vin_upper) >= 3 else 'UNK'
            
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            
            new_row = {
                'VIN': vin_upper,
                'Model Series': '',
                'ISO Countrycode (INT)': '',
                'Brand': '',
                'I-Level HO': '',
                'Fuel Type Description': '',
                'Build Phase': '',
                'Product Line': '',
                'V-Nr': '',
                'HU Name': hu_name
            }
            new_rows.append(new_row)
            total_to_add += 1
    
    # 处理测试VIN - 分配给MGU_02_A
    test_count = 0
    for vin in test_vins:
        vin_upper = vin.strip().upper()
        if vin_upper not in current_vins:
            new_row = {
                'VIN': vin_upper,
                'Model Series': 'TEST_DATA',
                'ISO Countrycode (INT)': 'TEST',
                'Brand': 'TEST',
                'I-Level HO': '',
                'Fuel Type Description': '',
                'Build Phase': 'TEST',
                'Product Line': 'TEST',
                'V-Nr': 'TEST',
                'HU Name': 'MGU_02_A'  # 测试数据分配给MGU_02_A
            }
            new_rows.append(new_row)
            test_count += 1
            total_to_add += 1
    
    if total_to_add > 0:
        # 创建新的DataFrame包含所有新行
        df_new = pd.DataFrame(new_rows)
        
        # 合并现有数据和新数据
        df_updated = pd.concat([df_current, df_new], ignore_index=True)
        
        # 保存更新后的Excel文件
        df_updated.to_excel(excel_file, index=False)
        print(f'\n成功添加 {total_to_add} 个新VIN到Excel文件')
        print(f'更新后的Excel文件包含 {len(df_updated)} 行数据')
        
        # 显示按前缀添加的分布
        print('\n按前缀添加的VIN分布:')
        for prefix, count in sorted(prefix_counts.items()):
            assigned_project = assign_project_by_prefix(prefix + "00000000000000")  # 临时VIN用于获取项目
            print(f'  {prefix}: {count} 个VIN -> {assigned_project}')
        
        if test_count > 0:
            print(f'  测试VIN: {test_count} 个 -> MGU_02_A')
        
        # 显示更新后的项目分布
        hu_name_counts = df_updated['HU Name'].value_counts()
        print('\n更新后的项目分布:')
        for hu_name, count in hu_name_counts.items():
            print(f'  {hu_name}: {count} 个VIN')
            
    else:
        print('没有需要添加的新VIN，Excel文件无需更新')
    
    return total_to_add

def move_excel_to_project_folder():
    """将Excel文件移动到project文件夹"""
    excel_file = 'vin_project_mapping.xlsx'
    project_dir = 'ecu'
    target_file = os.path.join(project_dir, 'vin_project_mapping.xlsx')
    
    # 创建project文件夹（如果不存在）
    os.makedirs(project_dir, exist_ok=True)
    
    # 移动文件
    if os.path.exists(excel_file):
        shutil.move(excel_file, target_file)
        print(f'\n成功将 {excel_file} 移动到 {target_file}')
        return True
    else:
        print(f'警告: 文件 {excel_file} 不存在，无法移动')
        return False

def main():
    """主函数"""
    print("开始处理未匹配VIN...")
    
    # 1. 添加未匹配VIN到Excel文件
    added_count = add_unmatched_vins_to_excel()
    
    # 2. 移动Excel文件到project文件夹
    if added_count is not None:  # 无论是否添加了VIN，都尝试移动文件
        move_success = move_excel_to_project_folder()
        if move_success:
            print("\n下一步需要更新 data_processor.py 中的文件路径...")
    
    print(f'\n脚本完成，共添加了 {added_count} 个VIN')

if __name__ == "__main__":
    main()