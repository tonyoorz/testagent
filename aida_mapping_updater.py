# aida_mapping_updater.py
import pandas as pd
import os
import re # 导入 re 模块
# 尝试从 data_processor 导入 load_test_data 函数
# 假设 data_processor.py 和这个脚本在同一个目录下或 Python 路径中
try:
    from data_processor import load_test_data
except ImportError:
    print("错误：无法导入 load_test_data 函数。")
    print("请确保 data_processor.py 文件存在且与此脚本位于同一目录，或者在 Python 的搜索路径中。")
    # 定义一个虚拟函数以允许脚本继续运行（但功能会受限）或直接退出
    def load_test_data():
        print("错误：load_test_data 未成功加载，无法执行核心功能。")
        # 返回一个带 'top_aida' 和 'project' 列的空 DataFrame 以避免后续报错
        return pd.DataFrame(columns=['top_aida', 'project'])

def find_and_report_missing_aida_mappings(
    mapping_excel_path="aida/top_aida_project_fv_mapping.xlsx"
):
    """
    分析测试数据 (来自 load_test_data)，找出在映射 Excel 文件所有工作表中都缺失的 top_aida 条目，
    并将这些缺失的 top_aida 追加到其对应的 Project 同名工作表中。

    Args:
        mapping_excel_path (str): 原始 AIDA->FV 映射 Excel 文件的路径。
    """
    print("--- 开始查找并更新缺失的 AIDA 映射 (按 Project 更新) ---")

    # 1. 加载测试数据并提取唯一的 top_aida
    print(f"步骤 1: 正在使用 load_test_data 加载测试数据...")
    tdf = load_test_data()
    if tdf.empty:
        print("错误：加载的测试数据 DataFrame 为空。无法继续。")
        return
    if 'top_aida' not in tdf.columns:
        print("错误：加载的测试数据 DataFrame 缺少 'top_aida' 列。无法继续。")
        return

    unique_tdf_aidas = set(tdf['top_aida'].fillna('').astype(str).str.strip().unique())
    unique_tdf_aidas.discard('')
    unique_tdf_aidas.discard('None')
    if not unique_tdf_aidas:
        print("警告：从测试数据中未能提取到有效的、非空的 top_aida 值。无需更新。")
        return
    print(f"从测试数据中找到 {len(unique_tdf_aidas)} 个唯一的、非空的 top_aida。")

    # 2. 从 Excel *所有* 工作表加载已知的 top_aida
    print(f"\n步骤 2: 正在从映射文件 '{mapping_excel_path}' 的 *所有* 工作表加载现有的 top_aida...")
    known_excel_aidas = set()
    if os.path.exists(mapping_excel_path):
        try:
            xls = pd.ExcelFile(mapping_excel_path)
            print(f"成功打开 Excel 文件，将检查所有工作表: {xls.sheet_names}")
            for sheet_name in xls.sheet_names:
                try:
                    df_map = pd.read_excel(xls, sheet_name=sheet_name, usecols=['top_aida'])
                    if 'top_aida' in df_map.columns:
                        sheet_aidas = set(df_map['top_aida'].fillna('').astype(str).str.strip().unique())
                        sheet_aidas.discard('')
                        sheet_aidas.discard('None')
                        known_excel_aidas.update(sheet_aidas)
                except ValueError:
                    print(f"  > 警告: 工作表 '{sheet_name}' 缺少 'top_aida' 列或无法读取。")
                except Exception as e:
                    print(f"  > 错误：读取或处理工作表 '{sheet_name}' 时出错: {e}。")
        except Exception as e:
            print(f"错误：读取 Excel 文件 '{mapping_excel_path}' 时发生严重错误: {e}。")
    else:
        print(f"警告：映射文件 '{mapping_excel_path}' 不存在。将创建新文件。")
    print(f"从映射文件的 *所有* 可读工作表中总共识别了 {len(known_excel_aidas)} 个唯一的、非空的 top_aida。")

    # 3. 找出真正缺失的 top_aida
    print("\n步骤 3: 正在比较测试数据和所有已知映射中的 top_aida...")
    missing_aidas = sorted(list(unique_tdf_aidas - known_excel_aidas))
    if not missing_aidas:
        print("\n--- 结果 ---")
        print(f"恭喜！没有在测试数据中发现任何在映射文件 '{mapping_excel_path}' 的任何工作表中缺失的 top_aida。文件未被修改。")
        return
    print("\n--- 结果 ---")
    print(f"发现 {len(missing_aidas)} 个 top_aida 存在于测试数据中，但在映射文件的任何工作表中都找不到。")

    # 4. 按 Project (目标工作表名) 分组缺失的 AIDA
    print(f"\n步骤 4: 按 Project (目标工作表名) 分组缺失的 AIDA...")
    missing_by_project = {}
    default_sheet_name = 'Sheet1'
    project_col_in_tdf = 'project' in tdf.columns
    project_data = tdf[['project', 'top_aida']].drop_duplicates() if project_col_in_tdf else pd.DataFrame(columns=['project', 'top_aida'])

    # +++ 添加调试日志标题 +++
    print("  --- 开始为每个缺失 AIDA 分配目标工作表 (Debug Log) ---")
    for i, aida in enumerate(missing_aidas): # 使用 enumerate 获取索引用于日志
        target_sheet_name = default_sheet_name
        project_value = 'Unknown'
        original_project_name_found = None # 用于日志
        if project_col_in_tdf:
            projects_for_aida = project_data.loc[project_data['top_aida'] == aida, 'project'].dropna().astype(str).str.strip()
            valid_projects = projects_for_aida[projects_for_aida != ''].tolist()
            if valid_projects:
                original_project_name_found = valid_projects[0] # 记录找到的原始 project 名
                project_value = original_project_name_found
                safe_sheet_name = re.sub(r'[\\/?:*\\[\]]', '_', original_project_name_found)[:31]
                target_sheet_name = safe_sheet_name
                # +++ 添加调试日志: 清理前后对比 +++
                # if safe_sheet_name != original_project_name_found:
                #    print(f"      [{i+1}] Project '{original_project_name_found}' cleaned to '{safe_sheet_name}'")
            # else: Project not found or invalid for this AIDA
        # else: No 'project' column in tdf

        # +++ 添加核心调试日志 +++
        print(f"    [{i+1}/{len(missing_aidas)}] AIDA: '{aida}' | Found Project: '{original_project_name_found or 'N/A'}' | Target Sheet: '{target_sheet_name}' | Value for Project Col: '{project_value}'")

        if target_sheet_name not in missing_by_project:
            missing_by_project[target_sheet_name] = []
        missing_by_project[target_sheet_name].append({'top_aida': aida, 'project_value': project_value})

    # +++ 添加调试日志结尾 +++
    print("  --- 分配完成 ---")

    print("分组完成:")
    for sheet, aida_infos in missing_by_project.items():
        print(f"  - 工作表 '{sheet}': 将添加 {len(aida_infos)} 个 AIDA")

    # 5 & 6: 读取所有现有表，准备更新，用 'w' 模式写回所有表
    print(f"\n步骤 5 & 6: 正在准备并写入更新到 Excel 文件 '{mapping_excel_path}'...")
    all_sheets_data_final = {}
    if os.path.exists(mapping_excel_path):
        print("  - 正在读取所有原始工作表数据...")
        try:
            xls_read_all = pd.ExcelFile(mapping_excel_path)
            for sheet_name in xls_read_all.sheet_names:
                try:
                    all_sheets_data_final[sheet_name] = pd.read_excel(xls_read_all, sheet_name=sheet_name)
                    print(f"    > 已加载工作表: '{sheet_name}' ({len(all_sheets_data_final[sheet_name])} 行)")
                except Exception as e_read_preserve:
                    print(f"    > 警告: 无法读取原始工作表 '{sheet_name}': {e_read_preserve}. 此表数据可能丢失。")
                    all_sheets_data_final[sheet_name] = pd.DataFrame() # 保留表名，但数据为空
        except Exception as e_read_all:
            print(f"  - 警告: 无法完全读取原始 Excel 文件: {e_read_all}. 将只创建/更新目标工作表。")
            all_sheets_data_final = {} # 清空，只处理需要更新的

    print("  - 正在准备更新后的工作表数据...")
    for target_sheet_name, aida_infos_for_sheet in missing_by_project.items():
        print(f"    > 处理目标工作表: '{target_sheet_name}'...")
        existing_sheet_df = all_sheets_data_final.get(target_sheet_name, pd.DataFrame())
        if existing_sheet_df.empty:
            default_columns = ['project', 'top_aida', 'fv'] # 始终包含这三列
            existing_sheet_df = pd.DataFrame(columns=default_columns)
            print(f"      - 工作表 '{target_sheet_name}' 不存在或为空，将使用列: {existing_sheet_df.columns.tolist()}")
            all_sheets_data_final[target_sheet_name] = existing_sheet_df # 确保加入最终列表

        missing_rows_data = []
        for aida_info in aida_infos_for_sheet:
            row = {
                'top_aida': aida_info['top_aida'],
                'fv': 'PLEASE_UPDATE',
                'project': aida_info['project_value']
            }
            # 只保留 DataFrame 中实际存在的列
            row_filtered = {k: v for k, v in row.items() if k in existing_sheet_df.columns}
            missing_rows_data.append(row_filtered)

        if not missing_rows_data:
            continue

        new_rows_df = pd.DataFrame(missing_rows_data)
        if not new_rows_df.empty:
            # 使用 concat 自动对齐列并合并
            # 确保原始 DataFrame 和新行 DataFrame 的列类型尽量一致，减少 Excel 警告
            for col in existing_sheet_df.columns:
                if col in new_rows_df.columns and existing_sheet_df[col].dtype != new_rows_df[col].dtype:
                    try:
                        # 尝试统一为字符串类型，通常比较安全
                        existing_sheet_df[col] = existing_sheet_df[col].astype(str)
                        new_rows_df[col] = new_rows_df[col].astype(str)
                    except Exception:
                        pass # 类型转换失败则忽略

            updated_sheet_df = pd.concat([existing_sheet_df, new_rows_df], ignore_index=True)
            all_sheets_data_final[target_sheet_name] = updated_sheet_df # 更新最终数据集
            print(f"      - 已准备好 {len(new_rows_df)} 行新数据追加到 '{target_sheet_name}'")

    # 7. 最终写入所有工作表
    print(f"\n步骤 7: 正在将 {len(all_sheets_data_final)} 个工作表写入 Excel 文件 '{mapping_excel_path}'...")
    try:
        with pd.ExcelWriter(mapping_excel_path, engine='openpyxl', mode='w') as writer:
            for sheet_name, df_to_write in all_sheets_data_final.items():
                if isinstance(df_to_write, pd.DataFrame):
                    print(f"  - 写入工作表: '{sheet_name}' ({len(df_to_write)} 行)")
                    df_cleaned = df_to_write.dropna(how='all') # 去除完全空的行
                    # 写入 Excel 前，将所有列转为字符串，避免混合类型问题
                    df_stringified = df_cleaned.astype(str)
                    df_stringified.to_excel(writer, sheet_name=sheet_name, index=False)
                else:
                    print(f"  - 跳过写入无效数据的工作表: '{sheet_name}'")

        print("-" * 30)
        print("Excel 文件已成功更新！")
        print(f"文件路径: {os.path.abspath(mapping_excel_path)}")
        print("涉及的工作表已被更新或创建。请检查并填写 'PLEASE_UPDATE' 的 FV 值。")
        print("-" * 30)

    except PermissionError:
        print(f"错误：权限不足，无法写入文件 '{mapping_excel_path}'。请检查文件是否已打开或权限设置。")
    except Exception as e:
        print(f"错误：无法将更新后的数据写入 Excel 文件 '{mapping_excel_path}': {e}")


# --- 主程序入口 ---
if __name__ == "__main__":
    print("=" * 50)
    print("  AIDA 映射更新工具 (直接修改 Excel - 按 Project 更新)")
    print("=" * 50)
    print("警告：此脚本将直接修改原始 Excel 文件!")
    print("请确保在运行前已备份 aida/top_aida_project_fv_mapping.xlsx 文件。")
    input("按 Enter 键继续，或按 Ctrl+C 取消...")
    find_and_report_missing_aida_mappings()
    print("\n操作完成。")
