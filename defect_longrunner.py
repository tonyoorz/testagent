import numpy as np
import pandas as pd
from dash_common_styles import create_theme_switcher, get_theme_css, theme_manager, MAIN_CONTAINER_STYLE, LIGHT_MAIN_CONTAINER_STYLE, TEXT_COLOR, LIGHT_TEXT_COLOR, LABEL_STYLE_DARK, LABEL_STYLE_LIGHT, DROPDOWN_STYLE_DARK, DROPDOWN_STYLE_LIGHT, DARK_ACCENT, LIGHT_BORDER_COLOR
from dash import Dash, dcc, html, Input, Output, State, dash_table, no_update
import plotly.express as px
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate
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

# 初始化Dash应用
app = Dash(__name__, suppress_callback_exceptions=True)

# 应用布局
app.layout = html.Div([
    # 主题切换器
    create_theme_switcher(),
    
    html.H1("Long Runner（长跑票据）监控看板", id='main-title', style={'textAlign': 'center', 'marginBottom': '30px'}),
    
    # 筛选控制面板
    html.Div([
        html.Div([
            html.Label("项目：", style={'fontWeight': 'bold', 'marginBottom': '5px'}),
            dcc.Dropdown(
                id='lr-project-dropdown',
                options=[{'label': '全部', 'value': 'all'}] + [{'label': proj, 'value': proj} for proj in sorted(df['ecu'].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())],
                value='all',
                multi=True,
                style={'minWidth': '200px'}
            )
        ], style={'flex': '1', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("AIDA：", style={'fontWeight': 'bold', 'marginBottom': '5px'}),
            dcc.Dropdown(
                id='lr-aida-dropdown',
                options=[{'label': '全部', 'value': 'all'}] + [{'label': aida, 'value': aida} for aida in sorted(df['aida_english'].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())],
                value='all',
                multi=True,
                style={'minWidth': '200px'}
            )
        ], style={'flex': '1', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("长跑严重程度：", style={'fontWeight': 'bold', 'marginBottom': '5px'}),
            dcc.Dropdown(
                id='lr-severity-dropdown',
                options=[{'label': '全部', 'value': 'all'}] + [{'label': sev, 'value': sev} for sev in ['正常', '关注', '警告', '严重']],
                value='all',
                multi=True,
                style={'minWidth': '150px'}
            )
        ], style={'flex': '1', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("处理周期：", style={'fontWeight': 'bold', 'marginBottom': '5px'}),
            dcc.Dropdown(
                id='lr-phase-category-dropdown',
                options=[{'label': '全部', 'value': 'all'}] + [{'label': cat, 'value': cat} for cat in ['测试处理周期', '开发处理周期', '其他']],
                value='all',
                multi=True,
                style={'minWidth': '150px'}
            )
        ], style={'flex': '1'})
    ], style={'display': 'flex', 'marginBottom': '30px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px'}),
    
    # KPI 卡片区域
    html.Div(id='lr-kpi-cards', style={'marginBottom': '30px'}),
    
    # 图表区域
    html.Div([
        html.Div([
            html.Div([dcc.Graph(id='lr-phase-transition-avg-chart')], style={'flex': '1'})
        ], style={'display': 'flex', 'marginBottom': '20px'}),
        # 第一行（2个图表）
        html.Div([
            html.Div([dcc.Graph(id='lr-trend-chart')], style={'flex': '1', 'marginRight': '10px'}),
            html.Div([
                html.Div([
                    dcc.Graph(id='lr-severity-distribution-chart', style={'height': '400px'})
                ], style={'flex': '2', 'marginRight': '15px'}),
                # 严重程度定义说明
                html.Div([
                    html.H5("严重程度定义:", style={'margin': '0 0 15px 0', 'fontWeight': 'bold', 'fontSize': '16px'}),
                    html.Ul([
                        html.Li("正常: < 3周 (21天)", style={'color': '#28a745', 'fontWeight': 'bold', 'marginBottom': '8px'}),
                        html.Li("关注: 3-6周 (21-42天)", style={'color': '#ffc107', 'fontWeight': 'bold', 'marginBottom': '8px'}),
                        html.Li("警告: 6-12周 (42-84天)", style={'color': '#fd7e14', 'fontWeight': 'bold', 'marginBottom': '8px'}),
                        html.Li("严重: > 12周 (84天以上)", style={'color': '#dc3545', 'fontWeight': 'bold', 'marginBottom': '8px'})
                    ], style={'margin': '0', 'paddingLeft': '20px', 'listStyle': 'disc'}),
                    html.P("* 基于票据创建时间至今的运行天数", 
                           style={'fontSize': '11px', 'color': '#6c757d', 'margin': '15px 0 0 0', 'fontStyle': 'italic'})
                ], style={'flex': '1', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px', 'border': '1px solid #e9ecef', 'height': 'fit-content', 'alignSelf': 'center'})
            ], style={'flex': '1', 'display': 'flex', 'alignItems': 'flex-start'})
        ], style={'display': 'flex', 'marginBottom': '20px'}),
        # 第二行（2个图表）
        html.Div([
            html.Div([dcc.Graph(id='lr-phase-distribution-chart')], style={'flex': '1', 'marginRight': '10px'}),
            html.Div([dcc.Graph(id='lr-project-comparison-chart')], style={'flex': '1'})
        ], style={'display': 'flex', 'marginBottom': '20px'}),
        # 第三行（2个图表）
        html.Div([
            html.Div([dcc.Graph(id='lr-aida-heatmap')], style={'flex': '1', 'marginRight': '10px'}),
            html.Div([dcc.Graph(id='lr-aging-analysis-chart')], style={'flex': '1'})
        ], style={'display': 'flex', 'marginBottom': '20px'})
    ]),
    
    # 详细数据表格
    html.Div([
        html.H3("长跑票据详细列表", style={'marginBottom': '20px'}),
        dash_table.DataTable(
            id='lr-detail-table',
            columns=[
                {"name": "ID", "id": "id"},
                {"name": "名称", "id": "name"},
                {"name": "项目", "id": "ecu"},
                {"name": "AIDA", "id": "aida_english"},
                {"name": "状态", "id": "status_phase"},
                {"name": "处理周期", "id": "phase_category"},
                {"name": "创建时间", "id": "creation_time", "type": "datetime"},
                {"name": "运行天数", "id": "age_days", "type": "numeric"},
                {"name": "运行周数", "id": "age_weeks", "type": "numeric", "format": {"specifier": ".1f"}},
                {"name": "严重程度", "id": "long_runner_severity"},
                {"name": "测试员", "id": "tester"},
                {"name": "Matrix", "id": "matrix_display"}
            ],
            sort_action="native",
            filter_action="native",
            page_action="native",
            page_current=0,
            page_size=20,
            style_cell={'textAlign': 'left', 'fontSize': '12px', 'fontFamily': 'Arial'},
            style_header={'backgroundColor': '#007bff', 'color': 'white', 'fontWeight': 'bold'},
            style_data_conditional=[
                {
                    'if': {'filter_query': '{long_runner_severity} = 严重'},
                    'backgroundColor': '#ffebee',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{long_runner_severity} = 警告'},
                    'backgroundColor': '#fff3e0',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{long_runner_severity} = 关注'},
                    'backgroundColor': '#e8f5e8',
                    'color': 'black',
                }
            ]
        )
    ], style={'marginTop': '40px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px'})
    
], id='main-container', style=MAIN_CONTAINER_STYLE)

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

# KPI卡片回调
@app.callback(
    Output('lr-kpi-cards', 'children'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_kpi_cards(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    total_long_runners = len(filtered_df)
    total_tickets = len(df)
    long_runner_rate = (total_long_runners / total_tickets * 100) if total_tickets > 0 else 0
    
    avg_age_days = filtered_df['age_days'].mean() if len(filtered_df) > 0 else 0
    
    severe_count = len(filtered_df[filtered_df['long_runner_severity'] == '严重'])
    warning_count = len(filtered_df[filtered_df['long_runner_severity'] == '警告'])
    
    # 计算开发与测试周期占比
    dev_count = len(filtered_df[filtered_df['phase_category'] == '开发处理周期'])
    test_count = len(filtered_df[filtered_df['phase_category'] == '测试处理周期'])
    
    cards = [
        html.Div([
            html.H3(f"{total_long_runners}", style={'color': '#dc3545', 'margin': '0'}),
            html.P("长跑票据总数", style={'margin': '5px 0 0 0'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fff', 'borderRadius': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'flex': '1', 'margin': '0 10px'}),
        
        html.Div([
            html.H3(f"{long_runner_rate:.1f}%", style={'color': '#fd7e14', 'margin': '0'}),
            html.P("长跑票据占比", style={'margin': '5px 0 0 0'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fff', 'borderRadius': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'flex': '1', 'margin': '0 10px'}),
        
        html.Div([
            html.H3(f"{avg_age_days:.0f}天", style={'color': '#6f42c1', 'margin': '0'}),
            html.P("平均运行天数", style={'margin': '5px 0 0 0'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fff', 'borderRadius': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'flex': '1', 'margin': '0 10px'}),
        
        html.Div([
            html.H3(f"{severe_count}", style={'color': '#dc3545', 'margin': '0'}),
            html.P("严重级别", style={'margin': '5px 0 0 0'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fff', 'borderRadius': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'flex': '1', 'margin': '0 10px'}),
        
        html.Div([
            html.H3(f"{dev_count}/{test_count}", style={'color': '#20c997', 'margin': '0'}),
            html.P("开发/测试周期", style={'margin': '5px 0 0 0'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fff', 'borderRadius': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'flex': '1', 'margin': '0 10px'})
    ]
    
    return html.Div(cards, style={'display': 'flex', 'justifyContent': 'space-between'})

# Phase Transition 平均耗时（分组堆叠）图
@app.callback(
    Output('lr-phase-transition-avg-chart', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_phase_transition_avg_chart(projects, aidas, severities, phase_categories):
    import os
    csv_path = os.path.join(os.getcwd(), 'phase_statistics_2025.csv')
    if not os.path.exists(csv_path):
        fig = apply_chart_style(go.Figure(), "Phase Transition 平均耗时（分组堆叠）", "平均耗时（天）", "分组", 420)
        fig.add_annotation(text="未找到 phase_statistics_2025.csv，请先运行 longrunner_analysis.py 生成统计数据",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    
    stats_df = pd.read_csv(csv_path, encoding='utf-8')
    if stats_df.empty:
        return apply_chart_style(go.Figure(), "Phase Transition 平均耗时（分组堆叠）", height=420)
    
    def transition_group(name: str) -> str:
        left = name.split('→')[0].strip()
        prefix = left.split('-')[0].strip()
        digits = ''.join([c for c in prefix if c.isdigit()]) or prefix
        if digits in ['02', '07']:
            return 'Q-Gate'
        elif digits in ['00', '01', '08']:
            return 'Integration'
        elif digits in ['03', '04', '05']:
            return 'CoC'
        else:
            return 'Other'
    
    stats_df['Group'] = stats_df['Phase_Transition'].apply(transition_group)
    stats_df = stats_df[stats_df['Group'].isin(['Q-Gate', 'Integration', 'CoC'])]
    if stats_df.empty:
        fig = apply_chart_style(go.Figure(), "Phase Transition 平均耗时（分组堆叠）", "平均耗时（天）", "分组", 420)
        fig.add_annotation(text="统计数据中不存在匹配的分组（Q-Gate/Integration/CoC）",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    
    pivot = stats_df.pivot_table(index='Group',
                                 columns='Phase_Transition',
                                 values='Avg_Days',
                                 aggfunc='mean').fillna(0)
    counts = stats_df.pivot_table(index='Group',
                                  columns='Phase_Transition',
                                  values='Count',
                                  aggfunc='sum').fillna(0)
    
    groups_order = ['Q-Gate', 'Integration', 'CoC']
    pivot = pivot.reindex(groups_order).fillna(0)
    counts = counts.reindex(groups_order).fillna(0)
    
    fig = go.Figure()
    for transition in pivot.columns:
        x_vals = pivot[transition].values
        y_vals = pivot.index.tolist()
        text_vals = []
        for g_idx, g in enumerate(y_vals):
            avg_days = x_vals[g_idx]
            cnt = counts.loc[g, transition] if transition in counts.columns else 0
            text_vals.append(f"{avg_days:.1f}天 | {int(cnt)}")
        fig.add_trace(go.Bar(
            y=y_vals,
            x=x_vals,
            name=transition,
            orientation='h',
            text=text_vals,
            textposition='inside',
            hovertemplate="<b>%{y}</b><br>%{fullData.name}<br>平均: %{x:.2f}天<br>数量: %{text}<extra></extra>"
        ))
    
    fig = apply_chart_style(fig, "Phase Transition 平均耗时（分组堆叠）", "平均耗时（天）", "分组", 420)
    fig.update_layout(barmode='stack', legend_orientation='h', legend_yanchor='bottom', legend_y=-0.25)
    return fig

# 长跑趋势图
@app.callback(
    Output('lr-trend-chart', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_trend_chart(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    if filtered_df.empty:
        return apply_chart_style(go.Figure(), "长跑票据趋势分析", height=400)
    # 只统计每周新晋长跑票据的平均老化（固定为21天）
    trend_data = filtered_df.groupby('long_runner_start_week').agg({
        'id': 'count',
        'age_at_long_runner_start': 'mean'
    }).reset_index()
    trend_data.columns = ['test_week', 'count', 'avg_age']
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_data['test_week'],
        y=trend_data['count'],
        name='新晋长跑票据数量',
        marker_color='#dc3545',
        yaxis='y1'
    ))
    fig.add_trace(go.Scatter(
        x=trend_data['test_week'],
        y=trend_data['avg_age'],
        mode='lines+markers',
        name='新晋长跑票据平均老化天数',
        line=dict(color='#fd7e14', width=3, dash='dash'),
        yaxis='y2'
    ))
    
    # 先应用基础样式
    fig = apply_chart_style(fig, "新晋长跑票据趋势分析", "长跑起始周", "数量", 400)
    
    # 然后重新设置双纵轴配置（这样不会被 apply_chart_style 覆盖）
    fig.update_layout(
        yaxis=dict(title='新晋长跑票据数量', side='left'),
        yaxis2=dict(
            title='平均处理时间（天）',
            side='right',
            overlaying='y',
            showline=True,
            showticklabels=True,
            linecolor='#fd7e14',
            tickcolor='#fd7e14'
        )
    )
    
    return fig

# 严重程度分布图
@app.callback(
    Output('lr-severity-distribution-chart', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_severity_distribution_chart(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    if filtered_df.empty:
        return apply_chart_style(go.Figure(), "长跑严重程度分布", height=400)
    
    severity_counts = filtered_df['long_runner_severity'].value_counts()
    
    colors = {
        '正常': '#28a745',
        '关注': '#ffc107', 
        '警告': '#fd7e14',
        '严重': '#dc3545'
    }
    
    fig = go.Figure(data=[go.Pie(
        labels=severity_counts.index,
        values=severity_counts.values,
        marker_colors=[colors.get(label, '#6c757d') for label in severity_counts.index],
        textinfo='label+percent+value',
        hovertemplate='<b>%{label}</b><br>数量: %{value}<br>占比: %{percent}<extra></extra>'
    )])
    
    return apply_chart_style(fig, "长跑严重程度分布", height=400)

# 阶段分布图
@app.callback(
    Output('lr-phase-distribution-chart', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_phase_distribution_chart(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    if filtered_df.empty:
        return apply_chart_style(go.Figure(), "处理阶段分布", height=400)
    
    phase_counts = filtered_df.groupby(['phase_category', 'status_phase']).size().reset_index(name='count')
    
    # 计算百分比
    total_count = phase_counts['count'].sum()
    phase_counts['percentage'] = (phase_counts['count'] / total_count * 100).round(1)
    
    # 计算每个处理周期的总数和百分比
    category_totals = phase_counts.groupby('phase_category')['count'].sum().reset_index()
    category_totals.columns = ['phase_category', 'total_count']
    category_totals['percentage'] = (category_totals['total_count'] / total_count * 100).round(1)
    
    # 计算每个处理周期的平均运行天数
    category_avg_days = filtered_df.groupby('phase_category')['age_days'].mean().reset_index()
    category_avg_days.columns = ['phase_category', 'avg_days']
    category_totals = category_totals.merge(category_avg_days, on='phase_category', how='left')
    
    fig = go.Figure()
    
    # 添加柱状图（左轴）
    for status_phase in phase_counts['status_phase'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique():
        phase_data = phase_counts[phase_counts['status_phase'] == status_phase]
        fig.add_trace(go.Bar(
            x=phase_data['phase_category'],
            y=phase_data['count'],
            name=status_phase,
            text=phase_data['count'],
            textposition='inside',
            yaxis='y1'
        ))
    
    # 添加一个不可见的散点图来激活右侧纵轴
    fig.add_trace(go.Scatter(
        x=category_totals['phase_category'],
        y=category_totals['avg_days'],
        mode='markers',
        name='平均运行天数',
        marker=dict(size=0, opacity=0),  # 完全透明，不可见
        yaxis='y2',
        showlegend=False  # 不在图例中显示
    ))
    
    # 先应用基础样式
    fig = apply_chart_style(fig, "处理阶段分布", "处理周期", "票据数量", 400)
    
    # 在柱状图顶部添加百分比标注
    for _, row in category_totals.iterrows():
        fig.add_annotation(
            x=row['phase_category'],
            y=row['total_count'] + max(category_totals['total_count']) * 0.05,
            text=f"{row['percentage']}%",
            showarrow=False,
            font=dict(size=12, color='#fd7e14', weight='bold'),
            xanchor='center'
        )
    
    # 设置双纵轴配置
    fig.update_layout(
        barmode='stack',
        yaxis=dict(title='票据数量', side='left'),
        yaxis2=dict(
            title='平均运行天数',
            side='right',
            overlaying='y',
            showline=True,
            showticklabels=True,
            linecolor='#6f42c1',
            tickcolor='#6f42c1'
        )
    )
    
    return fig

# 项目对比图
@app.callback(
    Output('lr-project-comparison-chart', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_project_comparison_chart(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    if filtered_df.empty:
        return apply_chart_style(go.Figure(), "项目长跑票据对比", height=400)
    
    project_stats = filtered_df.groupby('ecu').agg({
        'id': 'count',
        'age_days': 'mean'
    }).reset_index()
    project_stats.columns = ['ecu', 'count', 'avg_age']
    project_stats = project_stats.sort_values('count', ascending=True)
    
    fig = go.Figure()
    
    # 添加长跑票据数量
    fig.add_trace(go.Bar(
        y=project_stats['ecu'],
        x=project_stats['count'],
        name='长跑票据数量',
        orientation='h',
        marker_color='#dc3545',
        text=project_stats['count'],
        textposition='auto'
    ))
    
    return apply_chart_style(fig, "项目长跑票据对比", "票据数量", "项目", 400)

# AIDA热力图
@app.callback(
    Output('lr-aida-heatmap', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_aida_heatmap(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    if filtered_df.empty:
        return apply_chart_style(go.Figure(), "AIDA vs 严重程度热力图", height=400)
    
    # 创建透视表
    heatmap_data = filtered_df.groupby(['aida_english', 'long_runner_severity']).size().reset_index(name='count')
    pivot_table = heatmap_data.pivot(index='aida_english', columns='long_runner_severity', values='count').fillna(0)
    
    if pivot_table.empty:
        return apply_chart_style(go.Figure(), "AIDA vs 严重程度热力图", height=400)
    
    fig = go.Figure(data=go.Heatmap(
        z=pivot_table.values,
        x=pivot_table.columns,
        y=pivot_table.index,
        colorscale='Reds',
        text=pivot_table.values,
        texttemplate="%{text}",
        textfont={"size": 10},
        hoverongaps=False
    ))
    
    return apply_chart_style(fig, "AIDA vs 严重程度热力图", "严重程度", "AIDA", 400)

# 老化分析图
@app.callback(
    Output('lr-aging-analysis-chart', 'figure'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_aging_analysis_chart(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    if filtered_df.empty:
        return apply_chart_style(go.Figure(), "票据老化分析", height=400)
    
    # 创建年龄段
    filtered_df['age_group'] = pd.cut(
        filtered_df['age_weeks'], 
        bins=[0, 3, 6, 12, 24, float('inf')], 
        labels=['<3周', '3-6周', '6-12周', '12-24周', '>24周']
    )
    
    age_counts = filtered_df['age_group'].value_counts().sort_index()
    
    colors = ['#28a745', '#ffc107', '#fd7e14', '#dc3545', '#6f42c1']
    
    fig = go.Figure(data=[go.Bar(
        x=age_counts.index,
        y=age_counts.values,
        marker_color=colors[:len(age_counts)],
        text=age_counts.values,
        textposition='auto'
    )])
    
    return apply_chart_style(fig, "票据老化分析", "运行时间段", "票据数量", 400)

# 详细表格回调
@app.callback(
    Output('lr-detail-table', 'data'),
    [Input('lr-project-dropdown', 'value'),
     Input('lr-aida-dropdown', 'value'),
     Input('lr-severity-dropdown', 'value'),
     Input('lr-phase-category-dropdown', 'value')]
)
def update_lr_detail_table(projects, aidas, severities, phase_categories):
    filtered_df = filter_long_runner_data(projects, aidas, severities, phase_categories)
    
    if filtered_df.empty:
        return []
    
    # 选择需要显示的列
    display_columns = ['id', 'name', 'ecu', 'aida_english', 'status_phase', 
                      'phase_category', 'creation_time', 'age_days', 'age_weeks', 
                      'long_runner_severity', 'tester', 'matrix_display']
    
    table_data = filtered_df[display_columns].copy()
    
    # 格式化创建时间
    table_data['creation_time'] = table_data['creation_time'].dt.strftime('%Y-%m-%d %H:%M')
    
    # 按运行天数降序排列
    table_data = table_data.sort_values('age_days', ascending=False)
    
    return table_data.to_dict('records')

# 主题回调
@app.callback(
    [Output('main-container', 'style'),
     Output('main-title', 'style')],
    [Input('global-theme-switcher', 'value')],
    prevent_initial_call=False
)
def update_theme(selected_theme):
    if selected_theme == 'light':
        container_style = LIGHT_MAIN_CONTAINER_STYLE.copy()
        title_style = {'textAlign': 'center', 'marginBottom': '30px', 'color': LIGHT_TEXT_COLOR}
    else:
        container_style = MAIN_CONTAINER_STYLE.copy()
        title_style = {'textAlign': 'center', 'marginBottom': '30px', 'color': TEXT_COLOR}
    
    theme_manager.set_theme(selected_theme)
    
    return container_style, title_style

if __name__ == '__main__':
    app.run_server(debug=True, port=8062)
