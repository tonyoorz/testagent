import pandas as pd
import plotly.express as px

# 导入指定的CSV文件
raw_df = pd.read_csv('download/DTSV_CN Speech_IDCEVO_checklist_v2.csv')

# --- 数据转换为看板所需格式 ---

# 1. 识别ID变量和CW状态列
id_vars_for_status = ['Test Scope', 'Test Module', 'Customer Cases']
raw_df.columns = [col.strip() for col in raw_df.columns]
id_vars_for_status = [col for col in id_vars_for_status if col in raw_df.columns]

if 'Customer Cases' not in id_vars_for_status:
    print("Error: 'Customer Cases' column not found in CSV. Please ensure it exists.")
    if 'Test Step' in raw_df.columns:
        print("Hint: 'Test Step' column found. Modify script if you intend to use it.")
    exit()

if not all(item in raw_df.columns for item in ['Test Scope', 'Test Module']):
    print("Error: 'Test Scope' or 'Test Module' column missing from CSV.")
    exit()

cw_status_cols = [col for col in raw_df.columns if col.startswith('CW')]

if not cw_status_cols:
    print("Error: No columns starting with 'CW' (representing test weeks) found in CSV.")
    exit()

valid_id_vars = [col for col in id_vars_for_status if col in raw_df.columns]

# 2. 提取BugID数据
def clean_bug_id(value):
    s_val = str(value).strip()
    if not s_val or s_val.lower() == 'nan':
        return None
    status_words = {"pass", "fail", "blocked", "no run"}
    if s_val.lower() in status_words:
        return None
    return s_val

bug_data_records = []
columns_list = raw_df.columns.tolist()
for row_idx, row_series in raw_df.iterrows():
    base_data = {vid: row_series[vid] for vid in valid_id_vars}
    for col_idx, col_name in enumerate(columns_list):
        if col_name.startswith("CW"):
            if col_idx > 0:
                ticket_col_name = columns_list[col_idx - 1]
                if ticket_col_name not in valid_id_vars and not ticket_col_name.startswith("CW"):
                    bug_id_val = row_series[ticket_col_name]
                    cleaned_bug_id = clean_bug_id(bug_id_val)
                    if cleaned_bug_id:
                        record = base_data.copy()
                        record['TestWeek'] = col_name
                        record['BugID'] = cleaned_bug_id
                        bug_data_records.append(record)

bug_id_df = pd.DataFrame(bug_data_records)
if not bug_id_df.empty:
    bug_id_df = bug_id_df.drop_duplicates(subset=valid_id_vars + ['TestWeek'])

# 3. 提取状态数据并与BugID数据融合
melted_status_df = pd.melt(raw_df,
                           id_vars=valid_id_vars,
                           value_vars=cw_status_cols,
                           var_name='TestWeek',
                           value_name='Status_raw')

# 与BugID数据融合
if not bug_id_df.empty:
    merged_df = pd.merge(melted_status_df, bug_id_df, on=valid_id_vars + ['TestWeek'], how='left')
else:
    merged_df = melted_status_df
    merged_df['BugID'] = None

# 4. 后续处理
def clean_status_value(status_val):
    s = str(status_val).strip().lower()
    if not s or s == 'nan':
        return None
    if s.startswith('pass'): return 'Pass'
    if s.startswith('fail'): return 'Fail'
    if s == 'blocked': return 'Blocked'
    if s == 'no run': return 'No Run'
    return None

merged_df['Status'] = merged_df['Status_raw'].apply(clean_status_value)

# 计算Bug数量和对应的标记大小
def calculate_marker_size_from_bugid(bug_id_cell):
    if pd.isna(bug_id_cell):
        return 8
    num_bugs = len(str(bug_id_cell).split())
    if num_bugs <= 1:
        return 8
    elif num_bugs == 2:
        return 12
    else:
        return 16

def count_actual_bugs(bug_id_cell):
    if pd.isna(bug_id_cell):
        return 0
    return len(str(bug_id_cell).split())

merged_df['MarkerSizeValue'] = merged_df['BugID'].apply(calculate_marker_size_from_bugid)
merged_df['BugCount'] = merged_df['BugID'].apply(count_actual_bugs)

status_dashboard_df = merged_df.dropna(subset=['Test Scope', 'Test Module', 'Status'])

if not status_dashboard_df.empty:
    status_dashboard_df.loc[:, 'TestWeek'] = pd.Categorical(status_dashboard_df['TestWeek'], categories=cw_status_cols, ordered=True)
# --- 数据转换逻辑结束 ---
