import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import plotly.figure_factory as ff

# 导入数据处理模块
from data_processor import load_defect_data, apply_filters, apply_chart_style, SEVERITY_COLORS, CHART_HEIGHT, enrich_ddf_with_master_info

# 加载数据
df = load_defect_data()
# 丰富主票据信息
df = enrich_ddf_with_master_info(df)

# Long Runner 定义常量
LONG_RUNNER_WEEKS_THRESHOLD = 3  # 3周为长跑票据阈值

# 解决状态的定义 (根据您的描述)
RESOLVED_PHASES = {'06-concluded', '09-concluded without action', '10-closed'}  # 解决了的状态
TESTING_PHASES = {'00-draft', '01-new', '02-in pre-analysis', '08-in verification', '09-concluded without action', '06-concluded', '10-closed'}  # 测试处理周期内
DEVELOPMENT_PHASES = {
    '03-in analysis', '04-in progress', '05-in testing',
    '07-in review', '07-in pre-verification'
}  # 开发处理周期内


def _normalize_phase_text(phase_value):
    s = str(phase_value or '').strip().lower()
    if '_' in s:
        base, tail = s.rsplit('_', 1)
        if tail in {'critical', 'high', 'medium', 'low', 's1', 's2', 's3', 's4'}:
            s = base
    return s


def _is_resolved_phase(phase_value):
    s = _normalize_phase_text(phase_value)
    if not s:
        return False
    return (s in RESOLVED_PHASES) or ('conclud' in s) or ('resolv' in s) or ('clos' in s) or ('fix' in s) or ('结案' in s)

def calculate_ticket_age_days(creation_time):
    """计算票据从创建到现在的天数"""
    if pd.isna(creation_time):
        return 0
    try:
        if isinstance(creation_time, str):
            creation_time = pd.to_datetime(creation_time)

        current_time = datetime.now()
        age_days = (current_time - creation_time).days
        return max(0, age_days)
    except:
        return 0

def is_long_runner(row):
    """判断是否为长跑票据"""
    # 如果状态是已解决的，则不是长跑票据
    if _is_resolved_phase(row.get('status_phase')):
        return False

    # 计算天数，超过3周(21天)认为是长跑票据
    age_days = calculate_ticket_age_days(row['creation_time'])
    return age_days >= (LONG_RUNNER_WEEKS_THRESHOLD * 7)

def get_long_runner_severity(row):
    """根据天数和phase判断长跑票据的严重程度"""
    age_days = calculate_ticket_age_days(row['creation_time'])
    weeks = age_days / 7

    if weeks < 3:
        return "正常"
    elif weeks < 6:
        return "关注"
    elif weeks < 12:
        return "警告"
    else:
        return "严重"

def get_phase_category(phase):
    """获取阶段分类"""
    phase_norm = _normalize_phase_text(phase)
    if phase_norm in TESTING_PHASES:
        return "测试处理周期"
    elif phase_norm in DEVELOPMENT_PHASES:
        return "开发处理周期"
    else:
        return "其他"

# 处理数据，添加长跑相关字段
if not df.empty and len(df.columns) > 0:
    df['age_days'] = df.apply(lambda row: calculate_ticket_age_days(row['creation_time']), axis=1)
    df['age_weeks'] = df['age_days'] / 7
    df['is_long_runner'] = df.apply(is_long_runner, axis=1)
    df['long_runner_severity'] = df.apply(get_long_runner_severity, axis=1)
    df['phase_category'] = df['status_phase'].apply(get_phase_category)

    # 获取长跑票据
    long_runner_df = df[df['is_long_runner'] == True].copy()

    # 计算每个票据变成长跑的那一周
    long_runner_df['long_runner_start_time'] = long_runner_df['creation_time'] + pd.to_timedelta(LONG_RUNNER_WEEKS_THRESHOLD * 7, unit='D')
    long_runner_df['long_runner_start_week'] = 'CW' + long_runner_df['long_runner_start_time'].dt.isocalendar().week.astype(str).str.zfill(2)
    long_runner_df['age_at_long_runner_start'] = LONG_RUNNER_WEEKS_THRESHOLD * 7
else:
    long_runner_df = pd.DataFrame()

# 通用筛选函数
def filter_long_runner_data(projects=None, aidas=None, severities=None, phase_categories=None):
    """筛选长跑票据数据"""
    filtered = long_runner_df.copy()

    if projects and 'all' not in projects:
        filtered = filtered[filtered['ecu'].isin(projects)]
    if aidas and 'all' not in aidas:
        filtered = filtered[filtered['aida_english'].isin(aidas)]
    if severities and 'all' not in severities:
        filtered = filtered[filtered['long_runner_severity'].isin(severities)]
    if phase_categories and 'all' not in phase_categories:
        filtered = filtered[filtered['phase_category'].isin(phase_categories)]

    return filtered
