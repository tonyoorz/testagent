#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import os
from data_processor import load_defect_data

def update_vin_model_series():
    """更新Excel文件中新添加VIN的Model Series信息"""
    excel_file = 'project/vin_project_mapping.xlsx'
    
    if not os.path.exists(excel_file):
        print(f"Excel文件 {excel_file} 不存在")
        return
    
    print("正在加载缺陷数据...")
    ddf = load_defect_data()
    
    print("正在加载Excel文件...")
    df_excel = pd.read_excel(excel_file)
    
    # 检查必要的列是否存在
    if 'VIN' not in df_excel.columns or 'Model Series' not in df_excel.columns:
        print("Excel文件缺少必要的列（VIN 或 Model Series）")
        return
    
    # 创建VIN到model的映射
    print("创建VIN到model的映射...")
    
    # 从缺陷数据中提取VIN和model的映射关系
    if 'vin_udf' not in ddf.columns or 'lead_model' not in ddf.columns:
        print("缺陷数据中缺少vin_udf或lead_model列")
        return
    
    # 清理和标准化VIN数据
    ddf_clean = ddf[
        (ddf['vin_udf'].notna()) & 
        (ddf['vin_udf'] != '') & 
        (ddf['lead_model'].notna()) & 
        (ddf['lead_model'] != '')
    ].copy()
    
    # 创建VIN到model的映射字典
    vin_to_model = {}
    for _, row in ddf_clean.iterrows():
        vin = str(row['vin_udf']).strip().upper()
        model = str(row['lead_model']).strip()
        
        # 如果VIN已存在，选择非空model或者更新model
        if vin in vin_to_model:
            if vin_to_model[vin] == '' and model != '':
                vin_to_model[vin] = model
        else:
            vin_to_model[vin] = model
    
    print(f"从缺陷数据中提取了 {len(vin_to_model)} 个VIN->model映射")
    
    # 找到Model Series为空的记录
    empty_model_mask = (df_excel['Model Series'] == '') | (df_excel['Model Series'].isna())
    empty_model_records = df_excel[empty_model_mask]
    
    print(f"找到 {len(empty_model_records)} 个Model Series为空的记录")
    
    # 更新Model Series
    updated_count = 0
    df_updated = df_excel.copy()
    
    for idx, row in empty_model_records.iterrows():
        vin = str(row['VIN']).strip().upper()
        
        if vin in vin_to_model:
            model = vin_to_model[vin]
            if model and model != '':
                df_updated.at[idx, 'Model Series'] = model
                updated_count += 1
                print(f"更新VIN {vin} 的Model Series为: {model}")
    
    if updated_count > 0:
        # 保存更新后的Excel文件
        df_updated.to_excel(excel_file, index=False)
        print(f'\n成功更新了 {updated_count} 个VIN的Model Series信息')
        
        # 显示更新后的统计
        model_counts = df_updated[df_updated['Model Series'] != '']['Model Series'].value_counts()
        print('\n更新后的Model Series分布:')
        for model, count in model_counts.head(10).items():
            print(f'  {model}: {count} 个VIN')
        
        if len(model_counts) > 10:
            print(f'  ... 还有 {len(model_counts) - 10} 个其他model')
            
        # 显示仍然为空的记录数
        remaining_empty = len(df_updated[(df_updated['Model Series'] == '') | (df_updated['Model Series'].isna())])
        print(f'\n仍有 {remaining_empty} 个VIN的Model Series为空')
        
    else:
        print('没有找到可以更新的Model Series信息')
    
    return updated_count

def show_vin_model_mapping_samples():
    """显示一些VIN和model的映射样例"""
    print("正在加载缺陷数据以显示VIN-model映射样例...")
    ddf = load_defect_data()
    
    # 获取有VIN和model的记录
    sample_data = ddf[
        (ddf['vin_udf'].notna()) & 
        (ddf['vin_udf'] != '') & 
        (ddf['lead_model'].notna()) & 
        (ddf['lead_model'] != '')
    ][['vin_udf', 'lead_model']].drop_duplicates().head(20)
    
    print("\nVIN->Model映射样例:")
    for _, row in sample_data.iterrows():
        print(f"  {row['vin_udf']} -> {row['lead_model']}")

def main():
    """主函数"""
    print("开始更新VIN的Model Series信息...")
    
    # 显示一些映射样例
    show_vin_model_mapping_samples()
    
    # 更新Model Series
    updated_count = update_vin_model_series()
    
    print(f'\n脚本完成，共更新了 {updated_count} 个VIN的Model Series')

if __name__ == "__main__":
    main() 