import json
import pandas as pd
import plotly.graph_objects as go
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

# 加载缺陷数据 - 仅在独立运行该模块时执行，避免被其他模块导入时阻塞启动
if __name__ == '__main__':
    defect_data = load_defect_data("defect/*.json")
else:
    defect_data = pd.DataFrame()

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