import pandas as pd
import os

def update_vin_mapping_excel():
    """更新VIN项目映射Excel文件，添加原来手写映射中的VIN"""
    
    # 原来的手写映射数据（去重后）
    new_data = {
        'IDC': list(set([
            'LBV61FX08SM715231', 'WBA71GP0XP9U00371', 'LBV21GT04S1A62072', 
            'WMW21GC01PTA10121', 'WBA61EE0005W65834', 'LBV21FM03SSB30560',  
            'LBV41FX07RM618961', 'LBV61FX0XSM627118', 'WBACR6109L9D27145', 
            'WMW51GD06P2V17644', 'WMW81GC00RTA00421', 'LBV11HS05SSC03583', 
            'LBV21GJ09SM665436', 'WMW31GA05P7L81344', 'WBACV6105KLK20040', 
            'WBACR620X09F64155', 'WMW12GC04RTA10044', 'LBV21FM01RSD50015',
            'WMW21GD02P2U18032', 'HGS21GC05RTA46038', 'LBV71FM07SSC02320', 
            'WMW11GA010HY26704', 'WMW21GC02RTA00135', 'WMW11GY010HY16017', 
            'WBA62FX000HY29503'
        ])),
        'MGU': list(set([
            'LBV81BE08P1A02605', 'WBA21EH0XPCK79048', 'LBV5U5407NM303615', 
            'LBV81FM09SSC02288', 'WBACR6102KLH81514', 'WBA12EH000CJ07626', 
            'SCA21HA080HY35632', 'SCATK21030HY18414', 'WBA71EH0X0HY07492', 'CK79048'
        ])),
        'IDCEvo': list(set([
            'WBY21CF08PCN23000', 'WBY22CF0X0CN18562', 'WBY21CF02PCN18309', 
            'WBA31HR040HY35514', 'WBA21HY030HY47120', 'WBA31HR07RH021760', 
            'WBY21CF04RCR75965', 'WBY21CF06PCN19866'
        ]))
    }
    
    # 项目到HU Name的映射
    project_to_hu_name = {
        'IDC': 'MGU_02_A',
        'MGU': 'MGU_02_L', 
        'IDCEvo': 'IDCEVO25'
    }
    
    excel_file = 'project/vin_project_mapping.xlsx'
    
    # 读取当前 Excel 文件
    if os.path.exists(excel_file):
        df_current = pd.read_excel(excel_file)
        current_vins = set(df_current['VIN'].astype(str).str.strip().str.upper())
        print(f'当前Excel文件中的VIN数量: {len(current_vins)}')
    else:
        print(f'Excel文件 {excel_file} 不存在，将创建新文件')
        df_current = pd.DataFrame(columns=['VIN', 'Model Series', 'ISO Countrycode (INT)', 
                                          'Brand', 'I-Level HO', 'Fuel Type Description', 
                                          'Build Phase', 'Product Line', 'V-Nr', 'HU Name'])
        current_vins = set()
    
    # 收集需要添加的新VIN
    new_rows = []
    total_to_add = 0
    
    for project, vins in new_data.items():
        hu_name = project_to_hu_name[project]
        project_new_count = 0
        
        for vin in vins:
            vin_upper = vin.strip().upper()
            if vin_upper not in current_vins:
                new_row = {
                    'VIN': vin_upper,
                    'Model Series': '',  # 这些字段可以后续手动填充或从其他源获取
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
                project_new_count += 1
                total_to_add += 1
        
        print(f'{project} ({hu_name}): 需要添加 {project_new_count} 个VIN')
    
    if total_to_add > 0:
        # 创建新的DataFrame包含所有新行
        df_new = pd.DataFrame(new_rows)
        
        # 合并现有数据和新数据
        df_updated = pd.concat([df_current, df_new], ignore_index=True)
        
        # 保存更新后的Excel文件
        df_updated.to_excel(excel_file, index=False)
        print(f'\n成功添加 {total_to_add} 个新VIN到Excel文件')
        print(f'更新后的Excel文件包含 {len(df_updated)} 行数据')
        
        # 显示更新后的项目分布
        hu_name_counts = df_updated['HU Name'].value_counts()
        print('\n更新后的项目分布:')
        for hu_name, count in hu_name_counts.items():
            print(f'  {hu_name}: {count}个')
            
    else:
        print('没有需要添加的新VIN，Excel文件无需更新')
    
    return total_to_add

if __name__ == '__main__':
    added_count = update_vin_mapping_excel()
    print(f'\n脚本完成，共添加了 {added_count} 个VIN') 