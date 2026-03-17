import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import dash_bootstrap_components as dbc
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

# --- 4. Dash应用 ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "AIDA 覆盖率-缺陷分析"

app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H1("AIDA 覆盖率与缺陷数量分析", className="text-center my-4"))),
    
    dbc.Row([
        dbc.Col([
            dbc.Label("高缺陷阈值:", html_for='defect-threshold-input'),
            dcc.Input(
                id='defect-threshold-input', 
                type='number',
                value=HIGH_DEFECT_THRESHOLD,
                min=0,
                step=1,
                className="mb-2"
            )
        ], width=3),
        dbc.Col([
            dbc.Label("覆盖率阈值:", html_for='coverage-threshold-input'),
            dcc.Input(
                id='coverage-threshold-input', 
                type='number',
                value=50,
                min=0,
                max=100,
                step=1,
                className="mb-2"
            )
        ], width=3),
        dbc.Col([
            dbc.Label("启用按周动画:", html_for='animation-toggle'),
            dbc.Switch(
                id='animation-toggle',
                value=False,
                className="mb-2"
            )
        ], width=2),
        dbc.Col([
            html.Div(id='animation-controls', style={'display': 'none'}, children=[
                dbc.Label("周:", html_for='week-slider', className="mt-2"),
                dcc.Slider(
                    id='week-slider',
                    min=0,
                    max=len(all_weeks)-1 if all_weeks else 0,
                    value=0,
                    marks={i: w for i, w in enumerate(all_weeks)} if len(all_weeks) <= 20 
                          else {i: w for i, w in enumerate(all_weeks) if i % 4 == 0 or i == len(all_weeks)-1},
                    className="mb-2"
                ),
                html.Button('播放/暂停', id='play-pause-button', className="mt-2 btn btn-primary"),
                html.Div(className="d-flex align-items-center ml-3", children=[
                    dbc.Label("速度:", html_for='animation-speed', className="mt-2 mr-2"),
                    dcc.Slider(
                        id='animation-speed',
                        min=0.5,
                        max=3,
                        step=0.5,
                        value=1,
                        marks={i: f'{i}x' for i in [0.5, 1, 1.5, 2, 2.5, 3]},
                        className="mb-2 animation-speed-slider"
                    )
                ])
            ])
        ], width=7)
    ]),
    
    dbc.Row([
        dbc.Col(
            dcc.Graph(id='coverage-defect-scatter-plot', clear_on_unhover=True),
            width=12
        )
    ]),
    
    # 隐藏的动画帧存储
    dcc.Store(id='animation-frames', data=[]),
    dcc.Store(id='current-week-index', data=0),
    dcc.Store(id='selected-aida-store', data=None),
    dcc.Interval(id='animation-interval', interval=1000, n_intervals=0, disabled=True),
    
    dbc.Row([
        dbc.Col(html.H4(id='detail-title', children="数据详情:", className="mt-4"), width=12),
        dbc.Col(
            dbc.Tabs([
                dbc.Tab(
                    dbc.Spinner(html.Div(id='defect-detail-table')), 
                    label="缺陷详情",
                    tab_id="defect-tab"
                ),
                dbc.Tab(
                    dbc.Spinner(html.Div(id='test-detail-table')), 
                    label="测试用例详情",
                    tab_id="test-tab"
                )
            ], id="detail-tabs", active_tab="defect-tab"),
            width=12
        )
    ]),
], fluid=True)

# 定义应用程序中使用的CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            .animation-speed-container {
                width: 150px;
                margin-left: 15px;
            }
            .animation-speed-slider {
                width: 150px;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# 控制动画控件显示/隐藏
@app.callback(
    Output('animation-controls', 'style'),
    [Input('animation-toggle', 'value')]
)
def toggle_animation_controls(enabled):
    if enabled:
        return {'display': 'block'}
    return {'display': 'none'}

# 生成动画帧
@app.callback(
    Output('animation-frames', 'data'),
    [Input('animation-toggle', 'value')],
    [State('defect-threshold-input', 'value'),
     State('coverage-threshold-input', 'value')]
)
def generate_animation_frames(enabled, threshold, coverage_threshold):
    if not enabled:
        return []
    
    if threshold is None or threshold < 0:
        threshold = HIGH_DEFECT_THRESHOLD
        
    if coverage_threshold is None or coverage_threshold < 0 or coverage_threshold > 100:
        coverage_threshold = 50
    
    frames = []
    
    # 对每周数据进行处理
    for week_display in all_weeks:
        # 过滤到当前周之前（含当前周）的缺陷数据
        week_parts = week_display.split("-W")
        if len(week_parts) == 2:
            year = int(week_parts[0])
            week_num = int(week_parts[1])
            
            # 筛选到当前周为止的缺陷数据
            ddf_until_week = ddf[(ddf['created_at'].dt.year <= year) & 
                                (ddf['created_at'].dt.isocalendar().week <= week_num)]
            
            # 计算各AIDA的缺陷数量
            if not ddf_until_week.empty:
                defect_counts_until_week = ddf_until_week.groupby('top_aida')['id'].nunique().reset_index(name='defect_count')
                
                # 创建当前周的AIDA分析数据
                frame_data = aida_analysis.copy()
                
                # 更新缺陷数量
                frame_data = pd.merge(
                    frame_data.drop(columns=['defect_count'] if 'defect_count' in frame_data.columns else []), 
                    defect_counts_until_week, 
                    on='top_aida', 
                    how='left'
                )
                frame_data['defect_count'] = frame_data['defect_count'].fillna(0).astype(int)
                
                # 重新计算风险等级
                frame_data['risk_level'] = frame_data.apply(
                    lambda row: assess_risk(row['defect_count'], row['coverage_percentage'], threshold, coverage_threshold), 
                    axis=1
                )
                
                # 创建自定义hover文本
                frame_data['hover_text'] = frame_data.apply(
                    lambda row: f"<b>{row['top_aida']}</b><br>" + 
                              f"风险等级: {row['risk_level']}<br>" +
                              f"缺陷数量: {row['defect_count']}<br>" +
                              f"覆盖率(%): {row['coverage_percentage']:.1f}%<br>" +
                              f"测试case数量: {row['case_count']}",
                    axis=1
                )
                
                # 计算映射后的Y值
                def map_y_value(y):
                    if y < 0:
                        return y  # 负值保持不变
                    elif y <= 10:
                        # 0-10区间拉大到0-35范围，给予更多空间
                        return y * 3.5
                    elif y <= 20:
                        # 10-20区间映射到35-45范围
                        return 35 + (y - 10)
                    elif y <= 30:
                        # 20-30区间映射到45-55范围
                        return 45 + (y - 20)
                    elif y <= 40:
                        # 30-40区间映射到55-60范围
                        return 55 + (y - 30) * 0.5
                    elif y <= 50:
                        # 40-50区间映射到60-65范围
                        return 60 + (y - 40) * 0.5
                    elif y <= 100:
                        # 50-100区间映射到65-70范围 (同样宽度)
                        return 65 + (y - 50) * 0.1
                    else:
                        # 100以上映射到70-75范围
                        return 70 + (y - 100) * 0.05
                    
                frame_data['y_display'] = frame_data['defect_count'].apply(map_y_value)
                
                # 添加到帧列表
                frames.append({
                    'data': frame_data.to_dict('records'),
                    'week': week_display,
                    'index': len(frames)
                })
    
    return frames

# 修改动画间隔回调，处理未选中AIDA的情况
@app.callback(
    [Output('animation-interval', 'disabled'),
     Output('animation-interval', 'interval')],
    [Input('play-pause-button', 'n_clicks'),
     Input('animation-speed', 'value'),
     Input('animation-toggle', 'value')],
    [State('animation-interval', 'disabled'),
     State('selected-aida-store', 'data')]
)
def toggle_animation(n_clicks, speed, enabled, current_disabled, selected_aida):
    # 如果动画未启用，则禁用间隔
    if not enabled:
        return True, 1000
    
    # 计算速度对应的间隔时间
    interval = int(1000 / speed) if speed > 0 else 1000
    
    # 如果点击了播放/暂停按钮，则切换状态
    if n_clicks is not None and n_clicks > 0:
        return not current_disabled, interval
    
    # 否则仅更新间隔
    return current_disabled, interval

# 更新当前周索引
@app.callback(
    Output('current-week-index', 'data'),
    [Input('animation-interval', 'n_intervals'),
     Input('week-slider', 'value')],
    [State('animation-frames', 'data'),
     State('current-week-index', 'data'),
     State('animation-interval', 'disabled')]
)
def update_week_index(n_intervals, slider_value, frames, current_index, interval_disabled):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ''
    
    if not frames:
        return 0
    
    max_index = len(frames) - 1
    
    # 如果是通过滑块更新
    if trigger_id == 'week-slider':
        return slider_value
    
    # 如果是通过间隔更新且间隔启用
    if trigger_id == 'animation-interval' and not interval_disabled:
        return (current_index + 1) % (max_index + 1)  # 循环播放
    
    return current_index

# 从动画间隔更新滑块值
@app.callback(
    Output('week-slider', 'value', allow_duplicate=True),
    [Input('current-week-index', 'data')],
    prevent_initial_call=True
)
def sync_slider_with_week(week_index):
    return week_index

# 捕获选中的AIDA
@app.callback(
    Output('selected-aida-store', 'data'),
    [Input('coverage-defect-scatter-plot', 'clickData')]
)
def store_selected_aida(click_data):
    if not click_data:
        return None
    
    try:
        # 打印点击数据，帮助调试
        print(f"点击数据: {click_data}")
        
        # 直接从custom_data的第一个元素获取AIDA名称
        aida_name = click_data['points'][0]['customdata'][0]
        print(f"获取的AIDA名称: {aida_name}")
        return {'aida': aida_name}
    except Exception as e:
        print(f"提取AIDA名称时出错: {e}")
        return None

# 更新详情标题
@app.callback(
    Output('detail-title', 'children'),
    [Input('selected-aida-store', 'data'),
     Input('current-week-index', 'data'),
     Input('animation-toggle', 'value')],
    [State('animation-frames', 'data')]
)
def update_detail_title(selected_aida, week_index, animation_enabled, animation_frames):
    if not selected_aida or not selected_aida.get('aida'):
        return "数据详情:"
    
    week_info = ""
    if animation_enabled and animation_frames and 0 <= week_index < len(animation_frames):
        week_info = f" (截至 {animation_frames[week_index].get('week', '')})"
    
    return f"{selected_aida.get('aida')} 详情{week_info}:"

# 添加提取状态名称的全局函数
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

# 更新缺陷详情表
@app.callback(
    Output('defect-detail-table', 'children'),
    [Input('selected-aida-store', 'data'),
     Input('current-week-index', 'data'),
     Input('animation-toggle', 'value')],
    [State('animation-frames', 'data')]
)
def update_defect_detail_table(selected_aida, week_index, animation_enabled, animation_frames):
    # 如果没有选中AIDA，但动画正在播放，显示适当的提示
    if (not selected_aida or not selected_aida.get('aida')) and animation_enabled:
        if animation_frames and 0 <= week_index < len(animation_frames):
            current_week = animation_frames[week_index].get('week', '')
            return html.Div([
                html.P(f"动画播放中: 显示截至 {current_week} 的数据", className="text-info"),
                html.P("请点击气泡查看特定AIDA的缺陷详情", className="font-italic")
            ])
        return html.Div("动画播放中，请点击气泡查看AIDA缺陷详情")
    
    # 如果没有选中AIDA，显示基本提示
    if not selected_aida or not selected_aida.get('aida'):
        return html.Div("点击气泡查看AIDA详细缺陷信息")
    
    aida_name = selected_aida.get('aida')
    
    # 如果启用动画，使用当前周的数据
    if animation_enabled and animation_frames and 0 <= week_index < len(animation_frames):
        week_display = animation_frames[week_index].get('week')
        if week_display:
            week_parts = week_display.split("-W")
            if len(week_parts) == 2:
                try:
                    year = int(week_parts[0])
                    week_num = int(week_parts[1])
                    # 筛选到当前周为止的缺陷数据
                    filtered_ddf = ddf[(ddf['created_at'].dt.year <= year) & 
                                      (ddf['created_at'].dt.isocalendar().week <= week_num) &
                                      (ddf['top_aida'] == aida_name)]
                except Exception as e:
                    print(f"处理周日期时出错: {e}")
                    filtered_ddf = ddf[ddf['top_aida'] == aida_name]
            else:
                filtered_ddf = ddf[ddf['top_aida'] == aida_name]
        else:
            filtered_ddf = ddf[ddf['top_aida'] == aida_name]
    else:
        # 不使用动画或动画数据不可用，显示所有数据
        filtered_ddf = ddf[ddf['top_aida'] == aida_name]
    
    if filtered_ddf.empty:
        # 显示更友好的空数据消息
        if animation_enabled and animation_frames and 0 <= week_index < len(animation_frames):
            current_week = animation_frames[week_index].get('week', '')
            return html.Div([
                html.P(f"截至 {current_week} 没有找到 {aida_name} 的缺陷数据", className="text-warning"),
                html.P("可能在之后的周中会有缺陷数据", className="font-italic small")
            ])
        return html.Div(f"没有找到 {aida_name} 的缺陷数据")
    
    # 选择要显示的列（如果存在）
    display_columns = ['id', 'name', 'tester', 'matrix', 'status_phase', 'severity', 'priority', 'created_at']
    existing_columns = [col for col in display_columns if col in filtered_ddf.columns]
    
    if not existing_columns:
        return html.Div(f"缺少必要的缺陷详情列")
    
    # 准备数据，确保时间列格式化正确
    table_data = filtered_ddf[existing_columns].copy()
    if 'created_at' in table_data.columns:
        table_data['created_at'] = table_data['created_at'].dt.strftime('%Y-%m-%d')
    
    # 如果status_phase列存在，可以考虑同样处理JSON数据
    if 'status_phase' in table_data.columns and table_data['status_phase'].astype(str).str.contains('name').any():
        try:
            table_data['status_phase'] = table_data['status_phase'].apply(extract_status_name)
            print("成功处理缺陷状态字段")
        except Exception as e:
            print(f"处理缺陷状态字段时出错: {e}")
    
    # 将所有列转换为字符串类型，防止复杂对象渲染错误
    for col in table_data.columns:
        table_data[col] = table_data[col].astype(str)
    
    # 打印表格数据类型信息用于调试
    print(f"缺陷表格数据类型: {table_data.dtypes}")
    
    # 中文列名映射
    column_name_map = {
        'id': '缺陷ID',
        'name': '缺陷名称',
        'tester': '测试人员',
        'matrix': '复线率',
        'status_phase': '状态',
        'severity': '严重度',
        'priority': '优先级',
        'created_at': '创建时间'
    }
    
    # 重命名表格列
    renamed_columns = {col: column_name_map.get(col, col) for col in table_data.columns}
    table_data = table_data.rename(columns=renamed_columns)
    
    try:
        # 创建表格
        table = dbc.Table.from_dataframe(
            table_data,
            striped=True,
            bordered=True,
            hover=True,
            responsive=True,
            className="mt-3"
        )
        return table
    except Exception as e:
        print(f"缺陷表格创建错误: {e}")
        # 返回错误信息
        return html.Div(f"表格渲染错误: {str(e)}")

# 更新测试用例详情表
@app.callback(
    Output('test-detail-table', 'children'),
    [Input('selected-aida-store', 'data'),
     Input('current-week-index', 'data'),
     Input('animation-toggle', 'value')],
    [State('animation-frames', 'data')]
)
def update_test_detail_table(selected_aida, week_index, animation_enabled, animation_frames):
    # 如果没有选中AIDA，但动画正在播放，显示适当的提示
    if (not selected_aida or not selected_aida.get('aida')) and animation_enabled:
        if animation_frames and 0 <= week_index < len(animation_frames):
            current_week = animation_frames[week_index].get('week', '')
            return html.Div([
                html.P(f"动画播放中: 显示截至 {current_week} 的数据", className="text-info"),
                html.P("请点击气泡查看特定AIDA的测试用例详情", className="font-italic")
            ])
        return html.Div("动画播放中，请点击气泡查看AIDA测试用例详情")
    
    # 如果没有选中AIDA，显示基本提示
    if not selected_aida or not selected_aida.get('aida'):
        return html.Div("点击气泡查看AIDA测试用例详情")
    
    aida_name = selected_aida.get('aida')
    
    # 测试数据筛选条件（限制为选中的AIDA）
    base_filter = tdf['top_aida'] == aida_name
    
    # 如果启用动画，使用当前周的数据
    if animation_enabled and animation_frames and 0 <= week_index < len(animation_frames):
        week_display = animation_frames[week_index].get('week')
        if week_display and 'parsed_week_date' in tdf.columns:
            week_parts = week_display.split("-W")
            if len(week_parts) == 2:
                year = int(week_parts[0])
                week_num = int(week_parts[1])
                # 计算当前周的结束日期
                try:
                    current_week_end = datetime.strptime(f'{year}-{week_num}-7', "%Y-%W-%w").date()
                    # 筛选到当前周为止的测试数据
                    time_filter = tdf['parsed_week_date'].dt.date <= current_week_end
                    filtered_tdf = tdf[base_filter & time_filter]
                except Exception as e:
                    print(f"处理周日期时出错: {e}")
                    filtered_tdf = tdf[base_filter]
            else:
                filtered_tdf = tdf[base_filter]
        else:
            filtered_tdf = tdf[base_filter]
    else:
        # 不使用动画或动画数据不可用，显示所有数据
        filtered_tdf = tdf[base_filter]
    
    if filtered_tdf.empty:
        # 显示更友好的空数据消息
        if animation_enabled and animation_frames and 0 <= week_index < len(animation_frames):
            current_week = animation_frames[week_index].get('week', '')
            return html.Div([
                html.P(f"截至 {current_week} 没有找到 {aida_name} 的测试用例数据", className="text-warning"),
                html.P("可能在之后的周中会有测试数据", className="font-italic small")
            ])
        return html.Div(f"没有找到 {aida_name} 的测试用例数据")
    
    # 选择要显示的列（如果存在）
    display_columns = ['id', 'name', 'tester', 'status', 'test_week', 'blocking_reason']
    existing_columns = [col for col in display_columns if col in filtered_tdf.columns]
    
    if not existing_columns:
        return html.Div(f"缺少必要的测试用例详情列")
    
    # 准备数据表格
    table_data = filtered_tdf[existing_columns].copy()
    
    # 如果status列存在，处理JSON数据提取name值
    if 'status' in table_data.columns:
        try:
            # 尝试从JSON字符串中提取name字段
            table_data['status'] = table_data['status'].apply(extract_status_name)
            print("成功处理测试状态字段")
        except Exception as e:
            print(f"处理测试状态字段时出错: {e}")
    
    # 将所有列转换为字符串类型，防止复杂对象渲染错误
    for col in table_data.columns:
        table_data[col] = table_data[col].astype(str)
    
    # 打印表格数据类型信息用于调试
    print(f"表格数据类型: {table_data.dtypes}")
    
    # 中文列名映射
    column_name_map = {
        'id': '测试执行ID',
        'name': '测试用例名称',
        'tester': '测试人员',
        'status': '执行状态',
        'test_week': '测试周',
        'blocking_reason': '失败原因'
    }
    
    # 重命名表格列
    renamed_columns = {col: column_name_map.get(col, col) for col in table_data.columns}
    table_data = table_data.rename(columns=renamed_columns)
    
    try:
        # 创建表格
        table = dbc.Table.from_dataframe(
            table_data,
            striped=True,
            bordered=True,
            hover=True,
            responsive=True,
            className="mt-3"
        )
        return table
    except Exception as e:
        print(f"表格创建错误: {e}")
        # 返回错误信息
        return html.Div(f"表格渲染错误: {str(e)}")

@app.callback(
    Output('coverage-defect-scatter-plot', 'figure'),
    [Input('defect-threshold-input', 'value'),
     Input('coverage-threshold-input', 'value'),  # 添加覆盖率阈值输入
     Input('current-week-index', 'data'),
     Input('animation-toggle', 'value')],
    [State('animation-frames', 'data')]
)
def update_coverage_defect_dashboard(threshold, coverage_threshold, week_index, animation_enabled, animation_frames):
    # 使用当前阈值更新风险评估
    if threshold is None or threshold < 0:
        threshold = HIGH_DEFECT_THRESHOLD
    
    # 设置覆盖率阈值默认值
    if coverage_threshold is None or coverage_threshold < 0 or coverage_threshold > 100:
        coverage_threshold = 50
    
    # 如果启用了动画并且有动画帧，则使用对应的帧数据
    title_suffix = ""
    
    try:
        # 打印调试信息
        print(f"动画状态: 启用={animation_enabled}, 周索引={week_index}, 帧数={len(animation_frames) if animation_frames else 0}")
        
        if animation_enabled and animation_frames and week_index is not None:
            if isinstance(animation_frames, list) and 0 <= week_index < len(animation_frames):
                frame_data = animation_frames[week_index]
                
                if frame_data and 'data' in frame_data and frame_data['data']:
                    # 从帧数据创建DataFrame
                    try:
                        current_data = pd.DataFrame(frame_data['data'])
                        if 'week' in frame_data:
                            title_suffix = f" - 周: {frame_data['week']}"
                    except Exception as e:
                        print(f"创建DataFrame时出错: {e}")
                        current_data = aida_analysis.copy()
                else:
                    print("帧数据不完整，使用基本数据")
                    current_data = aida_analysis.copy()
            else:
                print(f"周索引无效: {week_index}")
                current_data = aida_analysis.copy()
        else:
            print("未启用动画或无帧数据")
            current_data = aida_analysis.copy()
    except Exception as e:
        print(f"处理动画帧数据时出错: {e}")
        current_data = aida_analysis.copy()
    
    # 重新计算风险等级（如果没有使用动画帧或需要更新）
    if not animation_enabled:
        try:
            current_data['risk_level'] = current_data.apply(
                lambda row: assess_risk(row['defect_count'], row['coverage_percentage'], threshold, coverage_threshold), 
                axis=1
            )
        except Exception as e:
            print(f"计算风险等级时出错: {e}")
    
    # 更新风险等级分类
    try:
        current_data['risk_level_cat'] = pd.Categorical(
            current_data['risk_level'], 
            categories=risk_level_order, 
            ordered=True
        )
    except Exception as e:
        print(f"创建风险等级分类时出错: {e}")
    
    # 创建自定义hover文本（如果动画帧中没有）
    if 'hover_text' not in current_data.columns:
        try:
            current_data['hover_text'] = current_data.apply(
                lambda row: f"<b>{row['top_aida']}</b><br>" + 
                        f"风险等级: {row['risk_level']}<br>" +
                        f"缺陷数量: {row['defect_count']}<br>" +
                        f"覆盖率(%): {row['coverage_percentage']:.1f}%<br>" +
                        f"测试case数量: {row['case_count']}",
                axis=1
            )
        except Exception as e:
            print(f"创建悬停文本时出错: {e}")
            # 创建一个简单的悬停文本作为后备
            if 'top_aida' in current_data.columns:
                current_data['hover_text'] = current_data['top_aida']
    
    # 创建不均匀增长但物理间隔均匀的Y轴刻度
    # 优化Y轴刻度点，调整分布
    y_ticks = list(range(0, 11, 2)) + [15, 20, 25, 30] + [40, 50, 100, 200, 300]
    y_ticktext = [str(y) for y in y_ticks]
    
    # 创建Y轴刻度的映射函数
    def map_y_value(y):
        if y < 0:
            return y  # 负值保持不变
        elif y <= 10:
            # 0-10区间拉大到0-35范围，给予更多空间
            return y * 3.5
        elif y <= 20:
            # 10-20区间映射到35-45范围
            return 35 + (y - 10)
        elif y <= 30:
            # 20-30区间映射到45-55范围
            return 45 + (y - 20)
        elif y <= 40:
            # 30-40区间映射到55-60范围
            return 55 + (y - 30) * 0.5
        elif y <= 50:
            # 40-50区间映射到60-65范围
            return 60 + (y - 40) * 0.5
        elif y <= 100:
            # 50-100区间映射到65-70范围 (同样宽度)
            return 65 + (y - 50) * 0.1
        else:
            # 100以上映射到70-75范围
            return 70 + (y - 100) * 0.05
    
    # 创建映射后的Y值列
    try:
        current_data['y_display'] = current_data['defect_count'].apply(map_y_value)
    except Exception as e:
        print(f"创建Y值映射时出错: {e}")
        # 如果无法映射，创建默认Y值
        if 'defect_count' in current_data.columns:
            current_data['y_display'] = current_data['defect_count']
        else:
            # 最后的备选方案
            current_data['y_display'] = 0
    
    # 确保所有必要的列都存在
    required_columns = ['top_aida', 'short_name', 'risk_level', 'x_position', 'y_display']
    for col in required_columns:
        if col not in current_data.columns:
            print(f"警告: 缺少必要列 {col}，创建默认值")
            if col == 'top_aida':
                current_data[col] = ['AIDA_' + str(i) for i in range(len(current_data))]
            elif col == 'short_name':
                current_data[col] = ['A' + str(i) for i in range(len(current_data))]
            elif col == 'risk_level':
                current_data[col] = '未知'
            elif col == 'x_position':
                current_data[col] = 50
            elif col == 'y_display':
                current_data[col] = 0
    
    # 使用映射后的Y值创建图表
    try:
        fig = px.scatter(
            current_data,
            x='x_position',  # 使用调整后的X轴位置
            y='y_display',   # 使用映射后的Y值
            color='risk_level',
            hover_name='top_aida',
            text='short_name',  # 显示简短名称
            custom_data=['top_aida', 'hover_text'],  # 添加AIDA名称到custom_data
            hover_data=None,  # 禁用默认hover数据
            color_discrete_map=risk_colors,
            category_orders={'risk_level': risk_level_order},
            labels={
                'defect_count': '缺陷数量',
                'coverage_percentage': '覆盖率(%)',
                'case_count': '测试case数量',
                'risk_level': '风险等级',
                'top_aida': 'AIDA',
                'short_name': 'AIDA简称',
                'y_display': '缺陷数量'  # Y轴标签仍然显示"缺陷数量"
            }
        )
        
        # 设置所有气泡为统一大小并自定义hover模板
        fig.update_traces(
            marker=dict(size=15),  # 设置统一的气泡大小
            textposition='top center',  # 将文本位置改为气泡上方
            textfont=dict(
                family="Arial, sans-serif",
                size=10,
                color="black"
            ),
            hovertemplate='%{customdata[1]}<extra></extra>'  # 使用hover_text (customdata[1])
        )
        
        # 添加辅助线 - 需要将原始值映射到显示值
        fig.add_hline(
            y=map_y_value(threshold), 
            line_dash="dash", 
            line_color="red",
            annotation_text=f"缺陷阈值({threshold})",
            annotation_position="right"
        )
        fig.add_vline(
            x=coverage_threshold, 
            line_dash="dash", 
            line_color="blue",
            annotation_text=f"覆盖率{coverage_threshold}%",
            annotation_position="top"
        )
        
        # 添加象限标注 - 需要将原始值映射到显示值
        fig.add_annotation(
            x=coverage_threshold/2, y=map_y_value(threshold*1.5),
            text="高风险区域<br>(低覆盖率、高缺陷)",
            showarrow=False,
            font=dict(size=12, color="darkred"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="darkred",
            borderwidth=1,
            borderpad=4
        )
        
        fig.add_annotation(
            x=coverage_threshold + (100-coverage_threshold)/2, y=map_y_value(threshold*0.5),
            text="低风险区域<br>(高覆盖率、低缺陷)",
            showarrow=False,
            font=dict(size=12, color="green"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="green",
            borderwidth=1,
            borderpad=4
        )
        
        fig.add_annotation(
            x=coverage_threshold + (100-coverage_threshold)/2, y=map_y_value(threshold*1.5),
            text="高覆盖率但缺陷多<br>可能用例质量需提升",
            showarrow=False,
            font=dict(size=12, color="orange"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="orange",
            borderwidth=1,
            borderpad=4
        )
        
        fig.add_annotation(
            x=coverage_threshold/2, y=map_y_value(threshold*0.5),
            text="低覆盖率低缺陷<br>需增加测试覆盖",
            showarrow=False,
            font=dict(size=12, color="gold"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="gold",
            borderwidth=1,
            borderpad=4
        )
        
        fig.update_layout(
            xaxis_title="覆盖率百分比 (%)",
            yaxis_title="缺陷数量",
            legend_title="风险等级",
            xaxis=dict(
                range=[-5, 105],  # 扩展X轴范围以确保边缘气泡完整显示
                tickmode='linear',
                tick0=0,
                dtick=10,
                showgrid=True,
                tickvals=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
                ticktext=['0%', '10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '90%', '100%']
            ),
            yaxis=dict(
                showgrid=True,
                # 使用自定义刻度
                tickmode='array',
                tickvals=[map_y_value(y) for y in y_ticks],  # 映射后的刻度位置
                ticktext=y_ticktext,  # 显示原始值
                # 增加刻度标签大小和调整垂直距离
                tickfont=dict(size=11),
                tickangle=-0,
            ),
            plot_bgcolor='rgba(240,240,240,0.9)',
            height=700,
            hoverlabel=dict(
                bgcolor="white",
                font_size=12,
                namelength=-1
            ),
            margin=dict(l=50, r=50, t=50, b=50)  # 减小顶部边距，因为不再需要显示标题
        )
        
        return fig
    except Exception as e:
        # 发生错误时创建空白图表，避免应用崩溃
        print(f"创建图表时出错: {e}")
        fig = px.scatter(x=[0], y=[0])
        fig.update_layout(
            title="数据加载错误，请尝试刷新页面",
            xaxis_title="覆盖率百分比 (%)",
            yaxis_title="缺陷数量"
        )
        return fig

# 添加在动画切换或选择AIDA时自动设置活动选项卡的回调
@app.callback(
    Output('detail-tabs', 'active_tab'),
    [Input('animation-toggle', 'value'),
     Input('selected-aida-store', 'data')]
)
def update_active_tab(animation_enabled, selected_aida):
    ctx = dash.callback_context
    if not ctx.triggered:
        # 默认情况
        return "defect-tab"
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 如果是切换动画
    if trigger_id == 'animation-toggle':
        # 动画启用时，保持当前选项卡
        return "defect-tab"
    
    # 如果是点击了AIDA
    if trigger_id == 'selected-aida-store' and selected_aida:
        # 选中AIDA时，默认显示缺陷选项卡
        return "defect-tab"
    
    # 其他情况，维持现状
    return "defect-tab"

# --- 5. 运行应用 ---
if __name__ == '__main__':
    app.run(debug=True, port=8057, host='0.0.0.0')