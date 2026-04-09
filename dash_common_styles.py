"""
提供常用 Dash 样式设置的工具函数和常量，用于统一所有看板的样式。
"""

import plotly.graph_objects as go
from dash import html, dcc

# 全局样式常量
DARK_BG = '#111827'
DARK_ACCENT = '#1F2937'
HIGHLIGHT_COLOR = '#3B82F6'
TEXT_COLOR = '#F9FAFB'
BORDER_COLOR = '#374151'

# 新增: 浅色主题常量
LIGHT_BG = '#F3F4F6' # 使用柔和的浅灰色背景
LIGHT_TEXT_COLOR = '#111827' # 深灰色文本
LIGHT_BORDER_COLOR = '#E5E7EB'
LIGHT_ACCENT_BG = '#FFFFFF' # 浅色主题的强调背景

# 新增: 筛选器和标签的样式常量
LABEL_STYLE_DARK = {
    'color': TEXT_COLOR,
    'marginBottom': '8px',
    'display': 'block',
    'fontWeight': '500',
    'fontSize': '14px'
}

LABEL_STYLE_LIGHT = {
    'color': '#4B5563',
    'marginBottom': '8px',
    'display': 'block',
    'fontWeight': '500',
    'fontSize': '14px'
}

# Dropdown 样式调整
DROPDOWN_STYLE_DARK = {}
DROPDOWN_STYLE_LIGHT = {}

# 主容器样式
MAIN_CONTAINER_STYLE = {
    'backgroundColor': DARK_BG, 
    'minHeight': '100vh', 
    'padding': '24px', 
    'fontFamily': "'Inter', sans-serif",
    'color': TEXT_COLOR
}

# 新增: 浅色主容器样式
LIGHT_MAIN_CONTAINER_STYLE = {
    'backgroundColor': LIGHT_BG,
    'minHeight': '100vh',
    'padding': '24px',
    'fontFamily': "'Inter', sans-serif",
    'color': LIGHT_TEXT_COLOR
}

# 标题样式
TITLE_STYLE = {
    'textAlign': 'left', 
    'color': TEXT_COLOR, 
    'marginBottom': '24px', 
    'marginTop': '0',
    'fontWeight': '600'
}

LIGHT_TITLE_STYLE = {
    'textAlign': 'left',
    'color': LIGHT_TEXT_COLOR,
    'marginBottom': '24px',
    'marginTop': '0',
    'fontWeight': '600'
}

# 子标题样式
SUBTITLE_STYLE = {
    'textAlign': 'left', 
    'color': '#9CA3AF', 
    'marginBottom': '16px',
    'fontWeight': '500'
}

LIGHT_SUBTITLE_STYLE = {
    'textAlign': 'left',
    'color': '#6B7280',
    'marginBottom': '16px',
    'fontWeight': '500'
}

# 图表容器样式
CHART_CONTAINER_STYLE = {
    'padding': '24px', 
    'backgroundColor': DARK_ACCENT, 
    'borderRadius': '16px', 
    'marginBottom': '24px',
    'border': f'1px solid {BORDER_COLOR}',
    'boxShadow': '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
}

LIGHT_CHART_CONTAINER_STYLE = {
    'padding': '24px',
    'backgroundColor': '#FFFFFF',
    'borderRadius': '16px',
    'marginBottom': '24px',
    'border': f'1px solid {LIGHT_BORDER_COLOR}',
    'boxShadow': '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    'color': LIGHT_TEXT_COLOR
}

# 内容容器样式
CONTENT_CONTAINER_STYLE = {
    'padding': '24px', 
    'backgroundColor': DARK_ACCENT, 
    'borderRadius': '16px', 
    'marginBottom': '24px', 
    'display': 'block',
    'border': f'1px solid {BORDER_COLOR}',
    'boxShadow': '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
}

LIGHT_CONTENT_CONTAINER_STYLE = {
    'padding': '24px',
    'backgroundColor': '#FFFFFF',
    'borderRadius': '16px',
    'marginBottom': '24px',
    'display': 'block',
    'border': f'1px solid {LIGHT_BORDER_COLOR}',
    'boxShadow': '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    'color': LIGHT_TEXT_COLOR
}

# 图表样式（如果未使用 apply_chart_style）
def apply_dark_theme_to_figure(fig, title="", x_title="", y_title="", height=None):
    """应用暗色主题到图表。"""
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_title,
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        font={'color': TEXT_COLOR},
        margin=dict(l=60, r=40, t=50, b=80),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=TEXT_COLOR),
            bgcolor='rgba(0,0,0,0.5)',
            bordercolor=BORDER_COLOR,
            borderwidth=1
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(80, 80, 80, 0.3)',
            showline=True,
            linewidth=1,
            linecolor='rgba(120, 120, 120, 0.7)',
            zeroline=True,
            zerolinecolor='rgba(80, 80, 80, 0.5)',
            zerolinewidth=1
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(80, 80, 80, 0.3)',
            showline=True,
            linewidth=1,
            linecolor='rgba(120, 120, 120, 0.7)',
            zeroline=True,
            zerolinecolor='rgba(80, 80, 80, 0.5)',
            zerolinewidth=1
        ),
        hovermode='closest'
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig

# 新增: 应用浅色主题到图表的函数
def apply_light_theme_to_figure(fig, title="", x_title="", y_title="", height=None):
    """应用浅色主题到图表。"""
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_title,
        paper_bgcolor=LIGHT_BG,       # 使用浅色背景
        plot_bgcolor=LIGHT_BG,        # 使用浅色绘图区背景
        font={'color': LIGHT_TEXT_COLOR}, # 使用浅色主题的文字颜色
        margin=dict(l=60, r=40, t=50, b=80),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color=LIGHT_TEXT_COLOR),
            bgcolor='rgba(255,255,255,0.7)', # 浅色图例背景
            bordercolor=LIGHT_BORDER_COLOR,
            borderwidth=1
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.5)', # 浅色网格线
            showline=True,
            linewidth=1,
            linecolor='rgba(150, 150, 150, 0.7)', # 浅色轴线
            zeroline=True,
            zerolinecolor='rgba(200, 200, 200, 0.5)',
            zerolinewidth=1
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.5)', # 浅色网格线
            showline=True,
            linewidth=1,
            linecolor='rgba(150, 150, 150, 0.7)', # 浅色轴线
            zeroline=True,
            zerolinecolor='rgba(200, 200, 200, 0.5)',
            zerolinewidth=1
        ),
        hovermode='closest'
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig

# 表格样式
def get_datatable_styles(theme='light'):
    """返回DataTable的样式配置，支持主题切换。"""
    if theme == 'dark':
        # 深色主题样式
        return {
            'css': [
                {"selector": ".dash-spreadsheet tr:nth-child(odd)", "rule": "background-color: #000000 !important;"},
                {"selector": ".dash-tooltip", "rule": "background-color: #000000 !important; color: #ffffff !important; border: 1px solid #555555 !important; border-radius: 4px !important; padding: 8px !important;"},
                {"selector": ".dash-tooltip *", "rule": "background-color: transparent !important; color: #ffffff !important;"},
                {"selector": ".dash-tooltip p", "rule": "background-color: transparent !important; color: #ffffff !important;"},
                {"selector": ".dash-tooltip div", "rule": "background-color: transparent !important; color: #ffffff !important;"},
                {"selector": ".dash-tooltip span", "rule": "background-color: transparent !important; color: #ffffff !important;"},
                {"selector": ".dash-spreadsheet tr:hover", "rule": "background-color: #330000 !important; color: #ffffff !important;"},
                {"selector": ".dash-spreadsheet tr:hover td", "rule": "background-color: #330000 !important;"},
                {"selector": ".dash-spreadsheet", "rule": "background-color: #000000 !important;"},
                {"selector": ".dash-spreadsheet-container", "rule": "background-color: #000000 !important;"},
                {"selector": ".dash-spreadsheet table", "rule": "background-color: #000000 !important;"},
                {"selector": ".dash-filter", "rule": "background-color: #000000 !important; color: white !important;"},
                {"selector": "input", "rule": "background-color: #222222 !important; color: white !important; border: 1px solid #555 !important;"}
            ],
            'style_header': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'fontWeight': 'bold',
                'border': '1px solid #333',
                'textAlign': 'left'
            },
            'style_cell': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'border': '1px solid #333',
                'padding': '10px',
                'textAlign': 'left',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'maxWidth': 170
            },
            'style_data': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'border': '1px solid #333'
            },
            'style_filter': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'border': '1px solid #333'
            },
            'style_table': {
                'overflowX': 'auto',
                'maxHeight': '600px',
                'borderCollapse': 'collapse',
                'border': '1px solid #333',
                'backgroundColor': DARK_BG
            }
        }
    else:
        # 浅色主题样式
        return {
            'css': [
                {"selector": ".dash-spreadsheet tr:nth-child(odd)", "rule": "background-color: #F8F9FA !important;"},
                {"selector": ".dash-tooltip", "rule": "background-color: #FFFFFF !important; color: #212529 !important; border: 1px solid #DEE2E6 !important; border-radius: 4px !important; padding: 8px !important;"},
                {"selector": ".dash-tooltip *", "rule": "background-color: transparent !important; color: #212529 !important;"},
                {"selector": ".dash-tooltip p", "rule": "background-color: transparent !important; color: #212529 !important;"},
                {"selector": ".dash-tooltip div", "rule": "background-color: transparent !important; color: #212529 !important;"},
                {"selector": ".dash-tooltip span", "rule": "background-color: transparent !important; color: #212529 !important;"},
                {"selector": ".dash-spreadsheet tr:hover", "rule": "background-color: #E9ECEF !important; color: #212529 !important;"},
                {"selector": ".dash-spreadsheet tr:hover td", "rule": "background-color: #E9ECEF !important;"},
                {"selector": ".dash-spreadsheet", "rule": "background-color: #FFFFFF !important;"},
                {"selector": ".dash-spreadsheet-container", "rule": "background-color: #FFFFFF !important;"},
                {"selector": ".dash-spreadsheet table", "rule": "background-color: #FFFFFF !important;"},
                {"selector": ".dash-filter", "rule": "background-color: #FFFFFF !important; color: #212529 !important;"},
                {"selector": "input", "rule": "background-color: #FFFFFF !important; color: #212529 !important; border: 1px solid #CED4DA !important;"}
            ],
            'style_header': {
                'backgroundColor': '#E9ECEF',
                'color': LIGHT_TEXT_COLOR,
                'fontWeight': 'bold',
                'border': '1px solid #DEE2E6',
                'textAlign': 'left'
            },
            'style_cell': {
                'backgroundColor': '#FFFFFF',
                'color': LIGHT_TEXT_COLOR,
                'border': '1px solid #DEE2E6',
                'padding': '10px',
                'textAlign': 'left',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'maxWidth': 170
            },
            'style_data': {
                'backgroundColor': '#FFFFFF',
                'color': LIGHT_TEXT_COLOR,
                'border': '1px solid #DEE2E6'
            },
            'style_filter': {
                'backgroundColor': '#FFFFFF',
                'color': LIGHT_TEXT_COLOR,
                'border': '1px solid #DEE2E6'
            },
            'style_table': {
                'overflowX': 'auto',
                'maxHeight': '600px',
                'borderCollapse': 'collapse',
                'border': '1px solid #DEE2E6',
                'backgroundColor': '#FFFFFF'
            }
        }

def create_empty_figure(message="加载中...", height=300, theme='light'):
    """创建一个符合指定主题的空图表占位符。"""
    fig = go.Figure()
    
    # 根据主题选择颜色
    if theme == 'dark':
        bg_color = DARK_BG
        text_color = TEXT_COLOR
    else:  # 默认为浅色主题
        bg_color = LIGHT_BG
        text_color = LIGHT_TEXT_COLOR
    
    fig.update_layout(
        height=height,
        xaxis={"visible": False, "showgrid": False, "zeroline": False},
        yaxis={"visible": False, "showgrid": False, "zeroline": False},
        annotations=[{
            "text": message, 
            "xref": "paper", 
            "yref": "paper", 
            "showarrow": False, 
            "font": {"size": 16, "color": text_color}
        }],
        plot_bgcolor=bg_color,
        paper_bgcolor=bg_color
    )
    return fig

# 高亮样式条件（可根据需要自定义）
def get_highlight_conditional_style(column_id, value, bg_color='rgba(102, 0, 0, 0.7)', text_color='white'):
    """创建条件样式，例如高亮特定的值。"""
    return {'if': {'filter_query': f'{{{column_id}}} = "{value}"'}, 
            'backgroundColor': bg_color, 
            'color': text_color}

# Placeholder for theme switching functionality
class ThemeManager:
    def __init__(self, default_theme='light'):
        self.current_theme = default_theme

    def set_theme(self, theme_name):
        self.current_theme = theme_name

    def get_theme(self):
        return self.current_theme

theme_manager = ThemeManager(default_theme='light')  # 明确设置默认为浅色主题

def create_theme_switcher():
    """
    创建主题切换器组件。
    使用 dcc.RadioItems 允许用户选择 'light' 或 'dark'。
    """
    current_theme = theme_manager.get_theme()
    text_color = LIGHT_TEXT_COLOR if current_theme == 'light' else TEXT_COLOR
    
    return dcc.RadioItems(
        id='global-theme-switcher',
        options=[
            {'label': '浅色主题', 'value': 'light'},
            {'label': '深色主题', 'value': 'dark'},
        ],
        value=current_theme, # 默认值，例如 'light'
        labelStyle={'display': 'inline-block', 'marginRight': '15px', 'color': text_color}, 
        inputStyle={'marginRight':'5px'} # 可选：调整单选按钮本身的边距
    )

BOOTSTRAP_CSS_LINK = '<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">'

def get_theme_css(theme_name='light'):
    """根据主题名称返回相应的 CSS 链接或样式字符串。"""
    # 始终包含 Bootstrap CSS 以确保网格系统工作
    # 未来可以根据 theme_name 加载特定主题的 CSS 文件
    # 例如:
    # if theme_name == 'dark':
    #     return BOOTSTRAP_CSS_LINK + '<link rel="stylesheet" href="/assets/dark_theme_override.css">'
    # else:
    #     return BOOTSTRAP_CSS_LINK + '<link rel="stylesheet" href="/assets/light_theme_override.css">'
    return BOOTSTRAP_CSS_LINK