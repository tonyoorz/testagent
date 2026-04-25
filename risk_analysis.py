import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import re
import json

from data_processor import load_defect_data, load_test_data

# --- 0. 配置与辅助函数 ---
px.defaults.template = "simple_white"
HIGH_DEFECT_THRESHOLD = 10
MAX_HOVER_ITEMS = 3
START_DATE = datetime(2025, 1, 1)  # 动画起始日期
START_WEEK = 1  # 起始周号

def parse_test_week_to_datetime(week_str):
    if not isinstance(week_str, str) or 'CW' not in week_str:
        return None
    try:
        if '-' in week_str:
            year_str, cw_str = week_str.split('-')
            year = int("20" + year_str)
            week_num_str = cw_str.replace('CW', '')
            week_num = int(week_num_str)
            return datetime.strptime(f'{year}-{week_num}-1', "%G-%V-%u")
        elif week_str.startswith('CW'):
            current_year = datetime.now().year
            week_num_str = week_str.replace('CW', '')
            week_num = int(week_num_str)
            try:
                return datetime.strptime(f'{current_year}-{week_num}-1', "%G-%V-%u")
            except ValueError:
                try:
                    return datetime.strptime(f'{current_year-1}-{week_num}-1', "%G-%V-%u")
                except ValueError:
                    return None
        return None
    except ValueError:
        return None

def calculate_coverage_percentage(aida_weeks):
    """
    简化后的覆盖率计算: 有case的周数 / 总周数
    从第一次有测试的周开始计算到当前周
    """
    if not aida_weeks or len(aida_weeks) == 0:
        return 0.0
    
    # 将日期按周排序
    sorted_weeks = sorted(aida_weeks)
    if not sorted_weeks:
        return 0.0

    # 获取起始日期(第一次有测试的周)和当前日期
    start_date = sorted_weeks[0]
    today = datetime.now().date()
    
    # 计算从起始到现在的总周数
    total_weeks = 0
    current_date = start_date
    while current_date <= today:
        total_weeks += 1
        current_date += timedelta(days=7)
    
    if total_weeks == 0:
        return 0.0
    
    # 有case的周数
    weeks_with_cases = len(sorted_weeks)
    
    # 计算覆盖率百分比
    coverage_percentage = (weeks_with_cases / total_weeks) * 100
    
    return min(100.0, max(0.0, coverage_percentage))  # 确保在0-100之间

def extract_short_name(aida_full_name):
    """提取AIDA的简短英文名称，不包含数字"""
    if not isinstance(aida_full_name, str):
        return "unknown"
    
    # 尝试提取英文字母部分，不包括数字
    match = re.search(r'[a-zA-Z]+', aida_full_name)
    if match:
        short_name = match.group(0)
        return short_name[:10]  # 限制最大长度
    
    return aida_full_name[:10]  # 如果无法提取，返回前10个字符

def count_test_cases(aida, tdf_valid):
    """计算指定AIDA的测试case数量"""
    if 'top_aida' not in tdf_valid.columns or 'id' not in tdf_valid.columns:
        return 0
    
    aida_df = tdf_valid[tdf_valid['top_aida'] == aida]
    if aida_df.empty:
        return 0
    
    return len(aida_df['id'].apply(lambda x: str(x) if isinstance(x, dict) else x).unique())

# --- 1. 加载数据 ---
print("加载缺陷数据...")
ddf = load_defect_data()
print("缺陷数据加载完毕。")

# 为缺陷数据添加时间字段（如果不存在）
if 'created_at' not in ddf.columns:
    print("添加模拟的缺陷创建时间数据用于动画...")
    # 创建从START_DATE到当前的随机日期
    end_date = datetime.now()
    days_range = (end_date - START_DATE).days
    if days_range <= 0:
        # 如果当前日期在START_DATE之前，使用一年的范围
        start_date = end_date - timedelta(days=365)
        days_range = 365
    
    # 为每个缺陷随机分配一个创建日期
    ddf['created_at'] = [START_DATE + timedelta(days=np.random.randint(0, max(1, days_range))) for _ in range(len(ddf))]
    # 确保created_at列是pandas datetime类型
    ddf['created_at'] = pd.to_datetime(ddf['created_at'])
else:
    # 确保created_at列是日期时间类型
    if pd.api.types.is_string_dtype(ddf['created_at']):
        ddf['created_at'] = pd.to_datetime(ddf['created_at'], errors='coerce')

# 添加周信息
ddf['week_number'] = ddf['created_at'].dt.isocalendar().week
ddf['week_display'] = ddf['created_at'].dt.year.astype(str) + "-W" + ddf['week_number'].astype(str).str.zfill(2)

# 获取所有周
all_weeks = sorted(ddf['week_display'].apply(lambda x: str(x) if isinstance(x, dict) else x).unique())
if not all_weeks:
    # 如果没有有效的周数据，创建一些模拟数据
    current_year = datetime.now().year
    all_weeks = [f"{current_year}-W{w:02d}" for w in range(START_WEEK, 53)]

print(f"周数据范围: {all_weeks[0]} 到 {all_weeks[-1]}, 共 {len(all_weeks)} 周")

print("加载测试数据...")
tdf = load_test_data()
print("测试数据加载完毕。")

# 调试：检查测试数据结构
print(f"测试数据形状: {tdf.shape}")
if not tdf.empty:
    print(f"测试数据列: {list(tdf.columns)}")
else:
    print("测试数据为空")

# 为测试数据添加执行时间（如果不存在）
if not tdf.empty and 'executed_at' not in tdf.columns and 'parsed_week_date' not in tdf.columns:
    if 'test_week' in tdf.columns:
        tdf['parsed_week_date'] = tdf['test_week'].apply(parse_test_week_to_datetime)
    else:
        print("警告: 测试数据中没有 'test_week' 列，跳过时间解析")
        tdf['parsed_week_date'] = None
    tdf_valid = tdf.dropna(subset=['parsed_week_date'])
    if not tdf_valid.empty:
        # 使用测试周作为执行时间
        tdf['executed_at'] = tdf['parsed_week_date']

# 预处理测试状态字段
def extract_status_name_simple(status_str):
    """简单版本：从状态字符串中提取name字段的值"""
    if not status_str or not isinstance(status_str, str):
        return status_str
    
    # 尝试正则表达式匹配
    name_match = re.search(r"'name':\s*'([^']*)'", status_str)
    if name_match:
        return name_match.group(1)
    
    # 匹配双引号形式
    name_match = re.search(r'"name":\s*"([^"]*)"', status_str)
    if name_match:
        return name_match.group(1)
    
    # 返回原始值
    return status_str

# 如果status字段存在，预处理它
if 'status' in tdf.columns:
    try:
        tdf['status'] = tdf['status'].apply(extract_status_name_simple)
        print("测试状态字段预处理完成")
    except Exception as e:
        print(f"预处理测试状态字段时出错: {e}")

# --- 2. 数据预处理 ---
# 确保关键列存在
required_cols_ddf = ['top_aida', 'id']
required_cols_tdf = ['top_aida', 'test_week', 'id']

if not all(col in ddf.columns for col in required_cols_ddf):
    print(f"警告: ddf 缺少必要列 {[col for col in required_cols_ddf if col not in ddf.columns]}")
    aida_defect_counts = pd.DataFrame(columns=['top_aida', 'defect_count'])
else:
    aida_defect_counts = ddf.groupby('top_aida')['id'].nunique().reset_index(name='defect_count')

has_test_data = all(col in tdf.columns for col in required_cols_tdf)
tdf_valid = None

if not has_test_data:
    print(f"警告: tdf 缺少必要列 {[col for col in required_cols_tdf if col not in tdf.columns]}")
    aida_test_weeks = pd.DataFrame(columns=['top_aida', 'parsed_week_date'])
    aida_test_cases = pd.DataFrame(columns=['top_aida', 'case_count'])
else:
    # 解析测试周到日期
    tdf['parsed_week_date'] = tdf['test_week'].apply(parse_test_week_to_datetime)
    tdf_valid = tdf.dropna(subset=['parsed_week_date'])
    
    # 获取每个AIDA的测试周日期列表(去重)
    aida_test_weeks = tdf_valid.groupby('top_aida')['parsed_week_date'].apply(
        lambda dates: sorted(set(d.date() for d in dates if d is not None))
    ).reset_index()
    
    # 计算每个AIDA的case数量
    aida_test_cases = tdf_valid.groupby('top_aida')['id'].nunique().reset_index(name='case_count')

# --- 3. 计算AIDA的覆盖率和风险评估 ---
all_aidas = set()
if 'top_aida' in ddf.columns:
    all_aidas.update(ddf['top_aida'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
if 'top_aida' in tdf.columns:
    all_aidas.update(tdf['top_aida'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
all_aidas = [aida for aida in all_aidas if pd.notna(aida) and aida != '']

aida_analysis = pd.DataFrame({'top_aida': list(all_aidas)})

# 合并缺陷数据
if not aida_defect_counts.empty:
    aida_analysis = pd.merge(aida_analysis, aida_defect_counts, on='top_aida', how='left')
    aida_analysis['defect_count'] = aida_analysis['defect_count'].fillna(0).astype(int)
else:
    aida_analysis['defect_count'] = 0

# 计算覆盖率百分比和测试case数量
if has_test_data and not aida_test_weeks.empty:
    # 计算每个AIDA的覆盖率
    coverage_percentages = {}
    for _, row in aida_test_weeks.iterrows():
        aida = row['top_aida']
        weeks = row['parsed_week_date']
        coverage_percentages[aida] = calculate_coverage_percentage(weeks)
    
    # 将覆盖率加入分析数据框
    coverage_df = pd.DataFrame(list(coverage_percentages.items()), columns=['top_aida', 'coverage_percentage'])
    aida_analysis = pd.merge(aida_analysis, coverage_df, on='top_aida', how='left')
    
    # 合并测试case数量
    if not aida_test_cases.empty:
        aida_analysis = pd.merge(aida_analysis, aida_test_cases, on='top_aida', how='left')
        aida_analysis['case_count'] = aida_analysis['case_count'].fillna(0).astype(int)
    else:
        aida_analysis['case_count'] = 0
else:
    aida_analysis['coverage_percentage'] = 0.0
    aida_analysis['case_count'] = 0

# 填充缺失的覆盖率
aida_analysis['coverage_percentage'] = aida_analysis['coverage_percentage'].fillna(0.0)

# 添加简化的AIDA名称
aida_analysis['short_name'] = aida_analysis['top_aida'].apply(extract_short_name)

# --- 计算X轴的调整值（使相同覆盖率的点根据case数量排布） ---
def calculate_x_position(group):
    # 按照case_count排序
    sorted_group = group.sort_values('case_count')
    
    # 如果只有一个点，不调整
    if len(sorted_group) <= 1:
        return sorted_group.assign(x_position=sorted_group['coverage_percentage'])
    
    # 根据case数量计算偏移量
    range_width = 5.0  # 偏移范围宽度（百分比单位）
    # 确保偏移不会导致0%或100%的气泡被切割
    if group['coverage_percentage'].iloc[0] < range_width:
        range_width = group['coverage_percentage'].iloc[0] / 2
    elif group['coverage_percentage'].iloc[0] > (100 - range_width):
        range_width = (100 - group['coverage_percentage'].iloc[0]) / 2

    # 创建偏移序列
    offsets = np.linspace(-range_width/2, range_width/2, len(sorted_group))
    sorted_group = sorted_group.copy()
    sorted_group['x_position'] = sorted_group['coverage_percentage'] + offsets
    
    return sorted_group

# 按覆盖率分组，计算X轴位置调整
if not aida_analysis.empty and 'coverage_percentage' in aida_analysis.columns:
    aida_analysis = aida_analysis.groupby('coverage_percentage').apply(calculate_x_position).reset_index(drop=True)
else:
    # 如果数据为空或缺少必要列，添加默认的 x_position 列
    aida_analysis['x_position'] = aida_analysis.get('coverage_percentage', 0)

# 风险评估
def assess_risk(defect_count, coverage_percentage, threshold=HIGH_DEFECT_THRESHOLD, coverage_threshold=50):
    if defect_count > threshold:
        if coverage_percentage < coverage_threshold:
            return "高风险"
        else:
            return "中风险(高缺陷)"
    else:
        if coverage_percentage < coverage_threshold:
            return "中风险(低覆盖)"
        else:
            return "低风险"

aida_analysis['risk_level'] = aida_analysis.apply(
    lambda row: assess_risk(row['defect_count'], row['coverage_percentage']), axis=1
)

# 设置风险等级颜色
risk_colors = {
    "高风险": "darkred",
    "中风险(高缺陷)": "orange",
    "中风险(低覆盖)": "gold", 
    "低风险": "green"
}

# 风险等级排序
risk_level_order = ["高风险", "中风险(高缺陷)", "中风险(低覆盖)", "低风险"]
aida_analysis['risk_level_cat'] = pd.Categorical(
    aida_analysis['risk_level'], 
    categories=risk_level_order, 
    ordered=True
)

# 排序数据(按风险等级和缺陷数量)
aida_analysis = aida_analysis.sort_values(
    by=['risk_level_cat', 'defect_count', 'coverage_percentage'], 
    ascending=[True, False, True]
)

print("数据分析完成，预览结果:")
print(aida_analysis[['top_aida', 'short_name', 'defect_count', 'coverage_percentage', 'case_count', 'x_position', 'risk_level']].head())

# --- 提取状态名称的工具函数 ---
def extract_status_name(status_str):
    """从状态字符串中提取name字段的值"""
    # 如果输入是None或空字符串，直接返回
    if not status_str:
        return ""

    try:
        # 确保是字符串类型
        if not isinstance(status_str, str):
            status_str = str(status_str)

        # 直接尝试使用正则表达式匹配最常见的情况 - 图片中的情况
        name_match = re.search(r"'name':\s*'([^']*)'", status_str)
        if name_match:
            result = name_match.group(1)
            return result

        # 匹配双引号形式
        name_match = re.search(r'"name":\s*"([^"]*)"', status_str)
        if name_match:
            result = name_match.group(1)
            return result

        # 标准JSON格式尝试
        if status_str.startswith('{') and status_str.endswith('}'):
            # 修复单引号JSON
            json_str = status_str.replace("'", '"')
            try:
                status_obj = json.loads(json_str)
                if 'name' in status_obj:
                    result = status_obj['name']
                    return result
            except:
                pass

        # 使用ast.literal_eval尝试解析Python字典字符串
        try:
            import ast
            # 确保是有效的字典形式
            if "{" in status_str and "}" in status_str:
                status_dict = ast.literal_eval(status_str)
                if isinstance(status_dict, dict) and 'name' in status_dict:
                    result = status_dict['name']
                    return result
        except:
            pass

        # 特殊情况：如果字符串包含Passed, Failed等关键字
        status_keywords = ['Passed', 'Failed', 'Blocked', 'Planned', 'InProgress']
        for keyword in status_keywords:
            if keyword in status_str:
                return keyword

        # 所有方法都失败，返回原始字符串
        return status_str

    except Exception as e:
        print(f"提取状态名称时出错: {e}")
        return status_str
