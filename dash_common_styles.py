"""
提供常用 Dash 样式设置的工具函数和常量，用于统一所有看板的样式。
Vizion-Lab 设计系统配色。
"""

import plotly.graph_objects as go
from dash import html, dcc

# ── Vizion-Lab 调色板 ──────────────────────────────────────────
# HSL references (for CSS variables)
# --primary:        215 70% 48%   → #2266cc
# --success:        152 60% 40%   → #29a066
# --warning:        38 92% 50%    → #f5a623
# --destructive:    0 72% 51%     → #e03e3e
# --background:     220 20% 97%   → #f4f6f9
# --card:           0 0% 100%     → #ffffff
# --border:         220 16% 90%   → #dde3eb
# --muted-foreground: 220 10% 50% → #737d8e
# --foreground:     220 25% 10%   → #131921
# --sidebar-bg:     220 25% 12%   → #171f2b
# --sidebar-fg:     220 10% 75%   → #b0b8c6

# 深色主题常量（保留兼容）
DARK_BG = '#171f2b'
DARK_ACCENT = '#1e2a3a'
HIGHLIGHT_COLOR = '#2a1520'
TEXT_COLOR = '#e2e8f0'
BORDER_COLOR = '#2d3a4a'

# Vizion-Lab 浅色主题常量
LIGHT_BG = '#f4f6f9'
LIGHT_TEXT_COLOR = '#131921'
LIGHT_BORDER_COLOR = '#dde3eb'
LIGHT_ACCENT_BG = '#e8ecf1'

# Vizion-Lab 语义色
PRIMARY_COLOR = '#2266cc'
SUCCESS_COLOR = '#29a066'
WARNING_COLOR = '#f5a623'
DESTRUCTIVE_COLOR = '#e03e3e'
MUTED_TEXT = '#737d8e'
SIDEBAR_BG = '#171f2b'
SIDEBAR_FG = '#b0b8c6'

# 筛选器和标签的样式常量
LABEL_STYLE_DARK = {
    'color': TEXT_COLOR,
    'marginBottom': '5px',
    'display': 'block',
    'fontSize': '0.7rem',
    'fontWeight': '700',
    'letterSpacing': '0.06em',
    'textTransform': 'uppercase',
}

LABEL_STYLE_LIGHT = {
    'color': MUTED_TEXT,
    'marginBottom': '5px',
    'display': 'block',
    'fontSize': '0.7rem',
    'fontWeight': '700',
    'letterSpacing': '0.06em',
    'textTransform': 'uppercase',
}

DROPDOWN_STYLE_DARK = {}
DROPDOWN_STYLE_LIGHT = {}

# 主容器样式
MAIN_CONTAINER_STYLE = {
    'backgroundColor': DARK_BG,
    'minHeight': '100vh',
    'padding': '20px',
    'fontFamily': "'DM Sans', system-ui, sans-serif",
    'color': TEXT_COLOR,
}

LIGHT_MAIN_CONTAINER_STYLE = {
    'backgroundColor': LIGHT_BG,
    'minHeight': '100vh',
    'padding': '20px',
    'fontFamily': "'DM Sans', system-ui, sans-serif",
    'color': LIGHT_TEXT_COLOR,
}

# 标题样式
TITLE_STYLE = {
    'textAlign': 'center',
    'color': TEXT_COLOR,
    'marginBottom': '30px',
    'marginTop': '20px',
    'fontWeight': '700',
    'letterSpacing': '-0.02em',
}

LIGHT_TITLE_STYLE = {
    'textAlign': 'center',
    'color': LIGHT_TEXT_COLOR,
    'marginBottom': '30px',
    'marginTop': '20px',
    'fontWeight': '700',
    'letterSpacing': '-0.02em',
}

# 子标题样式
SUBTITLE_STYLE = {
    'textAlign': 'center',
    'color': MUTED_TEXT,
    'marginBottom': '20px',
    'fontSize': '0.875rem',
}

LIGHT_SUBTITLE_STYLE = {
    'textAlign': 'center',
    'color': MUTED_TEXT,
    'marginBottom': '20px',
    'fontSize': '0.875rem',
}

# 图表容器样式 (vizion-lab: white card, rounded, subtle border)
CHART_CONTAINER_STYLE = {
    'padding': '16px',
    'backgroundColor': '#ffffff',
    'borderRadius': '12px',
    'border': '1px solid #dde3eb',
    'boxShadow': '0 1px 3px rgba(15,23,42,0.06)',
    'marginBottom': '20px',
}

LIGHT_CHART_CONTAINER_STYLE = {
    'padding': '16px',
    'backgroundColor': '#ffffff',
    'borderRadius': '12px',
    'border': '1px solid #dde3eb',
    'boxShadow': '0 1px 3px rgba(15,23,42,0.06)',
    'marginBottom': '20px',
    'color': LIGHT_TEXT_COLOR,
}

# 内容容器样式
CONTENT_CONTAINER_STYLE = {
    'padding': '20px',
    'backgroundColor': DARK_BG,
    'borderRadius': '12px',
    'border': '1px solid #2d3a4a',
    'marginBottom': '20px',
    'display': 'block',
}

LIGHT_CONTENT_CONTAINER_STYLE = {
    'padding': '20px',
    'backgroundColor': '#ffffff',
    'borderRadius': '12px',
    'border': '1px solid #dde3eb',
    'boxShadow': '0 1px 3px rgba(15,23,42,0.06)',
    'marginBottom': '20px',
    'display': 'block',
    'color': LIGHT_TEXT_COLOR,
}

# ── Plotly Layout Template (vizion-lab: minimal, clean) ───────
def _vizion_layout_colors(theme='light'):
    """Return common layout dict for vizion-lab styled charts."""
    if theme == 'dark':
        paper_bg = DARK_BG
        plot_bg = DARK_BG
        font_color = TEXT_COLOR
        grid_col = 'rgba(80, 80, 80, 0.2)'
        line_col = 'rgba(120, 120, 120, 0.3)'
        legend_bg = 'rgba(0,0,0,0.4)'
    else:
        paper_bg = '#ffffff'
        plot_bg = '#ffffff'
        font_color = LIGHT_TEXT_COLOR
        grid_col = 'rgba(0,0,0,0.04)'
        line_col = 'rgba(0,0,0,0.08)'
        legend_bg = 'rgba(255,255,255,0.85)'
    return paper_bg, plot_bg, font_color, grid_col, line_col, legend_bg


def apply_dark_theme_to_figure(fig, title="", x_title="", y_title="", height=None):
    """应用 vizion-lab 风格暗色主题到图表。"""
    paper_bg, plot_bg, font_color, grid_col, line_col, legend_bg = _vizion_layout_colors('dark')

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=font_color)),
        xaxis_title=x_title,
        yaxis_title=y_title,
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        font=dict(family="'DM Sans', system-ui, sans-serif", color=font_color, size=12),
        margin=dict(l=56, r=32, t=48, b=56),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11, color=font_color),
            bgcolor=legend_bg,
            bordercolor=BORDER_COLOR,
            borderwidth=1,
        ),
        xaxis=dict(
            showgrid=False,
            showline=True, linewidth=1, linecolor=line_col,
            zeroline=False,
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            showgrid=True, gridcolor=grid_col,
            showline=True, linewidth=1, linecolor=line_col,
            zeroline=False,
            tickfont=dict(size=11),
        ),
        hovermode='closest',
        hoverlabel=dict(
            bgcolor='#1e2a3a',
            bordercolor='#2d3a4a',
            font=dict(family="'DM Sans', sans-serif", size=12, color='#fff'),
        ),
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig


def apply_light_theme_to_figure(fig, title="", x_title="", y_title="", height=None):
    """应用 vizion-lab 风格浅色主题到图表 (minimal, clean)。"""
    paper_bg, plot_bg, font_color, grid_col, line_col, legend_bg = _vizion_layout_colors('light')

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=font_color)),
        xaxis_title=x_title,
        yaxis_title=y_title,
        paper_bgcolor=paper_bg,
        plot_bgcolor=plot_bg,
        font=dict(family="'DM Sans', system-ui, sans-serif", color=font_color, size=12),
        margin=dict(l=56, r=32, t=48, b=56),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11, color=MUTED_TEXT),
            bgcolor=legend_bg,
            bordercolor=LIGHT_BORDER_COLOR,
            borderwidth=1,
        ),
        xaxis=dict(
            showgrid=False,
            showline=True, linewidth=1, linecolor=line_col,
            zeroline=False,
            tickfont=dict(size=11, color=MUTED_TEXT),
        ),
        yaxis=dict(
            showgrid=True, gridcolor=grid_col,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color=MUTED_TEXT),
        ),
        hovermode='closest',
        hoverlabel=dict(
            bgcolor='#ffffff',
            bordercolor=LIGHT_BORDER_COLOR,
            font=dict(family="'DM Sans', sans-serif", size=12, color=LIGHT_TEXT_COLOR),
        ),
    )
    if height is not None:
        fig.update_layout(height=height)
    return fig


# ── DataTable Styles ───────────────────────────────────────────
def get_datatable_styles(theme='light'):
    """返回 DataTable 的样式配置，vizion-lab 风格。"""
    if theme == 'dark':
        return {
            'css': [
                {"selector": ".dash-spreadsheet tr:nth-child(odd)", "rule": "background-color: #171f2b !important;"},
                {"selector": ".dash-tooltip", "rule": "background-color: #1e2a3a !important; color: #e2e8f0 !important; border: 1px solid #2d3a4a !important; border-radius: 8px !important; padding: 8px !important;"},
                {"selector": ".dash-tooltip *", "rule": "background-color: transparent !important; color: #e2e8f0 !important;"},
                {"selector": ".dash-tooltip p", "rule": "background-color: transparent !important; color: #e2e8f0 !important;"},
                {"selector": ".dash-tooltip div", "rule": "background-color: transparent !important; color: #e2e8f0 !important;"},
                {"selector": ".dash-tooltip span", "rule": "background-color: transparent !important; color: #e2e8f0 !important;"},
                {"selector": ".dash-spreadsheet tr:hover", "rule": "background-color: #1e2a3a !important; color: #ffffff !important;"},
                {"selector": ".dash-spreadsheet tr:hover td", "rule": "background-color: #1e2a3a !important;"},
                {"selector": ".dash-spreadsheet", "rule": "background-color: #171f2b !important;"},
                {"selector": ".dash-spreadsheet-container", "rule": "background-color: #171f2b !important;"},
                {"selector": ".dash-spreadsheet table", "rule": "background-color: #171f2b !important;"},
                {"selector": ".dash-filter", "rule": "background-color: #171f2b !important; color: #e2e8f0 !important;"},
                {"selector": "input", "rule": "background-color: #1e2a3a !important; color: #e2e8f0 !important; border: 1px solid #2d3a4a !important; border-radius: 8px !important;"},
            ],
            'style_header': {
                'backgroundColor': '#1e2a3a',
                'color': TEXT_COLOR,
                'fontWeight': '600',
                'fontSize': '0.75rem',
                'letterSpacing': '0.04em',
                'textTransform': 'uppercase',
                'border': '1px solid #2d3a4a',
                'textAlign': 'left',
            },
            'style_cell': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'border': '1px solid #2d3a4a',
                'padding': '10px 14px',
                'textAlign': 'left',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'maxWidth': 170,
                'fontSize': '0.875rem',
            },
            'style_data': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'border': '1px solid #2d3a4a',
            },
            'style_filter': {
                'backgroundColor': DARK_BG,
                'color': TEXT_COLOR,
                'border': '1px solid #2d3a4a',
            },
            'style_table': {
                'overflowX': 'auto',
                'maxHeight': '600px',
                'borderCollapse': 'collapse',
                'border': '1px solid #2d3a4a',
                'backgroundColor': DARK_BG,
                'borderRadius': '12px',
            },
        }
    else:
        return {
            'css': [
                {"selector": ".dash-spreadsheet tr:nth-child(odd)", "rule": "background-color: #f8fafb !important;"},
                {"selector": ".dash-tooltip", "rule": "background-color: #ffffff !important; color: #131921 !important; border: 1px solid #dde3eb !important; border-radius: 8px !important; padding: 8px !important; box-shadow: 0 4px 12px rgba(15,23,42,0.08) !important;"},
                {"selector": ".dash-tooltip *", "rule": "background-color: transparent !important; color: #131921 !important;"},
                {"selector": ".dash-tooltip p", "rule": "background-color: transparent !important; color: #131921 !important;"},
                {"selector": ".dash-tooltip div", "rule": "background-color: transparent !important; color: #131921 !important;"},
                {"selector": ".dash-tooltip span", "rule": "background-color: transparent !important; color: #131921 !important;"},
                {"selector": ".dash-spreadsheet tr:hover", "rule": "background-color: hsl(215 70% 96%) !important; color: #131921 !important;"},
                {"selector": ".dash-spreadsheet tr:hover td", "rule": "background-color: hsl(215 70% 96%) !important;"},
                {"selector": ".dash-spreadsheet", "rule": "background-color: #ffffff !important;"},
                {"selector": ".dash-spreadsheet-container", "rule": "background-color: #ffffff !important;"},
                {"selector": ".dash-spreadsheet table", "rule": "background-color: #ffffff !important;"},
                {"selector": ".dash-filter", "rule": "background-color: #ffffff !important; color: #131921 !important;"},
                {"selector": "input", "rule": "background-color: #ffffff !important; color: #131921 !important; border: 1px solid #dde3eb !important; border-radius: 8px !important;"},
            ],
            'style_header': {
                'backgroundColor': '#e8ecf1',
                'color': '#737d8e',
                'fontWeight': '600',
                'fontSize': '0.75rem',
                'letterSpacing': '0.04em',
                'textTransform': 'uppercase',
                'border': '1px solid #dde3eb',
                'textAlign': 'left',
            },
            'style_cell': {
                'backgroundColor': '#ffffff',
                'color': LIGHT_TEXT_COLOR,
                'border': '1px solid #dde3eb',
                'padding': '10px 14px',
                'textAlign': 'left',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
                'maxWidth': 170,
                'fontSize': '0.875rem',
            },
            'style_data': {
                'backgroundColor': '#ffffff',
                'color': LIGHT_TEXT_COLOR,
                'border': '1px solid #dde3eb',
            },
            'style_filter': {
                'backgroundColor': '#ffffff',
                'color': LIGHT_TEXT_COLOR,
                'border': '1px solid #dde3eb',
            },
            'style_table': {
                'overflowX': 'auto',
                'maxHeight': '600px',
                'borderCollapse': 'collapse',
                'border': '1px solid #dde3eb',
                'backgroundColor': '#ffffff',
                'borderRadius': '12px',
            },
        }


def create_empty_figure(message="Loading...", height=300, theme='light'):
    """创建一个符合 vizion-lab 风格的空图表占位符。"""
    fig = go.Figure()

    if theme == 'dark':
        bg_color = DARK_BG
        text_color = TEXT_COLOR
    else:
        bg_color = '#ffffff'
        text_color = MUTED_TEXT

    fig.update_layout(
        height=height,
        xaxis={"visible": False, "showgrid": False, "zeroline": False},
        yaxis={"visible": False, "showgrid": False, "zeroline": False},
        annotations=[{
            "text": message,
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "font": {"size": 14, "color": text_color, "family": "'DM Sans', sans-serif"},
        }],
        plot_bgcolor=bg_color,
        paper_bgcolor=bg_color,
    )
    return fig


def get_highlight_conditional_style(column_id, value, bg_color='hsl(0 72% 51% / 0.12)', text_color='hsl(0 72% 51%)'):
    """创建 vizion-lab badge 风格的条件样式。"""
    return {
        'if': {'filter_query': f'{{{column_id}}} = "{value}"'},
        'backgroundColor': bg_color,
        'color': text_color,
    }


# ── Theme Manager ──────────────────────────────────────────────
class ThemeManager:
    def __init__(self, default_theme='light'):
        self.current_theme = default_theme

    def set_theme(self, theme_name):
        self.current_theme = theme_name

    def get_theme(self):
        return self.current_theme


theme_manager = ThemeManager(default_theme='light')


def create_theme_switcher():
    """创建主题切换器组件 (vizion-lab 风格)。"""
    current_theme = theme_manager.get_theme()
    text_color = MUTED_TEXT

    return dcc.RadioItems(
        id='global-theme-switcher',
        options=[
            {'label': ' Light', 'value': 'light'},
            {'label': ' Dark', 'value': 'dark'},
        ],
        value=current_theme,
        labelStyle={
            'display': 'inline-block',
            'marginRight': '12px',
            'color': text_color,
            'fontSize': '0.8rem',
            'fontWeight': '500',
        },
        inputStyle={'marginRight': '4px'},
    )


BOOTSTRAP_CSS_LINK = '<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">'


def get_theme_css(theme_name='light'):
    """根据主题名称返回相应的 CSS 链接或样式字符串。"""
    return BOOTSTRAP_CSS_LINK
