import json
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output, State, dash_table
from dash.exceptions import PreventUpdate # 从 dash.exceptions 导入
import numpy as np
import glob
import os
from datetime import datetime
import io # 导入 io 模块
import traceback # 导入 traceback 模块

# 导入数据处理函数
try:
    from data_processor import load_defect_data, apply_chart_style
except ImportError:
    print("警告：无法导入 data_processor 模块。请确保 data_processor.py 在PYTHONPATH中。")
    def load_defect_data(pattern): return pd.DataFrame()
    def apply_chart_style(fig, title, x_title, y_title, height): return fig

# 重新定义矩阵单元格位置和标识 - 1A在最上方，4A在最下方
MATRIX_CONFIG = {
    # A列 (右侧)
    '1A': {'row': 0, 'col': 4, 'label': '1A'},
    '2A': {'row': 1, 'col': 4, 'label': '2A'},
    '3A': {'row': 2, 'col': 4, 'label': '3A'},
    '4A': {'row': 3, 'col': 4, 'label': '4A'},
    # B列
    '1B': {'row': 0, 'col': 3, 'label': '1B'},
    '2B': {'row': 1, 'col': 3, 'label': '2B'},
    '3B': {'row': 2, 'col': 3, 'label': '3B'},
    '4B': {'row': 3, 'col': 3, 'label': '4B'},
    # C列
    '1C': {'row': 0, 'col': 2, 'label': '1C'},
    '2C': {'row': 1, 'col': 2, 'label': '2C'},
    '3C': {'row': 2, 'col': 2, 'label': '3C'},
    '4C': {'row': 3, 'col': 2, 'label': '4C'},
    # D列
    '1D': {'row': 0, 'col': 1, 'label': '1D'},
    '2D': {'row': 1, 'col': 1, 'label': '2D'},
    '3D': {'row': 2, 'col': 1, 'label': '3D'},
    '4D': {'row': 3, 'col': 1, 'label': '4D'},
    # E列 (左侧)
    '1E': {'row': 0, 'col': 0, 'label': '1E'},
    '2E': {'row': 1, 'col': 0, 'label': '2E'},
    '3E': {'row': 2, 'col': 0, 'label': '3E'},
    '4E': {'row': 3, 'col': 0, 'label': '4E'},
}

# 矩阵背景颜色 - 调整对应行索引
MATRIX_COLORS = {
    0: '#F8D7DA',  # 第一行背景(1A-1E) - 浅红色
    1: '#D1E7DD',  # 第二行背景(2A-2E) - 浅绿色 
    2: '#D1E7DD',  # 第三行背景(3A-3E) - 浅绿色
    3: '#D1E7DD',  # 第四行背景(4A-4E) - 浅绿色
}

# 定义严重问题的矩阵位置（这些位置使用浅红色背景）
SEVERE_MATRICES = ['1A', '1B', '1C', '1D', '1E', '2A', '2B', '2C', '3A']

def create_matrix_figure(defect_data, filtered_by=None):
    """创建缺陷矩阵分布图 (简化版，无复杂悬停)"""
    rows = 4
    cols = 5
    matrix_counts = {}
    if 'matrix_display' in defect_data.columns and not defect_data['matrix_display'].dropna().empty:
        # 确保大小写不敏感且更健壮地移除前缀
        counts_series = defect_data['matrix_display'].dropna().astype(str).str.upper().value_counts()
        counts_series.index = counts_series.index.str.replace('MATRIX-', '', regex=False)
        matrix_counts = counts_series.to_dict()
    else:
        matrix_counts = {}

    fig = go.Figure()

    for matrix_key, config in MATRIX_CONFIG.items():
        row = config['row']
        col = config['col']
        count = matrix_counts.get(matrix_key, 0)
        
        # Add background rectangle
        background_color = '#F8D7DA' if matrix_key in SEVERE_MATRICES else MATRIX_COLORS.get(row, '#FFFFFF')
        fig.add_shape(
            type="rect", x0=col, y0=row, x1=col+1, y1=row+1,
            fillcolor=background_color, line=dict(color="#000000", width=1), layer='below'
        )
        
        # Add matrix label
        fig.add_annotation(
            x=col+0.9, y=row+0.1, text=matrix_key, showarrow=False,
            font=dict(size=10, color="black"), xanchor='right', yanchor='bottom'
        )
        
        # If count > 0, add the bubble with count text
        if count > 0:
            size = min(max(count * 5, 20), 70) # Size based on count
            
            # Add the scatter trace for the bubble and text
            fig.add_trace(go.Scatter(
                x=[col+0.5],
                y=[row+0.5],
                mode='markers+text',
                marker=dict(
                    size=size,
                    color='#5DADE2',
                    opacity=0.7,
                    line=dict(width=1, color='#2874A6')
                ),
                text=[str(count)],
                textfont=dict(color='white', size=10, family='Arial Black'),
                textposition='middle center',
                # Simplified hover text
                hovertext=f"Matrix: {matrix_key}<br>Count: {count}",
                hoverinfo='text',
                showlegend=False,
                customdata=[[matrix_key]] # 也给气泡添加customdata
            ))
        
        # 添加一个透明的覆盖层用于捕获整个单元格区域的点击事件
        fig.add_trace(go.Scatter(
            x=[col+0.5],
            y=[row+0.5],
            mode='markers',
            marker=dict(
                size=90, # 大尺寸覆盖整个单元格
                color='rgba(0,0,0,0)', # 完全透明
                opacity=0
            ),
            hoverinfo='skip',
            showlegend=False,
            customdata=[[matrix_key]], # 保存矩阵标识用于点击回调
        ))
            
    # Set layout 
    title = f"缺陷矩阵分布 {filtered_by if filtered_by else ''}"
    fig.update_layout(
        title=title, height=550, width=700,
        xaxis=dict(range=[-0.1, cols+0.1], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=[-0.1, rows+0.1], showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=50, r=50, t=100, b=50), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', autosize=False,
        clickmode='event+select' # 确保启用点击事件
    )
    return fig

def create_matrix_figure_flipped(defect_data, filtered_by=None):
    """创建缺陷矩阵分布图 (上下翻转版本 - 1A在顶部，4A在底部)"""
    rows = 4
    cols = 5
    matrix_counts = {}
    if 'matrix_display' in defect_data.columns and not defect_data['matrix_display'].dropna().empty:
        counts_series = defect_data['matrix_display'].dropna().astype(str).str.upper().value_counts()
        counts_series.index = counts_series.index.str.replace('MATRIX-', '', regex=False)
        matrix_counts = counts_series.to_dict()
    else:
        matrix_counts = {}

    # --- 计算当前视图的最大缺陷数，用于动态调整气泡大小 ---
    max_count_in_view = max(matrix_counts.values()) if matrix_counts else 0
    min_bubble_size = 10
    max_bubble_size = 80 # 可以调整最大尺寸

    fig = go.Figure()

    # 完全重新定义矩阵配置 - 严格按数字定义行
    # 第1行在顶部(row=3)，第4行在底部(row=0)
    matrix_positions = {
        # 第1行 (顶部, row=3)
        '1A': {'row': 3, 'col': 4},  # 右上角
        '1B': {'row': 3, 'col': 3},
        '1C': {'row': 3, 'col': 2},
        '1D': {'row': 3, 'col': 1},
        '1E': {'row': 3, 'col': 0},  # 左上角
        
        # 第2行 (row=2)
        '2A': {'row': 2, 'col': 4},
        '2B': {'row': 2, 'col': 3},
        '2C': {'row': 2, 'col': 2},
        '2D': {'row': 2, 'col': 1},
        '2E': {'row': 2, 'col': 0},
        
        # 第3行 (row=1)
        '3A': {'row': 1, 'col': 4},
        '3B': {'row': 1, 'col': 3},
        '3C': {'row': 1, 'col': 2},
        '3D': {'row': 1, 'col': 1},
        '3E': {'row': 1, 'col': 0},
        
        # 第4行 (底部, row=0)
        '4A': {'row': 0, 'col': 4},  # 右下角
        '4B': {'row': 0, 'col': 3},
        '4C': {'row': 0, 'col': 2},
        '4D': {'row': 0, 'col': 1},
        '4E': {'row': 0, 'col': 0},  # 左下角
    }
    
    # 行背景颜色 - 确保颜色与行号对应 (row=3 顶部, row=0 底部)
    row_colors = {
        3: '#F8D7DA',  # 第1行(顶部, row=3) - 浅红色 
        2: '#D1E7DD',  # 第2行(row=2) - 浅绿色
        1: '#D1E7DD',  # 第3行(row=1) - 浅绿色
        0: '#D1E7DD',  # 第4行(底部, row=0) - 浅绿色
    }

    # 添加所有单元格
    for matrix_key, position in matrix_positions.items():
        row = position['row']
        col = position['col']
        count = matrix_counts.get(matrix_key, 0)
        
        # 绘制背景矩形
        background_color = '#F8D7DA' if matrix_key in SEVERE_MATRICES else row_colors.get(row, '#FFFFFF')
        fig.add_shape(
            type="rect", x0=col, y0=row, x1=col+1, y1=row+1,
            fillcolor=background_color, line=dict(color="#000000", width=1), layer='below'
        )
        
        # 添加矩阵标签
        fig.add_annotation(
            x=col+0.9, y=row+0.1, text=matrix_key, showarrow=False,
            font=dict(size=10, color="black"), xanchor='right', yanchor='bottom'
        )
        
        # 如果数量>0，添加气泡和文本
        if count > 0:
            # --- 动态计算气泡大小 ---
            if max_count_in_view > 0:
                relative_size = count / max_count_in_view
                size = min_bubble_size + relative_size * (max_bubble_size - min_bubble_size)
            else:
                size = min_bubble_size # 如果所有计数都为0，则使用最小尺寸
            # -------------------------
            
            # 添加气泡和文本
            fig.add_trace(go.Scatter(
                x=[col+0.5],
                y=[row+0.5],
                mode='markers+text',
                marker=dict(
                    size=size, # 使用动态计算的尺寸
                    color='#5DADE2',
                    opacity=0.7,
                    line=dict(width=1, color='#2874A6')
                ),
                text=[str(count)],
                textfont=dict(color='white', size=12, family='Arial Black'), # 固定字体大小为12
                textposition='middle center',
                hovertext=f"Matrix: {matrix_key}<br>Count: {count}",
                hoverinfo='text',
                showlegend=False,
                customdata=[[matrix_key]]
            ))
        
        # 添加透明覆盖层用于捕获点击事件
        fig.add_trace(go.Scatter(
            x=[col+0.5],
            y=[row+0.5],
            mode='markers',
            marker=dict(
                size=90,
                color='rgba(0,0,0,0)',
                opacity=0
            ),
            hoverinfo='skip',
            showlegend=False,
            customdata=[[matrix_key]],
        ))
            
    # 设置布局
    title = f"缺陷矩阵分布 {filtered_by if filtered_by else ''}"
    fig.update_layout(
        title="", height=550, width=700,
        xaxis=dict(range=[-0.1, cols+0.1], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=[-0.1, rows+0.1], showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=50, r=50, t=100, b=50), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', autosize=False,
        clickmode='event+select'
    )
    return fig

def filter_defect_data(df, project=None, domain=None, start_date=None, end_date=None, time_period=None):
    """
    根据条件过滤缺陷数据
    
    Args:
        df: 原始缺陷数据DataFrame
        project: 项目名称
        domain: 开发团队/领域
        start_date: 开始日期
        end_date: 结束日期
        time_period: 时间周期类型 ('week'/'month')
    
    Returns:
        过滤后的DataFrame和过滤描述
    """
    filtered_df = df.copy()
    filter_desc = []
    
    # 按项目过滤
    if project and 'project' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['project'] == project]
        filter_desc.append(f"项目: {project}")
    
    # 按领域/团队过滤
    if domain and 'aida_english' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['aida_english'] == domain]
        filter_desc.append(f"领域: {domain}")
    
    # 按日期过滤
    if 'creation_time' in filtered_df.columns:
        if start_date:
            filtered_df = filtered_df[filtered_df['creation_time'] >= pd.to_datetime(start_date)]
            filter_desc.append(f"从 {start_date}")
        
        if end_date:
            filtered_df = filtered_df[filtered_df['creation_time'] <= pd.to_datetime(end_date)]
            filter_desc.append(f"到 {end_date}")
    
    # 构建过滤描述
    filter_description = " | ".join(filter_desc) if filter_desc else None
    
    return filtered_df, filter_description

def get_available_projects(df):
    """获取可用的项目列表 (使用 tproject)"""
    if 'tproject' in df.columns:
        # 过滤掉空字符串或None值，然后获取唯一值并排序
        projects = df['tproject'].replace('', pd.NA).dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        return sorted(projects)
    return []

def get_available_aidas(df):
    """获取可用的AIDA列表 (重命名自 get_available_domains)"""
    if 'aida_english' in df.columns:
        # 过滤掉'Unknown'和空值
        aidas = df['aida_english'].replace('Unknown', pd.NA).replace('', pd.NA).dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        return sorted(aidas)
    return []

def get_available_statuses(df):
    """获取可用的状态列表"""
    if 'status_phase' in df.columns:
        statuses = df['status_phase'].replace('', pd.NA).dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        return sorted(statuses)
    return []

def get_available_domains(df):
    """获取可用的开发组(Domain)列表"""
    if 'domain' in df.columns:
        domains = df['domain'].replace('', pd.NA).dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        return sorted(domains)
    return []

def get_available_pus(df):
    """获取可用的PU列表"""
    if 'pu' in df.columns:
        pus = df['pu'].replace('', pd.NA).dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        return sorted(pus)
    return []

def get_time_periods(df):
    """从数据中获取可用的周和月列表"""
    if 'creation_time' not in df.columns:
        return [], []
    
    # 确保时间列是日期时间类型
    df_time = df.copy()
    df_time['creation_time'] = pd.to_datetime(df_time['creation_time'], errors='coerce')
    df_time = df_time.dropna(subset=['creation_time'])
    
    # 获取周
    df_time['week'] = df_time['creation_time'].dt.strftime('%Y-W%V') # 使用 %V for ISO week
    weeks = sorted(df_time['week'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
    
    # 获取月
    df_time['month'] = df_time['creation_time'].dt.strftime('%Y-%m')
    months = sorted(df_time['month'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
    
    return weeks, months 

# 创建Dash应用
app = dash.Dash(__name__, title="缺陷矩阵分布看板")

# 加载缺陷数据 - 使用完整的defect目录路径
defect_data = load_defect_data("defect/*.json")

# --- 调试：检查初始加载的数据 ---
print("--- 初始加载数据检查 ---")
if not defect_data.empty:
    print(f"初始数据列名: {defect_data.columns.tolist()}")
    if 'matrix_display' in defect_data.columns:
        print(f"初始 matrix_display 值计数:\n{defect_data['matrix_display'].value_counts()}")
    else:
        print("警告：初始加载的 defect_data 中缺少 'matrix_display' 列！")
else:
    print("警告：初始加载的 defect_data 为空！")
print("-------------------------")
# --- 调试结束 ---

# 如果数据为空，创建一个简单的示例数据框架，但不包含伪矩阵数据
if defect_data.empty:
    # 创建示例数据结构但不添加具体的矩阵值
    print("未找到缺陷数据，使用示例数据框架...")
    # 确保DataFrame至少有hover需要的列以防出错
    required_cols = [
        'id', 'name', 'tproject', 'matrix_display', 'topissue_display', 
        'status_phase', 'tester', 'creation_time', 'project', 'aida_english',
        'domain', 'classification'
    ]
    defect_data = pd.DataFrame(columns=required_cols)

# 获取可用的过滤选项
available_projects = get_available_projects(defect_data)
available_aidas = get_available_aidas(defect_data)
available_statuses = get_available_statuses(defect_data)
available_domains = get_available_domains(defect_data)
available_pus = get_available_pus(defect_data)
available_weeks, available_months = get_time_periods(defect_data)

# 计算默认选中的状态 (01, 02, 03, 04, 05, 08 开头)
default_status_prefixes = ('01', '02', '03', '04', '05', '08')
default_statuses = [s for s in available_statuses if s.startswith(default_status_prefixes)]

# 应用布局 - 调整筛选器布局 (修改时间选择下拉菜单默认值为None，添加全部选项)
app.layout = html.Div([
    html.H1("缺陷矩阵分布看板", style={'textAlign': 'center'}),
    
    # 过滤选项 - 两行布局
    html.Div([
        # 第一行
        html.Div([
            html.Label("时间周期"),
            dcc.RadioItems(id='time-period-selector', options=[{'label': '按周', 'value': 'week'}, {'label': '按月', 'value': 'month'}], value='month', inline=True)
        ], style={'width': '20%', 'display': 'inline-block', 'paddingRight': '10px'}),
        html.Div([
            html.Label("时间选择"),
            dcc.Dropdown(
                id='time-dropdown', 
                options=[{'label': '全部', 'value': 'all'}] + [{'label': month, 'value': month} for month in available_months], 
                value='all',  # 默认值设为'all'，显示所有数据
                clearable=False
            )
        ], style={'width': '25%', 'display': 'inline-block', 'paddingRight': '10px'}),
        html.Div([
            html.Label("项目 (tproject)"), # 明确标签
            dcc.Dropdown(
                id='project-dropdown', 
                options=[{'label': p, 'value': p} for p in available_projects], 
                multi=True, 
                placeholder="选择项目"
            )
        ], style={'width': '25%', 'display': 'inline-block', 'paddingRight': '10px'}),
        html.Div([
            html.Label("AIDA"), # 重命名标签
            dcc.Dropdown(
                id='aida-dropdown', 
                options=[{'label': a, 'value': a} for a in available_aidas], 
                multi=True, 
                placeholder="选择AIDA"
            )
        ], style={'width': '25%', 'display': 'inline-block'}),
    ], style={'marginBottom': '10px'}),
    
    # 第二行
    html.Div([
        html.Div([
            html.Label("状态 (status_phase)"),
            dcc.Dropdown(
                id='status-dropdown', 
                options=[{'label': s, 'value': s} for s in available_statuses], 
                multi=True, 
                placeholder="选择状态",
                value=default_statuses
            )
        ], style={'width': '32%', 'display': 'inline-block', 'paddingRight': '10px'}), 
        html.Div([
            html.Label("开发组 (domain)"),
            dcc.Dropdown(
                id='domain-dropdown', 
                options=[{'label': d, 'value': d} for d in available_domains], 
                multi=True, 
                placeholder="选择开发组"
            )
        ], style={'width': '32%', 'display': 'inline-block', 'paddingRight': '10px'}), 
        html.Div([
            html.Label("PU"),
            dcc.Dropdown(
                id='pu-dropdown', 
                options=[{'label': p, 'value': p} for p in available_pus], 
                multi=True, 
                placeholder="选择PU"
            )
        ], style={'width': '32%', 'display': 'inline-block'})
    ], style={'marginBottom': '20px'}),

    # 矩阵图 - 居中显示
    html.Div([
        dcc.Graph(id='matrix-chart', config={'staticPlot': False}) # 确保图表是交互式的
    ], style={'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center'}),
    
    # 添加缺陷详情区域 - 使用DataTable替代原来的列表
    html.Div([
        html.H3(id='defect-detail-title', children="点击矩阵区域查看缺陷详情", style={'textAlign': 'center'}),
        # 使用DataTable显示缺陷详情
        dash_table.DataTable(
            id='defect-detail-table',
            columns=[
                {"name": "ID", "id": "id", "type": "text"},
                {"name": "缺陷名称", "id": "name", "type": "text"},
                {"name": "项目", "id": "tproject", "type": "text"},
                {"name": "状态", "id": "status_phase", "type": "text"},
                {"name": "测试人员", "id": "tester", "type": "text"},
                {"name": "AIDA", "id": "aida_english", "type": "text"},
                {"name": "Lead Model", "id": "lead_model", "type": "text"},
                {"name": "ECU Pingpong", "id": "ECU Pingpong", "type": "numeric"},
                {"name": "复杂度", "id": "complexity", "type": "text"},
                {"name": "TopIssue", "id": "topissue_display", "type": "text"},
                {"name": "严重性", "id": "severity_group", "type": "text"}
            ],
            data=[],  # 初始为空，通过回调更新
            filter_action="native",  # 启用内置过滤
            sort_action="native",    # 启用内置排序
            sort_mode="multi",       # 允许多列排序
            page_action="native",    # 启用内置分页
            page_size=15,            # 每页显示15行
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'left',
                'padding': '10px',
                'minWidth': '100px', 
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'maxWidth': '200px',
            },
            style_header={
                'backgroundColor': 'rgb(230, 230, 230)',
                'fontWeight': 'bold'
            },
            style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': 'rgb(248, 248, 248)'
                },
                {
                    'if': {'filter_query': '{topissue_display} contains "TopIssue"'},
                    'backgroundColor': '#FFEBEE',
                    'fontWeight': 'bold'
                },
                {
                    'if': {'filter_query': '{severity_group} contains "严重问题"'},
                    'backgroundColor': '#FFF8E1'
                }
            ],
            tooltip_data=[],  # 初始为空，通过回调更新
            tooltip_duration=None,
            css=[{"selector": ".dash-spreadsheet-menu", "rule": "margin-top: 4px;"}]
        )
    ], style={'margin': '20px'}),
    
    # 隐藏的中间状态
    dcc.Store(id='filtered-data')
], style={'fontFamily': 'Arial', 'margin': '0 auto', 'maxWidth': '1200px'})

# 更新时间选择下拉框的回调
@app.callback(
    Output('time-dropdown', 'options'),
    Output('time-dropdown', 'value'),
    Input('time-period-selector', 'value')
)
def update_time_options(time_period):
    if time_period == 'week':
        options = [{'label': '全部', 'value': 'all'}] + [{'label': week, 'value': week} for week in available_weeks]
        value = 'all'  # 默认值设为'all'，显示所有数据
    else:  # month
        options = [{'label': '全部', 'value': 'all'}] + [{'label': month, 'value': month} for month in available_months]
        value = 'all'  # 默认值设为'all'，显示所有数据
    
    return options, value

# 根据过滤条件更新图表 - 添加对'all'选项的处理
@app.callback(
    Output('filtered-data', 'data'),
    Input('time-period-selector', 'value'),
    Input('time-dropdown', 'value'),
    Input('project-dropdown', 'value'),
    Input('aida-dropdown', 'value'), # 输入重命名为 aida
    Input('status-dropdown', 'value'), # 新增输入
    Input('domain-dropdown', 'value'), # 新增输入
    Input('pu-dropdown', 'value')      # 新增输入
)
def filter_data(time_period, time_value, projects, aidas, statuses, domains, pus):
    # 初始化日期过滤条件
    start_date = None
    end_date = None
    
    # 根据时间周期设置日期范围
    # 当选择"全部"时不设定日期范围（维持start_date和end_date为None）
    if time_value and time_value != 'all':
        if time_period == 'week':
            try:
                # 解析周标识 (例如 '2023-W01' 或 '2023-W1')
                year, week_str = time_value.split('-W')
                week = int(week_str)
                # 计算该周的开始日期 (ISO week date system Monday as first day)
                start_date = datetime.strptime(f'{year}-{week}-1', "%Y-%W-%w") 
                end_date = start_date + pd.DateOffset(days=6)
            except ValueError:
                print(f"警告：无法解析周标识 '{time_value}'")
                start_date, end_date = None, None
        else:  # month
            try:
                # 解析月标识 (例如 '2023-01')
                year_month = time_value.split('-')
                if len(year_month) == 2:
                    year, month = map(int, year_month)
                    # 计算月份的开始和结束日期
                    start_date = datetime(year, month, 1)
                    if month == 12:
                        end_date = datetime(year + 1, 1, 1) - pd.DateOffset(days=1)
                    else:
                        end_date = datetime(year, month + 1, 1) - pd.DateOffset(days=1)
                else:
                     start_date, end_date = None, None
            except ValueError:
                print(f"警告：无法解析月标识 '{time_value}'")
                start_date, end_date = None, None

    # 应用过滤
    current_df = defect_data.copy()
    filter_desc = []

    # 按日期过滤 (确保日期是datetime对象)
    if 'creation_time' in current_df.columns:
        current_df['creation_time'] = pd.to_datetime(current_df['creation_time'], errors='coerce')
        if start_date:
            current_df = current_df[current_df['creation_time'] >= start_date]
            filter_desc.append(f"从 {start_date.strftime('%Y-%m-%d')}")
        if end_date:
            # 包含结束日期当天
            end_date_inclusive = end_date + pd.Timedelta(days=1) 
            current_df = current_df[current_df['creation_time'] < end_date_inclusive]
            filter_desc.append(f"到 {end_date.strftime('%Y-%m-%d')}")

    # 将多选项目和领域转换为列表
    project_list = projects if isinstance(projects, list) else [projects] if projects else None
    aida_list = aidas if isinstance(aidas, list) else [aidas] if aidas else None
    status_list = statuses if isinstance(statuses, list) else [statuses] if statuses else None
    domain_list = domains if isinstance(domains, list) else [domains] if domains else None
    pu_list = pus if isinstance(pus, list) else [pus] if pus else None
    
    # 按项目过滤 (使用 tproject 列)
    if project_list and 'tproject' in current_df.columns:
        current_df = current_df[current_df['tproject'].isin(project_list)]
        filter_desc.append(f"项目: {', '.join(project_list)}")

    # 按AIDA过滤
    if aida_list and 'aida_english' in current_df.columns:
        current_df = current_df[current_df['aida_english'].isin(aida_list)]
        filter_desc.append(f"AIDA: {', '.join(aida_list)}")
        
    # 按状态过滤
    if status_list and 'status_phase' in current_df.columns:
        current_df = current_df[current_df['status_phase'].isin(status_list)]
        filter_desc.append(f"状态: {', '.join(status_list)}")

    # 按开发组 (Domain) 过滤
    if domain_list and 'domain' in current_df.columns:
        current_df = current_df[current_df['domain'].isin(domain_list)]
        filter_desc.append(f"开发组: {', '.join(domain_list)}")
    
    # 按PU过滤
    if pu_list and 'pu' in current_df.columns:
        current_df = current_df[current_df['pu'].isin(pu_list)]
        filter_desc.append(f"PU: {', '.join(pu_list)}")
    
    filter_description = " | ".join(filter_desc) if filter_desc else None
    
    # 返回过滤后的数据和描述
    return {
        'data': current_df.to_json(orient='split', date_format='iso'),
        'description': filter_description
    }

# 更新矩阵图表
@app.callback(
    Output('matrix-chart', 'figure'),
    Input('filtered-data', 'data')
)
def update_matrix_chart(filtered_data):
    if not filtered_data:
        return create_matrix_figure_flipped(defect_data)
    
    # 从JSON中恢复DataFrame - 使用 io.StringIO
    json_data = filtered_data['data']
    filtered_df = pd.read_json(io.StringIO(json_data), orient='split')
    filter_description = filtered_data['description']
    
    # 创建并返回图表 - 使用上下翻转版本
    return create_matrix_figure_flipped(filtered_df, filtered_by=filter_description)

# 添加新的回调来处理矩阵点击并显示缺陷详情 - 改用DataTable
@app.callback(
    [Output('defect-detail-title', 'children'),
     Output('defect-detail-table', 'data'),
     Output('defect-detail-table', 'tooltip_data')],
    [Input('matrix-chart', 'clickData')],
    [State('filtered-data', 'data')]
)
def update_defect_detail_list(click_data, filtered_data):
    """根据点击的矩阵区域，显示对应的缺陷详情表格"""
    if click_data is None or filtered_data is None:
        raise PreventUpdate # 没有点击或无数据，不更新详情
    
    try:
        # 健壮性检查点击数据结构
        if not click_data.get('points'):
            print("Debug: click_data缺少'points'。")
            raise PreventUpdate # 点击没有命中数据点
            
        point_data = click_data['points'][0]
        
        # 检查点击的点是否包含customdata
        if 'customdata' not in point_data:
            print(f"Debug: 点击的点缺少'customdata'。点击数据: {point_data}")
            raise PreventUpdate # 优雅地停止回调而不显示错误
            
        # 安全地访问customdata，处理各种可能的数据结构
        if isinstance(point_data['customdata'], list) and len(point_data['customdata']) > 0:
            matrix_key = point_data['customdata'][0] # 调整如果customdata=[['1A']]
            if isinstance(matrix_key, list) and len(matrix_key) > 0: # 处理嵌套列表如customdata=[['1A']]
                matrix_key = matrix_key[0]
        else:
            matrix_key = point_data['customdata'] # 如果结构更简单则回退
            
        if not isinstance(matrix_key, str):
            print(f"Debug: 提取的matrix_key不是字符串: {matrix_key}")
            raise PreventUpdate
            
        # 从JSON中恢复过滤后的DataFrame
        json_data = filtered_data['data']
        filtered_df = pd.read_json(io.StringIO(json_data), orient='split')
        
        # 数据验证
        if 'matrix_display' not in filtered_df.columns:
            print("Error: 过滤数据中缺少'matrix_display'列。")
            return f"数据错误: 缺少'matrix_display'列", [], []
            
        # 将matrix_display转换为大写以进行稳健的比较
        filtered_df['matrix_display'] = filtered_df['matrix_display'].astype(str).str.upper()
        
        # 筛选符合选定矩阵的缺陷
        target_matrix_display = f'MATRIX-{matrix_key.upper()}' # 确保比较不区分大小写
        cell_defects = filtered_df[filtered_df['matrix_display'] == target_matrix_display].copy()
        
        if cell_defects.empty:
            return f"Matrix: {matrix_key} - 无符合条件的缺陷数据", [], []
        
        # 构建要显示的列清单 (包括额外的字段)
        display_columns = [
            'id', 'name', 'tproject', 'status_phase', 'tester', 'aida_english', 
            'lead_model', 'ECU Pingpong', 'complexity', 'topissue_display', 'severity_group'
        ]
        
        # 确保所有列都存在，如果不存在则添加空列
        for col in display_columns:
            if col not in cell_defects.columns:
                cell_defects[col] = 'N/A'
        
        # 准备DataTable数据
        table_data = cell_defects[display_columns].to_dict('records')
        
        # 准备悬停提示数据 (显示完整的name字段)
        tooltip_data = [{
            'name': {'value': row['name'], 'type': 'markdown'}
        } for row in table_data]
        
        title = f"Matrix: {matrix_key} - {len(cell_defects)} 个缺陷"
        return title, table_data, tooltip_data
        
    except PreventUpdate:
        raise
    except Exception as e:
        print(f"update_defect_detail_list处理点击时发生错误: {e}")
        traceback.print_exc()
        return f"处理点击时发生错误: {str(e)}", [], []

if __name__ == '__main__':
    app.run(debug=True, port=8053)