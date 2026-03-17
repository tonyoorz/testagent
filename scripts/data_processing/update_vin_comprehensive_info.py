#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import os
import re
from data_processor import load_defect_data

def extract_country_from_vin(vin):
    """从VIN码提取国家信息"""
    if not vin or len(vin) < 3:
        return ""
    
    # VIN的前3位是WMI（World Manufacturer Identifier）
    wmi = vin[:3].upper()
    
    # 常见的中国制造商代码
    china_codes = ['LBV', 'LGB', 'LDC', 'LFV', 'LGX', 'LHG', 'LKL', 'LMG', 'LNB', 'LPL', 'LVS', 'LVY', 'LZZ']
    # BMW德国代码
    germany_codes = ['WBA', 'WBS', 'WBX']
    # BMW美国代码  
    usa_codes = ['4US', '5UX', '5YM']
    # BMW英国代码
    uk_codes = ['SAJ', 'SAL', 'SAR', 'SAV']
    # MINI英国代码
    mini_uk_codes = ['WMW']
    # Rolls-Royce英国代码  
    rr_uk_codes = ['SCA']
    # BMW南非代码
    sa_codes = ['NC1']
    # 中国香港和台湾的特殊情况
    # 这里需要更复杂的逻辑，可能需要结合其他信息
    
    if wmi in china_codes:
        return 'CN'
    elif wmi in germany_codes:
        return 'DE' 
    elif wmi in usa_codes:
        return 'US'
    elif wmi in uk_codes or wmi in mini_uk_codes or wmi in rr_uk_codes:
        return 'GB'
    elif wmi in sa_codes:
        return 'ZA'
    else:
        # 对于一些特殊情况，可能需要额外的逻辑
        return ""

def extract_brand_from_vin(vin, model_series=""):
    """从VIN码和模型系列推断品牌"""
    if not vin or len(vin) < 3:
        return ""
    
    wmi = vin[:3].upper()
    
    # BMW WMI代码
    bmw_codes = ['WBA', 'WBS', 'WBX', 'LBV', 'LGB', 'LDC', 'LFV', 'LGX', 'LHG', 
                 'LKL', 'LMG', 'LNB', 'LPL', 'LVS', 'LVY', 'LZZ', '4US', '5UX', '5YM']
    # MINI代码
    mini_codes = ['WMW']
    # Rolls-Royce代码
    rr_codes = ['SCA']
    
    if wmi in bmw_codes:
        return 'BMW'
    elif wmi in mini_codes:
        return 'MINI'
    elif wmi in rr_codes:
        return 'Rolls-Royce'
    else:
        # 基于模型系列的推断
        if model_series.startswith('RR'):
            return 'Rolls-Royce'
        elif model_series in ['F65', 'F66', 'J01', 'J05', 'U25', 'U06']:
            return 'MINI'
        else:
            return 'BMW'

def determine_fuel_type_from_model(model_series=""):
    """根据模型系列推断燃料类型"""
    if not model_series:
        return ""
    
    # 电动车型号
    electric_models = ['i01', 'i03', 'i12', 'i15', 'i20', 'iX1', 'iX3', 'iX']
    # 插电混动型号通常包含 'e' 或特定代码
    phev_models = ['530e', '540e', '745e', 'X5e']
    
    model_upper = model_series.upper()
    
    # 检查是否为电动车
    for electric in electric_models:
        if electric.upper() in model_upper:
            return 'Elektro'
    
    # 检查是否为插电混动
    for phev in phev_models:
        if phev.upper() in model_upper:
            return 'Benzin+Elektro'
    
    # 默认汽油
    return 'Benzin'

def map_model_to_product_line(model_series=""):
    """将模型系列映射到产品线"""
    if not model_series:
        return ""
    
    product_line_mapping = {
        # BMW轿车系列
        'G20': 'LK', 'G21': 'LK', 'G28': 'LK', 'G48': 'LK', 'G45': 'LK',
        'G70': 'LG', 'G71': 'LG', 'G78': 'LG', 'G68': 'LK',
        # BMW X系列
        'G01': 'LG', 'G02': 'LG', 'G05': 'LG', 'G06': 'LG', 'G07': 'LG',
        # MINI系列
        'F65': 'LU', 'F66': 'LU', 'J01': 'LU', 'J05': 'LU', 'U25': 'LU', 'U06': 'LU',
        # BMW i系列
        'U11': 'LU', 'U12': 'LU',
        # Rolls-Royce
        'RR31': 'LG', 'RR25': 'LG',
        # 其他
        'NA5': 'LN', 'NA6': 'LN',
        'F78': 'LU', 'G18': 'LK', 'G06': 'LG'
    }
    
    return product_line_mapping.get(model_series, '')

def update_comprehensive_vin_info():
    """全面更新Excel文件中VIN的各种信息"""
    excel_file = 'project/vin_project_mapping.xlsx'
    
    if not os.path.exists(excel_file):
        print(f"Excel文件 {excel_file} 不存在")
        return 0
    
    print("正在加载缺陷数据...")
    ddf = load_defect_data()
    
    print("正在加载Excel文件...")
    df_excel = pd.read_excel(excel_file)
    
    # 检查必要的列是否存在
    required_columns = ['VIN', 'Model Series']
    missing_columns = [col for col in required_columns if col not in df_excel.columns]
    if missing_columns:
        print(f"Excel文件缺少必要的列: {missing_columns}")
        return 0
    
    # 从缺陷数据创建VIN到详细信息的映射
    print("创建VIN到详细信息的映射...")
    
    if 'vin_udf' not in ddf.columns or 'lead_model' not in ddf.columns:
        print("缺陷数据中缺少必要的列")
        return 0
    
    # 清理和标准化VIN数据
    ddf_clean = ddf[
        (ddf['vin_udf'].notna()) & 
        (ddf['vin_udf'] != '') & 
        (ddf['lead_model'].notna()) & 
        (ddf['lead_model'] != '')
    ].copy()
    
    # 创建VIN到各种信息的映射字典
    vin_to_info = {}
    for _, row in ddf_clean.iterrows():
        vin = str(row['vin_udf']).strip().upper()
        model = str(row['lead_model']).strip()
        
        if vin not in vin_to_info:
            # 从VIN和模型推断各种信息
            country_code = extract_country_from_vin(vin)
            brand = extract_brand_from_vin(vin, model)
            fuel_type = determine_fuel_type_from_model(model)
            product_line = map_model_to_product_line(model)
            
            vin_to_info[vin] = {
                'model_series': model,
                'country_code': country_code,
                'brand': brand,
                'fuel_type': fuel_type,
                'product_line': product_line
            }
    
    print(f"从缺陷数据中提取了 {len(vin_to_info)} 个VIN的详细信息")
    
    # 更新Excel文件
    df_updated = df_excel.copy()
    updated_count = 0
    
    # 定义字段映射关系（Excel列名 -> 我们的数据键名）
    field_mapping = {
        'Model Series': 'model_series',
        'ISO Countrycode (INT)': 'country_code', 
        'Brand': 'brand',
        'Fuel Type Description': 'fuel_type',
        'Product Line': 'product_line'
    }
    
    print("开始更新VIN信息...")
    for idx, row in df_updated.iterrows():
        vin = str(row['VIN']).strip().upper()
        
        if vin in vin_to_info:
            vin_info = vin_to_info[vin]
            updated_fields = []
            
            # 更新各个字段
            for excel_col, data_key in field_mapping.items():
                if excel_col in df_updated.columns:
                    current_value = str(row[excel_col]) if pd.notna(row[excel_col]) else ""
                    new_value = vin_info[data_key]
                    
                    # 只更新空值或者改进现有值
                    if not current_value or current_value == "" or current_value == "nan":
                        if new_value:
                            df_updated.at[idx, excel_col] = new_value
                            updated_fields.append(f"{excel_col}={new_value}")
            
            if updated_fields:
                updated_count += 1
                print(f"更新VIN {vin}: {', '.join(updated_fields)}")
    
    if updated_count > 0:
        # 保存更新后的Excel文件
        df_updated.to_excel(excel_file, index=False)
        print(f'\n成功更新了 {updated_count} 个VIN的信息')
        
        # 显示更新后的统计
        print('\n更新后的统计信息:')
        for excel_col, data_key in field_mapping.items():
            if excel_col in df_updated.columns:
                non_empty_count = len(df_updated[df_updated[excel_col].notna() & (df_updated[excel_col] != '')])
                print(f'  {excel_col}: {non_empty_count} 个VIN有数据')
        
    else:
        print('没有找到需要更新的VIN信息')
    
    return updated_count

def show_vin_comprehensive_mapping_samples():
    """显示VIN的综合信息映射样例"""
    print("正在加载缺陷数据以显示VIN综合信息映射样例...")
    ddf = load_defect_data()
    
    # 获取有VIN和model的记录样例
    sample_data = ddf[
        (ddf['vin_udf'].notna()) & 
        (ddf['vin_udf'] != '') & 
        (ddf['lead_model'].notna()) & 
        (ddf['lead_model'] != '')
    ][['vin_udf', 'lead_model']].drop_duplicates().head(10)
    
    print("\nVIN综合信息映射样例:")
    for _, row in sample_data.iterrows():
        vin = str(row['vin_udf']).strip().upper()
        model = str(row['lead_model']).strip()
        
        country = extract_country_from_vin(vin)
        brand = extract_brand_from_vin(vin, model)
        fuel_type = determine_fuel_type_from_model(model)
        product_line = map_model_to_product_line(model)
        
        print(f"  VIN: {vin}")
        print(f"    模型: {model}, 国家: {country}, 品牌: {brand}")
        print(f"    燃料: {fuel_type}, 产品线: {product_line}")
        print()

def main():
    """主函数"""
    print("开始全面更新VIN信息...")
    
    # 显示一些映射样例
    show_vin_comprehensive_mapping_samples()
    
    # 更新综合信息
    updated_count = update_comprehensive_vin_info()
    
    print(f'\n脚本完成，共更新了 {updated_count} 个VIN的综合信息')

if __name__ == "__main__":
    main() 