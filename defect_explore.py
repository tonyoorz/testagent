import os
import sys
from pathlib import Path

# 默认关闭 reloader/hot reload，避免运行时文件写入触发服务重载
DISABLE_RELOADER = os.environ.get("DISABLE_RELOADER", "1").lower() in ("1", "true", "yes")

# 早期进程检查：仅在启用 reloader 时，父进程才被视为 reloader 进程
IS_RELOADER = (not DISABLE_RELOADER) and (os.environ.get("WERKZEUG_RUN_MAIN") != "true")

# Windows兼容性设置
if os.name == 'nt':  # Windows系统
    # 确保路径分隔符正确
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    print("🪟 检测到Windows系统，启用兼容模式")

if IS_RELOADER:
    print("🔄 Reloader进程启动，最小化导入...")

import numpy as np
import pandas as pd
from dash_common_styles import create_theme_switcher, get_theme_css, theme_manager, MAIN_CONTAINER_STYLE, LIGHT_MAIN_CONTAINER_STYLE, TEXT_COLOR, LIGHT_TEXT_COLOR, LABEL_STYLE_DARK, LABEL_STYLE_LIGHT, DROPDOWN_STYLE_DARK, DROPDOWN_STYLE_LIGHT, DARK_ACCENT, LIGHT_BORDER_COLOR
from dash import Dash, dcc, html, Input, Output, State, dash_table, no_update, callback_context
import plotly.express as px
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate
import warnings
import httpx
from openai import OpenAI
import json
import hashlib
import re
import time
import sqlite3
import socket
from datetime import datetime
import threading
import queue
import uuid
import logging
from collections import defaultdict
from functools import lru_cache, wraps
import base64
from io import BytesIO, StringIO
from dimension_utils import normalize_dimension_value, build_preferred_dimension, build_chart_dimension, sort_dimension_with_unknown_last

# 统一缓存管理器导入
try:
    from unified_cache_manager import UnifiedCacheManager
    unified_cache_manager = UnifiedCacheManager()
    UNIFIED_CACHE_AVAILABLE = True
    print("✅ 统一缓存管理器已加载")
except ImportError:
    unified_cache_manager = None
    UNIFIED_CACHE_AVAILABLE = False
    print("⚠️ 统一缓存管理器不可用，使用传统缓存机制")
try:
    from wordcloud import WordCloud, STOPWORDS
    # 设置matplotlib后端为非GUI模式，避免macOS上的NSWindow线程问题
    import matplotlib
    matplotlib.use('Agg')  # 使用非GUI后端
    import matplotlib.pyplot as plt
    WORDCLOUD_AVAILABLE = True
except ImportError:
    WORDCLOUD_AVAILABLE = False
    print("⚠️ wordcloud 或 matplotlib 未安装，词云图功能将不可用")
warnings.filterwarnings('ignore')

# 性能监控装饰器
def performance_monitor(func):
    """性能监控装饰器，记录函数执行时间"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            end_time = time.time()
            execution_time = end_time - start_time
            
            # 记录性能数据
            if execution_time > 1.0:  # 只记录执行时间超过1秒的函数
                print(f"⏱️  性能监控: {func.__name__} 执行时间: {execution_time:.2f}秒")
            
            return result
        except Exception as e:
            end_time = time.time()
            execution_time = end_time - start_time
            print(f"❌ 错误监控: {func.__name__} 执行失败 (用时: {execution_time:.2f}秒): {str(e)}")
            raise
    return wrapper

# 简单的性能统计收集器
class PerformanceStats:
    def __init__(self):
        self.stats = defaultdict(list)
        self.error_count = defaultdict(int)
    
    def record(self, function_name, execution_time, success=True):
        self.stats[function_name].append(execution_time)
        if not success:
            self.error_count[function_name] += 1
    
    def get_stats(self):
        """获取性能统计摘要"""
        summary = {}
        for func_name, times in self.stats.items():
            summary[func_name] = {
                'avg_time': sum(times) / len(times),
                'max_time': max(times),
                'min_time': min(times),
                'call_count': len(times),
                'error_count': self.error_count[func_name]
            }
        return summary

# 全局性能统计实例
perf_stats = PerformanceStats()

def extract_status_value(value):
    if isinstance(value, dict):
        if 'name' in value:
            return value['name']
        if 'full_name' in value:
            return value['full_name']
    return value

def get_status_series(current_df):
    if current_df is None or current_df.empty:
        return pd.Series([], dtype=str)
    for col in ['status', 'status_phase', 'phase', 'status.name', 'phase.name']:
        if col in current_df.columns:
            series = current_df[col].apply(extract_status_value)
            series = series.apply(lambda x: str(x) if x is not None else '')
            return series
    return pd.Series([], dtype=str)


def extract_filter_value(value):
    if isinstance(value, dict):
        for key in ('name', 'full_name', 'value', 'id'):
            if key in value and value.get(key) not in (None, ''):
                return str(value.get(key)).strip()
        return ''
    if value is None:
        return ''
    if isinstance(value, float) and pd.isna(value):
        return ''
    return str(value).strip()


def clean_unique_values(series, keep_empty=False):
    unique_values = []
    for value in series.tolist():
        normalized = extract_filter_value(value)
        if normalized:
            unique_values.append(normalized)
        elif keep_empty:
            unique_values.append('')
    return sorted(set(unique_values))


def extract_year_series(dataframe, year_col='year', week_col='test_week'):
    year_series = pd.to_numeric(dataframe[year_col], errors='coerce') if year_col in dataframe.columns else pd.Series(index=dataframe.index, dtype='float64')
    if week_col in dataframe.columns:
        week_series = dataframe[week_col].apply(extract_filter_value)
        extracted_years = pd.to_numeric(week_series.astype(str).str.extract(r'(\d{2,4})\s*-\s*CW')[0], errors='coerce')
        extracted_years = extracted_years.apply(lambda y: y + 2000 if pd.notna(y) and y < 100 else y)
        year_series = extracted_years.where(extracted_years.notna(), year_series)
    return pd.to_numeric(year_series, errors='coerce')


def sort_weeks_with_year(values):
    def sort_key(week_value):
        text = extract_filter_value(week_value)
        match = pd.Series([text]).str.extract(r'(\d{2,4})\s*-\s*CW\s*(\d{1,2})', flags=0)
        year_val = pd.to_numeric(match.iloc[0, 0], errors='coerce')
        week_num = pd.to_numeric(match.iloc[0, 1], errors='coerce')
        if pd.notna(year_val) and year_val < 100:
            year_val = year_val + 2000
        if pd.notna(year_val) and pd.notna(week_num):
            return (0, int(year_val), int(week_num), text)
        return (1, 9999, 99, text)
    return sorted([extract_filter_value(v) for v in values if extract_filter_value(v)], key=sort_key)


DEFECT_STATUS_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
LONG_RUNNER_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


def _normalize_cache_value(value):
    if isinstance(value, dict):
        return {str(k): _normalize_cache_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set)):
        normalized_items = [_normalize_cache_value(v) for v in value]
        return sorted(normalized_items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _build_defect_status_cache_key(cache_payload):
    normalized_payload = _normalize_cache_value(cache_payload)
    payload_text = json.dumps(normalized_payload, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))
    payload_hash = hashlib.md5(payload_text.encode('utf-8')).hexdigest()
    return f"defect_status_chart_v3_{payload_hash}"


def _get_defect_data_signature(current_df):
    """Build a lightweight signature so chart cache invalidates after data refresh."""
    if current_df is None or current_df.empty:
        return "empty"

    row_count = int(len(current_df))
    year_part = ""
    try:
        years = sorted({int(y) for y in extract_year_series(current_df).dropna().astype(int).tolist()})
        year_part = ",".join(str(y) for y in years[:8])
    except Exception:
        year_part = ""

    latest_marker = ""
    for col in ("last_modified", "creation_time", "fetched_at"):
        if col in current_df.columns:
            try:
                latest_val = pd.to_datetime(current_df[col], errors='coerce').max()
                if pd.notna(latest_val):
                    latest_marker = latest_val.isoformat()
                    break
            except Exception:
                continue

    return f"rows={row_count}|years={year_part}|latest={latest_marker}"

# 统一过滤器组件函数
def create_unified_filters(prefix='', active_label_style=None):
    """
    创建统一的过滤器组件，所有页面都使用相同的过滤器ID
    prefix: 过滤器ID前缀，用于区分不同页面（如果需要）
    active_label_style: 标签样式
    """
    if active_label_style is None:
        current_theme = theme_manager.get_theme()
        active_label_style = LABEL_STYLE_LIGHT if current_theme == 'light' else LABEL_STYLE_DARK

    # 预计算 matrix 和 classification 选项（带默认值）
    matrix_options = []
    if 'matrix' in df.columns and not df.empty:
        # 获取所有唯一值，包括空值
        matrix_values = df['matrix'].apply(lambda x: str(x) if isinstance(x, dict) else x).unique()
        # 处理正常值
        valid_options = [{'label': m.replace('Matrix-', '').replace('matrix-', '').upper(), 'value': m}
                         for m in sorted([m for m in matrix_values if pd.notna(m) and m and str(m).strip() != '']) 
                         if m and m.lower().startswith('matrix-')]
        # 检查是否存在空值或Unknown
        has_empty = any(pd.isna(m) or not m or str(m).strip() == '' or str(m) == 'UnknownMatrix' for m in matrix_values)
        if has_empty:
            valid_options.append({'label': 'Unknown/Empty', 'value': 'UnknownMatrix'})
        matrix_options = valid_options

    if not matrix_options:
        default_matrices = ['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E',
                           'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-2D', 'Matrix-2E',
                           'Matrix-3A', 'Matrix-3B', 'Matrix-3C', 'Matrix-3D', 'Matrix-3E',
                           'Matrix-4A', 'Matrix-4B', 'Matrix-4C', 'Matrix-4D', 'Matrix-4E']
        matrix_options = [{'label': m.replace('Matrix-', ''), 'value': m} for m in default_matrices]

    classification_options = []
    if 'classification' in df.columns and not df.empty:
        try:
            classification_values = sorted([cls for cls_list in df['classification']
                                           if isinstance(cls_list, list) for cls in cls_list if cls])
            classification_options = [{'label': cls, 'value': cls} for cls in classification_values]
        except:
            pass
    if not classification_options:
        default_classifications = ['Showstopper_Candidate', 'Showstopper_Confirmed',
                                 'Preventing Maturity Grade ConDrive', 'Obstructing Maturity Grade ConDrive']
        classification_options = [{'label': cls, 'value': cls} for cls in default_classifications]

    status_values = [s for s in sorted(get_status_series(df).replace('nan', '').dropna().unique()) if s]
    status_default_values = [s for s in status_values if str(s)[:2] not in ('06', '08', '09')]
    if not status_default_values:
        status_default_values = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification']

    return html.Div([
        # 第一行过滤器
        html.Div([
            html.Div([
                html.Label('Year:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}year-dropdown',
                    options=[{'label': str(y), 'value': int(y)} for y in sorted({int(y) for y in extract_year_series(df).dropna().astype(int).tolist()})] if not df.empty else [],
                    value=[2026] if (not df.empty and 2026 in set(extract_year_series(df).dropna().astype(int).tolist())) else [],
                    multi=True,
                    clearable=True,
                    placeholder='Select Year...',
                    style={'width': '100%'}
                ),
            ], style={'width': '10%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
            html.Div([
                html.Label('Project:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}project-dropdown',
                    options=[{'label': p, 'value': p} for p in clean_unique_values(df['project'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'project' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select Project...',
                    style={'width': '100%'}
                ),
            ], style={'width': '14.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
            
            html.Div([
                html.Label('Date Range:', style=active_label_style),
                dcc.DatePickerRange(
                    id=f'{prefix}date-range-picker-main',
                    start_date_placeholder_text='Start Date',
                    end_date_placeholder_text='End Date',
                    display_format='YYYY-MM-DD',
                    style={'width': '100%'}
                ),
            ], style={'width': '14.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
            
            html.Div([
                html.Label('AIDA:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}aida-dropdown',
                    options=[{'label': a, 'value': a} for a in clean_unique_values(df['aida_english'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'aida_english' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select AIDA...',
                    style={'width': '100%'}
                ),
            ], style={'width': '14.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
            
            html.Div([
                html.Label('Status:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}status-dropdown',
                    options=[{'label': s, 'value': s} for s in status_values] + [{'label': '09-concluded without action (child)', 'value': '09-concluded without action (child)'}],
                    value=status_default_values,
                    multi=True,
                    clearable=True,
                    placeholder='Select Status...',
                    style={'width': '100%'}
                ),
            ], style={'width': '14.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),

            html.Div([
                html.Label('PU:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}pu-dropdown',
                    options=[{'label': pu_val, 'value': pu_val} for pu_val in clean_unique_values(df['pu'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'pu' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select PU...',
                    style={'width': '100%'}
                ),
            ], style={'width': '14.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),

            html.Div([
                html.Label('Tester:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}tester-dropdown-main',
                    options=[{'label': tester, 'value': tester} for tester in clean_unique_values(df['tester'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'tester' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select Tester...',
                    style={'width': '100%'}
                ),
            ], style={'width': '14.5%', 'display': 'inline-block', 'verticalAlign': 'top'}),
        ], style={'marginBottom': '20px', 'marginTop': '20px'}),
        
        # 第二行过滤器 - FV、ECU、Market、Lead Model和FVP
        html.Div([
            html.Div([
                html.Label('FV (Function Variant):', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}fv-dropdown',
                    options=[{'label': fv, 'value': fv} for fv in clean_unique_values(df['fv'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'fv' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select FV...',
                    style={'width': '100%'}
                ),
            ], style={'width': '18%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            html.Div([
                html.Label('ECU:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}ecu-dropdown',
                    options=[{'label': ecu, 'value': ecu} for ecu in clean_unique_values(df['ecu'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'ecu' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select ECU...',
                    style={'width': '100%'}
                ),
            ], style={'width': '19%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            # Market filter
            html.Div([
                html.Label('Market:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}market-dropdown',
                    options=[{'label': market, 'value': market} for market in clean_unique_values(df['market'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'market' in df.columns else [],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select Market...',
                    style={'width': '100%'}
                ),
            ], style={'width': '18%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            html.Div([
                html.Label('Lead Model:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}lead-model-dropdown',
                    options=[{'label': lm, 'value': lm} for lm in clean_unique_values(df['lead_model'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'lead_model' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select Lead Model...',
                    style={'width': '100%'}
                ),
            ], style={'width': '21%', 'display': 'inline-block', 'marginRight': '1%'}),
            
            html.Div([
                html.Label('FVP:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}fvp-dropdown',
                    options=[{'label': fvp, 'value': fvp} for fvp in clean_unique_values(df['fvp'])] + [{'label': 'Unknown/Empty', 'value': ''}] if 'fvp' in df.columns else [{'label': 'Unknown/Empty', 'value': ''}],
                    value=[],
                    multi=True,
                    clearable=True,
                    placeholder='Select FVP...',
                    style={'width': '100%'}
                ),
            ], style={'width': '18%', 'display': 'inline-block'}),
        ], style={'marginBottom': '20px', 'marginTop': '20px'}),

        # 严重性Matrix选择器
        html.Div([
            html.Div([
                html.Label('Critical Issue Matrix Definition:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}severe-matrix-dropdown',
                    options=matrix_options,
                    value=['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E',
                           'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-3A'],
                    multi=True,
                    clearable=True,
                    placeholder='Select Critical Matrix...',
                    style={'width': '100%'}
                ),
                html.Small('Select which Matrix should be classified as critical issues', style={'color': 'gray'})
            ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),

            html.Div([
                html.Label('Critical Issue Severity Definition:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}severe-classification-dropdown',
                    options=classification_options,
                    value=['Showstopper_Candidate', 'Showstopper_Confirmed', 'Preventing Maturity Grade ConDrive',
                           'Obstructing Maturity Grade ConDrive'],
                    multi=True,
                    clearable=True,
                    placeholder='Select Critical Classification...',
                    style={'width': '100%'}
                ),
                html.Small('Select which Classification should be classified as critical issues', style={'color': 'gray'})
            ], style={'width': '48%', 'display': 'inline-block'})
        ], style={'marginBottom': '20px'}),
    ])

# 词云图生成函数
def generate_wordcloud_figure(text_series, title, width=800, height=400):
    """
    生成词云图并返回为Plotly图表格式
    """
    if not WORDCLOUD_AVAILABLE:
        # 如果wordcloud不可用，返回空图表
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.update_layout(
            title=f"{title} (词云库不可用)",
            height=500,
            annotations=[
                dict(
                    text="需要安装 wordcloud 和 matplotlib 库",
                    x=0.5, y=0.5,
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=16)
                )
            ]
        )
        return fig
    
    try:
        # 过滤掉空字符串、None、NaN 和 'Unknown'
        filtered_series = text_series.dropna().astype(str)
        filtered_series = filtered_series[filtered_series.str.strip() != '']
        filtered_series = filtered_series[filtered_series.str.lower() != 'unknown']
        
        if filtered_series.empty:
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.update_layout(
                title=f"{title} (无有效数据)",
                height=500,
                annotations=[
                    dict(
                        text="没有可用于生成词云的数据",
                        x=0.5, y=0.5,
                        xref="paper", yref="paper",
                        showarrow=False,
                        font=dict(size=16)
                    )
                ]
            )
            return fig
        
        # 将Series中的所有文本合并为一个长字符串
        text = ' '.join(filtered_series.str.lower().tolist())
        
        # 准备停用词集合
        stopwords = set(STOPWORDS)
        additional_common_words = {'tsp', 'cn', 'iuk', 'dips', 'bmw', 'sys', 'mini', 'evo',
                                   'manage', 'aisa', 'provide', 'test', 'via', 'connected',
                                   'international', 'service', 'control', 'asia',
                                   'remote', 'display', 'china', 'chinese'}
        stopwords.update(additional_common_words)
        
        # 创建词云对象
        wordcloud = WordCloud(
            width=width, height=height,
            background_color=None,
            mode='RGBA',
            stopwords=stopwords,
            collocations=False,
            max_words=150,
            relative_scaling=0.6,
            prefer_horizontal=0.7,
            min_font_size=12,
            max_font_size=100,
            colormap='viridis'
        ).generate(text)
        
        # 生成词云图片
        plt.figure(figsize=(width/100, height/100))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis('off')
        
        # 将图片转换为base64
        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150, 
                   transparent=True, facecolor='none', edgecolor='none')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close()  # 关闭图片以释放内存
        
        # 创建Plotly图表
        import plotly.graph_objects as go
        fig = go.Figure()
        
        # 添加图片
        fig.add_layout_image(
            dict(
                source=f"data:image/png;base64,{image_base64}",
                xref="paper", yref="paper",
                x=0, y=1,
                sizex=1, sizey=1,
                sizing="stretch",
                opacity=1,
                layer="below"
            )
        )
        
        # 设置图表布局（移除图上标题，保持与其他图表一致的高度）
        fig.update_layout(
            height=500,  # 增加图表高度
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, visible=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, visible=False),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=0, b=0)  # 移除边距以最大化词云显示区域
        )
        
        return fig
        
    except Exception as e:
        # 错误处理
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.update_layout(
            height=500,  # 统一图表高度
            margin=dict(l=0, r=0, t=0, b=0),
            annotations=[
                dict(
                    text=f"生成词云时出错: {str(e)}",
                    x=0.5, y=0.5,
                    xref="paper", yref="paper",
                    showarrow=False,
                    font=dict(size=14)
                )
            ]
        )
        return fig

# 导入根目录下的数据处理模块 - 条件导入以避免reloader进程执行数据加载
if not IS_RELOADER:
    from data_processor import load_defect_data, load_test_data, apply_filters, apply_chart_style, SEVERITY_COLORS, CHART_HEIGHT, enrich_ddf_with_master_info, calculate_processing_cycle_days, make_ticket_link, get_ecu_transition_path, get_solution_cluster_transition_path, calculate_inflow_outflow_trends, get_inflow_outflow_summary_stats
    from defect_matrix import create_matrix_figure_flipped
else:
    # 为reloader进程提供占位符，避免未定义错误
    load_defect_data = load_test_data = apply_filters = apply_chart_style = None
    SEVERITY_COLORS = CHART_HEIGHT = enrich_ddf_with_master_info = None
    calculate_processing_cycle_days = make_ticket_link = None
    get_ecu_transition_path = get_solution_cluster_transition_path = None
    calculate_inflow_outflow_trends = get_inflow_outflow_summary_stats = None
    create_matrix_figure_flipped = None

_ECU_TRANSITION_PATH_CACHE = {}
_DOMAIN_TRANSITION_PATH_CACHE = {}
_MASTER_LOOKUP = None
_MASTER_STATUS_LOOKUP = None
_MASTER_LOOKUP_SIGNATURE = None

def _cached_ecu_transition_path(defect_id: str) -> str:
    k = str(defect_id)
    v = _ECU_TRANSITION_PATH_CACHE.get(k)
    if v is not None:
        return v
    try:
        path = get_ecu_transition_path(k) if get_ecu_transition_path else ""
    except Exception:
        path = ""
    if not path or path == "No change":
        path = ""
    _ECU_TRANSITION_PATH_CACHE[k] = path
    return path

def _cached_domain_transition_path(defect_id: str) -> str:
    k = str(defect_id)
    v = _DOMAIN_TRANSITION_PATH_CACHE.get(k)
    if v is not None:
        return v
    try:
        path = get_solution_cluster_transition_path(k) if get_solution_cluster_transition_path else ""
    except Exception:
        path = ""
    if not path or path == "No change":
        path = ""
    _DOMAIN_TRANSITION_PATH_CACHE[k] = path
    return path

def _ensure_master_lookups():
    global _MASTER_LOOKUP, _MASTER_STATUS_LOOKUP, _MASTER_LOOKUP_SIGNATURE, master_df
    sig = None
    try:
        if master_df is not None:
            sig = (id(master_df), len(master_df))
    except Exception:
        sig = None
    if sig == _MASTER_LOOKUP_SIGNATURE and _MASTER_LOOKUP is not None and _MASTER_STATUS_LOOKUP is not None:
        return
    _MASTER_LOOKUP_SIGNATURE = sig
    _MASTER_LOOKUP = {}
    _MASTER_STATUS_LOOKUP = {}
    if master_df is None or getattr(master_df, "empty", True):
        return
    try:
        m = master_df
        if "id" not in m.columns:
            return
        ids = m["id"].astype(str)
        name = m["name"] if "name" in m.columns else None
        ecu = m["ecu"] if "ecu" in m.columns else None
        status_phase = m["status_phase"] if "status_phase" in m.columns else None
        phase_name = m["phase.name"] if "phase.name" in m.columns else None
        matrix = m["matrix"] if "matrix" in m.columns else None
        for i in range(len(m)):
            mid = ids.iat[i]
            if not mid:
                continue
            n = name.iat[i] if name is not None else ""
            e = ecu.iat[i] if ecu is not None else ""
            sp = status_phase.iat[i] if status_phase is not None else ""
            pn = phase_name.iat[i] if phase_name is not None else ""
            mx = matrix.iat[i] if matrix is not None else ""
            mx_disp = str(mx).replace('Matrix-', '').replace('matrix-', '').upper() if isinstance(mx, str) and mx else ""
            _MASTER_LOOKUP[mid] = {"id": mid, "name": n, "ecu": e, "status_phase": sp, "phase.name": pn, "matrix_display": mx_disp}
            _MASTER_STATUS_LOOKUP[mid] = pn if pn else sp
    except Exception:
        _MASTER_LOOKUP = {}
        _MASTER_STATUS_LOOKUP = {}

# 导入测试覆盖率组件 - 条件导入
if not IS_RELOADER:
    from test_coverage_components import create_test_coverage_page
    from test_coverage_callbacks import register_test_coverage_callbacks
    # 导入Phase Duration分析模块
    from longrunner_analysis import (
        analyze_ticket_phases, get_all_ticket_ids, 
        calculate_phase_duration, extract_phase_changes
    )
else:
    create_test_coverage_page = register_test_coverage_callbacks = None
    analyze_ticket_phases = get_all_ticket_ids = None
    calculate_phase_duration = extract_phase_changes = None

# 导入AI聊天管理器 - 条件导入
if not IS_RELOADER:
    try:
        # 优先导入 agent/core 增强版AI聊天管理器（支持 SQLite + semantic + tool-calling）
        from agent.core.enhanced_ai_chat_manager import create_enhanced_chat_manager
        AI_CHAT_AVAILABLE = True
        AI_CHAT_ENHANCED = True
        ai_chat_manager = create_enhanced_chat_manager(
            dashboard_type='defect_explore',
            use_agent=True,
            assistant_name='SiSi'
        )
        print("✅ agent/core 增强版AI聊天管理器已加载（智能Agent已启用）")

        # 尝试从基础版导入CSS样式函数
        try:
            from ai_chat_manager import get_chat_css_styles
        except ImportError:
            # 如果基础版不可用，定义空函数
            def get_chat_css_styles():
                return ""
    except ImportError:
        try:
            # 降级到根目录增强版AI聊天管理器
            from enhanced_ai_chat_manager import create_enhanced_chat_manager
            AI_CHAT_AVAILABLE = True
            AI_CHAT_ENHANCED = True
            ai_chat_manager = create_enhanced_chat_manager(
                dashboard_type='defect_explore',
                use_agent=True,
                assistant_name='SiSi'
            )
            print("⚠️  已降级到根目录增强版AI聊天管理器")

            try:
                from ai_chat_manager import get_chat_css_styles
            except ImportError:
                def get_chat_css_styles():
                    return ""
        except ImportError:
            try:
                # 再降级到基础版AI聊天管理器
                from ai_chat_manager import ai_chat_manager, get_chat_css_styles
                AI_CHAT_AVAILABLE = True
                AI_CHAT_ENHANCED = False
                print("⚠️  使用基础版AI聊天管理器（智能Agent不可用）")
            except ImportError:
                print("❌ 警告：无法导入AI聊天管理器")
                AI_CHAT_AVAILABLE = False
                AI_CHAT_ENHANCED = False
                ai_chat_manager = None
                get_chat_css_styles = None
else:
    AI_CHAT_AVAILABLE = False
    AI_CHAT_ENHANCED = False
    ai_chat_manager = None
    get_chat_css_styles = None


# Import optimized data loader and data manager
try:
    from scripts.performance.loaders.data_loader_optimized import get_defect_data
    from scripts.performance.data_manager import get_managed_data, data_manager
    print("✅ Using optimized data loader with caching")
    OPTIMIZED_LOADER_AVAILABLE = True
except ImportError:
    print("⚠️  Optimized data loader not available, using standard loader")
    OPTIMIZED_LOADER_AVAILABLE = False
    data_manager = None

# Global variables for tracking update status - REMOVED





# 缓存版本号 - 修改此值可使缓存失效
_DATA_CACHE_VERSION = "v4_db_first_fast_start"
try:
    DEFAULT_DEFECT_YEAR = int(os.environ.get("DEFAULT_DEFECT_YEAR", "2026"))
except (TypeError, ValueError):
    DEFAULT_DEFECT_YEAR = 2026

FAST_START_MODE = os.environ.get("DEFECT_EXPLORE_FAST_START", "1").lower() in ("1", "true", "yes")
OCTANE_TEAM = os.environ.get("OCTANE_TEAM", "DTSV_China")
_loaded_defect_years = set()
_defect_data_load_lock = threading.Lock()


def _default_octane_db_path():
    env_db_path = os.environ.get("OCTANE_DB_PATH")
    if env_db_path:
        return env_db_path

    rebuilt_path = os.path.join("database", "local_data_rebuilt.db")
    if os.path.exists(rebuilt_path):
        return rebuilt_path

    return os.path.join("database", "local_data.db")


def _load_master_payload_from_db(year):
    db_path = _default_octane_db_path()
    if not db_path or not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT payload_json FROM octane_payloads WHERE kind=? AND team=? AND year=? AND spec=?",
                ("defects_master", OCTANE_TEAM, int(year), ""),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        payload = json.loads(row[0])
        data_list = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data_list, list) and data_list and all(isinstance(item, dict) for item in data_list):
            return data_list
    except Exception:
        return None

    return None


def _normalize_defect_years(years=None):
    """将年份输入标准化为升序元组。"""
    if years is None:
        years = (DEFAULT_DEFECT_YEAR,)

    if isinstance(years, (int, str)):
        years = (years,)

    normalized_years = []
    for year in years:
        if year in (None, ""):
            continue
        try:
            normalized_years.append(int(year))
        except (TypeError, ValueError):
            print(f"⚠️ 无法识别年份值，已跳过: {year}")

    if not normalized_years:
        normalized_years = [DEFAULT_DEFECT_YEAR]

    return tuple(sorted(set(normalized_years)))


def _extract_years_from_date_range(start_date=None, end_date=None):
    """根据日期范围推断需要加载的数据年份。"""
    parsed_dates = []
    for date_val in (start_date, end_date):
        if not date_val:
            continue
        try:
            parsed_dates.append(pd.to_datetime(date_val))
        except Exception:
            print(f"⚠️ 无法解析日期，忽略年份推断: {date_val}")

    if not parsed_dates:
        return (DEFAULT_DEFECT_YEAR,)

    years = set()
    if len(parsed_dates) == 2:
        start_dt = min(parsed_dates)
        end_dt = max(parsed_dates)
        years.update(range(start_dt.year, end_dt.year + 1))
    else:
        years.add(parsed_dates[0].year)

    return _normalize_defect_years(years)


def _combine_yearly_dataframes(dataframes):
    """合并多个年度 DataFrame，保留原有列并尽量维持时间排序。"""
    valid_frames = [frame for frame in dataframes if frame is not None and not frame.empty]
    if not valid_frames:
        return pd.DataFrame()

    combined_df = pd.concat(valid_frames, ignore_index=True, sort=False)
    if 'creation_time' in combined_df.columns:
        try:
            combined_df = combined_df.sort_values('creation_time', ascending=False, na_position='last').reset_index(drop=True)
        except Exception:
            pass

    return combined_df


@lru_cache(maxsize=8)
def _cached_load_master_data(years_key=None, cache_version=None):
    """按年份缓存加载 master 数据。"""
    if cache_version != _DATA_CACHE_VERSION:
        print(f"🔄 master缓存版本变更: {cache_version} -> {_DATA_CACHE_VERSION}")

    years = _normalize_defect_years(years_key)
    master_frames = []

    for year in years:
        master_file_path = f"defect/{year}_defect_master.json"
        data_list = _load_master_payload_from_db(year)

        if data_list:
            print(f"📦 从数据库加载 {year} 年 master 数据 {len(data_list)} 条")
        else:
            if not os.path.exists(master_file_path):
                print(f"⚠️ 未找到 {year} 年 master 文件且数据库无数据: {master_file_path}")
                continue

        try:
            if data_list is None:
                with open(master_file_path, encoding="utf8") as f:
                    loaded_json = json.load(f)

                if isinstance(loaded_json, dict) and "data" in loaded_json and isinstance(loaded_json["data"], list):
                    data_list = loaded_json["data"]
                elif isinstance(loaded_json, list):
                    data_list = loaded_json
                else:
                    print(f"警告: 主票据文件 {master_file_path} 的 JSON 结构不符合预期。")
                    continue

            if not data_list:
                continue

            year_master_df = pd.json_normalize(data_list, max_level=1)
            if year_master_df.empty:
                continue

            if 'phase' in year_master_df.columns:
                year_master_df["status_phase"] = year_master_df["phase"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else "")
            else:
                year_master_df["status_phase"] = ""

            if 'detected_by' in year_master_df.columns:
                year_master_df["tester"] = year_master_df["detected_by"].apply(lambda x: x.get("full_name", "") if isinstance(x, dict) else "")
            else:
                year_master_df["tester"] = ""

            if 'user_tags' in year_master_df.columns:
                year_master_df["tags"] = year_master_df["user_tags"].apply(
                    lambda x: [i.get("name", "") for i in x.get("data", [])] if isinstance(x, dict) and "data" in x else []
                )
            else:
                year_master_df["tags"] = [[] for _ in range(len(year_master_df))]

            def extract_matrix(tags):
                if isinstance(tags, list) and tags:
                    matrix_tags = [tag for tag in tags if isinstance(tag, str) and tag.lower().startswith('matrix-')]
                    return matrix_tags[0] if matrix_tags else ""
                return ""

            year_master_df["matrix"] = year_master_df["tags"].apply(extract_matrix)
            year_master_df["matrix_display"] = year_master_df["matrix"].fillna("未分类")

            if 'reporting_class_udf' in year_master_df.columns:
                year_master_df["classification"] = year_master_df["reporting_class_udf"].apply(
                    lambda x: [i.get("name", "") for i in x.get("data", [])]
                    if isinstance(x, dict) and "data" in x and isinstance(x["data"], list)
                    else []
                )
            else:
                year_master_df["classification"] = [[] for _ in range(len(year_master_df))]

            year_master_df['classification_display'] = year_master_df['classification'].apply(
                lambda x: ', '.join(x) if isinstance(x, list) else str(x) if x is not None else '未分类'
            )

            if 'product_areas' in year_master_df.columns:
                year_master_df["aidas"] = year_master_df["product_areas"].apply(
                    lambda x: [i.get("name", "") for i in x.get("data", [])] if isinstance(x, dict) and "data" in x else []
                )
                year_master_df['aida_english'] = year_master_df['aidas'].apply(
                    lambda x: x[0] if isinstance(x, list) and len(x) > 0 else ""
                )
            else:
                year_master_df["aidas"] = [[] for _ in range(len(year_master_df))]
                year_master_df['aida_english'] = ""

            if 'assigned_ecu_udf' in year_master_df.columns:
                year_master_df["ecu"] = year_master_df["assigned_ecu_udf"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else "")
            else:
                year_master_df["ecu"] = ""

            year_master_df['data_year'] = year
            master_frames.append(year_master_df)
            print(f"✅ 成功加载 {year} 年 master 数据 {len(year_master_df)} 条")

        except Exception as e:
            print(f"警告: 处理主票据文件 {master_file_path} 时发生错误: {e}")

    return _combine_yearly_dataframes(master_frames)


@lru_cache(maxsize=8)
def _cached_load_defect_data(years_key=None, cache_version=None):
    """按年份缓存加载缺陷数据，默认仅加载当前配置年份。"""
    if cache_version != _DATA_CACHE_VERSION:
        print(f"🔄 defect缓存版本变更: {cache_version} -> {_DATA_CACHE_VERSION}")

    years = _normalize_defect_years(years_key)
    defect_frames = []

    for year in years:
        print(f"📊 加载 {year} 年缺陷数据...")
        year_df = load_defect_data(f"defect/{year}_defect.json")
        if year_df is None or year_df.empty:
            print(f"⚠️ {year} 年缺陷数据为空")
            continue

        year_df = enrich_ddf_with_master_info(year_df, master_file_path=f"defect/{year}_defect_master.json")
        year_df['data_year'] = year
        defect_frames.append(year_df)
        print(f"✅ 成功加载 {year} 年缺陷数据 {len(year_df)} 条")

    return _combine_yearly_dataframes(defect_frames)


def ensure_defect_data_for_date_range(start_date=None, end_date=None):
    """根据筛选日期范围按需补载缺陷数据。"""
    global df, master_df, _loaded_defect_years

    required_years = set(_extract_years_from_date_range(start_date, end_date))
    missing_years = sorted(required_years - _loaded_defect_years)
    if not missing_years:
        return

    with _defect_data_load_lock:
        missing_years = sorted(required_years - _loaded_defect_years)
        if not missing_years:
            return

        target_years = _normalize_defect_years(tuple(_loaded_defect_years.union(required_years)))
        print(f"⏳ 检测到跨年份筛选，补载年份: {missing_years}，当前目标年份集合: {target_years}")
        df = _cached_load_defect_data(target_years, cache_version=_DATA_CACHE_VERSION)
        master_df = _cached_load_master_data(target_years, cache_version=_DATA_CACHE_VERSION)
        _loaded_defect_years = set(target_years)
        print(f"✅ 缺陷数据补载完成，已加载年份: {sorted(_loaded_defect_years)}，总行数: {len(df)}")

# 导入统一缓存管理器
try:
    from scripts.performance.cache.cache_manager import default_cache_manager
    CACHE_MANAGER_AVAILABLE = True
except ImportError:
    default_cache_manager = None
    CACHE_MANAGER_AVAILABLE = False
    print("⚠️ 缓存管理器不可用，将使用基础缓存")

def _cached_load_test_data():
    """使用统一缓存管理器的测试数据加载函数"""
    cache_key = "test_status_data_v4_multi_year"
    
    # 尝试从统一缓存获取
    if CACHE_MANAGER_AVAILABLE and default_cache_manager:
        cached_result = default_cache_manager.get(cache_key)
        if cached_result is not None:
            print(f"从缓存加载 {len(cached_result)} 条测试数据")
            return cached_result
    
    try:
        print("加载测试管理数据...")
        test_df = load_test_data()
        print(f"成功加载 {len(test_df)} 条测试数据")
        
        # 存储到统一缓存（缓存1小时）
        if CACHE_MANAGER_AVAILABLE and default_cache_manager:
            default_cache_manager.set(cache_key, test_df, timeout=3600)
            
        return test_df
    except Exception as e:
        print(f"测试数据加载失败: {e}")
        return pd.DataFrame()

@performance_monitor
def load_application_data(force_reload=False, initial_years=None):
    """
    Optimized application data loading function - now loads both defect and test data
    """
    global df, test_df, master_df, _loaded_defect_years
    if initial_years is None:
        # 快速启动模式仅加载默认年份；非快速模式才预加载两年。
        if FAST_START_MODE:
            target_years = _normalize_defect_years((DEFAULT_DEFECT_YEAR,))
        else:
            startup_years = (DEFAULT_DEFECT_YEAR - 1, DEFAULT_DEFECT_YEAR)
            target_years = _normalize_defect_years(startup_years)
    else:
        target_years = _normalize_defect_years(initial_years)
    
    if force_reload:
        # 使用统一缓存管理器清除所有缓存
        try:
            if 'unified_cache_manager' in globals():
                print("🧹 使用统一缓存管理器清除所有缓存...")
                unified_cache_manager.clear_all_caches()
            else:
                # 回退到传统缓存清理
                print("🧹 使用传统方式清除缓存...")
                _cached_load_defect_data.cache_clear()
                _cached_load_master_data.cache_clear()
                _cached_load_test_data.cache_clear()
        except Exception as e:
            print(f"⚠️ 缓存清理失败，使用传统方式: {e}")
            _cached_load_defect_data.cache_clear()
            _cached_load_master_data.cache_clear()
            _cached_load_test_data.cache_clear()
        _loaded_defect_years = set()
    
    print(f"🎯 启动仅加载缺陷年份: {target_years}")
    df = _cached_load_defect_data(target_years, cache_version=_DATA_CACHE_VERSION)
    master_df = _cached_load_master_data(target_years, cache_version=_DATA_CACHE_VERSION)
    _loaded_defect_years = set(target_years)

    # 数据清理：确保 classification 列没有 None 值
    if 'classification' in df.columns:
        df['classification'] = df['classification'].apply(lambda x: x if isinstance(x, list) else [])

    # 加载测试数据
    test_df = _cached_load_test_data()

    return df, test_df

# 初始化数据加载
print("🎯 正在初始化应用数据...")

# 显示优化状态
if OPTIMIZED_LOADER_AVAILABLE:
    print("✅ 性能优化已启用:")
    print("   • 数据管理器缓存")
    print("   • 历史数据预加载") 
    print("   • 单例数据管理")
else:
    print("📊 使用标准加载模式")

def ensure_dropdown_data(df):
    """确保筛选器有基本数据，即使加载失败"""
    if df is None or df.empty:
        print("⚠️  数据为空，创建默认筛选器选项")
        # 创建一个包含基本列的空DataFrame
        df = pd.DataFrame({
            'project': ['项目数据加载中...'],
            'fv': ['FV数据加载中...'], 
            'fvp': ['FVP数据加载中...'],
            'aida_english': ['AIDA数据加载中...'],
            'status_phase': ['状态数据加载中...'],
            'ecu': ['ECU数据加载中...'],
            'lead_model': ['Lead Model数据加载中...']
        })
    else:
        # 检查关键列是否存在且不为空
        for col in ['project', 'fv', 'fvp', 'aida_english', 'status_phase', 'ecu', 'lead_model']:
            if col not in df.columns or df[col].dropna().empty:
                print(f"⚠️  列 '{col}' 为空，添加默认值")
                df[col] = df[col].fillna(f'{col}数据加载中...')
    return df

try:
    # 检查是否是reloader进程以避免重复初始化
    if IS_RELOADER:
        print("🔄 这是reloader进程，跳过所有数据加载...")
        df = pd.DataFrame()
        test_df = pd.DataFrame()
        master_df = pd.DataFrame()
        # 设置空的筛选器数据避免错误
        projects_list = ['示例项目']
        aidas_list = ['示例AIDA'] 
        fvs_list = ['示例FV']
        print("✅ Reloader进程初始化完成")
    else:
        print("🚀 主进程开始数据加载...")
        df, test_df = load_application_data()
        
        # 验证缺陷数据是否有效
        if df is None or df.empty:
            print("警告: 缺陷数据为空，创建默认空DataFrame")
            df = pd.DataFrame()
        else:
            print(f"成功加载 {len(df)} 条缺陷数据")
            
        # 验证测试数据是否有效
        if test_df is None or test_df.empty:
            print("警告: 测试数据为空，创建默认空DataFrame")
            test_df = pd.DataFrame()
        else:
            print(f"成功加载 {len(test_df)} 条测试数据")
            
        # 确保必要的列存在，防止访问不存在的列导致错误
        required_columns = ['project', 'ecu', 'aida_english', 'status_phase', 'pu', 'tester', 
                          'creation_time', 'matrix', 'classification', 'severity_group',
                          'fv', 'fvp', 'lead_model', 'market']
        
        # 如果df为空，创建一个带有必要列的空DataFrame
        if df.empty:
             df = pd.DataFrame(columns=required_columns)
        
        for col in required_columns:
            if col not in df.columns:
                if col == 'severity_group':
                    df[col] = 'General Issues'  # 默认值
                elif col == 'classification':
                    df[col] = [[]]  # 空列表的列表
                else:
                    df[col] = ''  # 空字符串默认值
                print(f"添加缺失列: {col}")
        
        # 处理NaN值
        df = df.fillna({
            'project': '未知项目',
            'ecu': '未知项目',
            'aida_english': '未知AIDA',
            'status_phase': '未知状态',
            'pu': '未知PU',
            'tester': '未知测试员',
            'matrix': '',
            'severity_group': 'General Issues',
            'fv': 'Unknown',
            'fvp': 'Unknown',
            'lead_model': '',
            'market': ''
        })
            
except Exception as e:
    print(f"数据加载失败: {e}")
    # 创建一个最小的默认DataFrame以防止应用崩溃
    df = pd.DataFrame({
        'project': ['示例项目'],
        'ecu': ['示例项目'],
        'aida_english': ['示例AIDA'],
        'status_phase': ['示例状态'],
        'pu': ['示例PU'],
        'tester': ['示例测试员'],
        'creation_time': [pd.Timestamp.now()],
        'matrix': [''],
        'classification': [[]],
        'severity_group': ['General Issues']
    })
    test_df = pd.DataFrame({
        'test_id': ['示例测试'],
        'project': ['示例项目'],
        'aida_english': ['示例AIDA'],
        'run_status': ['示例状态'],
        'tester': ['示例测试员'],
        'test_week': ['2025-CW01']
    })
    print("使用默认示例数据")

# 启动优化预加载（如果使用优化加载器）
if OPTIMIZED_LOADER_AVAILABLE and (not IS_RELOADER):
    if FAST_START_MODE:
        print("⚡ FAST_START_MODE 已启用，跳过启动时历史预加载")
        print("   历史数据将按需加载")
    else:
        try:
            print("📚 初始化历史数据缓存...")
            from data_processor import history_cache

            # 延迟启动历史数据预加载（避免阻塞启动）
            def delayed_history_preload():
                import time
                time.sleep(5)  # 等5秒让应用完全启动

                try:
                    if 'df' in globals() and df is not None and not df.empty and 'id' in df.columns:
                        defect_ids = df['id'].astype(str).tolist()[:50]
                        if defect_ids:
                            print(f"🚀 后台预加载 {len(defect_ids)} 个历史记录...")
                            history_cache.preload_histories(defect_ids, max_workers=4)
                            print("✅ 历史数据预加载完成")
                except Exception as e:
                    print(f"历史预加载失败: {e}")

            # 启动延迟后台线程
            import threading
            history_thread = threading.Thread(target=delayed_history_preload, daemon=True)
            history_thread.start()
        except Exception as e:
            print(f"⚠️  历史缓存初始化失败: {e}")
            print("   历史数据将按需加载")

# --- High Runner Helper Functions ---
def count_linked_defects_hr(relation_str):
    """Counts linked defects from a comma-separated string in relation_to_udf."""
    if pd.isna(relation_str) or not isinstance(relation_str, str) or relation_str.strip() == '':
        return 0
    return len([item for item in relation_str.split(',') if item.strip()])

def categorize_defect_level_hr(count):
    """Categorizes defect level based on child_count_of_master. Aligned with TopIssue risk scoring thresholds."""
    if pd.isna(count) or count < 3:
        return 'Low'      # <3个子票
    elif 3 <= count < 5:
        return 'Medium'   # 3-4个子票
    elif count >= 5:
        return 'High'     # ≥5个子票
    return 'Unknown'

def categorize_master_linked_level_hr(count):
    """Categorizes master ticket linked defect level based on relation_to_udf count. Aligned with TopIssue risk scoring thresholds."""
    if count < 3:
        return 'Low'      # <3个链接缺陷
    elif 3 <= count < 5:
        return 'Medium'   # 3-4个链接缺陷
    elif count >= 5:
        return 'High'     # ≥5个链接缺陷
    return 'None'

def create_child_complexity_line_chart_hr(ddf_input, relevant_weeks_for_axis_display):
    """Create child complexity line chart for high runner page"""
    try:
        from dash_common_styles import create_empty_figure
    except ImportError:
        # Fallback empty figure creation
        import plotly.graph_objects as go
        def create_empty_figure(title, height=400, theme="light"):
            fig = go.Figure()
            fig.update_layout(
                title=title,
                height=height,
                xaxis=dict(title="测试周 (CW)"),
                yaxis=dict(title="子缺陷数量")
            )
            return fig
    
    if ddf_input.empty:
        return create_empty_figure("Child Complexity (数据为空)", height=400, theme=theme_manager.get_theme())

    ddf = ddf_input.copy()
    if 'defect_level' not in ddf.columns or 'test_week_sortable' not in ddf.columns:
        return create_empty_figure("Child Complexity (缺少必要列)", height=400, theme=theme_manager.get_theme())
    
    # 筛选只包含 Child 和 Child (candidate) 类型的票据
    if 'parent_child' in ddf.columns:
        valid_child_types = ['Child', 'Child (candidate)']
        ddf_child_only = ddf[ddf['parent_child'].isin(valid_child_types)]
        if ddf_child_only.empty:
            return create_empty_figure("Child Complexity (没有符合条件的 Child 类型票据)", height=400, theme=theme_manager.get_theme())
        ddf = ddf_child_only
        
    if relevant_weeks_for_axis_display:
        ddf_filtered = ddf[ddf['test_week_sortable'].isin(relevant_weeks_for_axis_display)]
    else:
        ddf_filtered = ddf

    if ddf_filtered.empty:
        return create_empty_figure("Child Complexity (筛选周后数据为空)", height=400, theme=theme_manager.get_theme())

    line_data = ddf_filtered.groupby(['test_week_sortable', 'defect_level'], observed=True, dropna=False).size().reset_index(name='count')
    if line_data.empty:
        return create_empty_figure("Child Complexity (分组后数据为空)", height=400, theme=theme_manager.get_theme())

    fig = px.line(
        line_data, x='test_week_sortable', y='count', color='defect_level',
        labels={'count': '子缺陷数量', 'test_week_sortable': '测试周 (CW)', 'defect_level': '子缺陷等级'},
        markers=True, category_orders={'defect_level': ['High', 'Medium', 'Low', 'Unknown']},
        color_discrete_map={'Low': 'green', 'Medium': 'yellow', 'High': 'red', 'Unknown': 'grey'},
        custom_data=['defect_level', 'test_week_sortable', 'count']
    )
    # Apply chart style if available, otherwise apply basic styling
    if apply_chart_style is not None:
        fig = apply_chart_style(fig, title="Child Complexity (按子缺陷等级划分)", x_title="测试周 (CW)", y_title="子缺陷数量")
    else:
        fig.update_layout(
            title="Child Complexity (按子缺陷等级划分)",
            xaxis_title="测试周 (CW)",
            yaxis_title="子缺陷数量",
            height=400
        )
    if relevant_weeks_for_axis_display:
        fig.update_xaxes(type='category', categoryorder='array', categoryarray=relevant_weeks_for_axis_display)
    elif not line_data.empty:
        sorted_weeks = sorted(line_data['test_week_sortable'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique().tolist())
        fig.update_xaxes(type='category', categoryorder='array', categoryarray=sorted_weeks)
    return fig

def create_parent_complexity_line_chart_hr(ddf_input, relevant_weeks_for_axis_display):
    """Create parent complexity line chart for high runner page"""
    try:
        from dash_common_styles import create_empty_figure
    except ImportError:
        # Fallback empty figure creation
        import plotly.graph_objects as go
        def create_empty_figure(title, height=400, theme="light"):
            fig = go.Figure()
            fig.update_layout(
                title=title,
                height=height,
                xaxis=dict(title="测试周 (CW)"),
                yaxis=dict(title="父票据数量")
            )
            return fig
    
    if ddf_input.empty:
        return create_empty_figure("Parent Complexity (数据为空)", height=400, theme=theme_manager.get_theme())

    # Filter for actual Parent tickets for the chart itself
    ddf_parents_for_chart = ddf_input[ddf_input['parent_child'] == 'Parent'].copy()
    if ddf_parents_for_chart.empty:
        return create_empty_figure("Parent Complexity (无Parent票据数据)", height=400, theme=theme_manager.get_theme())
        
    if 'master_linked_defect_level' not in ddf_parents_for_chart.columns or 'test_week_sortable' not in ddf_parents_for_chart.columns:
        return create_empty_figure("Parent Complexity (缺少必要列)", height=400, theme=theme_manager.get_theme())

    if relevant_weeks_for_axis_display:
        ddf_filtered = ddf_parents_for_chart[ddf_parents_for_chart['test_week_sortable'].isin(relevant_weeks_for_axis_display)]
    else:
        ddf_filtered = ddf_parents_for_chart
        
    if ddf_filtered.empty:
        return create_empty_figure("Parent Complexity (筛选周后数据为空)", height=400, theme=theme_manager.get_theme())

    valid_levels = ['High', 'Medium', 'Low']
    line_data = ddf_filtered[
        ddf_filtered['master_linked_defect_level'].isin(valid_levels)
    ].groupby(['test_week_sortable', 'master_linked_defect_level'], observed=True).size().reset_index(name='count')

    if line_data.empty:
        return create_empty_figure("Parent Complexity (分组后数据为空)", height=400, theme=theme_manager.get_theme())
        
    fig = px.line(
        line_data, x='test_week_sortable', y='count', color='master_linked_defect_level',
        labels={'count': '父票据数量', 'test_week_sortable': '测试周 (CW)', 'master_linked_defect_level': '父票据关联等级'},
        markers=True, category_orders={'master_linked_defect_level': valid_levels},
        color_discrete_map={'Low': 'green', 'Medium': 'orange', 'High': 'red'},
        custom_data=['master_linked_defect_level', 'test_week_sortable', 'count']
    )
    # Apply chart style if available, otherwise apply basic styling
    if apply_chart_style is not None:
        fig = apply_chart_style(fig, title="Parent Complexity (按父票据关联等级)", x_title="测试周 (CW)", y_title="父票据数量")
    else:
        fig.update_layout(
            title="Parent Complexity (按父票据关联等级)",
            xaxis_title="测试周 (CW)",
            yaxis_title="父票据数量",
            height=400
        )
    if relevant_weeks_for_axis_display:
        fig.update_xaxes(type='category', categoryorder='array', categoryarray=relevant_weeks_for_axis_display)
    elif not line_data.empty:
        sorted_weeks = sorted(line_data['test_week_sortable'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique().tolist())
        fig.update_xaxes(type='category', categoryorder='array', categoryarray=sorted_weeks)
    return fig


# 添加linked_defect_count字段计算 - 用于Parent Child Count显示
def count_linked_defects(relation_str):
    """计算relation_to_udf中的缺陷数量"""
    if not relation_str or pd.isna(relation_str):
        return 0
    try:
        # 假设relation_to_udf是逗号分隔的ID列表
        ids = str(relation_str).split(',')
        return len([id.strip() for id in ids if id.strip()])
    except:
        return 0

# 新增函数：加载完整的master数据
def load_master_data(master_file_path=None):
    """
    加载完整的master数据，用于获取父票的详细信息
    """
    if master_file_path:
        year_match = re.search(r"(\d{4})", master_file_path)
        target_years = (int(year_match.group(1)),) if year_match else (DEFAULT_DEFECT_YEAR,)
    else:
        target_years = tuple(sorted(_loaded_defect_years)) if _loaded_defect_years else (DEFAULT_DEFECT_YEAR,)

    return _cached_load_master_data(target_years, cache_version=_DATA_CACHE_VERSION)

# 加载master数据
master_df = load_master_data()

@performance_monitor
def filter_dataframe(df, years=None, projects=None, start_date=None, end_date=None, aidas=None, statuses=None, pus=None, testers=None, fvs=None, ecus=None, lead_models=None, fvps=None, markets=None):
    """通用数据筛选函数"""
    ensure_defect_data_for_date_range(start_date, end_date)
    filtered_df = globals().get('df', df).copy()

    if years:
        try:
            years_norm = [int(y) for y in years if str(y).strip().isdigit()]
            if years_norm:
                year_series = extract_year_series(filtered_df)
                filtered_df = filtered_df[year_series.astype('Int64').isin(years_norm)]
        except Exception:
            pass

    if projects and 'project' in filtered_df.columns:
        project_values = filtered_df['project'].apply(extract_filter_value)
        project_targets = {extract_filter_value(p) for p in projects}
        filtered_df = filtered_df[project_values.isin(project_targets)]

    # 日期范围筛选
    if start_date or end_date:
        # 自动适配常见时间字段
        time_field = None
        for candidate in ['creation_time', 'create_time', 'created_at', 'ticket_create_time', '创建时间']:
            if candidate in filtered_df.columns:
                time_field = candidate
                break
        if not time_field:
            print("[警告] 未找到任何可用的时间字段，已跳过日期筛选。可用字段：", filtered_df.columns.tolist())
        else:
            try:
                filtered_df[time_field] = pd.to_datetime(filtered_df[time_field], errors='coerce')
                if start_date and end_date:
                    before_count = len(filtered_df)
                    filtered_df = filtered_df[
                        (filtered_df[time_field].dt.date >= pd.to_datetime(start_date).date()) &
                        (filtered_df[time_field].dt.date <= pd.to_datetime(end_date).date())
                    ]
                    print(f"日期筛选 - 开始日期: {start_date}, 结束日期: {end_date}, 筛选前: {before_count}, 筛选后: {len(filtered_df)}")
            except Exception as e:
                print(f"日期筛选错误: {e}")
                print(f"start_date: {start_date}, end_date: {end_date}")
                print(f"{time_field}样本: {filtered_df[time_field].head()}")

    # AIDA筛选
    if aidas and 'aida_english' in filtered_df.columns:
        aida_values = filtered_df['aida_english'].apply(extract_filter_value)
        aida_targets = {extract_filter_value(a) for a in aidas}
        filtered_df = filtered_df[aida_values.isin(aida_targets)]

    # PU筛选
    if pus and 'pu' in filtered_df.columns:
        pu_values = filtered_df['pu'].apply(extract_filter_value)
        pu_targets = {extract_filter_value(pu) for pu in pus}
        filtered_df = filtered_df[pu_values.isin(pu_targets)]

    # Tester筛选
    if testers and 'tester' in filtered_df.columns:
        tester_values = filtered_df['tester'].apply(extract_filter_value)
        tester_targets = {extract_filter_value(t) for t in testers}
        filtered_df = filtered_df[tester_values.isin(tester_targets)]

    # FV筛选
    if fvs and 'fv' in filtered_df.columns:
        fv_values = filtered_df['fv'].apply(extract_filter_value)
        fv_targets = {extract_filter_value(fv) for fv in fvs}
        filtered_df = filtered_df[fv_values.isin(fv_targets)]

    # ECU筛选
    if ecus and 'ecu' in filtered_df.columns:
        ecu_values = filtered_df['ecu'].apply(extract_filter_value)
        ecu_targets = {extract_filter_value(ecu) for ecu in ecus}
        filtered_df = filtered_df[ecu_values.isin(ecu_targets)]

    # Lead Model筛选
    if lead_models and 'lead_model' in filtered_df.columns:
        lead_values = filtered_df['lead_model'].apply(extract_filter_value)
        lead_targets = {extract_filter_value(m) for m in lead_models}
        filtered_df = filtered_df[lead_values.isin(lead_targets)]

    # FVP筛选
    if fvps and 'fvp' in filtered_df.columns:
        fvp_values = filtered_df['fvp'].apply(extract_filter_value)
        fvp_targets = {extract_filter_value(v) for v in fvps}
        filtered_df = filtered_df[fvp_values.isin(fvp_targets)]

    if statuses:
        special_child_status = "09-concluded without action (child)"
        if special_child_status in statuses and 'status_phase' in filtered_df.columns and 'blocking_reason' in filtered_df.columns:
            normal_statuses = [s for s in statuses if s != special_child_status]
            normal_statuses.append("09-Concluded without action")
            if len(statuses) == 1 and statuses[0] == special_child_status:
                filtered_df = filtered_df[
                    (filtered_df['status_phase'] == '09-Concluded without action') &
                    (filtered_df['blocking_reason'] == 'Child (Duplicate)')
                ]
            else:
                filtered_df = filtered_df[filtered_df['status_phase'].isin(normal_statuses)]
        else:
            status_series = get_status_series(filtered_df)
            if not status_series.empty:
                filtered_df = filtered_df[status_series.isin(statuses)]

    # Market筛选
    if markets and 'market' in filtered_df.columns:
        market_values = filtered_df['market'].apply(extract_filter_value)
        market_targets = {extract_filter_value(m) for m in markets}
        filtered_df = filtered_df[market_values.isin(market_targets)]

    return filtered_df

# Long Runner Analysis - Phase Duration Analysis Content
def create_long_runner_analysis_content(active_label_style):
    """创建Long Runner Analysis页面内容"""
    available_years = sorted({int(y) for y in extract_year_series(df).dropna().astype(int).tolist()}) if not df.empty else []
    year_options = sorted(set(available_years + [2026]))
    
    # 数据加载函数
    def load_defect_info():
        """从defect数据文件加载ticket名称和tester信息"""
        defect_info = {}
        defect_file = 'defect/2025_defect.json'
        
        if os.path.exists(defect_file):
            try:
                with open(defect_file, 'r', encoding='utf-8') as f:
                    defects = json.load(f)
                
                for defect in defects:
                    ticket_id = str(defect.get('id', ''))
                    ticket_name = defect.get('name', f'Ticket {ticket_id}')
                    
                    # 正确提取tester信息从detected_by字段
                    detected_by = defect.get('detected_by', {})
                    if isinstance(detected_by, dict):
                        tester = detected_by.get('full_name', 'Unknown')
                    else:
                        tester = 'Unknown'
                    
                    defect_info[ticket_id] = {
                        'name': ticket_name[:100],  # 限制长度
                        'tester': tester
                    }
            except Exception as e:
                print(f"加载defect信息时出错: {e}")
        
        return defect_info

    def bulk_analyze_phases_live(history_folder: str = 'history') -> dict:
        """实时批量分析所有ticket的phase duration"""
        print("开始从真实数据源分析phase durations...")
        
        # 加载defect信息（名称和tester）
        defect_info = load_defect_info()
        
        # 获取所有ticket IDs
        ticket_ids = get_all_ticket_ids(history_folder)
        
        all_durations = defaultdict(list)  # phase_name -> [duration1, duration2, ...]
        ticket_details = defaultdict(list)  # phase_name -> [ticket_detail1, ticket_detail2, ...]
        successful_analyses = 0
        failed_analyses = 0
        
        for i, ticket_id in enumerate(ticket_ids):
            result = analyze_ticket_phases(ticket_id, history_folder)
            
            if 'error' in result:
                failed_analyses += 1
                continue
                
            successful_analyses += 1
            
            # 收集每个phase的duration数据和详细信息
            for duration in result.get('phase_durations', []):
                phase_transition = f"{duration['from_phase']} → {duration['to_phase']}"
                all_durations[phase_transition].append(duration['duration_hours'])
                
                # 获取真实的ticket信息
                ticket_info = defect_info.get(ticket_id, {'name': f"Ticket {ticket_id}", 'tester': 'Unknown'})
                ticket_name = ticket_info['name']
                tester = ticket_info['tester']
                
                # 保存详细的ticket信息
                ticket_details[phase_transition].append({
                    'ticket_id': ticket_id,
                    'ticket_name': ticket_name,
                    'duration_hours': duration['duration_hours'],
                    'duration_days': round(duration['duration_hours'] / 24, 2),
                    'start_time': duration['start_time'],
                    'end_time': duration['end_time'],
                    'changed_by': duration['changed_by'],
                    'tester': tester,
                    'from_phase': duration['from_phase'],
                    'to_phase': duration['to_phase']
                })
        
        return {
            'phase_durations': dict(all_durations),
            'ticket_details': dict(ticket_details),
            'successful_count': successful_analyses,
            'failed_count': failed_analyses
        }

    def calculate_phase_statistics_live(phase_durations: dict) -> pd.DataFrame:
        """从实时数据计算phase transition统计信息"""
        statistics_data = []
        
        for phase_transition, durations in phase_durations.items():
            if durations:
                avg_hours = sum(durations) / len(durations)
                stats = {
                    'Phase_Transition': phase_transition,
                    'Count': len(durations),
                    'Avg_Hours': round(avg_hours, 2),
                    'Avg_Days': round(avg_hours / 24, 2),
                    'Min_Hours': round(min(durations), 2),
                    'Max_Hours': round(max(durations), 2),
                    'Median_Hours': round(sorted(durations)[len(durations)//2], 2),
                    'Phase_From': phase_transition.split(' → ')[0],
                    'Phase_To': phase_transition.split(' → ')[1],
                    'Total_Hours': round(avg_hours * len(durations), 2)
                }
                statistics_data.append(stats)
        
        expected_cols = [
            'Phase_Transition', 'Count', 'Avg_Hours', 'Avg_Days',
            'Min_Hours', 'Max_Hours', 'Median_Hours', 'Phase_From', 'Phase_To', 'Total_Hours'
        ]
        if not statistics_data:
            return pd.DataFrame(columns=expected_cols)

        df = pd.DataFrame(statistics_data)
        if 'Avg_Days' not in df.columns:
            return pd.DataFrame(columns=expected_cols)
        return df.sort_values('Avg_Days', ascending=False)

    # 创建页面布局
    return html.Div([
        html.H2("Long Runner Analysis - Phase Duration Dashboard", 
                style={'textAlign': 'center', 'marginBottom': '30px', **active_label_style}),
        
        # 数据状态显示
        html.Div([
            html.Div(id='phase-data-status', style={'textAlign': 'center', 'marginBottom': '20px'})
        ]),
        
        # 筛选器区域
        html.Div([
            html.H3("筛选条件", style=active_label_style),
            html.Div([
                html.Div([
                    html.Label('最小样本量:', style=active_label_style),
                    dcc.Slider(
                        id='phase-min-count-slider',
                        min=1,
                        max=100,
                        step=1,
                        value=1,
                        marks={i: str(i) for i in [1, 10, 25, 50, 100]},
                        tooltip={"placement": "bottom", "always_visible": True}
                    )
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '3%'}),
                
                html.Div([
                    html.Label('Phase类型:', style=active_label_style),
                    dcc.Dropdown(
                        id='phase-type-dropdown',
                        options=[
                            {'label': '全部', 'value': 'all'},
                            {'label': '正常流程', 'value': 'normal'},
                            {'label': '回退流程', 'value': 'rollback'},
                            {'label': '结束流程', 'value': 'conclusion'}
                        ],
                        value='all',
                        style={'backgroundColor': 'white'}
                    )
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '3%'}),

                html.Div([
                    html.Label('Year:', style=active_label_style),
                    dcc.Dropdown(
                        id='long-runner-year-dropdown',
                        options=[{'label': str(y), 'value': int(y)} for y in year_options],
                        value=[2026],
                        multi=True,
                        clearable=True,
                        placeholder='Select Year...',
                        style={'backgroundColor': 'white'}
                    )
                ], style={'width': '30%', 'display': 'inline-block'})
            ], style={'marginBottom': '20px'})
        ], style={'padding': '15px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px', 'marginBottom': '20px'}),
        
        # 图表区域
        html.Div([
            dcc.Graph(id='phase-duration-bar-chart-lr'),
            
            # Phase Duration统计表
            html.Div([
                html.H4("Phase Duration统计", style=active_label_style),
                dash_table.DataTable(
                    id='phase-stats-table-lr',
                    columns=[
                        {'name': 'Phase Transition', 'id': 'Phase_Transition', 'type': 'text'},
                        {'name': 'Count', 'id': 'Count', 'type': 'numeric'},
                        {'name': 'Avg Days', 'id': 'Avg_Days', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Min Days', 'id': 'Min_Days', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Max Days', 'id': 'Max_Days', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                        {'name': 'Std Dev', 'id': 'Std_Days', 'type': 'numeric', 'format': {'specifier': '.2f'}}
                    ],
                    data=[],
                    style_cell={
                        'textAlign': 'left',
                        'padding': '10px',
                        'fontFamily': 'Arial',
                        'fontSize': '13px'
                    },
                    style_header={
                        'backgroundColor': '#3498db',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'textAlign': 'center'
                    },
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#f8f9fa'
                        }
                    ],
                    sort_action='native',
                    page_size=20
                )
            ], style={'marginTop': '30px', 'marginBottom': '20px'}),
            
            # 点击提示信息
            html.Div([
                html.Div(id='phase-click-info-lr', style={'marginBottom': '20px'})
            ], style={'marginTop': '30px'})
        ], style={'marginTop': '20px'}),
        
        # 模态框（Modal）用于显示ticket详细信息
        html.Div([
            # 遮罩层 - 点击可关闭模态框
            html.Div(id='ticket-details-modal-lr-overlay', style={
                'position': 'absolute',
                'top': '0',
                'left': '0',
                'width': '100%',
                'height': '100%',
                'zIndex': '1',
                'pointerEvents': 'auto'
            }),
            html.Div([
                # 模态框内容
                html.Div([
                    # 模态框头部
                    html.Div([
                        html.H3(id='modal-title-lr', style={'margin': '0', 'color': '#2c3e50'}),
                        html.Button([
                            html.I(className="fas fa-times")
                        ], id='close-modal-lr', style={
                            'position': 'absolute',
                            'top': '15px',
                            'right': '15px',
                            'background': 'none',
                            'border': 'none',
                            'fontSize': '20px',
                            'cursor': 'pointer',
                            'color': '#666'
                        })
                    ], style={
                        'position': 'relative',
                        'padding': '20px',
                        'borderBottom': '1px solid #eee'
                    }),
                    
                    # 模态框主体
                    html.Div([
                        html.Div(id='modal-phase-info-lr', style={'marginBottom': '20px'}),
                        html.Div([
                            dash_table.DataTable(
                                id='modal-ticket-details-table-lr',
                                columns=[
                                    {'name': 'Ticket ID', 'id': 'ticket_id', 'type': 'text'},
                                    {'name': 'Ticket Name', 'id': 'ticket_name', 'type': 'text'},
                                    {'name': '耗时(天)', 'id': 'duration_days', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                                    {'name': '耗时(小时)', 'id': 'duration_hours', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                                    {'name': '开始时间', 'id': 'start_time', 'type': 'text'},
                                    {'name': '结束时间', 'id': 'end_time', 'type': 'text'},
                                    {'name': 'Tester', 'id': 'tester', 'type': 'text'}
                                ],
                                data=[],
                                sort_action='native',
                                page_action='native',
                                page_size=10,
                                style_cell={
                                    'textAlign': 'left', 
                                    'padding': '8px', 
                                    'fontSize': '12px',
                                    'whiteSpace': 'normal',
                                    'height': 'auto'
                                },
                                style_header={
                                    'backgroundColor': '#2ecc71', 
                                    'color': 'white', 
                                    'fontWeight': 'bold'
                                },
                                style_data={
                                    'whiteSpace': 'normal', 
                                    'height': 'auto'
                                }
                            )
                        ])
                    ], style={'padding': '20px'})
                ], style={
                    'backgroundColor': 'white',
                    'borderRadius': '8px',
                    'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)',
                    'maxWidth': '90vw',
                    'maxHeight': '80vh',
                    'overflow': 'auto',
                    'position': 'relative',
                    'zIndex': '10'
                })
            ], style={
                'position': 'fixed',
                'top': '0',
                'left': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0, 0, 0, 0.5)',
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'zIndex': '9999'
            })
        ], id='ticket-details-modal-lr', style={'display': 'none'})
    ])

# 初始化Dash应用
import dash_bootstrap_components as dbc
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], assets_folder='assets', suppress_callback_exceptions=True)
server = app.server  # 暴露给 Gunicorn 使用

# 创建侧边导航栏组件
def create_sidebar_nav():
    """创建可展开/隐藏的侧边导航栏"""
    nav_items = [
        {'id': 'tab-chat', 'label': 'SiSi Chat', 'icon': 'fas fa-comments'},
        {'id': 'tab-defect-status', 'label': 'Topissue analysis', 'icon': 'fas fa-chart-bar'},
        {'id': 'tab-project-analysis', 'label': 'Project Analysis', 'icon': 'fas fa-project-diagram'},
        {'id': 'tab-testing-team', 'label': 'Testing Team Analysis', 'icon': 'fas fa-users'},
        {'id': 'tab-test-coverage', 'label': 'Test Coverage Analysis', 'icon': 'fas fa-tasks'},
        {'id': 'tab-test-status', 'label': 'Test Status Analysis', 'icon': 'fas fa-flask'},
        {'id': 'tab-testing-efficiency', 'label': 'Defect Status Analysis', 'icon': 'fas fa-chart-line'},
    ]
    
    return html.Div([
        # 导航栏切换按钮 - 位置调整为导航栏外侧
        html.Button(
            [html.I(className="fas fa-bars", style={'fontSize': '18px'})],
            id='nav-toggle-btn',
            className='nav-toggle-btn',
            style={
                'position': 'fixed',
                'top': '20px',
                'left': '290px',  # 放在导航栏右侧
                'zIndex': '1001',
                'backgroundColor': '#28a745',
                'color': 'white',
                'border': 'none',
                'padding': '12px',
                'borderRadius': '6px',
                'cursor': 'pointer',
                'fontSize': '16px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.3)',
                'transition': 'all 0.3s ease'
            }
        ),
        
        # 边缘条 - 当侧边栏关闭时显示
        html.Div([
            html.Button(
                [html.I(className="fas fa-chevron-right", style={'fontSize': '12px', 'color': 'white'})],
                id='nav-edge-toggle-btn',
                style={
                    'position': 'absolute',
                    'top': '50%',
                    'left': '50%',
                    'transform': 'translate(-50%, -50%)',
                    'backgroundColor': 'transparent',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '8px',
                    'borderRadius': '50%',
                    'transition': 'background-color 0.3s ease'
                }
            )
        ],
        id='nav-edge-bar',
        style={
            'position': 'fixed',
            'top': '90px',
            'left': '-30px',  # 默认隐藏
            'width': '30px',
            'height': 'calc(100vh - 90px)',
            'backgroundColor': '#2c3e50',
            'zIndex': '999',
            'transition': 'left 0.3s ease',
            'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center'
        }),
        
        # 侧边导航栏
        html.Div([
            # 导航栏头部
            html.Div([
                html.H3("Navigation", style={
                    'color': 'white',
                    'margin': '0',
                    'padding': '20px',
                    'borderBottom': '1px solid #444',
                    'fontSize': '18px'
                }),
                html.Button(
                    [html.I(className="fas fa-times", style={'fontSize': '16px'})],
                    id='nav-close-btn',
                    style={
                        'position': 'absolute',
                        'top': '15px',
                        'right': '15px',
                        'backgroundColor': 'transparent',
                        'color': 'white',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '5px',
                        'borderRadius': '3px'
                    }
                )
            ], style={'position': 'relative'}),
            
            # 导航项目
            html.Div([
                html.Div([
                    html.I(className=item['icon'], style={'marginRight': '12px', 'width': '20px'}),
                    html.Span(item['label'])
                ], 
                id=f"nav-{item['id']}", 
                className='nav-item',
                style={
                    'padding': '15px 20px',
                    'cursor': 'pointer',
                    'borderLeft': '4px solid transparent',
                    'color': 'white',
                    'transition': 'all 0.3s ease',
                    'display': 'flex',
                    'alignItems': 'center',
                    'fontSize': '14px'
                }) for item in nav_items
            ])
        ], 
        id='sidebar-nav',
        className='sidebar-nav',
        style={
            'position': 'fixed',
            'top': '90px',  # 从标题栏下方开始
            'left': '0px',  # 默认显示
            'width': '280px',
            'height': 'calc(100vh - 90px)',  # 调整高度以适应标题栏
            'backgroundColor': '#2c3e50',
            'zIndex': '1000',
            'transition': 'left 0.3s ease',
            'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
            'overflowY': 'auto'
        }),
        
        # 遮罩层
        html.Div(
            id='nav-overlay',
            style={
                'position': 'fixed',
                'top': '0',
                'left': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.5)',
                'zIndex': '999',
                'display': 'none'
            }
        ),
        
        # 边缘条 - 用于在导航栏隐藏时快速访问
        html.Div([
            html.Button(
                [html.I(className="fas fa-chevron-right", style={'fontSize': '14px'})],
                id='nav-edge-toggle-btn-2',
                style={
                    'width': '100%',
                    'height': '50px',
                    'backgroundColor': 'transparent',
                    'border': 'none',
                    'color': 'white',
                    'cursor': 'pointer',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center'
                }
            )
        ], 
        id='nav-edge-bar-2',
        style={
            'position': 'fixed',
            'top': '90px',
            'left': '-30px',  # 默认隐藏
            'width': '30px',
            'height': 'calc(100vh - 90px)',
            'backgroundColor': '#2c3e50',
            'zIndex': '999',
            'transition': 'left 0.3s ease',
            'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center'
        }),
        
        # 存储当前选中的导航项
        dcc.Store(id='current-nav-item', data='tab-defect-status'),
        dcc.Store(id='filtered-data-store', data=None)
    ])

# 应用布局
app.layout = html.Div([
    # 顶部固定标题栏 - 贯穿整个页面宽度
    html.Div([
        # 主题切换器
        html.Div([
            create_theme_switcher()
        ], style={'position': 'absolute', 'top': '10px', 'right': '20px', 'zIndex': '1005'}),
        
        # 主标题
        html.H1("DTSV Testing and Defect Data Analysis Dashboard", id='main-title', style={
            'textAlign': 'center', 
            'margin': '0', 
            'padding': '25px 0',
            'fontSize': '32px',
            'fontWeight': 'bold',
            'color': '#2c3e50'
        })
    ], style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '90px',  # 固定标题栏高度
        'backgroundColor': 'white',
        'borderBottom': '2px solid #e5e7eb',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
        'zIndex': '1002'
    }),
    
    # 侧边导航栏 - 移到标题下方
    create_sidebar_nav(),
    
    # 主内容区域 - 添加左边距以适应导航栏
    html.Div([
        # 内容区域 - 使用回调动态加载内容
        html.Div(id='tabs-content'),
    ], id='main-content-wrapper', style={
        'marginLeft': '300px',  # 默认为导航栏留出空间
        'marginTop': '110px',  # 为固定标题栏留出空间
        'transition': 'margin-left 0.3s ease',
        'minHeight': 'calc(100vh - 110px)',
        'padding': '20px'
    }),
    
    # 缺陷详情Modal弹窗
    html.Div(
        id='defect-modal',
        children=[
            # 遮罩层 - 点击可关闭模态框
            html.Div(id='defect-modal-overlay', style={
                'position': 'absolute',
                'top': '0',
                'left': '0',
                'width': '100%',
                'height': '100%',
                'zIndex': '1',
                'pointerEvents': 'auto'
            }),
            html.Div(
                id='modal-content',
                children=[
                    html.Div([
                        html.H3("缺陷详情", style={
                            'margin': '0', 
                            'display': 'inline-block', 
                            'color': '#1f2937',
                            'fontSize': '20px',
                            'fontWeight': '600'
                        }),
                        html.Button(
                            "×", 
                            id='close-modal-btn',
                            style={
                                'float': 'right',
                                'border': 'none',
                                'background': 'transparent',
                                'fontSize': '28px',
                                'cursor': 'pointer',
                                'color': '#6b7280',
                                'padding': '0',
                                'width': '32px',
                                'height': '32px',
                                'borderRadius': '4px',
                                'transition': 'all 0.2s ease'
                            }
                        )
                    ], style={
                        'borderBottom': '2px solid #f3f4f6', 
                        'paddingBottom': '12px', 
                        'marginBottom': '18px',
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'space-between'
                    }),
                    
                    html.Div(id='modal-info', style={
                        'marginBottom': '16px', 
                        'fontSize': '13px', 
                        'color': '#4b5563',
                        'backgroundColor': '#f8fafc',
                        'padding': '8px 12px',
                        'borderRadius': '6px',
                        'border': '1px solid #e5e7eb',
                        'fontWeight': '500'
                    }),
                    
                    dash_table.DataTable(
                        id='modal-defect-table',
                        columns=[
                            {'name': 'ID', 'id': 'id', 'presentation': 'markdown'},
                            {'name': 'Name', 'id': 'name', 'type': 'text'},
                            {'name': 'ECU', 'id': 'ecu', 'type': 'text'},
                            {'name': 'Creation Time', 'id': 'creation_time', 'type': 'text'},
                            {'name': 'Matrix', 'id': 'matrix_display', 'type': 'text'},
                            {'name': 'Classification', 'id': 'classification_display', 'type': 'text'},
                            {'name': 'ECU Transfer', 'id': 'ecu_pingpong_display', 'type': 'text'},
                            {'name': 'Domain Transfer', 'id': 'domain_pingpong_display', 'type': 'text'},
                            {'name': 'Parent/Child', 'id': 'parent_child_display', 'type': 'text'},
                            {'name': 'Master Child Count', 'id': 'child_count_display', 'type': 'numeric'},
                            {'name': 'Parent Child Count', 'id': 'parent_child_count_display', 'type': 'numeric'},
                            {'name': 'Master Ticket Info', 'id': 'parent_ticket_info', 'type': 'text'},
                            {'name': 'Process Days', 'id': 'processing_cycle_days', 'type': 'numeric'},
                            {'name': 'PU', 'id': 'pu', 'type': 'text'},
                            {'name': 'Shift PU', 'id': 'Shift_PU', 'type': 'text'},
                            {'name': 'Risk Score', 'id': 'topissue_display', 'type': 'text'},
                            {'name': 'TopIssue Recommendation Reason', 'id': 'topissue_recommend_reason', 'type': 'text'},
                            {'name': 'AIDA', 'id': 'aida_english', 'type': 'text'},
                            {'name': 'Status', 'id': 'status_phase', 'type': 'text'},
                            {'name': 'Reporter', 'id': 'tester', 'type': 'text'},
                            {'name': 'Master Status', 'id': 'master_status', 'type': 'text'}
                        ],
                        # 排序功能 - 支持多列排序
                        sort_action='native',
                        sort_mode='multi',
                        # 筛选功能 - 每列都有筛选输入框
                        filter_action='native',
                        filter_options={'placeholder_text': 'Filter column...'},
                        # 列宽调整功能 - 启用表格自动调整和列调整功能
                        css=[{
                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table',
                            'rule': 'table-layout: auto; border-collapse: separate; border-spacing: 0;'
                        }, {
                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner .column-header--resizable',
                            'rule': 'cursor: col-resize;'
                        }, {
                            'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner .column-header',
                            'rule': 'position: sticky; top: 0; z-index: 10; background-color: #f8fafc !important;'
                        }, {
                            'selector': '.dash-spreadsheet-container',
                            'rule': 'position: relative;'
                        }],
                        # 固定表头设置
                        fixed_rows={'headers': True},
                        # 分页
                        page_action='native',
                        page_current=0,
                        page_size=30,
                        style_table={
                            'overflowX': 'auto', 
                            'maxHeight': '650px', 
                            'overflowY': 'auto', 
                            'border': '1px solid #e5e7eb', 
                            'borderRadius': '8px', 
                            'boxShadow': '0 2px 8px 0 rgba(0, 0, 0, 0.1)',
                            'backgroundColor': 'white',
                            'minWidth': '1200px',
                            'width': '100%'
                        },
                        style_cell={
                            'textAlign': 'left',
                            'padding': '5px 8px',
                            'whiteSpace': 'nowrap',
                            'overflow': 'hidden',
                            'textOverflow': 'ellipsis',
                            'height': 'auto',
                            'fontSize': '11px',
                            'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                            'border': '1px solid #e5e7eb',
                            'borderCollapse': 'collapse',
                            'color': '#374151',
                            'lineHeight': '1.3'
                        },
                        style_header={
                            'backgroundColor': '#f8fafc',
                            'fontWeight': '600',
                            'fontSize': '12px',
                            'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                            'border': '1px solid #e5e7eb',
                            'color': '#374151',
                            'textAlign': 'center',
                            'padding': '8px 10px'
                        },
                        style_cell_conditional=[
                            # 基本信息列 - 前6列，约570px
                            {
                                'if': {'column_id': 'id'},
                                'width': '60px',
                                'minWidth': '60px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'name'},
                                'width': '200px',
                                'minWidth': '180px',
                                'maxWidth': '220px'
                            },
                            {
                                'if': {'column_id': 'ecu'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'creation_time'},
                                'width': '120px',
                                'minWidth': '100px',
                                'maxWidth': '140px'
                            },
                            {
                                'if': {'column_id': 'matrix_display'},
                                'width': '80px',
                                'minWidth': '70px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'classification_display'},
                                'width': '120px',
                                'minWidth': '100px',
                                'maxWidth': '150px'
                            },
                            # 流转信息列 - 第7-8列，约200px
                            {
                                'if': {'column_id': 'ecu_pingpong_display'},
                                'width': '100px',
                                'minWidth': '90px',
                                'maxWidth': '120px'
                            },
                            {
                                'if': {'column_id': 'domain_pingpong_display'},
                                'width': '100px',
                                'minWidth': '90px',
                                'maxWidth': '120px'
                            },
                            # 关系信息列 - 第9-12列，约300px
                            {
                                'if': {'column_id': 'parent_child_display'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'child_count_display'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'parent_child_count_display'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'parent_ticket_info'},
                                'width': '120px',
                                'minWidth': '100px',
                                'maxWidth': '140px'
                            },
                            # 状态信息列 - 第13-15列，约180px
                            {
                                'if': {'column_id': 'processing_cycle_days'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'pu'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'Shift_PU'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            # 风险信息列 - 第16-17列，约220px
                            {
                                'if': {'column_id': 'topissue_display'},
                                'width': '60px',
                                'minWidth': '50px',
                                'maxWidth': '70px'
                            },
                            {
                                'if': {'column_id': 'topissue_recommend_reason'},
                                'width': '320px',
                                'minWidth': '300px',
                                'maxWidth': '350px'
                            },
                            # 执行信息列 - 最后4列，约320px
                            {
                                'if': {'column_id': 'aida_english'},
                                'width': '80px',
                                'minWidth': '70px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'status_phase'},
                                'width': '80px',
                                'minWidth': '70px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'tester'},
                                'width': '80px',
                                'minWidth': '70px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'master_status'},
                                'width': '80px',
                                'minWidth': '70px',
                                'maxWidth': '90px'
                            },
                            # 特殊文本列处理 - 允许换行的列
                            {
                                'if': {'column_id': 'name'},
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            {
                                'if': {'column_id': 'classification_display'},
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            {
                                'if': {'column_id': 'ecu_pingpong_display'},
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            {
                                'if': {'column_id': 'domain_pingpong_display'},
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            {
                                'if': {'column_id': 'parent_ticket_info'},
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            },
                            {
                                'if': {'column_id': 'topissue_recommend_reason'},
                                'whiteSpace': 'pre-line',
                                'height': 'auto',
                                'textAlign': 'left'
                            },
                            {
                                'if': {'column_id': 'aida_english'},
                                'whiteSpace': 'normal',
                                'height': 'auto'
                            }
                        ],
                        style_data_conditional=[
                            {
                                'if': {'filter_query': '{severity_group} = "Critical Issues"'},
                                'backgroundColor': '#fef2f2',
                                'fontWeight': '500',
                                'border': '1px solid #fecaca'
                            },
                            {
                                'if': {'filter_query': '{is_topissue} = true'},
                                'fontWeight': 'bold',
                                'backgroundColor': '#fffbeb',
                                'border': '1px solid #fed7aa'
                            },
                            {
                                'if': {'column_id': 'Shift_PU'}, 
                                'color': '#dc2626', 
                                'fontWeight': '500'
                            }
                        ]
                    )
                ],
                style={
                    'backgroundColor': 'white',
                    'padding': '25px',
                    'borderRadius': '12px',
                    'boxShadow': '0 20px 60px rgba(0,0,0,0.3), 0 8px 25px rgba(0,0,0,0.15)',
                    'border': '1px solid #e5e7eb',
                    'width': '96%',
                    'maxWidth': '1700px',
                    'maxHeight': '85vh',
                    'overflowY': 'auto',
                    'position': 'relative',
                    'transform': 'scale(1)',
                    'transition': 'all 0.3s ease',
                    'zIndex': '10'
                }
            )
        ],
        style={
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.65)',
            'justifyContent': 'center',
            'alignItems': 'center',
            'backdropFilter': 'blur(2px)'
        }
    ),
    
    # 定时器组件，用于定期更新状态
    dcc.Interval(
        id='interval-component',
        interval=2*1000,  # 每2秒更新一次
        n_intervals=0
    ),
    
    # 导航状态存储
    dcc.Store(id='nav-open-state', data=True),
    
    # 搜索结果信息显示区域
    html.Div(id='search-results-info', style={'display': 'none'}),
    
    # AI聊天模态框
    html.Div(id='ai-chat-modal', children=[
        # 遮罩层 - 点击可关闭模态框
        html.Div(id='ai-chat-modal-overlay', style={
            'position': 'absolute',
            'top': '0',
            'left': '0',
            'width': '100%',
            'height': '100%',
            'zIndex': '1'
        }),
        # 模态框内容
        html.Div([
            # 模态框头部
            html.Div([
                html.H3("🤖 SiSi", style={
                    'margin': '0',
                    'color': '#2c3e50',
                    'fontSize': '24px',
                    'fontWeight': 'bold'
                }),
                html.Button(
                    html.I(className="fas fa-times", style={'fontSize': '18px'}),
                    id='ai-chat-modal-close',
                    n_clicks=0,
                    style={
                        'position': 'absolute',
                        'right': '15px',
                        'top': '15px',
                        'backgroundColor': 'transparent',
                        'border': 'none',
                        'cursor': 'pointer',
                        'fontSize': '20px',
                        'color': '#999',
                        'padding': '5px'
                    }
                )
            ], style={
                'position': 'relative',
                'padding': '15px',
                'borderBottom': '1px solid #e0e0e0',
                'backgroundColor': '#f8f9fa'
            }),
            
            # 使用ai_chat_manager的增强版界面
            ai_chat_manager.create_enhanced_chat_interface(
                chat_id_prefix='defect-explore-chat'
            ) if AI_CHAT_AVAILABLE else html.Div(
                "AI聊天功能暂不可用，请检查配置。",
                style={'padding': '20px', 'textAlign': 'center', 'color': '#666'}
            )
        ], style={
            'position': 'relative',
            'backgroundColor': 'white',
            'borderRadius': '0',
            'width': '95vw',
            'height': '92vh',
            'minWidth': '0',
            'minHeight': '0',
            'maxWidth': '95vw',
            'maxHeight': '92vh',
            'boxShadow': '0 4px 20px rgba(0,0,0,0.3)',
            'overflow': 'auto',
            'resize': 'none',
            'zIndex': '2'  # 确保内容在遮罩层之上
        })
    ], style={
        'display': 'none',
        'position': 'fixed',
        'zIndex': '2000',
        'left': '0',
        'top': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.6)',
        'justifyContent': 'center',
        'alignItems': 'center',
        'backdropFilter': 'blur(3px)'
    })
] + (
    ai_chat_manager.create_enhanced_chat_stores(chat_id_prefix='defect-explore-chat') +
    ai_chat_manager.create_enhanced_chat_stores(chat_id_prefix='defect-explore-chat-page')
    if AI_CHAT_AVAILABLE else []
), style=MAIN_CONTAINER_STYLE, id="main-container")

# 添加导航栏控制回调
@app.callback(
    [Output('sidebar-nav', 'style'),
     Output('nav-overlay', 'style'),
     Output('main-content-wrapper', 'style'),
     Output('nav-open-state', 'data'),
     Output('nav-toggle-btn', 'style'),
     Output('nav-edge-bar', 'style'),
     Output('nav-edge-bar-2', 'style')],
    [Input('nav-toggle-btn', 'n_clicks'),
     Input('nav-close-btn', 'n_clicks'),
     Input('nav-overlay', 'n_clicks'),
     Input('nav-edge-toggle-btn', 'n_clicks'),
     Input('nav-edge-toggle-btn-2', 'n_clicks'),
     Input('nav-tab-defect-status', 'n_clicks'),
     Input('nav-tab-project-analysis', 'n_clicks'),
     Input('nav-tab-testing-team', 'n_clicks'),
     Input('nav-tab-testing-efficiency', 'n_clicks'),
     Input('nav-tab-test-coverage', 'n_clicks'),
     Input('nav-tab-test-status', 'n_clicks'),
     Input('nav-tab-chat', 'n_clicks')],
    [State('nav-open-state', 'data')],
    prevent_initial_call=False  # 只在用户点击时触发
)
def toggle_sidebar(toggle_clicks, close_clicks, overlay_clicks, edge_toggle_clicks, edge_toggle_clicks_2,
                  nav1_clicks, nav2_clicks, nav3_clicks, nav4_clicks, nav5_clicks, nav6_clicks, nav7_clicks, is_open):
    from dash import callback_context
    
    # 确定触发的按钮
    if not callback_context.triggered:
        raise PreventUpdate
    
    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    
    # 导航栏基础样式
    nav_base_style = {
        'position': 'fixed',
        'top': '90px',  # 从标题栏下方开始
        'width': '280px',
        'height': 'calc(100vh - 90px)',  # 调整高度
        'backgroundColor': '#2c3e50',
        'zIndex': '1000',
        'transition': 'left 0.3s ease',
        'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
        'overflowY': 'auto'
    }
    
    # 主内容区基础样式
    main_content_base_style = {
        'marginTop': '110px',  # 为固定标题栏留出空间
        'transition': 'margin-left 0.3s ease',
        'minHeight': 'calc(100vh - 110px)',
        'padding': '20px'
    }
    
    # 遮罩层基础样式
    overlay_base_style = {
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'zIndex': '999'
    }
    
    # 切换按钮基础样式
    toggle_btn_base_style = {
        'position': 'fixed',
        'top': '20px',
        'zIndex': '1001',
        'backgroundColor': '#28a745',
        'color': 'white',
        'border': 'none',
        'padding': '12px',
        'borderRadius': '6px',
        'cursor': 'pointer',
        'fontSize': '16px',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.3)',
        'transition': 'all 0.3s ease'
    }
    
    # 边缘条基础样式
    edge_bar_base_style = {
        'position': 'fixed',
        'top': '90px',
        'width': '30px',
        'height': 'calc(100vh - 90px)',
        'backgroundColor': '#2c3e50',
        'zIndex': '999',
        'transition': 'left 0.3s ease',
        'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'center'
    }
    
    # 切换导航栏显示/隐藏
    if trigger_id in ['nav-toggle-btn', 'nav-close-btn', 'nav-overlay', 'nav-edge-toggle-btn', 'nav-edge-toggle-btn-2']:
        # 点击切换按钮、关闭按钮、遮罩层或边缘按钮时切换显示状态
        is_open = not is_open
        
        if is_open:
            nav_style = {**nav_base_style, 'left': '0px'}
            overlay_style = {**overlay_base_style, 'display': 'none'}  # 默认显示时不需要遮罩
            main_content_style = {**main_content_base_style, 'marginLeft': '300px'}
            toggle_btn_style = {**toggle_btn_base_style, 'left': '290px'}  # 导航栏显示时按钮在右侧
            edge_bar_style = {**edge_bar_base_style, 'left': '-30px'}  # 隐藏边缘条
        else:
            nav_style = {**nav_base_style, 'left': '-280px'}
            overlay_style = {**overlay_base_style, 'display': 'none'}
            main_content_style = {**main_content_base_style, 'marginLeft': '40px'}  # 为边缘条留出空间
            toggle_btn_style = {**toggle_btn_base_style, 'left': '50px'}  # 导航栏隐藏时按钮在边缘条右侧
            edge_bar_style = {**edge_bar_base_style, 'left': '0px'}  # 显示边缘条
            
        return nav_style, overlay_style, main_content_style, is_open, toggle_btn_style, edge_bar_style, edge_bar_style
    
    elif trigger_id.startswith('nav-tab-'):
        # 点击导航项时不改变导航栏的显示状态，使用no_update提升性能
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    
    raise PreventUpdate

# 添加导航项点击回调
@app.callback(
    [Output('current-nav-item', 'data'),
     Output('nav-tab-defect-status', 'style'),
     Output('nav-tab-project-analysis', 'style'),
     Output('nav-tab-testing-team', 'style'),
     Output('nav-tab-testing-efficiency', 'style'),
     Output('nav-tab-test-coverage', 'style'),
     Output('nav-tab-test-status', 'style'),
     Output('nav-tab-chat', 'style')],
    [Input('nav-tab-defect-status', 'n_clicks'),
     Input('nav-tab-project-analysis', 'n_clicks'),
     Input('nav-tab-testing-team', 'n_clicks'),
     Input('nav-tab-testing-efficiency', 'n_clicks'),
     Input('nav-tab-test-coverage', 'n_clicks'),
     Input('nav-tab-test-status', 'n_clicks'),
     Input('nav-tab-chat', 'n_clicks')],
    [State('current-nav-item', 'data')],
    prevent_initial_call=False  # 允许初始调用以设置默认样式
)
def update_nav_selection(nav1_clicks, nav2_clicks, nav3_clicks, nav4_clicks, nav5_clicks, nav6_clicks, nav7_clicks, current_nav):
    from dash import callback_context
    valid_tabs = {
        'tab-defect-status',
        'tab-project-analysis',
        'tab-testing-team',
        'tab-testing-efficiency',
        'tab-test-coverage',
        'tab-test-status',
        'tab-chat'
    }
    
    # 基础导航项样式
    base_nav_style = {
        'padding': '15px 20px',
        'cursor': 'pointer',
        'borderLeft': '4px solid transparent',
        'color': 'white',
        'transition': 'all 0.3s ease',
        'display': 'flex',
        'alignItems': 'center',
        'fontSize': '14px'
    }
    
    # 激活状态样式
    active_nav_style = {
        **base_nav_style,
        'backgroundColor': '#34495e',
        'borderLeft': '4px solid #3498db',
        'color': '#3498db'
    }
    
    # 确定当前选中的导航项
    selected_nav = current_nav  # 使用默认值
    if selected_nav not in valid_tabs:
        selected_nav = 'tab-defect-status'
    
    # 如果有回调触发，检查是哪个导航项被点击
    if callback_context.triggered:
        trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]
        
        # 根据触发的导航项更新选中状态
        nav_mapping = {
            'nav-tab-defect-status': 'tab-defect-status',
            'nav-tab-project-analysis': 'tab-project-analysis',
            'nav-tab-testing-team': 'tab-testing-team',
            'nav-tab-testing-efficiency': 'tab-testing-efficiency',
            'nav-tab-test-coverage': 'tab-test-coverage',
            'nav-tab-test-status': 'tab-test-status',
            'nav-tab-chat': 'tab-chat'
        }
        
        selected_nav = nav_mapping.get(trigger_id, current_nav)
    
    # 设置每个导航项的样式
    nav1_style = active_nav_style if selected_nav == 'tab-defect-status' else base_nav_style
    nav2_style = active_nav_style if selected_nav == 'tab-project-analysis' else base_nav_style
    nav3_style = active_nav_style if selected_nav == 'tab-testing-team' else base_nav_style
    nav4_style = active_nav_style if selected_nav == 'tab-testing-efficiency' else base_nav_style
    nav5_style = active_nav_style if selected_nav == 'tab-test-coverage' else base_nav_style
    nav6_style = active_nav_style if selected_nav == 'tab-test-status' else base_nav_style
    nav7_style = active_nav_style if selected_nav == 'tab-chat' else base_nav_style
    
    return selected_nav, nav1_style, nav2_style, nav3_style, nav4_style, nav5_style, nav6_style, nav7_style

# 添加回调函数来处理选项卡切换
@app.callback(
    Output('tabs-content', 'children'),
    [Input('current-nav-item', 'data')]
)
def render_content(tab):
    current_theme = theme_manager.get_theme()
    active_label_style = LABEL_STYLE_LIGHT if current_theme == 'light' else LABEL_STYLE_DARK
    
    # 如果tab为None或者无效值，默认显示缺陷状态分析页面
    if tab is None or tab not in ['tab-defect-status', 'tab-project-analysis', 'tab-testing-team', 'tab-testing-efficiency', 'tab-test-coverage', 'tab-test-status', 'tab-chat', 'tab-word-cloud']:
        tab = 'tab-defect-status'
    
    if tab == 'tab-defect-status':
        return html.Div([
            
            # 搜索区域 - 搜索框和AI区域水平排列
            html.Div([
                # 搜索框和AI区域的水平容器
                html.Div([
                    # 搜索框区域
                    html.Div([
                        html.I(className="fas fa-search", style={'position': 'absolute', 'left': '15px', 'top': '50%', 'transform': 'translateY(-50%)', 'color': '#666', 'zIndex': '10'}),
                        dcc.Input(
                            id='global-search-input',
                            type='text',
                            placeholder='Search Defect ID or Name...',
                            style={
                                'width': '100%',
                                'padding': '12px 80px 12px 45px',
                                'fontSize': '16px',
                                'border': '2px solid #ddd',
                                'borderRadius': '25px',
                                'outline': 'none',
                                'transition': 'border-color 0.3s ease',
                                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
                            }
                        ),
                        html.Button(
                            "Search",
                            id='search-button',
                            style={
                                'position': 'absolute',
                                'right': '8px',
                                'top': '50%',
                                'transform': 'translateY(-50%)',
                                'padding': '8px 20px',
                                'backgroundColor': '#3498db',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '20px',
                                'cursor': 'pointer',
                                'fontSize': '14px',
                                'fontWeight': 'bold'
                            }
                        )
                    ], style={'position': 'relative', 'width': '500px', 'minWidth': '300px'}),
                    
                    # AI助手按钮区域 - 与搜索框齐平
                    html.Div([
                        html.Span("AI", style={
                            'color': '#666',
                            'fontSize': '16px',
                            'fontWeight': 'bold',
                            'marginRight': '8px'
                        }),
                        html.Button(
                            html.Img(
                                src='/assets/deepseek.png',
                                style={
                                    'width': '32px',
                                    'height': '32px',
                                    'borderRadius': '50%',
                                    'objectFit': 'cover'
                                }
                            ),
                            id='ai-chat-toggle-btn',
                            n_clicks=0,
                            style={
                                'padding': '4px',
                                'backgroundColor': 'transparent',
                                'border': 'none',
                                'borderRadius': '50%',
                                'cursor': 'pointer',
                                'width': '40px',
                                'height': '40px',
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'center',
                                'transition': 'all 0.3s ease',
                                'boxShadow': '0 2px 4px rgba(0,0,0,0.2)'
                            },
                            title="SiSi - 点击打开智能缺陷分析"
                        )
                    ], style={
                        'display': 'flex',
                        'alignItems': 'center',
                        'backgroundColor': '#f8f9fa',
                        'padding': '8px 12px',
                        'borderRadius': '20px',
                        'border': '1px solid #e9ecef',
                        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
                    })
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'space-between',
                    'width': '100%',
                    'maxWidth': '800px',
                    'margin': '0 auto'
                }),
                
                # 搜索结果提示 - 不显示任何文字
                html.Div(id='search-results-info', style={'textAlign': 'center', 'marginTop': '8px', 'fontSize': '14px', 'color': '#666', 'display': 'none'})
            ], style={
                'marginBottom': '10px',
                'padding': '15px',
                'backgroundColor': '#f8f9fa',
                'borderRadius': '8px',
                'border': '1px solid #e9ecef',
                'display': 'flex',
                'flexDirection': 'column',
                'alignItems': 'center'
            }),
            
            # 使用统一的过滤器组件
            create_unified_filters(active_label_style=active_label_style),
            
            # 添加Excel导出按钮
            html.Div([
                html.Button(
                    [
                        html.I(className="fas fa-download", style={'marginRight': '8px'}),
                        "Export Excel"
                    ],
                    id='export-excel-btn',
                    style={
                        'backgroundColor': '#28a745',
                        'color': 'white',
                        'border': 'none',
                        'padding': '10px 20px',
                        'borderRadius': '5px',
                        'cursor': 'pointer',
                        'fontSize': '14px',
                        'fontWeight': 'bold',
                        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                        'transition': 'background-color 0.3s ease'
                    }
                ),
                dcc.Download(id="download-excel"),
                html.Div(id='export-status', style={'marginLeft': '15px', 'display': 'inline-block', 'fontSize': '14px', 'color': '#666'})
            ], style={'marginBottom': '20px', 'textAlign': 'left'}),
            
            # Excel风格的缺陷列表视图
            html.H3("Top Issue List", style=active_label_style),
            html.Div([
                dash_table.DataTable(
                    id='excel-defect-table',
                    data=[],  # 添加初始空数据
                    columns=[
                        {'name': 'ID', 'id': 'id', 'presentation': 'markdown'},
                        {'name': 'Name', 'id': 'name', 'type': 'text'},
                        {'name': 'ECU', 'id': 'ecu', 'type': 'text'},
                        {'name': 'Creation Time', 'id': 'creation_time', 'type': 'text'},
                        {'name': 'Matrix', 'id': 'matrix_display', 'type': 'text'},
                        {'name': 'Classification', 'id': 'classification_display', 'type': 'text'},
                        {'name': 'ECU Transfer', 'id': 'ecu_pingpong_display', 'type': 'text'},
                        {'name': 'Domain Transfer', 'id': 'domain_pingpong_display', 'type': 'text'},
                        {'name': 'Parent/Child', 'id': 'parent_child_display', 'type': 'text'},
                        {'name': 'Master Child Count', 'id': 'child_count_display', 'type': 'numeric'},
                        {'name': 'Parent Child Count', 'id': 'parent_child_count_display', 'type': 'numeric'},
                        {'name': 'Master Ticket Info', 'id': 'parent_ticket_info', 'type': 'text'},
                        {'name': 'Process Days', 'id': 'processing_cycle_days', 'type': 'numeric'},
                        {'name': 'PU', 'id': 'pu', 'type': 'text'},
                        {'name': 'Shift PU', 'id': 'Shift_PU', 'type': 'text'},
                        {'name': 'Risk Score', 'id': 'topissue_display', 'type': 'text'},
                        {'name': 'TopIssue Recommendation Reason', 'id': 'topissue_recommend_reason', 'type': 'text'},
                        {'name': 'AIDA', 'id': 'aida_english', 'type': 'text'},
                        {'name': 'Status', 'id': 'status_phase', 'type': 'text'},
                        {'name': 'Reporter', 'id': 'tester', 'type': 'text'},
                        {'name': 'Master Status', 'id': 'master_status', 'type': 'text'}
                    ],
                    # 排序功能 - 支持多列排序
                    sort_action='native',
                    sort_mode='multi',
                    # 筛选功能 - 每列都有筛选输入框
                    filter_action='native',
                    filter_options={'placeholder_text': 'Filter column...'},
                    # 表格样式优化
                    css=[{
                        'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table',
                        'rule': 'table-layout: auto; border-collapse: separate; border-spacing: 0;'
                    }, {
                        'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner .column-header',
                        'rule': 'position: sticky; top: 0; z-index: 10; background-color: #f8fafc !important; resize: horizontal;'
                    }, {
                        'selector': '.dash-spreadsheet-container',
                        'rule': 'position: relative;'
                    }, {
                        'selector': '.dash-tooltip',
                        'rule': 'white-space: pre-line !important; max-width: 450px !important; word-wrap: break-word !important; font-family: monospace !important; line-height: 1.4 !important; padding: 10px !important;'
                    }],
                    # 固定表头设置
                    fixed_rows={'headers': True},
                    # 分页
                    page_action='native',
                    page_current=0,
                    page_size=50,
                    style_table={
                        'overflowX': 'auto', 
                        'maxHeight': '650px', 
                        'overflowY': 'auto', 
                        'border': '1px solid #e5e7eb', 
                        'borderRadius': '8px', 
                        'boxShadow': '0 2px 8px 0 rgba(0, 0, 0, 0.1)',
                        'backgroundColor': 'white',
                        'minWidth': '1200px',
                        'width': '100%'
                    },
                    style_cell={
                        'textAlign': 'left',
                        'padding': '5px 8px',
                        'whiteSpace': 'nowrap',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'height': 'auto',
                        'fontSize': '11px',
                        'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                        'border': '1px solid #e5e7eb',
                        'borderCollapse': 'collapse',
                        'color': '#374151',
                        'lineHeight': '1.3'
                    },
                    style_header={
                        'backgroundColor': '#f8fafc',
                        'fontWeight': '600',
                        'fontSize': '12px',
                        'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                        'border': '1px solid #e5e7eb',
                        'color': '#374151',
                        'textAlign': 'center',
                        'padding': '8px 10px'
                    },
                    # 工具提示配置
                    tooltip_data=[],
                    tooltip_delay=0,
                    tooltip_duration=None,
                    style_cell_conditional=[
                        # 基本信息列
                        {
                            'if': {'column_id': 'id'},
                            'width': '60px',
                            'minWidth': '60px',
                            'maxWidth': '70px'
                        },
                        {
                            'if': {'column_id': 'name'},
                            'width': '200px',
                            'minWidth': '150px',
                            'maxWidth': '250px'
                        },
                        {
                            'if': {'column_id': 'ecu'},
                            'width': '80px',
                            'minWidth': '70px',
                            'maxWidth': '100px'
                        },
                        {
                            'if': {'column_id': 'creation_time'},
                            'width': '110px',
                            'minWidth': '110px',
                            'maxWidth': '120px'
                        },
                        {
                            'if': {'column_id': 'matrix_display'},
                            'width': '60px',
                            'minWidth': '60px',
                            'maxWidth': '70px'
                        },
                        # 重要列 - 稍微增加宽度
                        {
                            'if': {'column_id': 'classification_display'},
                            'width': '120px',
                            'minWidth': '120px',
                            'maxWidth': '150px'
                        },
                        {
                            'if': {'column_id': 'ecu_pingpong_display'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '120px'
                        },
                        {
                            'if': {'column_id': 'domain_pingpong_display'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '120px'
                        },
                        # 父子关系列
                        {
                            'if': {'column_id': 'parent_child_display'},
                            'width': '50px',
                            'minWidth': '50px',
                            'maxWidth': '60px'
                        },
                        {
                            'if': {'column_id': 'child_count_display'},
                            'width': '50px',
                            'minWidth': '50px',
                            'maxWidth': '60px'
                        },
                        {
                            'if': {'column_id': 'parent_child_count_display'},
                            'width': '50px',
                            'minWidth': '50px',
                            'maxWidth': '60px'
                        },
                        {
                            'if': {'column_id': 'parent_ticket_info'},
                            'width': '80px',
                            'minWidth': '80px',
                            'maxWidth': '100px'
                        },
                        # 处理时间列
                        {
                            'if': {'column_id': 'processing_cycle_days'},
                            'width': '80px',
                            'minWidth': '80px',
                            'maxWidth': '90px'
                        },
                        # PU信息列
                        {
                            'if': {'column_id': 'pu'},
                            'width': '60px',
                            'minWidth': '60px',
                            'maxWidth': '70px'
                        },
                        {
                            'if': {'column_id': 'Shift_PU'},
                            'width': '60px',
                            'minWidth': '60px',
                            'maxWidth': '70px'
                        },
                        # 风险评分列
                        {
                            'if': {'column_id': 'topissue_display'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '110px'
                        },
                        {
                            'if': {'column_id': 'topissue_recommend_reason'},
                            'width': '150px',
                            'minWidth': '150px',
                            'maxWidth': '180px'
                        },
                        # AIDA和状态列
                        {
                            'if': {'column_id': 'aida_english'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '110px'
                        },
                        {
                            'if': {'column_id': 'status_phase'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '110px'
                        },
                        # 测试人员和主状态列
                        {
                            'if': {'column_id': 'tester'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '110px'
                        },
                        {
                            'if': {'column_id': 'master_status'},
                            'width': '100px',
                            'minWidth': '100px',
                            'maxWidth': '110px'
                        }
                    ]
                )
            ], style={'marginBottom': '30px'}),
            
            # FV缺陷分布图表
            html.H3("Top Issue by FV", style=active_label_style),
            dcc.Graph(id='fv-distribution-chart'),
            
            # 缺陷状态图表
            html.H3("Top Issue by AIDA", style=active_label_style),
            dcc.Graph(id='defect-status-chart'),
            
            # Solution Cluster图表
            html.H3("Top Issue by Solution Cluster", style=active_label_style),
            
            # 添加Solution Cluster导出按钮
                html.Div([
                    html.Button(
                    [
                        html.I(className="fas fa-download", style={'marginRight': '8px'}),
                        "Export Excel"
                    ],
                    id='export-cluster-excel-btn',
                        style={
                        'backgroundColor': '#17a2b8',
                            'color': 'white',
                            'border': 'none',
                        'padding': '8px 16px',
                        'borderRadius': '5px',
                            'cursor': 'pointer',
                        'fontSize': '13px',
                        'fontWeight': 'bold',
                        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                        'transition': 'background-color 0.3s ease'
                    }
                ),
                dcc.Download(id="download-cluster-excel"),
                html.Div(id='export-cluster-status', style={'marginLeft': '15px', 'display': 'inline-block', 'fontSize': '14px', 'color': '#666'})
            ], style={'marginBottom': '15px', 'textAlign': 'left'}),
            
            dcc.Graph(id='solution-cluster-chart'),
            
            # 提示信息
                html.Div([
                html.Div([
                    html.I(className="fas fa-info-circle", style={'marginRight': '10px', 'fontSize': '18px', 'color': '#3498db'}),
                    html.Span("Click on the bar areas in the chart above to view corresponding defect details", style={'fontSize': '16px', 'color': '#2c3e50'})
                ], style={
                    'textAlign': 'center',
                    'padding': '20px',
                    'backgroundColor': '#f8f9fa',
                    'border': '1px solid #e9ecef',
                    'borderRadius': '8px',
                    'marginTop': '20px'
                })
            ])
        ])
    elif tab == 'tab-project-analysis':
        # 项目分析选项卡 - 移除筛选器，添加KPI卡片和横向对比分析
        return html.Div([
            # 项目KPI指标卡片
            html.H3("项目关键指标概览", style=active_label_style),
            html.Div(id='project-kpi-cards', style={'marginBottom': '30px'}),
            
            # 项目横向对比图表区域
            html.H3("项目横向对比分析", style=active_label_style),
            
            # 第一行：项目缺陷总量对比 + 项目严重缺陷率对比
            html.Div([
                html.Div([
                    html.H4("项目缺陷总量对比", style=active_label_style),
                    dcc.Graph(id='project-defect-volume-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                html.Div([
                    html.H4("项目严重缺陷率对比", style=active_label_style),
                    dcc.Graph(id='project-severity-rate-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # 第二行：项目状态分布对比 + 项目AIDA覆盖度对比
            html.Div([
                html.Div([
                    html.H4("项目缺陷状态分布对比", style=active_label_style),
                    dcc.Graph(id='project-status-distribution-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                html.Div([
                    html.H4("项目AIDA领域覆盖度对比", style=active_label_style),
                    dcc.Graph(id='project-aida-coverage-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # 第三行：项目缺陷发现趋势对比 + 项目阻塞原因分析对比
            html.Div([
                html.Div([
                    html.H4("项目缺陷发现趋势对比", style=active_label_style),
                    dcc.Graph(id='project-trend-comparison-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                html.Div([
                    html.H4("项目阻塞原因分析对比", style=active_label_style),
                    dcc.Graph(id='project-blocking-comparison-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # 第四行：项目Matrix分布对比（占据一整行，因为这个图表可能需要更多空间）
            html.Div([
                html.H4("项目Matrix分布对比", style=active_label_style),
                dcc.Graph(id='project-matrix-distribution-chart'),
            ], style={'marginBottom': '30px'}),
            
            # 项目详细统计表
            html.H4("项目详细统计表", style=active_label_style),
            dash_table.DataTable(
                id='project-stats-table',
                columns=[
                    {'name': 'Project', 'id': 'ecu'},
                    {'name': '总缺陷数', 'id': 'total_defects'},
                    {'name': '严重缺陷数', 'id': 'severe_defects'},
                    {'name': '严重缺陷率(%)', 'id': 'severe_rate'},
                    {'name': '已解决缺陷数', 'id': 'resolved_defects'},
                    {'name': '解决率(%)', 'id': 'resolution_rate'},
                    {'name': 'AIDA覆盖数', 'id': 'aida_coverage'},
                    {'name': '平均处理时间(天)', 'id': 'avg_resolution_time'},
                    {'name': '阻塞缺陷数', 'id': 'blocked_defects'}
                ],
                style_cell={'textAlign': 'center', 'fontSize': '13px',
                            'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                            'border': '1px solid #f3f4f6',
                            'color': '#374151'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                        style_cell_conditional=[
                            {
                                'if': {'column_id': 'ecu_pingpong_display'},
                                'width': '200px',
                                'minWidth': '200px',
                                'maxWidth': '200px'
                            },
                            {
                                'if': {'column_id': 'domain_pingpong_display'},
                                'width': '200px',
                                'minWidth': '200px',
                                'maxWidth': '200px'
                            },
                            {
                                'if': {'column_id': 'child_count_display'},
                                'width': '90px',
                                'minWidth': '90px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'processing_cycle_days'},
                                'width': '100px',
                                'minWidth': '100px',
                                'maxWidth': '100px'
                            }
                        ],
                        style_data_conditional=[
                    {
                        'if': {'column_id': 'severe_rate', 'filter_query': '{severe_rate} > 30'},
                        'backgroundColor': '#fadbd8',
                        'fontWeight': '500',
                    },
                    {
                        'if': {'column_id': 'resolution_rate', 'filter_query': '{resolution_rate} < 50'},
                        'backgroundColor': '#fadbd8',
                        'fontWeight': '500',
                    }
                ],
                sort_action="native",
                page_size=20
            ),
            
            # 隐藏的HR图表占位符，防止callback ID不存在错误
            html.Div([
                dcc.Graph(id='hr-child-complexity-chart', style={'display': 'none'}),
                dcc.Graph(id='hr-parent-complexity-chart', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    elif tab == 'tab-chat':
        return html.Div([
            html.Div(
                ai_chat_manager.create_enhanced_chat_interface(
                    chat_id_prefix='defect-explore-chat-page'
                ) if AI_CHAT_AVAILABLE else html.Div(
                    "AI聊天功能暂不可用，请检查配置。",
                    style={'padding': '20px', 'textAlign': 'center', 'color': '#666'}
                ),
                style={
                    'height': 'calc(100vh - 155px)',
                    'minHeight': '680px',
                    'backgroundColor': 'white',
                    'border': '1px solid #e5e7eb',
                    'borderRadius': '12px',
                    'boxShadow': '0 2px 10px rgba(0,0,0,0.08)',
                    'overflow': 'hidden'
                }
            )
        ])
    elif tab == 'tab-defect-high-runner':
        # High Complexity Defect Analysis Tab
        # Prepare data
        ddf = df.copy()
        
        # Ensure necessary columns exist and calculate defect levels
        if 'child_count_of_master' in ddf.columns:
            ddf['defect_level'] = ddf['child_count_of_master'].apply(categorize_defect_level_hr)
        else:
            # If child_count_of_master column doesn't exist, create a default one
            ddf['child_count_of_master'] = 0
            ddf['defect_level'] = 'Low'
        
        # Calculate master linked defect level
        if 'relation_to_udf' in ddf.columns:
            ddf['linked_defect_count'] = ddf['relation_to_udf'].apply(count_linked_defects_hr)
            ddf['master_linked_defect_level'] = ddf['linked_defect_count'].apply(categorize_master_linked_level_hr)
        else:
            ddf['linked_defect_count'] = 0
            ddf['master_linked_defect_level'] = 'Low'
        
        # Ensure test_week_sortable column exists
        if 'test_week' in ddf.columns and 'test_week_sortable' not in ddf.columns:
            ddf['test_week_sortable'] = ddf['test_week']
        
        # Get relevant test weeks
        if 'test_week_sortable' in ddf.columns:
            relevant_weeks = sorted(ddf['test_week_sortable'].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
        else:
            relevant_weeks = []
        
        return html.Div([
            html.H2("High Complexity Defect Analysis", style={
                'textAlign': 'center', 
                'marginBottom': '30px',
                'color': '#2c3e50',
                'fontSize': '28px',
                'fontWeight': 'bold'
            }),
            
            # 使用统一的过滤器组件
            create_unified_filters(prefix='hr-', active_label_style=active_label_style),
            
            # 第一个图表：Child Complexity
            html.Div([
                html.H3("Child Complexity Analysis", style={
                    'marginBottom': '15px',
                    'color': '#34495e',
                    'fontSize': '20px',
                    'fontWeight': '600'
                }),
                dcc.Graph(
                    id='hr-child-complexity-chart',
                    style={'height': '450px'}
                )
            ], style={
                'marginBottom': '40px',
                'padding': '20px',
                'backgroundColor': '#f8f9fa',
                'borderRadius': '8px',
                'border': '1px solid #e9ecef'
            }),
            
            # 第二个图表：Parent Complexity
            html.Div([
                html.H3("Parent Complexity Analysis", style={
                    'marginBottom': '15px',
                    'color': '#34495e',
                    'fontSize': '20px',
                    'fontWeight': '600'
                }),
                dcc.Graph(
                    id='hr-parent-complexity-chart',
                    style={'height': '450px'}
                )
            ], style={
                'marginBottom': '40px',
                'padding': '20px',
                'backgroundColor': '#f8f9fa',
                'borderRadius': '8px',
                'border': '1px solid #e9ecef'
            }),
            
            # 说明信息
            html.Div([
                html.H4("分析说明", style={'color': '#2c3e50', 'marginBottom': '15px'}),
                html.P([
                    "Child Complexity：基于子缺陷数量（child_count_of_master）的复杂度分析。",
                    html.Br(),
                    "分级标准：Low（<3个子票）、Medium（3-4个子票）、High（≥5个子票）"
                ], style={'marginBottom': '10px'}),
                html.P([
                    "Parent Complexity：基于父票据关联缺陷数量（relation_to_udf）的复杂度分析。",
                    html.Br(),
                    "分级标准：Low（<3个链接缺陷）、Medium（3-4个链接缺陷）、High（≥5个链接缺陷）"
                ], style={'marginBottom': '10px'}),
                html.P("图表显示不同复杂度等级的缺陷在各测试周的分布趋势，有助于识别高复杂度问题的发生模式。",
                       style={'fontStyle': 'italic', 'color': '#666'})
            ], style={
                'padding': '20px',
                'backgroundColor': '#e8f4f8',
                'borderRadius': '8px',
                'border': '1px solid #bee5eb'
            }),
            
            # 隐藏的图表占位符，防止callback ID不存在错误
            html.Div([
                dcc.Graph(id='fv-distribution-chart-project', style={'display': 'none'}),
                dcc.Graph(id='defect-status-chart-project', style={'display': 'none'}),
                dcc.Graph(id='solution-cluster-chart-project', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    elif tab == 'tab-defect-long-runner':
        # Long Runner Analysis - Phase Duration Analysis
        return create_long_runner_analysis_content(active_label_style)
    elif tab == 'tab-testing-team':
        # 测试团队分析选项卡
        return html.Div([
            # 使用统一的过滤器组件
            create_unified_filters(prefix='team-', active_label_style=active_label_style),
            
            # KPI指标区域
            html.Div([
                html.H3("测试团队KPI指标", style=active_label_style),
                html.Div(id='testing-kpi-cards', style={'marginBottom': '20px'})
            ]),
            
            # 图表区域
            html.Div([
                # 测试人员效率分析
                html.Div([
                    html.H3("测试人员缺陷发现效率", style=active_label_style),
                    dcc.Graph(id='tester-efficiency-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                # 缺陷发现趋势
                html.Div([
                    html.H3("缺陷发现趋势", style=active_label_style),
                    dcc.Graph(id='defect-discovery-trend-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            html.Div([
                # 缺陷严重性分布（按测试人员）
                html.Div([
                    html.H3("测试人员严重缺陷发现分布", style=active_label_style),
                    dcc.Graph(id='tester-severity-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                # 缺陷状态转换分析
                html.Div([
                    html.H3("缺陷状态分布", style=active_label_style),
                    dcc.Graph(id='defect-status-distribution-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            html.Div([
                # AIDA领域覆盖分析
                html.Div([
                    html.H3("AIDA领域测试覆盖", style=active_label_style),
                    dcc.Graph(id='aida-coverage-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                # 项目缺陷贡献分析
                html.Div([
                    html.H3("项目缺陷发现贡献", style=active_label_style),
                    dcc.Graph(id='project-contribution-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # 详细数据表格
            html.Div([
                html.H3("测试人员详细统计表", style=active_label_style),
                dash_table.DataTable(
                    id='tester-stats-table',
                    columns=[
                        {'name': '测试人员', 'id': 'tester'},
                        {'name': '总缺陷数', 'id': 'total_defects'},
                        {'name': '严重缺陷数', 'id': 'severe_defects'},
                        {'name': '严重缺陷率(%)', 'id': 'severe_rate'},
                        {'name': '平均每日发现', 'id': 'daily_avg'},
                        {'name': '主要AIDA领域', 'id': 'main_aida'},
                        {'name': '主要项目', 'id': 'main_project'}
                    ],
                    sort_action='native',
                    sort_mode='single',
                    page_size=15,
                    style_table={'overflowX': 'auto'},
                    style_cell={
                        'textAlign': 'left',
                        'padding': '5px',
                        'whiteSpace': 'normal',
                        'height': 'auto',
                    },
                    style_header={
                        'backgroundColor': '#f8fafc',
                        'fontWeight': 'bold'
                    },
                    style_cell_conditional=[
                            {
                                'if': {'column_id': 'ecu_pingpong_display'},
                                'width': '200px',
                                'minWidth': '200px',
                                'maxWidth': '200px'
                            },
                            {
                                'if': {'column_id': 'domain_pingpong_display'},
                                'width': '200px',
                                'minWidth': '200px',
                                'maxWidth': '200px'
                            },
                            {
                                'if': {'column_id': 'child_count_display'},
                                'width': '90px',
                                'minWidth': '90px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'processing_cycle_days'},
                                'width': '100px',
                                'minWidth': '100px',
                                'maxWidth': '100px'
                            }
                        ],
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': '#f9fafb'
                            },
                            {
                                'if': {'filter_query': '{severe_rate} > 30'},
                                'backgroundColor': '#d4edda',
                                'fontWeight': '500'
                            }
                        ]
                )
            ]),
            
            # 隐藏的图表占位符，防止callback ID不存在错误
            html.Div([
                dcc.Graph(id='fv-distribution-chart-hr', style={'display': 'none'}),
                dcc.Graph(id='defect-status-chart-hr', style={'display': 'none'}),
                dcc.Graph(id='solution-cluster-chart-hr', style={'display': 'none'}),
                dcc.Graph(id='hr-child-complexity-chart', style={'display': 'none'}),
                dcc.Graph(id='hr-parent-complexity-chart', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    elif tab == 'tab-testing-efficiency':
        # 测试效率与质量选项卡
        return html.Div([
            # 使用统一的过滤器组件
            create_unified_filters(prefix='efficiency-', active_label_style=active_label_style),
            
            # KPI指标区域
            html.Div([
                html.H3("测试效率与质量KPI指标", style=active_label_style),
                html.Div(id='efficiency-kpi-cards', style={'marginBottom': '20px'})
            ]),
            
            # 图表区域 - 第一行
            html.Div([
                html.Div([
                    html.H3("Ticket收敛趋势 (Inflow/Outflow)", style=active_label_style),
                    dcc.Graph(id='inflow-outflow-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                html.Div([
                    html.H3("缺陷矩阵分布", style=active_label_style),
                    dcc.Graph(id='defect-matrix-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # 图表区域 - 第二行：词云和缺陷密度在同一行
            html.Div([
                html.Div([
                    html.H3("DDF热词AIDA词云", style=active_label_style),
                    dcc.Graph(id='defect-aida-wordcloud'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                html.Div([
                    html.H3("缺陷密度分析", style=active_label_style),
                    dcc.Graph(id='defect-density-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # CWA票据分析 - 单独占一行
            html.Div([
                html.H3("CWA票据分析", style=active_label_style),
                dcc.Graph(id='test-execution-status-chart'),
            ], style={'marginBottom': '30px'}),
            
            # 图表区域 - 第四行
            html.Div([
                html.Div([
                    html.H3("缺陷状态转换效率", style=active_label_style),
                    dcc.Graph(id='status-transition-efficiency-chart'),
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%'}),
                
                html.Div([
                    html.H3("AIDA领域生产力", style=active_label_style),
                    dcc.Graph(id='aida-productivity-chart'),
                ], style={'width': '48%', 'display': 'inline-block'}),
            ], style={'marginBottom': '30px'}),
            
            # 质量评估表格
            html.Div([
                html.H3("项目质量评估表", style=active_label_style),
                dash_table.DataTable(
                    id='quality-assessment-table',
                    columns=[
                        {'name': 'Project Name', 'id': 'project'},
                        {'name': '总缺陷数', 'id': 'total_defects'},
                        {'name': '严重缺陷数', 'id': 'severe_defects'},
                        {'name': '缺陷密度', 'id': 'defect_density'},
                        {'name': '平均发现时间(天)', 'id': 'avg_discovery_time'},
                        {'name': 'AIDA覆盖率(%)', 'id': 'aida_coverage'},
                        {'name': '质量得分', 'id': 'quality_score'}
                    ],
                    sort_action='native',
                    sort_mode='single',
                    page_size=15,
                    style_table={'overflowX': 'auto'},
                    style_cell={
                        'textAlign': 'left',
                        'padding': '5px',
                        'whiteSpace': 'normal',
                        'height': 'auto',
                    },
                    style_header={
                        'backgroundColor': '#f8fafc',
                        'fontWeight': 'bold'
                    },
                        style_cell_conditional=[
                            {
                                'if': {'column_id': 'ecu_pingpong_display'},
                                'width': '200px',
                                'minWidth': '200px',
                                'maxWidth': '200px'
                            },
                            {
                                'if': {'column_id': 'domain_pingpong_display'},
                                'width': '200px',
                                'minWidth': '200px',
                                'maxWidth': '200px'
                            },
                            {
                                'if': {'column_id': 'child_count_display'},
                                'width': '90px',
                                'minWidth': '90px',
                                'maxWidth': '90px'
                            },
                            {
                                'if': {'column_id': 'processing_cycle_days'},
                                'width': '100px',
                                'minWidth': '100px',
                                'maxWidth': '100px'
                            }
                        ],
                        style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#f9fafb'
                        },
                        {
                            'if': {'filter_query': '{quality_score} > 80', 'column_id': 'quality_score'},
                            'backgroundColor': '#d4edda',
                            'fontWeight': '500'
                        },
                        {
                            'if': {'filter_query': '{quality_score} < 60', 'column_id': 'quality_score'},
                            'backgroundColor': '#f8d7da',
                            'fontWeight': '500'
                        }
                    ]
                )
            ]),
            
            # 隐藏的图表占位符，防止callback ID不存在错误
            html.Div([
                dcc.Graph(id='fv-distribution-chart-efficiency', style={'display': 'none'}),
                dcc.Graph(id='defect-status-chart-efficiency', style={'display': 'none'}),
                dcc.Graph(id='solution-cluster-chart-efficiency', style={'display': 'none'}),
                dcc.Graph(id='hr-child-complexity-chart', style={'display': 'none'}),
                dcc.Graph(id='hr-parent-complexity-chart', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    elif tab == 'tab-test-coverage':
        # 测试覆盖率分析页面
        return html.Div([
            create_test_coverage_page(source="defect-explore"),
            
            # 隐藏的图表和组件占位符，防止callback ID不存在错误
            html.Div([
                dcc.Graph(id='fv-distribution-chart-coverage', style={'display': 'none'}),
                dcc.Graph(id='defect-status-chart-coverage', style={'display': 'none'}),
                dcc.Graph(id='solution-cluster-chart-coverage', style={'display': 'none'}),
                dcc.Graph(id='hr-child-complexity-chart-coverage', style={'display': 'none'}),
                dcc.Graph(id='hr-parent-complexity-chart-coverage', style={'display': 'none'}),
                
                # 隐藏的下拉菜单组件，用于满足modal回调的State依赖
                dcc.Dropdown(id='project-dropdown', style={'display': 'none'}),
                dcc.DatePickerRange(id='date-range-picker-main', style={'display': 'none'}),
                dcc.Dropdown(id='aida-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='hidden-status-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='pu-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='tester-dropdown-main', style={'display': 'none'}),
                dcc.Dropdown(id='fv-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='ecu-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='severe-matrix-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='severe-classification-dropdown', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    
    elif tab == 'tab-test-status':
        # Test Status Analysis页面 - 参考test coverage设计
        try:
            # 加载测试数据
            test_data = load_test_data()
            if test_data.empty:
                return html.Div([
                    html.H3("Test Status Analysis", style={'marginBottom': '20px'}),
                    html.Div("暂无测试数据，请检查数据源配置", style={'color': 'red', 'textAlign': 'center', 'marginTop': '50px'})
                ])
                
            # 清理数据以用于筛选器选项生成
            def extract_value_from_dict(x):
                """从字典中提取有用的值"""
                if isinstance(x, dict):
                    if 'name' in x:
                        return x['name']
                    elif 'value' in x:
                        return x['value']
                    else:
                        return str(x)
                return x
            
            # 清理测试数据用于筛选器选项
            for col in test_data.columns:
                if test_data[col].dtype == 'object':
                    test_data[col] = test_data[col].apply(extract_value_from_dict)

            ts_year_series = extract_year_series(test_data, year_col='year', week_col='test_week')
            ts_year_values = sorted({int(v) for v in ts_year_series.dropna().tolist()})
            ts_year_default = [2026] if 2026 in ts_year_values else []
                    
        except Exception as e:
            return html.Div([
                html.H3("Test Status Analysis", style={'marginBottom': '20px'}),
                html.Div(f"数据加载失败: {str(e)}", style={'color': 'red', 'textAlign': 'center', 'marginTop': '50px'})
            ])
        
        return html.Div([
            # 页面标题
            html.Div([
                html.H3("Test Status Analysis", style=active_label_style),
                html.P(f"数据概览: 共 {len(test_data)} 条测试记录", 
                       style={'color': '#666', 'fontSize': '14px'})
            ], style={'marginBottom': '20px'}),
            
            # 筛选器区域
            html.Div([
                html.H4("筛选条件", style=active_label_style),
                html.Div([
                    # 第一行筛选器
                    html.Div([
                        html.Div([
                            html.Label('Year:', style=active_label_style),
                            dcc.Dropdown(
                                id='ts-year-dropdown',
                                options=[{'label': str(y), 'value': int(y)} for y in ts_year_values],
                                value=ts_year_default,
                                multi=True,
                                placeholder='选择年份...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '12%', 'display': 'inline-block', 'marginRight': '1%'}),

                        html.Div([
                            html.Label('项目:', style=active_label_style),
                            dcc.Dropdown(
                                id='ts-project-dropdown',
                                options=[{'label': str(p), 'value': str(p)} for p in sorted(test_data['project'].dropna().unique()) if str(p) and str(p) != 'nan'] if 'project' in test_data.columns else [],
                                value=[],
                                multi=True,
                                placeholder='选择项目...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15%', 'display': 'inline-block', 'marginRight': '1%'}),
                        
                        html.Div([
                            html.Label('测试周:', style=active_label_style),
                            dcc.Dropdown(
                                id='ts-testweek-dropdown',
                                options=[{'label': str(w), 'value': str(w)} for w in sorted(test_data['test_week'].dropna().unique()) if str(w) and str(w) != 'nan'] if 'test_week' in test_data.columns else [],
                                value=[],
                                multi=True,
                                placeholder='选择测试周...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15%', 'display': 'inline-block', 'marginRight': '1%'}),
                        
                        html.Div([
                            html.Label('FV:', style=active_label_style),
                            dcc.Dropdown(
                                id='ts-fv-dropdown',
                                options=[{'label': '全部', 'value': 'all'}] + [{'label': str(f), 'value': str(f)} for f in sorted(test_data['fv'].dropna().unique()) if str(f) and str(f) != 'nan'] if 'fv' in test_data.columns else [],
                                value=['all'],
                                multi=True,
                                placeholder='选择FV...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15%', 'display': 'inline-block', 'marginRight': '1%'}),
                        
                        html.Div([
                            html.Label('状态:', style=active_label_style),
                            dcc.Dropdown(
                                id='ts-status-dropdown',
                                options=[{'label': str(s), 'value': str(s)} for s in sorted(test_data[next((col for col in ['native_status', 'run_status', 'status', 'execution_status'] if col in test_data.columns), 'native_status')].dropna().unique()) if str(s) and str(s) != 'nan'] if any(col in test_data.columns for col in ['native_status', 'status', 'run_status', 'execution_status']) else [],
                                value=[],
                                multi=True,
                                placeholder='选择状态...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15%', 'display': 'inline-block', 'marginRight': '1%'}),
                        
                        html.Div([
                            html.Label('AIDA:', style=active_label_style),
                            dcc.Dropdown(
                                id='ts-aida-dropdown',
                                options=[{'label': str(a), 'value': str(a)} for a in sorted(test_data['top_aida'].dropna().unique()) if str(a) and str(a) != 'nan'] if 'top_aida' in test_data.columns else [],
                                value=[],
                                multi=True,
                                placeholder='选择AIDA...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15%', 'display': 'inline-block'})
                    ], style={'marginBottom': '10px'})
                ])
            ], style={'marginBottom': '30px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'}),
            
            # KPI指标展示区域
            html.Div(id='ts-kpi-indicators', style={'marginBottom': '30px'}),
            
            # 图表区域
            html.Div([
                # 测试执行状态分布和项目测试数量并排显示
                html.Div([
                    html.Div([
                        html.H4("📊 测试执行状态分布", style=active_label_style),
                        dcc.Graph(
                            id='ts-status-distribution-pie',
                            config={'displayModeBar': False}
                        )
                    ], className='col-md-6'),
                    html.Div([
                        html.H4("项目测试数量", style=active_label_style),
                        dcc.Graph(
                            id='test-project-count-chart-main',
                            config={'displayModeBar': False}
                        )
                    ], className='col-md-6')
                ], className='row', style={'marginBottom': '30px'}),
                
                # 第一行：前两个图表并列
                html.Div([
                    html.Div([
                        html.H4("📈 测试通过率趋势", style=active_label_style),
                        dcc.Graph(
                            id='ts-pass-rate-trend-chart',
                            config={'displayModeBar': False}
                        )
                    ], className='col-md-6'),
                    html.Div([
                        html.H4("🔥 测试热点AIDA词云图", style=active_label_style), 
                        dcc.Graph(
                            id='ts-aida-wordcloud',
                            config={'displayModeBar': False}
                        )
                    ], className='col-md-6')
                ], className='row', style={'marginBottom': '30px'}),
                
                html.Div([
                    html.Div([
                        html.H4("FV vs 测试用例数量 (按执行状态分组)", style=active_label_style),
                        dcc.Graph(
                            id='test-status-fv-chart-main',
                            config={'displayModeBar': False}
                        )
                    ], className='col-md-6'),
                    html.Div([
                        html.H4("Release趋势图", style=active_label_style),
                        dcc.Graph(
                            id='test-release-trend-chart-main',
                            config={'displayModeBar': False}
                        )
                    ], className='col-md-6')
                ], className='row', style={'marginBottom': '30px'}),
                

            ]),
            
            # 存储组件
            dcc.Store(id='test-status-store-main', data={}),
            
            # 隐藏的组件以避免回调错误
            html.Div([
                dcc.Graph(id='fv-distribution-chart-matrix', style={'display': 'none'}),
                dcc.Graph(id='defect-status-chart-matrix', style={'display': 'none'}),
                dcc.Graph(id='solution-cluster-chart-matrix', style={'display': 'none'}),
                dcc.Graph(id='hr-child-complexity-chart-matrix', style={'display': 'none'}),
                dcc.Graph(id='hr-parent-complexity-chart-matrix', style={'display': 'none'}),
                
                # 隐藏的下拉菜单组件，用于满足modal回调的State依赖
                dcc.Dropdown(id='project-dropdown', style={'display': 'none'}),
                dcc.DatePickerRange(id='date-range-picker-main', style={'display': 'none'}),
                dcc.Dropdown(id='aida-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='hidden-status-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='pu-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='tester-dropdown-main', style={'display': 'none'}),
                dcc.Dropdown(id='fv-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='ecu-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='severe-matrix-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='severe-classification-dropdown', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    
    elif tab == 'tab-word-cloud':
        # 词云分析页面
        return html.Div([
            # 页面标题和导航
            nav_manager.create_breadcrumb('tab-word-cloud'),
            html.H2("词云分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            # 筛选器区域
            html.Div([
                html.H4("筛选条件", style=active_label_style),
                html.Div([
                    # 第一行筛选器
                    html.Div([
                        html.Div([
                            html.Label('Project:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-project-dropdown',
                                options=[{'label': p, 'value': p} for p in sorted(df['project'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()) if p],
                                value=[],
                                multi=True,
                                clearable=True,
                                placeholder='Select Project...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
                        
                        html.Div([
                            html.Label('Date Range:', style=active_label_style),
                            dcc.DatePickerRange(
                                id='wc-date-range-picker',
                                start_date_placeholder_text='Start Date',
                                end_date_placeholder_text='End Date',
                                display_format='YYYY-MM-DD',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
                        
                        html.Div([
                            html.Label('AIDA:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-aida-dropdown',
                                options=[{'label': a, 'value': a} for a in sorted(df['aida_english'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()) if a],
                                value=[],
                                multi=True,
                                clearable=True,
                                placeholder='Select AIDA...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
                        
                        html.Div([
                            html.Label('Status:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-status-dropdown',
                                options=[{'label': s, 'value': s} for s in sorted(df['status_phase'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()) if s],
                                value=['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification'],
                                multi=True,
                                clearable=True,
                                placeholder='Select Status...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
                        
                        html.Div([
                            html.Label('Severity:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-severity-dropdown',
                                options=[
                                    {'label': 'All', 'value': 'all'},
                                    {'label': 'Critical Issues Only', 'value': 'critical'},
                                    {'label': 'General Issues Only', 'value': 'general'}
                                ],
                                value='all',
                                clearable=False,
                                placeholder='Select Severity...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'verticalAlign': 'top'})
                    ], style={'marginBottom': '15px'}),
                    
                    # 第二行筛选器
                    html.Div([
                        html.Div([
                            html.Label('Text Source:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-text-source-dropdown',
                                options=[
                                    {'label': 'Defect Name', 'value': 'defect_name'},
                                    {'label': 'Description', 'value': 'description'},
                                    {'label': 'Solution Cluster', 'value': 'domain'},
                                    {'label': 'Combined (Name + Description)', 'value': 'combined'}
                                ],
                                value='defect_name',
                                clearable=False,
                                placeholder='Select Text Source...',
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
                        
                        html.Div([
                            html.Label('Max Words:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-max-words-dropdown',
                                options=[
                                    {'label': '50', 'value': 50},
                                    {'label': '100', 'value': 100},
                                    {'label': '150', 'value': 150},
                                    {'label': '200', 'value': 200}
                                ],
                                value=100,
                                clearable=False,
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'}),
                        
                        html.Div([
                            html.Label('Language Filter:', style=active_label_style),
                            dcc.Dropdown(
                                id='wc-language-dropdown',
                                options=[
                                    {'label': 'All Languages', 'value': 'all'},
                                    {'label': 'English Only', 'value': 'english'},
                                    {'label': 'Chinese Only', 'value': 'chinese'}
                                ],
                                value='english',
                                clearable=False,
                                style={'width': '100%'}
                            ),
                        ], style={'width': '15.5%', 'display': 'inline-block', 'marginRight': '1%', 'verticalAlign': 'top'})
                    ])
                ])
            ], style={'marginBottom': '30px', 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'}),
            
            # 词云图表区域
            html.Div([
                # 左侧：主词云图
                html.Div([
                    html.H4("缺陷关键词词云", style=active_label_style),
                    html.Div([
                        dcc.Graph(
                            id='main-wordcloud-chart',
                            config={'displayModeBar': True, 'toImageButtonOptions': {'format': 'png', 'filename': 'defect_wordcloud', 'height': 600, 'width': 800}}
                        )
                    ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'padding': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'})
                ], style={'width': '48%', 'display': 'inline-block', 'marginRight': '2%', 'verticalAlign': 'top'}),
                
                # 右侧：词频统计表
                html.Div([
                    html.H4("词频统计", style=active_label_style),
                    html.Div([
                        dash_table.DataTable(
                            id='wordcloud-frequency-table',
                            columns=[
                                {'name': 'Keyword', 'id': 'word'},
                                {'name': 'Frequency', 'id': 'frequency'},
                                {'name': 'Percentage', 'id': 'percentage'}
                            ],
                            style_cell={
                                'textAlign': 'left',
                                'fontSize': '13px',
                                'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                                'border': '1px solid #f3f4f6',
                                'color': '#374151',
                                'padding': '8px'
                            },
                            style_header={
                                'backgroundColor': '#f8f9fa',
                                'fontWeight': 'bold',
                                'textAlign': 'center'
                            },
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 0},
                                    'backgroundColor': '#e3f2fd',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {'row_index': [1, 2]},
                                    'backgroundColor': '#f3e5f5'
                                }
                            ],
                            page_size=20,
                            sort_action='native'
                        )
                    ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'padding': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'height': '600px', 'overflowY': 'auto'})
                ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'})
            ], style={'marginBottom': '30px'}),
            
            # 统计信息区域
            html.Div([
                html.H4("分析统计", style=active_label_style),
                html.Div(id='wordcloud-stats-info', style={
                    'backgroundColor': '#f8f9fa',
                    'padding': '15px',
                    'borderRadius': '8px',
                    'border': '1px solid #e9ecef'
                })
            ], style={'marginBottom': '30px'}),
            
            # 隐藏的组件以避免回调错误
            html.Div([
                dcc.Graph(id='fv-distribution-chart-trend', style={'display': 'none'}),
                dcc.Graph(id='defect-status-chart-trend', style={'display': 'none'}),
                dcc.Graph(id='solution-cluster-chart-trend', style={'display': 'none'}),
                dcc.Graph(id='hr-child-complexity-chart-trend', style={'display': 'none'}),
                dcc.Graph(id='hr-parent-complexity-chart-trend', style={'display': 'none'}),
                
                # 隐藏的下拉菜单组件，用于满足modal回调的State依赖
                dcc.Dropdown(id='project-dropdown', style={'display': 'none'}),
                dcc.DatePickerRange(id='date-range-picker-main', style={'display': 'none'}),
                dcc.Dropdown(id='aida-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='hidden-status-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='pu-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='tester-dropdown-main', style={'display': 'none'}),
                dcc.Dropdown(id='fv-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='ecu-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='severe-matrix-dropdown', style={'display': 'none'}),
                dcc.Dropdown(id='severe-classification-dropdown', style={'display': 'none'})
            ], style={'display': 'none'})
        ])
    
    # 默认情况（包括任何其他未定义的tab）
    return html.Div([
        html.H3("选择一个标签页查看内容"),
        # 隐藏的图表占位符，防止callback ID不存在错误
        html.Div([
            dcc.Graph(id='fv-distribution-chart-default', style={'display': 'none'}),
            dcc.Graph(id='defect-status-chart-default', style={'display': 'none'}),
            dcc.Graph(id='solution-cluster-chart-default', style={'display': 'none'}),
            dcc.Graph(id='hr-child-complexity-chart-default', style={'display': 'none'}),
            dcc.Graph(id='hr-parent-complexity-chart-default', style={'display': 'none'})
        ], style={'display': 'none'})
    ])


# 回调函数 - FV分布图表
@app.callback(
    Output('fv-distribution-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('project-dropdown', 'value'),
     Input('date-range-picker-main', 'start_date'),
     Input('date-range-picker-main', 'end_date'),
     Input('aida-dropdown', 'value'),
     Input('status-dropdown', 'value'),
     Input('pu-dropdown', 'value'),
     Input('tester-dropdown-main', 'value'),
     Input('fv-dropdown', 'value'),
     Input('ecu-dropdown', 'value'),
     Input('lead-model-dropdown', 'value'),
     Input('fvp-dropdown', 'value'),
     Input('market-dropdown', 'value'),
     Input('severe-matrix-dropdown', 'value'),
     Input('severe-classification-dropdown', 'value')],
    prevent_initial_call=False
)
def update_fv_distribution_chart(years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    try:
        # 检查数据是否可用
        if df is None or df.empty:
            return go.Figure().add_annotation(text="数据暂未加载", showarrow=False)
        
        # 如果statuses为None，使用默认的状态筛选值（与主下拉菜单保持一致）
        if statuses is None:
            statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
        
        # 使用通用筛选函数
        filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
        
        # 检查筛选后的数据
        if filtered_data is None or filtered_data.empty:
            return go.Figure().add_annotation(text="筛选后无数据", showarrow=False)
        
        # 动态计算严重性分组，基于用户选择的matrix和classification
        if severe_matrices is None:
            severe_matrices = []
        if severe_classifications is None:
            severe_classifications = []
        
        # 重新计算严重性分组
        filtered_data = filtered_data.copy()
    except Exception as e:
        print(f"FV分布图表更新错误: {e}")
        return go.Figure().add_annotation(text=f"数据处理错误: {str(e)[:100]}", showarrow=False)
    
    def is_severe_defect(row):
        # 检查Matrix是否为严重
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        
        # 检查Classification是否为严重
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        # 只要满足任一条件就是严重问题
        return matrix_severe or classification_severe
    
    filtered_data['severity_group'] = filtered_data.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 在Modal中也执行智能分配逻辑
    def reassign_unassigned_clusters_modal(data):
        # 找到未分配的缺陷
        unassigned_mask = (data['domain'].isna()) | (data['domain'] == '') | (data['domain'].str.strip() == '')
        unassigned_data = data[unassigned_mask].copy()
        assigned_data = data[~unassigned_mask].copy()
        
        if len(unassigned_data) == 0:
            return data
        
        # 为每个AIDA领域建立Solution Cluster映射
        aida_to_cluster_map = {}
        for _, row in assigned_data.iterrows():
            aida = row.get('aida_english', '')
            cluster = row.get('domain', '')
            if aida and cluster:
                if aida not in aida_to_cluster_map:
                    aida_to_cluster_map[aida] = {}
                if cluster not in aida_to_cluster_map[aida]:
                    aida_to_cluster_map[aida][cluster] = 0
                aida_to_cluster_map[aida][cluster] += 1
        
        # 定义AIDA到合理Solution Cluster的预期映射（基于领域知识）
        expected_aida_cluster_mapping = {
            'videostreaming': ['multimedia', 'streaming', 'video', 'display', 'camera'],
            'audio': ['audio', 'multimedia', 'sound', 'speaker'],
            'communication': ['communication', 'network', 'connectivity', 'radio'],
            'navigation': ['navigation', 'gps', 'maps', 'routing'],
            'vehicle_control': ['vehicle', 'control', 'drive', 'chassis'],
            'safety': ['safety', 'security', 'protection', 'airbag'],
            'infotainment': ['infotainment', 'entertainment', 'multimedia', 'hmi'],
            'diagnosis': ['diagnosis', 'diagnostic', 'system', 'obd'],
            'climate': ['climate', 'hvac', 'temperature', 'air'],
            'lighting': ['lighting', 'light', 'illumination', 'led'],
            'body': ['body', 'door', 'window', 'seat'],
            'powertrain': ['powertrain', 'engine', 'transmission', 'hybrid'],
            'connectivity': ['connectivity', 'bluetooth', 'wifi', 'cellular']
        }
        
        # 为每个AIDA选择最合理的Solution Cluster
        aida_preferred_cluster = {}
        for aida, clusters in aida_to_cluster_map.items():
            if clusters:
                # 首先检查是否有符合预期的映射
                expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                
                best_cluster = None
                best_score = 0
                best_count = 0
                
                for cluster, count in clusters.items():
                    score = 0
                    cluster_lower = cluster.lower()
                    
                    # 计算匹配分数：如果cluster名称包含预期关键词，给予额外分数
                    for keyword in expected_keywords:
                        if keyword in cluster_lower:
                            score += 10  # 预期匹配给高分
                    
                    # 添加出现频次作为基础分数
                    score += count
                    
                    # 选择分数最高的cluster
                    if score > best_score or (score == best_score and count > best_count):
                        best_cluster = cluster
                        best_score = score
                        best_count = count
                
                if best_cluster:
                    aida_preferred_cluster[aida] = best_cluster
        
        # 重新分配未分配的缺陷
        data_copy = data.copy()
        assigned_count = 0
        skipped_count = 0
        for idx, row in unassigned_data.iterrows():
            aida = row.get('aida_english', '')
            if aida in aida_preferred_cluster:
                # 额外验证：如果分配结果明显不合理，跳过自动分配
                preferred_cluster = aida_preferred_cluster[aida]
                expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                
                # 对于有预期映射的AIDA，验证分配的合理性
                should_assign = True
                if expected_keywords:
                    match_found = any(keyword in preferred_cluster.lower() for keyword in expected_keywords)
                    if not match_found:
                        # 如果分配明显不合理，保持未分配状态
                        should_assign = False
                        skipped_count += 1
                
                if should_assign:
                    data_copy.at[idx, 'domain'] = preferred_cluster
                    assigned_count += 1
        
        return data_copy
    
    # 执行智能分配
    filtered_data = reassign_unassigned_clusters_modal(filtered_data)
    
    # 按FV和严重性分组
    fv_chart_data = filtered_data.copy()
    fv_chart_data['fv_dimension'] = build_chart_dimension(fv_chart_data, 'fv')
    fv_status = fv_chart_data.groupby(['fv_dimension', 'severity_group']).size().reset_index(name='缺陷数量')
    
    # 按FV的总缺陷数量降序排列
    fv_totals = fv_status.groupby('fv_dimension')['缺陷数量'].sum().reset_index()
    fv_order = sort_dimension_with_unknown_last(fv_totals, 'fv_dimension')
    
    # 计算总defect数量
    total_defects = filtered_data.shape[0]
    
    # 创建堆叠条形图
    fig = px.bar(
        fv_status,
        x='fv_dimension',
        y='缺陷数量',
        color='severity_group',
        barmode='stack',
        color_discrete_map=SEVERITY_COLORS,
        title="FV (Feature Team) 缺陷分布（按严重性）",
        category_orders={'fv_dimension': fv_order}  # 添加排序
    )
    
    # 设置悬停模板
    fig.update_traces(
        hovertemplate='<b>FV: %{x}</b><br>缺陷数量: %{y}<br>类型: %{fullData.name}'
    )
    
    # 设置标题和布局
    projects_text = "所有项目"
    date_range_text = "所有日期" if not start_date and not end_date else f"{start_date or 'Beginning'} to {end_date or 'Now'}"
    aidas_text = "所有AIDA" if not aidas or len(aidas) == 0 else ", ".join(aidas)
    statuses_text = "所有状态" if not statuses or len(statuses) == 0 else ", ".join(statuses)
    pus_text = "所有PU" if not pus or len(pus) == 0 else ", ".join(pus)
    fvs_text = "所有FV" if not fvs or len(fvs) == 0 else ", ".join(fvs)
    severe_matrices_text = "默认" if not severe_matrices or len(severe_matrices) == 0 else f"{len(severe_matrices)}个Matrix"
    severe_classifications_text = "默认" if not severe_classifications or len(severe_classifications) == 0 else f"{len(severe_classifications)}个Classification"
    
    title = f"FV (Feature Team) 缺陷分布（按严重性）<br><sup>项目: {projects_text} | 日期范围: {date_range_text} | AIDA: {aidas_text} | Status: {statuses_text} | PU: {pus_text} | FV: {fvs_text} | 严重Matrix: {severe_matrices_text} | 严重Classification: {severe_classifications_text}</sup>"
    
    # 使用通用样式函数
    fig = apply_chart_style(
        fig, 
        title=title,
        x_title="FV (Feature Team)",
        y_title="缺陷数量"
    )
    
    # 在图表右上角添加总数标注
    fig.add_annotation(
        text=f"total: {total_defects} 个Defect",
        xref="paper", yref="paper",
        x=0.98, y=0.98,
        showarrow=False,
        font=dict(size=14, color="black"),
        xanchor='right'
    )
    
    # 在每个柱状图顶部添加总数标注
    for fv in fv_order:
        fv_total = fv_totals[fv_totals['fv_dimension'] == fv]['缺陷数量'].iloc[0]
        fig.add_annotation(
            text=str(fv_total),
            x=fv,
            y=fv_total,
            yshift=10,
            showarrow=False,
            font=dict(size=12, color="black"),
            xanchor='center'
        )
    
    return fig

# 回调函数 - 缺陷状态图表
@app.callback(
    Output('defect-status-chart', 'figure'),
    [Input('current-nav-item', 'data'),
     Input('year-dropdown', 'value'),
     Input('project-dropdown', 'value'),
     Input('date-range-picker-main', 'start_date'),
     Input('date-range-picker-main', 'end_date'),
     Input('aida-dropdown', 'value'),
     Input('status-dropdown', 'value'),
     Input('pu-dropdown', 'value'),
     Input('tester-dropdown-main', 'value'),
     Input('fv-dropdown', 'value'),
     Input('ecu-dropdown', 'value'),
     Input('lead-model-dropdown', 'value'),
     Input('fvp-dropdown', 'value'),
     Input('market-dropdown', 'value'),
     Input('severe-matrix-dropdown', 'value'),
     Input('severe-classification-dropdown', 'value')],
    prevent_initial_call=False
)
def update_defect_status_chart(current_nav_item, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    if current_nav_item != 'tab-defect-status':
        raise PreventUpdate

    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']

    if severe_matrices is None:
        severe_matrices = []
    if severe_classifications is None:
        severe_classifications = []

    cache_key = _build_defect_status_cache_key({
        'tab': current_nav_item,
        'data_signature': _get_defect_data_signature(df),
        'years': years,
        'projects': projects,
        'start_date': start_date,
        'end_date': end_date,
        'aidas': aidas,
        'statuses': statuses,
        'pus': pus,
        'testers': testers,
        'fvs': fvs,
        'ecus': ecus,
        'lead_models': lead_models,
        'fvps': fvps,
        'markets': markets,
        'severe_matrices': severe_matrices,
        'severe_classifications': severe_classifications
    })
    if CACHE_MANAGER_AVAILABLE and default_cache_manager:
        cached_figure = default_cache_manager.get(cache_key)
        if cached_figure is not None:
            return cached_figure

    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
    filtered_data = filtered_data.copy()
    
    def is_severe_defect(row):
        # 检查Matrix是否为严重
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        
        # 检查Classification是否为严重
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        # 只要满足任一条件就是严重问题
        return matrix_severe or classification_severe
    
    filtered_data['severity_group'] = filtered_data.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 在Modal中也执行智能分配逻辑
    def reassign_unassigned_clusters_modal(data):
        # 找到未分配的缺陷
        unassigned_mask = (data['domain'].isna()) | (data['domain'] == '') | (data['domain'].str.strip() == '')
        unassigned_data = data[unassigned_mask].copy()
        assigned_data = data[~unassigned_mask].copy()
        
        if len(unassigned_data) == 0:
            return data
        
        # 为每个AIDA领域建立Solution Cluster映射
        aida_to_cluster_map = {}
        for _, row in assigned_data.iterrows():
            aida = row.get('aida_english', '')
            cluster = row.get('domain', '')
            if aida and cluster:
                if aida not in aida_to_cluster_map:
                    aida_to_cluster_map[aida] = {}
                if cluster not in aida_to_cluster_map[aida]:
                    aida_to_cluster_map[aida][cluster] = 0
                aida_to_cluster_map[aida][cluster] += 1
        
        # 定义AIDA到合理Solution Cluster的预期映射（基于领域知识）
        expected_aida_cluster_mapping = {
            'videostreaming': ['multimedia', 'streaming', 'video', 'display', 'camera'],
            'audio': ['audio', 'multimedia', 'sound', 'speaker'],
            'communication': ['communication', 'network', 'connectivity', 'radio'],
            'navigation': ['navigation', 'gps', 'maps', 'routing'],
            'vehicle_control': ['vehicle', 'control', 'drive', 'chassis'],
            'safety': ['safety', 'security', 'protection', 'airbag'],
            'infotainment': ['infotainment', 'entertainment', 'multimedia', 'hmi'],
            'diagnosis': ['diagnosis', 'diagnostic', 'system', 'obd'],
            'climate': ['climate', 'hvac', 'temperature', 'air'],
            'lighting': ['lighting', 'light', 'illumination', 'led'],
            'body': ['body', 'door', 'window', 'seat'],
            'powertrain': ['powertrain', 'engine', 'transmission', 'hybrid'],
            'connectivity': ['connectivity', 'bluetooth', 'wifi', 'cellular']
        }
        
        # 为每个AIDA选择最合理的Solution Cluster
        aida_preferred_cluster = {}
        for aida, clusters in aida_to_cluster_map.items():
            if clusters:
                # 首先检查是否有符合预期的映射
                expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                
                best_cluster = None
                best_score = 0
                best_count = 0
                
                for cluster, count in clusters.items():
                    score = 0
                    cluster_lower = cluster.lower()
                    
                    # 计算匹配分数：如果cluster名称包含预期关键词，给予额外分数
                    for keyword in expected_keywords:
                        if keyword in cluster_lower:
                            score += 10  # 预期匹配给高分
                    
                    # 添加出现频次作为基础分数
                    score += count
                    
                    # 选择分数最高的cluster
                    if score > best_score or (score == best_score and count > best_count):
                        best_cluster = cluster
                        best_score = score
                        best_count = count
                
                if best_cluster:
                    aida_preferred_cluster[aida] = best_cluster
        
        # 重新分配未分配的缺陷
        data_copy = data.copy()
        assigned_count = 0
        skipped_count = 0
        for idx, row in unassigned_data.iterrows():
            aida = row.get('aida_english', '')
            if aida in aida_preferred_cluster:
                # 额外验证：如果分配结果明显不合理，跳过自动分配
                preferred_cluster = aida_preferred_cluster[aida]
                expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                
                # 对于有预期映射的AIDA，验证分配的合理性
                should_assign = True
                if expected_keywords:
                    match_found = any(keyword in preferred_cluster.lower() for keyword in expected_keywords)
                    if not match_found:
                        # 如果分配明显不合理，保持未分配状态
                        should_assign = False
                        skipped_count += 1
                
                if should_assign:
                    data_copy.at[idx, 'domain'] = preferred_cluster
                    assigned_count += 1
        
        return data_copy
    
    # 执行智能分配
    filtered_data = reassign_unassigned_clusters_modal(filtered_data)
    
    status_values_normalized = {str(s).strip().lower() for s in (statuses or [])}
    cwa_selected = any('09-concluded without action' in s for s in status_values_normalized)
    chart_data = filtered_data.copy()
    x_field = 'aida_dimension'
    x_axis_title = "AIDA领域"
    title_prefix = "AIDA领域缺陷分布（按严重性）"
    hover_prefix = "AIDA领域"

    if cwa_selected:
        if 'blocking_reason' in chart_data.columns:
            chart_data['blocking_reason_dimension'] = chart_data['blocking_reason'].apply(extract_filter_value)
        elif 'blocking_reason_udf' in chart_data.columns:
            chart_data['blocking_reason_dimension'] = chart_data['blocking_reason_udf'].apply(
                lambda x: extract_filter_value(x.get('name', '')) if isinstance(x, dict) else extract_filter_value(x)
            )
        else:
            chart_data['blocking_reason_dimension'] = ''
        chart_data['blocking_reason_dimension'] = chart_data['blocking_reason_dimension'].replace('', 'Unknown/Empty')
        x_field = 'blocking_reason_dimension'
        x_axis_title = "Blocking Reason"
        title_prefix = "CWA Blocking Reason分布（按严重性）"
        hover_prefix = "Blocking Reason"
    else:
        chart_data['aida_dimension'] = build_chart_dimension(chart_data, 'top_aida', 'aida_english')
    
    grouped_status = chart_data.groupby([x_field, 'severity_group']).size().reset_index(name='缺陷数量')
    
    dimension_totals = grouped_status.groupby(x_field)['缺陷数量'].sum().reset_index()
    dimension_order = sort_dimension_with_unknown_last(dimension_totals, x_field)
    
    # 计算总defect数量
    total_defects = filtered_data.shape[0]
    
    # 创建堆叠条形图
    fig = px.bar(
        grouped_status,
        x=x_field,
        y='缺陷数量',
        color='severity_group',
        barmode='stack',
        color_discrete_map=SEVERITY_COLORS,
        title=title_prefix,
        category_orders={x_field: dimension_order}
    )
    
    # 设置悬停模板
    fig.update_traces(
        hovertemplate=f'<b>{hover_prefix}: %{{x}}</b><br>缺陷数量: %{{y}}<br>类型: %{{fullData.name}}'
    )
    
    # 设置文本位置为柱内居中
    
    # 设置标题和布局
    projects_text = "所有项目"
    date_range_text = "所有日期" if not start_date and not end_date else f"{start_date or 'Beginning'} to {end_date or 'Now'}"
    aidas_text = "所有AIDA" if not aidas or len(aidas) == 0 else ", ".join(aidas)
    statuses_text = "所有状态" if not statuses or len(statuses) == 0 else ", ".join(statuses)
    pus_text = "所有PU" if not pus or len(pus) == 0 else ", ".join(pus)
    severe_matrices_text = "默认" if not severe_matrices or len(severe_matrices) == 0 else f"{len(severe_matrices)}个Matrix"
    severe_classifications_text = "默认" if not severe_classifications or len(severe_classifications) == 0 else f"{len(severe_classifications)}个Classification"
    
    title = f"{title_prefix}<br><sup>项目: {projects_text} | 日期范围: {date_range_text} | AIDA: {aidas_text} | Status: {statuses_text} | PU: {pus_text} | 严重Matrix: {severe_matrices_text} | 严重Classification: {severe_classifications_text}</sup>"
    
    # 使用通用样式函数
    fig = apply_chart_style(
        fig, 
        title=title,
        x_title=x_axis_title,
        y_title="缺陷数量"
    )
    
    # 在图表右上角添加总数标注
    fig.add_annotation(
        text=f"total: {total_defects} 个Defect",
        xref="paper", yref="paper",
        x=0.98, y=0.98,
        showarrow=False,
        font=dict(size=14, color="black"),
        xanchor='right'
    )
    
    # 在每个柱状图顶部添加总数标注
    for dimension_value in dimension_order:
        dimension_total = dimension_totals[dimension_totals[x_field] == dimension_value]['缺陷数量'].iloc[0]
        fig.add_annotation(
            text=str(dimension_total),
            x=dimension_value,
            y=dimension_total,
            yshift=10,
            showarrow=False,
            font=dict(size=12, color="black"),
            xanchor='center'
        )
    
    if CACHE_MANAGER_AVAILABLE and default_cache_manager:
        default_cache_manager.set(cache_key, fig, timeout=DEFECT_STATUS_CACHE_TTL_SECONDS)

    return fig

@app.callback(
    Output('solution-cluster-chart', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('project-dropdown', 'value'),
     Input('date-range-picker-main', 'start_date'),
     Input('date-range-picker-main', 'end_date'),
     Input('aida-dropdown', 'value'),
     Input('status-dropdown', 'value'),
     Input('pu-dropdown', 'value'),
     Input('tester-dropdown-main', 'value'),
     Input('fv-dropdown', 'value'),
     Input('ecu-dropdown', 'value'),
     Input('lead-model-dropdown', 'value'),
     Input('fvp-dropdown', 'value'),
     Input('market-dropdown', 'value'),
     Input('severe-matrix-dropdown', 'value'),
     Input('severe-classification-dropdown', 'value')],
    prevent_initial_call=False
)
def update_solution_cluster_chart(years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值（与主下拉菜单保持一致）
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
    
    # 动态计算严重性分组，基于用户选择的matrix和classification
    if severe_matrices is None:
        severe_matrices = []
    if severe_classifications is None:
        severe_classifications = []
    
    # 重新计算严重性分组
    filtered_data = filtered_data.copy()
    
    def is_severe_defect(row):
        # 检查Matrix是否为严重
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        
        # 检查Classification是否为严重
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        # 只要满足任一条件就是严重问题
        return matrix_severe or classification_severe
    
    filtered_data['severity_group'] = filtered_data.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 智能分配逻辑：根据AIDA领域将未分配的缺陷归属到包含相同AIDA的Solution Cluster
    def reassign_unassigned_clusters(data):
        # 找到未分配的缺陷
        unassigned_mask = (data['domain'].isna()) | (data['domain'] == '') | (data['domain'].str.strip() == '')
        unassigned_data = data[unassigned_mask].copy()
        assigned_data = data[~unassigned_mask].copy()
        
        if len(unassigned_data) == 0:
            return data
        
        # 为每个AIDA领域建立Solution Cluster映射
        aida_to_cluster_map = {}
        for _, row in assigned_data.iterrows():
            aida = row.get('aida_english', '')
            cluster = row.get('domain', '')
            if aida and cluster:
                if aida not in aida_to_cluster_map:
                    aida_to_cluster_map[aida] = {}
                if cluster not in aida_to_cluster_map[aida]:
                    aida_to_cluster_map[aida][cluster] = 0
                aida_to_cluster_map[aida][cluster] += 1
        
        # 定义AIDA到合理Solution Cluster的预期映射（基于领域知识）
        expected_aida_cluster_mapping = {
            'videostreaming': ['multimedia', 'streaming', 'video', 'display', 'camera'],
            'audio': ['audio', 'multimedia', 'sound', 'speaker'],
            'communication': ['communication', 'network', 'connectivity', 'radio'],
            'navigation': ['navigation', 'gps', 'maps', 'routing'],
            'vehicle_control': ['vehicle', 'control', 'drive', 'chassis'],
            'safety': ['safety', 'security', 'protection', 'airbag'],
            'infotainment': ['infotainment', 'entertainment', 'multimedia', 'hmi'],
            'diagnosis': ['diagnosis', 'diagnostic', 'system', 'obd'],
            'climate': ['climate', 'hvac', 'temperature', 'air'],
            'lighting': ['lighting', 'light', 'illumination', 'led'],
            'body': ['body', 'door', 'window', 'seat'],
            'powertrain': ['powertrain', 'engine', 'transmission', 'hybrid'],
            'connectivity': ['connectivity', 'bluetooth', 'wifi', 'cellular']
        }
        
        # 为每个AIDA选择最合理的Solution Cluster
        aida_preferred_cluster = {}
        for aida, clusters in aida_to_cluster_map.items():
            if clusters:
                # 首先检查是否有符合预期的映射
                expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                
                best_cluster = None
                best_score = 0
                best_count = 0
                
                for cluster, count in clusters.items():
                    score = 0
                    cluster_lower = cluster.lower()
                    
                    # 计算匹配分数：如果cluster名称包含预期关键词，给予额外分数
                    for keyword in expected_keywords:
                        if keyword in cluster_lower:
                            score += 10  # 预期匹配给高分
                    
                    # 添加出现频次作为基础分数
                    score += count
                    
                    # 选择分数最高的cluster
                    if score > best_score or (score == best_score and count > best_count):
                        best_cluster = cluster
                        best_score = score
                        best_count = count
                
                if best_cluster:
                    aida_preferred_cluster[aida] = best_cluster
        
        # 重新分配未分配的缺陷
        data_copy = data.copy()
        assigned_count = 0
        skipped_count = 0
        for idx, row in unassigned_data.iterrows():
            aida = row.get('aida_english', '')
            if aida in aida_preferred_cluster:
                # 额外验证：如果分配结果明显不合理，跳过自动分配
                preferred_cluster = aida_preferred_cluster[aida]
                expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                
                # 对于有预期映射的AIDA，验证分配的合理性
                should_assign = True
                if expected_keywords:
                    match_found = any(keyword in preferred_cluster.lower() for keyword in expected_keywords)
                    if not match_found:
                        # 如果分配明显不合理，保持未分配状态
                        should_assign = False
                        skipped_count += 1
                
                if should_assign:
                    data_copy.at[idx, 'domain'] = preferred_cluster
                    assigned_count += 1
        
        return data_copy
    
    # 执行智能分配
    filtered_data = reassign_unassigned_clusters(filtered_data)
    
    # 处理空的solution cluster值
    filtered_data['domain_display'] = filtered_data['domain'].apply(
        lambda x: x if x and x.strip() else "未分配"
    )
    
    # 按Solution Cluster和严重性分组
    cluster_status = filtered_data.groupby(['domain_display', 'severity_group']).size().reset_index(name='缺陷数量')
    
    # 按Solution Cluster的总缺陷数量降序排列
    cluster_totals = cluster_status.groupby('domain_display')['缺陷数量'].sum().reset_index()
    cluster_totals = cluster_totals.sort_values('缺陷数量', ascending=False)
    cluster_order = cluster_totals['domain_display'].tolist()
    
    # 计算总defect数量
    total_defects = filtered_data.shape[0]
    
    # 创建堆叠条形图
    fig = px.bar(
        cluster_status,
        x='domain_display',
        y='缺陷数量',
        color='severity_group',
        barmode='stack',
        color_discrete_map=SEVERITY_COLORS,
        title="Solution Cluster缺陷分布（按严重性）",
        category_orders={'domain_display': cluster_order},  # 添加排序
    )
    
    # 设置文本位置为柱内居中
    
    # 设置悬停模板
    fig.update_traces(
        hovertemplate='<b>Solution Cluster: %{x}</b><br>缺陷数量: %{y}<br>类型: %{fullData.name}'
    )
    
    # 设置标题和布局（移除总数）
    projects_text = "所有项目"
    date_range_text = "所有日期" if not start_date and not end_date else f"{start_date or 'Beginning'} to {end_date or 'Now'}"
    aidas_text = "所有AIDA" if not aidas or len(aidas) == 0 else ", ".join(aidas)
    statuses_text = "所有状态" if not statuses or len(statuses) == 0 else ", ".join(statuses)
    pus_text = "所有PU" if not pus or len(pus) == 0 else ", ".join(pus)
    severe_matrices_text = "默认" if not severe_matrices or len(severe_matrices) == 0 else f"{len(severe_matrices)}个Matrix"
    severe_classifications_text = "默认" if not severe_classifications or len(severe_classifications) == 0 else f"{len(severe_classifications)}个Classification"
    
    title = f"Solution Cluster缺陷分布（智能分配）<br><sup>项目: {projects_text} | 日期范围: {date_range_text} | AIDA: {aidas_text} | Status: {statuses_text} | PU: {pus_text} | 严重Matrix: {severe_matrices_text} | 严重Classification: {severe_classifications_text}</sup>"
    
    # 使用通用样式函数
    fig = apply_chart_style(
        fig, 
        title=title,
        x_title="Solution Cluster",
        y_title="缺陷数量"
    )
    
    # 添加总数标注到右上角
    fig.add_annotation(
        text=f"total: {total_defects} 个Defect",
        xref="paper", yref="paper",
        x=0.98, y=0.98,
        showarrow=False,
        font=dict(size=14, color="black"),
        align="right",
        xanchor='right'
    )
    
    # 在每个柱状图顶部添加总数标注
    for cluster in cluster_order:
        cluster_total = cluster_totals[cluster_totals['domain_display'] == cluster]['缺陷数量'].iloc[0]
        fig.add_annotation(
            text=str(cluster_total),
            x=cluster,
            y=cluster_total,
            yshift=10,
            showarrow=False,
            font=dict(size=12, color="black"),
            xanchor='center'
        )
    
    # 旋转x轴标签以避免重叠
    fig.update_layout(
        xaxis_tickangle=-45
    )
    
    return fig

# Callback to close modal
@app.callback(
    Output('defect-modal', 'style', allow_duplicate=True),
    [Input('close-modal-btn', 'n_clicks'),
     Input('defect-modal-overlay', 'n_clicks')],
    prevent_initial_call=True
)
def close_modal(close_clicks, overlay_clicks):
    from dash import callback_context
    from dash.exceptions import PreventUpdate

    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    return {'display': 'none'}

# 专门的HR图表Modal回调函数
@app.callback(
    [Output('defect-modal', 'style', allow_duplicate=True),
     Output('modal-defect-table', 'data', allow_duplicate=True),
     Output('modal-info', 'children', allow_duplicate=True)],
    [Input('hr-child-complexity-chart', 'clickData'),
     Input('hr-parent-complexity-chart', 'clickData')],
    [State('current-nav-item', 'data'),
     State('hr-year-dropdown', 'value'),
     State('hr-project-dropdown', 'value'),
     State('hr-date-range-picker-main', 'start_date'),
     State('hr-date-range-picker-main', 'end_date'),
     State('hr-aida-dropdown', 'value'),
     State('hr-status-dropdown', 'value'),
     State('hr-pu-dropdown', 'value'),
     State('hr-tester-dropdown-main', 'value')],
    prevent_initial_call=True,
    suppress_callback_exceptions=True
)
def show_hr_modal(hr_child_click_data, hr_parent_click_data, current_tab, years, projects, start_date, end_date, aidas, statuses, pus, testers):
    from dash import callback_context, no_update
    from dash.exceptions import PreventUpdate

    ctx = callback_context
    if not ctx.triggered or current_tab != 'tab-defect-high-runner':
        raise PreventUpdate

    triggered_input = ctx.triggered[0]['prop_id'].split('.')[0]
    click_data = hr_child_click_data if triggered_input == 'hr-child-complexity-chart' else hr_parent_click_data

    if not click_data:
        raise PreventUpdate

    modal_style = {
        'display': 'flex',
        'position': 'fixed',
        'zIndex': '1000',
        'left': '0',
        'top': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'justifyContent': 'center',
        'alignItems': 'center'
    }

    info_text = ""
    filtered_data = filter_dataframe(
        df=df,
        years=years or [],
        projects=projects or [],
        start_date=start_date,
        end_date=end_date,
        aidas=aidas or [],
        statuses=statuses or [],
        pus=pus or [],
        testers=testers or [],
        fvs=[],
        ecus=[],
        lead_models=[],
        fvps=[],
        markets=[]
    )

    if triggered_input == 'hr-child-complexity-chart' and hr_child_click_data:
        # 点击了 High Runner Child Complexity 图表
        try:
            # 从 customdata 中获取 level 和 week 信息 [level, week, count]
            if 'customdata' in hr_child_click_data['points'][0] and len(hr_child_click_data['points'][0]['customdata']) >= 2:
                clicked_level = hr_child_click_data['points'][0]['customdata'][0]  # defect_level (High/Medium/Low)
                clicked_week = hr_child_click_data['points'][0]['customdata'][1]   # test_week_sortable
                
                # 筛选对应的数据 - Child tickets with specific level and week
                filtered_data = filtered_data[
                    (filtered_data['test_week'].apply(extract_filter_value) == extract_filter_value(clicked_week)) &
                    (filtered_data['parent_child'].isin(['Child', 'Child (candidate)']))
                ]
                
                # 计算缺陷级别并筛选
                if 'child_count_of_master' in filtered_data.columns:
                    filtered_data = filtered_data.copy()
                    filtered_data['defect_level_calc'] = filtered_data['child_count_of_master'].apply(categorize_defect_level_hr)
                    filtered_data = filtered_data[filtered_data['defect_level_calc'] == clicked_level]
                
                info_text = f"Child Complexity | 测试周: {clicked_week} | 复杂度级别: {clicked_level} | 共找到 {len(filtered_data)} 条子缺陷"
                
            else:
                # 如果没有customdata，尝试从x和trace name获取信息
                clicked_week = hr_child_click_data['points'][0]['x']
                clicked_level = hr_child_click_data['points'][0]['fullData']['name']
                
                filtered_data = filtered_data[
                    (filtered_data['test_week'].apply(extract_filter_value) == extract_filter_value(clicked_week)) &
                    (filtered_data['parent_child'].isin(['Child', 'Child (candidate)']))
                ]
                
                # 计算缺陷级别并筛选
                if 'child_count_of_master' in filtered_data.columns:
                    filtered_data = filtered_data.copy()
                    filtered_data['defect_level_calc'] = filtered_data['child_count_of_master'].apply(categorize_defect_level_hr)
                    filtered_data = filtered_data[filtered_data['defect_level_calc'] == clicked_level]
                
                info_text = f"Child Complexity | 测试周: {clicked_week} | 复杂度级别: {clicked_level} | 共找到 {len(filtered_data)} 条子缺陷"
                
        except (KeyError, IndexError, TypeError) as e:
            print(f"处理Child Complexity图表点击数据时出错: {e}")
            # 降级处理：只显示包含child_count_of_master > 0的数据
            filtered_data = filtered_data[
                (filtered_data['parent_child'].isin(['Child', 'Child (candidate)'])) &
                (filtered_data.get('child_count_of_master', 0) > 0)
            ]
            info_text = f"Child Complexity | 共找到 {len(filtered_data)} 条高复杂度子缺陷"
        
        # 显示Modal
        modal_style['display'] = 'flex'
        
    elif triggered_input == 'hr-parent-complexity-chart' and hr_parent_click_data:
        # 点击了 High Runner Parent Complexity 图表
        try:
            # 从 customdata 中获取 level 和 week 信息 [level, week, count]
            if 'customdata' in hr_parent_click_data['points'][0] and len(hr_parent_click_data['points'][0]['customdata']) >= 2:
                clicked_level = hr_parent_click_data['points'][0]['customdata'][0]  # master_linked_defect_level (High/Medium/Low)
                clicked_week = hr_parent_click_data['points'][0]['customdata'][1]   # test_week_sortable
                
                # 筛选对应的数据 - Parent tickets with specific level and week
                filtered_data = filtered_data[
                    (filtered_data['test_week'].apply(extract_filter_value) == extract_filter_value(clicked_week)) &
                    (filtered_data['parent_child'] == 'Parent')
                ]
                
                # 计算关联缺陷级别并筛选
                if 'relation_to_udf' in filtered_data.columns:
                    filtered_data = filtered_data.copy()
                    filtered_data['linked_defect_count_calc'] = filtered_data['relation_to_udf'].apply(count_linked_defects_hr)
                    filtered_data['master_linked_defect_level_calc'] = filtered_data['linked_defect_count_calc'].apply(categorize_master_linked_level_hr)
                    filtered_data = filtered_data[filtered_data['master_linked_defect_level_calc'] == clicked_level]
                
                info_text = f"Parent Complexity | 测试周: {clicked_week} | 关联级别: {clicked_level} | 共找到 {len(filtered_data)} 条父缺陷"
                
            else:
                # 如果没有customdata，尝试从x和trace name获取信息
                clicked_week = hr_parent_click_data['points'][0]['x']
                clicked_level = hr_parent_click_data['points'][0]['fullData']['name']
                
                filtered_data = filtered_data[
                    (filtered_data['test_week'].apply(extract_filter_value) == extract_filter_value(clicked_week)) &
                    (filtered_data['parent_child'] == 'Parent')
                ]
                
                # 计算关联缺陷级别并筛选
                if 'relation_to_udf' in filtered_data.columns:
                    filtered_data = filtered_data.copy()
                    filtered_data['linked_defect_count_calc'] = filtered_data['relation_to_udf'].apply(count_linked_defects_hr)
                    filtered_data['master_linked_defect_level_calc'] = filtered_data['linked_defect_count_calc'].apply(categorize_master_linked_level_hr)
                    filtered_data = filtered_data[filtered_data['master_linked_defect_level_calc'] == clicked_level]
                
                info_text = f"Parent Complexity | 测试周: {clicked_week} | 关联级别: {clicked_level} | 共找到 {len(filtered_data)} 条父缺陷"
                
        except (KeyError, IndexError, TypeError) as e:
            print(f"处理Parent Complexity图表点击数据时出错: {e}")
            # 降级处理：只显示包含relation_to_udf的父票
            filtered_data = filtered_data[
                (filtered_data['parent_child'] == 'Parent') &
                (filtered_data.get('relation_to_udf', '').astype(str).str.len() > 0)
            ]
            info_text = f"Parent Complexity | 共找到 {len(filtered_data)} 条有关联的父缺陷"
        
        # 显示Modal
        modal_style['display'] = 'flex'
    
    # 如果没有点击图表，不做处理
    if not (triggered_input in ['hr-child-complexity-chart', 'hr-parent-complexity-chart'] and 
            (hr_child_click_data or hr_parent_click_data)):
        from dash.exceptions import PreventUpdate
        raise PreventUpdate
    
    # 准备表格数据
    if filtered_data.empty:
        return modal_style, [], info_text
    
    # HR图表需要额外的列
    available_columns = ['id', 'name', 'ecu', 'creation_time', 'aida_english', 'status_phase', 'tester', 'parent_child']
    
    # 添加HR特有的列（如果存在）
    if 'child_count_of_master' in filtered_data.columns:
        available_columns.append('child_count_of_master')
    if 'relation_to_udf' in filtered_data.columns:
        available_columns.append('relation_to_udf')
    if 'master_id' in filtered_data.columns:
        available_columns.append('master_id')
    if 'pu' in filtered_data.columns:
        available_columns.append('pu')
    if 'matrix' in filtered_data.columns:
        available_columns.append('matrix')
        
    # 过滤出实际存在的列
    existing_columns = [col for col in available_columns if col in filtered_data.columns]
    
    # 先按Risk Score排序，确保高分ticket在前面
    if 'topissue_risk_score' in filtered_data.columns:
        filtered_data_sorted = filtered_data.sort_values('topissue_risk_score', ascending=False)
    elif 'topissue_display' in filtered_data.columns:
        # 提取topissue_display中的数值进行排序
        def extract_numeric_score(score_str):
            if pd.isna(score_str) or score_str == '':
                return 0
            try:
                # 提取数字部分，如"230分" -> 230
                import re
                numbers = re.findall(r'\d+', str(score_str))
                return int(numbers[0]) if numbers else 0
            except:
                return 0
        
        filtered_data['topissue_score_numeric'] = filtered_data['topissue_display'].apply(extract_numeric_score)
        filtered_data_sorted = filtered_data.sort_values('topissue_score_numeric', ascending=False)
    else:
        filtered_data_sorted = filtered_data
    
    table_data = filtered_data_sorted[existing_columns].head(100).copy()
    
    # 将ID转换为超链接格式
    table_data['id'] = table_data['id'].apply(make_ticket_link)
    
    # 处理matrix显示
    if 'matrix' in table_data.columns:
        table_data['matrix_display'] = table_data['matrix'].apply(lambda x: 
            x.replace('Matrix-', '').replace('matrix-', '').upper() if x else '')
    
    # 处理relation_to_udf字段的显示
    if 'relation_to_udf' in table_data.columns:
        table_data['child_ids_of_master_display'] = table_data['relation_to_udf'].astype(str)
        # 添加计算字段
        table_data['linked_defect_count'] = filtered_data['relation_to_udf'].apply(count_linked_defects_hr)
        table_data['master_linked_defect_level'] = table_data['linked_defect_count'].apply(categorize_master_linked_level_hr)
    
    return modal_style, table_data.to_dict('records'), info_text

# 修改为Modal回调函数 - 恢复原始defect_explore 24.py的完整实现
@app.callback(
    [Output('defect-modal', 'style'),
     Output('modal-defect-table', 'data'),
     Output('modal-info', 'children')],
    [Input('fv-distribution-chart', 'clickData'),
     Input('defect-status-chart', 'clickData'),
     Input('solution-cluster-chart', 'clickData'),
     Input('close-modal-btn', 'n_clicks'),
     Input('defect-modal-overlay', 'n_clicks')],
    [State('defect-modal', 'style'),
     State('current-nav-item', 'data'),
     State('year-dropdown', 'value'),
     State('project-dropdown', 'value'),
     State('date-range-picker-main', 'start_date'),
     State('date-range-picker-main', 'end_date'),
     State('aida-dropdown', 'value'),
     State('status-dropdown', 'value'),
     State('pu-dropdown', 'value'),
     State('tester-dropdown-main', 'value'),
     State('fv-dropdown', 'value'),
     State('ecu-dropdown', 'value'),
     State('lead-model-dropdown', 'value'),
     State('fvp-dropdown', 'value'),
     State('market-dropdown', 'value'),
     State('severe-matrix-dropdown', 'value'),
     State('severe-classification-dropdown', 'value')],
    prevent_initial_call=True
)
def update_modal(fv_click_data, status_click_data, cluster_click_data, close_clicks, overlay_clicks,
                current_modal_style, current_tab, years, projects, start_date, end_date, 
                aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets,
                severe_matrices, severe_classifications):
    # 处理筛选器参数，确保它们是列表格式
    if projects is None:
        projects = []
    if aidas is None:
        aidas = []
    if statuses is None:
        statuses = []
    if pus is None:
        pus = []
    if testers is None:
        testers = []
    if fvs is None:
        fvs = []
    if ecus is None:
        ecus = []
    if lead_models is None:
        lead_models = []
    if fvps is None:
        fvps = []
    if severe_matrices is None:
        severe_matrices = []
    if severe_classifications is None:
        severe_classifications = []
    from dash import callback_context
    topissue_chart_inputs = ['fv-distribution-chart', 'defect-status-chart', 'solution-cluster-chart']
    
    # 如果当前在测试覆盖率页面，不处理modal回调
    if current_tab == 'tab-test-coverage':
        return {'display': 'none'}, [], ""
    
    ctx = callback_context
    triggered_input = None
    
    if ctx.triggered:
        triggered_input = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 如果点击了关闭按钮或遮罩层，隐藏Modal
    if triggered_input in ['close-modal-btn', 'defect-modal-overlay']:
        modal_style = {
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        return modal_style, [], ""
    
    if triggered_input not in topissue_chart_inputs:
        return current_modal_style, [], ""
    
    if current_tab != 'tab-defect-status':
        return current_modal_style, [], ""
    
    # 使用通用筛选函数，传入当前的筛选器状态（包括market筛选）
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
    
    # 动态计算严重性分组，基于用户选择的matrix和classification（仅适用于非High Runner页面）
    if current_tab != 'tab-defect-high-runner':
        if severe_matrices is None:
            severe_matrices = []
        if severe_classifications is None:
            severe_classifications = []
        
        # 重新计算严重性分组
        filtered_data = filtered_data.copy()
        
        def is_severe_defect(row):
            # 检查Matrix是否为严重
            matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
            
            # 检查Classification是否为严重
            classification_severe = False
            if isinstance(row['classification'], list):
                classification_severe = any(cls in severe_classifications for cls in row['classification'])
            
            # 只要满足任一条件就是严重问题
            return matrix_severe or classification_severe
        
        filtered_data['severity_group'] = filtered_data.apply(
            lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues",
            axis=1
        )
    
    # 根据点击的图表类型过滤数据
    if triggered_input == 'fv-distribution-chart' and fv_click_data:
        # 处理FV分布图表点击
        clicked_fv = fv_click_data['points'][0]['x']
        filtered_data = filtered_data.copy()
        filtered_data['fv_dimension'] = build_chart_dimension(filtered_data, 'fv')
        
        # 确定点击的是哪个严重性组
        try:
            clicked_trace_name = fv_click_data['points'][0]['fullData']['name']
            clicked_curve_name = clicked_trace_name  # 直接使用trace name，它应该是'Critical Issues'或'General Issues'
            
            filtered_data = filtered_data[
                (filtered_data['fv_dimension'] == clicked_fv) & 
                (filtered_data['severity_group'] == clicked_curve_name)
            ]
            
            info_text = f"FV: {clicked_fv} | 类型: {clicked_curve_name} | 共找到 {len(filtered_data)} 条缺陷"
            
        except (KeyError, IndexError):
            filtered_data = filtered_data[filtered_data['fv_dimension'] == clicked_fv]
            info_text = f"FV: {clicked_fv} | 共找到 {len(filtered_data)} 条缺陷"
        
        # 显示Modal
        modal_style = {
            'display': 'flex',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        
    elif triggered_input == 'defect-status-chart' and status_click_data:
        # 处理AIDA图表点击
        clicked_aida = status_click_data['points'][0]['x']
        filtered_data = filtered_data.copy()
        filtered_data['aida_dimension'] = build_chart_dimension(filtered_data, 'top_aida', 'aida_english')
        
        # 确定点击的是哪个严重性组
        try:
            clicked_trace_name = status_click_data['points'][0]['fullData']['name']
            clicked_curve_name = clicked_trace_name  # 直接使用trace name，它应该是'Critical Issues'或'General Issues'
            
            filtered_data = filtered_data[
                (filtered_data['aida_dimension'] == clicked_aida) & 
                (filtered_data['severity_group'] == clicked_curve_name)
            ]
            
            info_text = f"AIDA: {clicked_aida} | 类型: {clicked_curve_name} | 共找到 {len(filtered_data)} 条缺陷"
            
        except (KeyError, IndexError):
            filtered_data = filtered_data[filtered_data['aida_dimension'] == clicked_aida]
            info_text = f"AIDA: {clicked_aida} | 共找到 {len(filtered_data)} 条缺陷"
        
        # 显示Modal
        modal_style = {
            'display': 'flex',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        
    elif triggered_input == 'solution-cluster-chart' and cluster_click_data:
        # 点击了Solution Cluster图表
        clicked_cluster = cluster_click_data['points'][0]['x']
        
        # 处理空的solution cluster值显示为"未分配"
        if clicked_cluster == "未分配":
            # 筛选空的domain值
            filtered_data = filtered_data[
                (filtered_data['domain'].isna()) | 
                (filtered_data['domain'] == '') | 
                (filtered_data['domain'].str.strip() == '')
            ]
        else:
            # 筛选对应的domain值
            filtered_data = filtered_data[filtered_data['domain'] == clicked_cluster]
        
        # 确定点击的是哪个严重性组
        try:
            clicked_trace_name = cluster_click_data['points'][0]['fullData']['name']
            clicked_curve_name = clicked_trace_name  # 直接使用trace name，它应该是'Critical Issues'或'General Issues'
            
            filtered_data = filtered_data[filtered_data['severity_group'] == clicked_curve_name]
            info_text = f"Solution Cluster: {clicked_cluster} | 类型: {clicked_curve_name} | 共找到 {len(filtered_data)} 条缺陷"
            
        except (KeyError, IndexError):
            # 如果无法确定严重性组，显示所有数据
            info_text = f"Solution Cluster: {clicked_cluster} | 共找到 {len(filtered_data)} 条缺陷"
        
        # 显示Modal
        modal_style = {
            'display': 'flex',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        
    # 如果没有点击图表，隐藏Modal
    if not (triggered_input in ['fv-distribution-chart', 'defect-status-chart', 'solution-cluster-chart'] and 
            (fv_click_data or status_click_data or cluster_click_data)):
        modal_style = {
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        return modal_style, [], ""
    
    # 按Matrix严重性排序（兼容缺少matrix_order列的场景）
    if 'matrix_order' in filtered_data.columns:
        filtered_data = filtered_data.sort_values('matrix_order')
    elif 'matrix_display' in filtered_data.columns:
        filtered_data = filtered_data.sort_values('matrix_display')
    
    # 选择要显示的列并限制行数
    table_data = filtered_data[['id', 'name', 'ecu', 'creation_time', 'matrix_display', 'topissue_display', 'aida_english', 'status_phase', 'tester', 'severity_group', 'is_topissue', 'classification']].head(100)
    
    # 处理classification列表
    table_data = table_data.copy()
    
    # 将ID转换为超链接格式
    table_data['id'] = table_data['id'].apply(make_ticket_link)       
    
    table_data['classification_display'] = table_data['classification'].apply(lambda x: ', '.join(x) if isinstance(x, list) else str(x) if x is not None else '未分类')
    
    # 处理ECU变更次数 - 改为显示流转路径
    print("开始处理ECU流转路径...")
    def get_ecu_flow_path(row):
        """获取ECU流转路径"""
        defect_id = str(row.get('id', ''))
        if defect_id:
            try:
                path = get_ecu_transition_path(defect_id)
                if path and path != "No change":
                    # path已经包含了次数和路径（格式："次数, 路径"），直接返回
                    return path
                return "No change"
            except Exception as e:
                print(f"获取ECU流转路径失败 (ID: {defect_id}): {e}")
                return "No change"
        return "No change"
    
    table_data['ecu_pingpong_display'] = filtered_data.apply(get_ecu_flow_path, axis=1)
    
    # 处理Solution Cluster变更 - 改为显示流转路径
    print("开始处理Solution Cluster流转路径...")
    def get_solution_cluster_flow_path(row):
        """获取Solution Cluster流转路径"""
        defect_id = str(row.get('id', ''))
        if defect_id:
            try:
                path = get_solution_cluster_transition_path(defect_id)
                if path and path != "No change":
                    # path已经包含了次数和路径（格式："次数, 路径"），直接返回
                    return path
                return "No change"
            except Exception as e:
                print(f"获取Solution Cluster流转路径失败 (ID: {defect_id}): {e}")
                return "No change"
        return "No change"
    
    table_data['domain_pingpong_display'] = filtered_data.apply(get_solution_cluster_flow_path, axis=1)
    
    # 处理Parent/Child字段 - 基于parent_child字段
    if 'parent_child' in filtered_data.columns:
        table_data['parent_child_display'] = filtered_data['parent_child'].fillna('Unknown')
    else:
        # 如果没有parent_child字段，设置为Unknown
        table_data['parent_child_display'] = 'Unknown'
    
    # 处理Child Count字段 - 当ticket是子票时，显示它所链接的主票包含多少个子票
    if 'child_count_of_master' in filtered_data.columns:
        # 只有当ticket是Child时才显示child count，否则显示0
        table_data['child_count_display'] = filtered_data.apply(
            lambda row: row['child_count_of_master'] if row.get('parent_child') in ['Child', 'Child (candidate)'] else 0,
            axis=1
        ).fillna(0).astype(int)
    else:
        table_data['child_count_display'] = 0
    
    # 处理Parent Child Count字段 - 当ticket是父票时，显示它自己作为主票链接了多少个子票
    # 修复逻辑：对于父票，应该计算relation_to_udf中的缺陷数量，而不是依赖linked_defect_count字段
    def count_linked_defects_for_parent(relation_str):
        """计算relation_to_udf中的缺陷数量 - 用于父票"""
        if not relation_str or pd.isna(relation_str):
            return 0
        try:
            # relation_to_udf是逗号分隔的ID列表
            ids = str(relation_str).split(',')
            return len([id.strip() for id in ids if id.strip()])
        except:
            return 0
    
    # 对于父票，使用relation_to_udf计算子票数量；对于非父票，显示0
    table_data['parent_child_count_display'] = filtered_data.apply(
        lambda row: count_linked_defects_for_parent(row.get('relation_to_udf', '')) if row.get('parent_child') == 'Parent' else 0,
        axis=1
    ).astype(int)
    
    # 新增：处理父票信息展示 - 当票据是子票时，显示其父票的详细信息
    def get_parent_ticket_info(row):
        """获取父票信息"""
        if row.get('parent_child') not in ['Child', 'Child (candidate)']:
            return ""
        
        master_id = row.get('master_id')
        if not master_id or pd.isna(master_id):
            return ""
        
        # 首先从全局的master_df中查找父票信息
        global master_df
        if master_df is not None and not master_df.empty:
            # 确保ID类型匹配
            master_df_copy = master_df.copy()
            master_df_copy['id'] = master_df_copy['id'].astype(str)
            master_id_str = str(master_id)
            
            parent_info = master_df_copy[master_df_copy['id'] == master_id_str]
            if not parent_info.empty:
                parent_row = parent_info.iloc[0]
                # 构建父票信息字符串，包含ID、名称、项目、状态等关键信息
                parent_info_str = f"ID: {parent_row.get('id', 'N/A')}"
                if parent_row.get('name'):
                    parent_info_str += f" | Name: {parent_row.get('name', 'N/A')[:50]}..."  # 限制长度
                if parent_row.get('ecu'):
                    parent_info_str += f" | Project: {parent_row.get('ecu', 'N/A')}"
                if parent_row.get('status_phase'):
                    parent_info_str += f" | Status: {parent_row.get('status_phase', 'N/A')}"
                if parent_row.get('matrix_display'):
                    parent_info_str += f" | Matrix: {parent_row.get('matrix_display', 'N/A')}"
                return parent_info_str
        
        # 如果在master_df中找不到，尝试在当前数据中查找
        parent_in_current = filtered_data[filtered_data['id'] == str(master_id)]
        if not parent_in_current.empty:
            parent_row = parent_in_current.iloc[0]
            parent_info_str = f"ID: {parent_row.get('id', 'N/A')}"
            if parent_row.get('name'):
                parent_info_str += f" | Name: {parent_row.get('name', 'N/A')[:50]}..."
            if parent_row.get('ecu'):
                parent_info_str += f" | Project: {parent_row.get('ecu', 'N/A')}"
            if parent_row.get('status_phase'):
                parent_info_str += f" | Status: {parent_row.get('status_phase', 'N/A')}"
            return parent_info_str
        
        return f"Parent Ticket ID: {master_id} (Details not found)"
    
    # 添加父票信息列
    table_data['parent_ticket_info'] = filtered_data.apply(get_parent_ticket_info, axis=1)
    
    # 新增：获取主票状态的专用函数
    def get_master_status(row):
        """获取主票状态"""
        if row.get('parent_child') not in ['Child', 'Child (candidate)']:
            return ""
        
        master_id = row.get('master_id')
        if not master_id or pd.isna(master_id):
            return ""
        
        # 首先从全局的master_df中查找主票状态
        global master_df
        if master_df is not None and not master_df.empty:
            # 确保ID类型匹配
            master_df_copy = master_df.copy()
            master_df_copy['id'] = master_df_copy['id'].astype(str)
            master_id_str = str(master_id)
            
            parent_info = master_df_copy[master_df_copy['id'] == master_id_str]
            if not parent_info.empty:
                parent_row = parent_info.iloc[0]
                # 从phase.name字段获取状态
                phase_name = parent_row.get('phase.name', '')
                if phase_name:
                    return phase_name
                # 如果phase.name为空，尝试其他可能的字段
                return parent_row.get('status_phase', '')
        
        # 如果在master_df中找不到，尝试在当前数据中查找
        parent_in_current = filtered_data[filtered_data['id'] == str(master_id)]
        if not parent_in_current.empty:
            parent_row = parent_in_current.iloc[0]
            return parent_row.get('status_phase', '')
        
        return ""
    
    # 添加主票状态列
    table_data['master_status'] = filtered_data.apply(get_master_status, axis=1)
    
    # 添加处理周期（天数）列
    def calculate_processing_cycle_display(row):
        """为表格显示计算处理周期"""
        return calculate_processing_cycle_days(
            row.get('id'),
            row.get('status_phase'),
            row.get('creation_time')
        )
    
    table_data['processing_cycle_days'] = filtered_data.apply(calculate_processing_cycle_display, axis=1)
    
    # 添加pu和Shift_PU列
    # 如果原数据中有pu列，则直接使用
    if 'pu' in filtered_data.columns:
        table_data['pu'] = filtered_data['pu']
    else:
        table_data['pu'] = '未知'
    
    # 添加Shift_PU列，直接使用数据处理器添加的Shift_PU列
    if 'Shift_PU' in filtered_data.columns:
        table_data['Shift_PU'] = filtered_data['Shift_PU'].fillna('').astype(str)
    else:
        table_data['Shift_PU'] = ''
    
    # 检查并添加topissue_recommend_reason字段 - 格式化为5行显示
    def format_topissue_recommendation(reason_str, row):
        """格式化TopIssue推荐理由为5行清晰显示，包含实际分数计算"""
        if pd.isna(reason_str) or not reason_str or reason_str.strip() == '':
            return 'No recommendation available'
        
        # 如果已经是格式化的字符串，直接返回
        if '1. Severity:' in str(reason_str):
            return str(reason_str)
        
        # 尝试解析原始的推荐理由并格式化
        try:
            reason_text = str(reason_str).strip()
            if reason_text == 'No recommendation available':
                return reason_text
            
            # 初始化4个因素的默认值
            severity_info = "Not detected"
            high_runner_info = "Not detected"
            complexity_info = "Not detected"
            processing_efficiency_info = "Not detected"
            
            # 按行分割原始推荐理由
            lines = reason_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if line.startswith('SEVERITY:'):
                    severity_info = line.replace('SEVERITY:', '').strip()
                elif line.startswith('COMPLEXITY:'):
                    high_runner_info = line.replace('COMPLEXITY:', '').strip()
                elif line.startswith('HIGH RUNNER:'):
                    complexity_info = line.replace('HIGH RUNNER:', '').strip()
                elif line.startswith('LONG RUNNER:'):
                    processing_efficiency_info = line.replace('LONG RUNNER:', '').strip()
            
            # 重新生成COMPLEXITY信息，使用当前行的最新格式化数据
            updated_complexity_items = []
            
            # 使用最新的ECU转移路径信息
            ecu_path = row.get('ecu_pingpong_display', '')
            if ecu_path and str(ecu_path) != 'No change' and str(ecu_path).strip():
                updated_complexity_items.append(f"ECU {ecu_path}")
            
            # 使用最新的Domain转移路径信息  
            domain_path = row.get('domain_pingpong_display', '')
            if domain_path and str(domain_path) != 'No change' and str(domain_path).strip():
                updated_complexity_items.append(f"Domain {domain_path}")
            
            # 如果有更新的COMPLEXITY信息，使用它
            if updated_complexity_items:
                complexity_info = '; '.join(updated_complexity_items)
            elif complexity_info == "Not detected":
                # 如果没有检测到，保持原有逻辑
                pass
            
            # 获取实际的Risk Score和分数分解
            actual_risk_score = row.get('topissue_risk_score', 0)
            if pd.isna(actual_risk_score):
                actual_risk_score = 0
            
            # 计算基础维度分数（用于显示分解）
            basic_scores = calculate_basic_scores(row)
            basic_total = sum([basic_scores[key] for key in basic_scores if key != 'nonlinear'])
            nonlinear_adjustment = max(0, actual_risk_score - basic_total)
            
            # 构建分数分解显示
            score_breakdown = f"Matrix {basic_scores['matrix']}pts + Classification {basic_scores['classification']}pts + ECU Transfer {basic_scores['ecu_transfer']}pts + Domain Transfer {basic_scores['domain_transfer']}pts + Parent Complexity {basic_scores['parent_complexity']}pts + Child Complexity {basic_scores['child_complexity']}pts + Processing Cycle {basic_scores['processing_cycle']}pts + Shift PU {basic_scores['shift_pu']}pts"
            
            if nonlinear_adjustment > 0:
                score_breakdown += f" + Adjustments {nonlinear_adjustment:.0f}pts"
            
            score_breakdown += f" = Total {actual_risk_score}pts"
            
            # 创建格式化的5行推荐理由
            formatted_reason = f"1. Severity: {severity_info}\n"
            formatted_reason += f"2. High Runner: {high_runner_info}\n"
            formatted_reason += f"3. Complexity: {complexity_info}\n"
            formatted_reason += f"4. Processing Efficiency: {processing_efficiency_info}\n"
            formatted_reason += f"5. Risk Score Calculation: {score_breakdown}"
            
            return formatted_reason
        except:
            return 'No recommendation available'
    
    def calculate_basic_scores(row):
        """计算单个票据的基础各维度分数（不包括非线性调整）"""
        scores = {
            'matrix': 0, 'classification': 0, 'ecu_transfer': 0, 'domain_transfer': 0,
            'parent_complexity': 0, 'child_complexity': 0, 'processing_cycle': 0, 'shift_pu': 0
        }
        
        # Matrix分数
        matrix = row.get('matrix', '')
        if isinstance(matrix, str) and matrix:
            matrix_scores = {
                'matrix-1a': 30, 'matrix-1b': 28, 'matrix-1c': 26, 'matrix-1d': 24, 'matrix-1e': 22,
                'matrix-2a': 20, 'matrix-2b': 18, 'matrix-3a': 16, 'matrix-2d': 14, 'matrix-2e': 12,
                'matrix-3b': 10, 'matrix-3c': 8, 'matrix-3d': 6, 'matrix-4a': 4,
                'matrix-3e': 2, 'matrix-4b': 2, 'matrix-4c': 2, 'matrix-4d': 2, 'matrix-4e': 2
            }
            scores['matrix'] = matrix_scores.get(matrix.lower(), 0)
        
        # Classification分数
        classification = row.get('classification', [])
        if isinstance(classification, list):
            if 'Showstopper_Confirmed' in classification or 'Preventing Maturity Grade ConDrive' in classification:
                scores['classification'] = 30
            elif 'Showstopper_Candidate' in classification:
                scores['classification'] = 20
            elif 'Obstructing Maturity Grade ConDrive' in classification or 'Homologation L-labelled' in classification:
                scores['classification'] = 10
        
        # ECU Transfer分数 - 使用实际流转路径次数
        ecu_path = row.get('ecu_pingpong_display', '')
        if ecu_path and ecu_path != 'No change':
            # 从显示字符串中提取次数（格式："次数, 路径"）
            if ',' in ecu_path:
                try:
                    ecu_transfer = int(ecu_path.split(',')[0].strip())
                except:
                    ecu_transfer = ecu_path.count(' -> ')
            else:
                ecu_transfer = ecu_path.count(' -> ')
            
            if ecu_transfer >= 5: scores['ecu_transfer'] = 30
            elif ecu_transfer >= 3: scores['ecu_transfer'] = 24
            elif ecu_transfer >= 1: scores['ecu_transfer'] = 20
        
        # Domain Transfer分数 - 使用实际流转路径次数
        domain_path = row.get('domain_pingpong_display', '')
        if domain_path and domain_path != 'No change':
            # 从显示字符串中提取次数（格式："次数, 路径"）
            if ',' in domain_path:
                try:
                    domain_transfer = int(domain_path.split(',')[0].strip())
                except:
                    domain_transfer = domain_path.count(' -> ')
            else:
                domain_transfer = domain_path.count(' -> ')
            
            if domain_transfer >= 5: scores['domain_transfer'] = 20
            elif domain_transfer >= 3: scores['domain_transfer'] = 14
            elif domain_transfer >= 1: scores['domain_transfer'] = 10
        
        # Parent Complexity分数
        if row.get('parent_child', '') == 'Parent':
            child_count = row.get('子票数量', 0)
            if pd.notna(child_count):
                if child_count >= 5: scores['parent_complexity'] = 30
                elif child_count >= 3: scores['parent_complexity'] = 20
                elif child_count >= 1: scores['parent_complexity'] = 10
        
        # Child Complexity分数
        elif row.get('parent_child', '') == 'Child':
            master_child_count = row.get('子票数量', 0)
            if pd.notna(master_child_count):
                if master_child_count >= 5: scores['child_complexity'] = 30
                elif master_child_count >= 3: scores['child_complexity'] = 20
                elif master_child_count >= 1: scores['child_complexity'] = 10
        
        # Processing Cycle分数
        processing_days = row.get('processing_cycle_days', 0)
        if pd.notna(processing_days):
            if processing_days >= 30: scores['processing_cycle'] = 20
            elif processing_days >= 15: scores['processing_cycle'] = 14
            elif processing_days >= 7: scores['processing_cycle'] = 6
        
        # Shift PU分数
        shift_pu = row.get('Shift_PU', '')
        if shift_pu and str(shift_pu).strip():
            scores['shift_pu'] = 10
        
        return scores
    
    if 'topissue_recommend_reason' not in filtered_data.columns:
        table_data['topissue_recommend_reason'] = 'No recommendation available'
    else:
        table_data['topissue_recommend_reason'] = filtered_data.apply(lambda row: format_topissue_recommendation(row['topissue_recommend_reason'], row), axis=1)
    
    # 添加数值型的Risk Score字段用于正确排序
    def extract_numeric_score(display_score):
        """从topissue_display中提取数值分数"""
        if pd.isna(display_score) or display_score == '' or display_score == '0':
            return 0
        # 移除星号和其他非数字字符，只保留数字
        import re
        numbers = re.findall(r'\d+', str(display_score))
        return int(numbers[0]) if numbers else 0
    
    
    table_data['topissue_score_numeric'] = table_data['topissue_display'].apply(extract_numeric_score)
    
    # 先按Risk Score数值降序排序
    table_data = table_data.sort_values('topissue_score_numeric', ascending=False)
    
    # 移除原始的classification列，只保留需要显示的列，并添加处理周期列
    final_columns = ['id', 'name', 'ecu', 'creation_time', 'matrix_display', 'classification_display', 'ecu_pingpong_display', 'domain_pingpong_display', 'parent_child_display', 'child_count_display', 'parent_child_count_display', 'parent_ticket_info', 'processing_cycle_days', 'pu', 'Shift_PU', 'topissue_display', 'topissue_recommend_reason', 'aida_english', 'status_phase', 'master_status', 'tester', 'severity_group', 'is_topissue']
    table_data_final = table_data[final_columns]
    
    return modal_style, table_data_final.to_dict('records'), info_text

# Excel表格回调
@app.callback(
    [Output('excel-defect-table', 'data'),
     Output('excel-defect-table', 'tooltip_data')],
    [Input('year-dropdown', 'value'),
     Input('project-dropdown', 'value'),
     Input('date-range-picker-main', 'start_date'),
     Input('date-range-picker-main', 'end_date'),
     Input('aida-dropdown', 'value'),
     Input('status-dropdown', 'value'),
     Input('pu-dropdown', 'value'),
     Input('tester-dropdown-main', 'value'),
     Input('fv-dropdown', 'value'),
     Input('ecu-dropdown', 'value'),
     Input('lead-model-dropdown', 'value'),
     Input('fvp-dropdown', 'value'),
     Input('severe-matrix-dropdown', 'value'),
     Input('severe-classification-dropdown', 'value'),
     Input('market-dropdown', 'value')],
    prevent_initial_call=False
)
def update_excel_defect_table(years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, severe_matrices, severe_classifications, markets):
    try:
        # 检查数据是否有效
        if df is None or df.empty:
            return [], []
        
        filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
        
        # 如果筛选后没有数据，返回空列表
        if filtered_data.empty:
            return [], []

        if 'topissue_risk_score' in filtered_data.columns:
            filtered_data = filtered_data.copy()
            filtered_data['topissue_risk_score'] = filtered_data['topissue_risk_score'].fillna(0)
            filtered_data = filtered_data.sort_values('topissue_risk_score', ascending=False)
        elif 'topissue_display' in filtered_data.columns:
            def extract_numeric_score(score_str):
                if pd.isna(score_str) or score_str == '':
                    return 0
                try:
                    import re
                    numbers = re.findall(r'\d+(?:\.\d+)?', str(score_str))
                    return float(numbers[0]) if numbers else 0
                except Exception:
                    return 0
            filtered_data = filtered_data.copy()
            filtered_data['topissue_score_numeric'] = filtered_data['topissue_display'].apply(extract_numeric_score)
            filtered_data = filtered_data.sort_values('topissue_score_numeric', ascending=False)

        max_rows = 500
        if len(filtered_data) > max_rows:
            filtered_data = filtered_data.head(max_rows).copy()
        
        # 动态计算严重性分组，基于用户选择的matrix和classification
        if severe_matrices is None:
            severe_matrices = []
        if severe_classifications is None:
            severe_classifications = []
        
        # 重新计算严重性分组
        filtered_data = filtered_data.copy()
        
        def is_severe_defect(row):
            # 检查Matrix是否为严重
            matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
            
            # 检查Classification是否为严重
            classification_severe = False
            if isinstance(row['classification'], list):
                classification_severe = any(cls in severe_classifications for cls in row['classification'])
            
            # 只要满足任一条件就是严重问题
            return matrix_severe or classification_severe
        
        filtered_data['severity_group'] = filtered_data.apply(
            lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues",
            axis=1
        )
        
        # 处理数据以便显示 - 使用与modal相同的逻辑
        table_data = filtered_data.copy()
        
        # 创建链接格式的ID
        table_data['id'] = table_data['id'].apply(make_ticket_link)
        
        # 创建matrix_display列
        table_data['matrix_display'] = table_data['matrix'].apply(lambda x: 
            str(x).replace('Matrix-', '').replace('matrix-', '').replace('MATRIX-', '').upper() if x else '')
        
        # 创建classification_display列
        table_data['classification_display'] = table_data['classification'].apply(lambda x: 
            ', '.join(x) if isinstance(x, list) else str(x) if x is not None else '未分类')
        
        # 处理ECU变更次数 - 改为显示流转路径
        def get_ecu_flow_path(row):
            defect_id = str(row.get('id', ''))
            return _cached_ecu_transition_path(defect_id) if defect_id else "No change"
        table_data['ecu_pingpong_display'] = filtered_data.apply(get_ecu_flow_path, axis=1)
        
        # 处理Domain变更次数 - 改为显示流转路径
        def get_solution_cluster_flow_path(row):
            defect_id = str(row.get('id', ''))
            return _cached_domain_transition_path(defect_id) if defect_id else "No change"
        table_data['domain_pingpong_display'] = filtered_data.apply(get_solution_cluster_flow_path, axis=1)
        
        # 处理Parent/Child字段 - 基于parent_child字段
        if 'parent_child' in filtered_data.columns:
            pc = filtered_data['parent_child'].fillna('').astype(str)
            table_data['parent_child_display'] = np.where(pc.str.lower().isin(['unknown', 'nan']) | (pc.str.strip() == ''), '', pc)
        else:
            table_data['parent_child_display'] = ''
        
        # 处理Child Count字段 - 当ticket是子票时，显示它所链接的主票包含多少个子票
        if 'child_count_of_master' in filtered_data.columns and 'parent_child' in filtered_data.columns:
            pc2 = filtered_data['parent_child'].fillna('').astype(str)
            cnt = pd.to_numeric(filtered_data['child_count_of_master'], errors='coerce').fillna(0).astype(int)
            table_data['child_count_display'] = np.where(pc2.isin(['Child', 'Child (candidate)']), cnt, 0)
        else:
            table_data['child_count_display'] = 0
        table_data['child_count_display'] = table_data['child_count_display'].replace(0, '')
        
        # 处理Parent Child Count字段 - 当ticket是父票时，显示它自己作为主票链接了多少个子票
        def count_linked_defects_for_parent(relation_str):
            """计算relation_to_udf中的缺陷数量 - 用于父票"""
            if not relation_str or pd.isna(relation_str):
                return 0
            try:
                ids = str(relation_str).split(',')
                return len([id.strip() for id in ids if id.strip()])
            except:
                return 0
        
        if 'parent_child' in filtered_data.columns:
            pc3 = filtered_data['parent_child'].fillna('').astype(str)
            if 'child_count' in filtered_data.columns:
                p_cnt = pd.to_numeric(filtered_data['child_count'], errors='coerce').fillna(0).astype(int)
                table_data['parent_child_count_display'] = np.where(pc3.eq('Parent'), p_cnt, 0)
            else:
                table_data['parent_child_count_display'] = filtered_data.apply(
                    lambda row: count_linked_defects_for_parent(row.get('relation_to_udf', '')) if row.get('parent_child') == 'Parent' else 0,
                    axis=1
                ).astype(int)
        else:
            table_data['parent_child_count_display'] = 0
        table_data['parent_child_count_display'] = table_data['parent_child_count_display'].replace(0, '')
        
        # 新增：处理父票信息展示 - 当票据是子票时，显示其父票的详细信息
        _ensure_master_lookups()
        master_lookup = _MASTER_LOOKUP or {}
        master_status_lookup = _MASTER_STATUS_LOOKUP or {}

        def get_parent_ticket_info(row):
            """获取父票信息"""
            if row.get('parent_child') not in ['Child', 'Child (candidate)']:
                return ""
            
            master_id = row.get('master_id')
            if not master_id or pd.isna(master_id):
                return ""
            master_id_str = str(master_id)
            parent_row = master_lookup.get(master_id_str)
            if parent_row:
                parent_info_str = f"ID: {parent_row.get('id', 'N/A')}"
                nm = parent_row.get('name')
                if nm:
                    parent_info_str += f" | Name: {str(nm)[:50]}..."
                ec = parent_row.get('ecu')
                if ec:
                    parent_info_str += f" | Project: {ec}"
                st = parent_row.get('status_phase') or parent_row.get('phase.name')
                if st:
                    parent_info_str += f" | Status: {st}"
                mx = parent_row.get('matrix_display')
                if mx:
                    parent_info_str += f" | Matrix: {mx}"
                return parent_info_str
            
            # 如果在master_df中找不到，尝试在当前数据中查找
            parent_in_current = filtered_data[filtered_data['id'] == str(master_id)]
            if not parent_in_current.empty:
                parent_row = parent_in_current.iloc[0]
                parent_info_str = f"ID: {parent_row.get('id', 'N/A')}"
                if parent_row.get('name'):
                    parent_info_str += f" | Name: {parent_row.get('name', 'N/A')[:50]}..."
                if parent_row.get('ecu'):
                    parent_info_str += f" | Project: {parent_row.get('ecu', 'N/A')}"
                if parent_row.get('status_phase'):
                    parent_info_str += f" | Status: {parent_row.get('status_phase', 'N/A')}"
                return parent_info_str
            
            return f"Parent Ticket ID: {master_id} (Details not found)"
        
        # 添加父票信息列
        table_data['parent_ticket_info'] = filtered_data.apply(get_parent_ticket_info, axis=1)
        
        # 新增：获取主票状态的专用函数
        def get_master_status(row):
            """获取主票状态"""
            if row.get('parent_child') not in ['Child', 'Child (candidate)']:
                return ""
            
            master_id = row.get('master_id')
            if not master_id or pd.isna(master_id):
                return ""
            master_id_str = str(master_id)
            st = master_status_lookup.get(master_id_str)
            if st:
                return st
            
            # 如果在master_df中找不到，尝试在当前数据中查找
            parent_in_current = filtered_data[filtered_data['id'] == str(master_id)]
            if not parent_in_current.empty:
                parent_row = parent_in_current.iloc[0]
                return parent_row.get('status_phase', '')
            
            return ""
        
        # 添加主票状态列
        table_data['master_status'] = filtered_data.apply(get_master_status, axis=1)
        
        # 添加处理周期（天数）列
        def calculate_processing_cycle_display(row):
            """为表格显示计算处理周期"""
            return calculate_processing_cycle_days(
                row.get('id'),
                row.get('status_phase'),
                row.get('creation_time')
            )
        
        table_data['processing_cycle_days'] = filtered_data.apply(calculate_processing_cycle_display, axis=1)
        
        # 添加pu和Shift_PU列
        # 如果原数据中有pu列，则直接使用
        if 'pu' in filtered_data.columns:
            table_data['pu'] = filtered_data['pu']
        else:
            table_data['pu'] = '未知'
        
        # 添加Shift_PU列，直接使用数据处理器添加的Shift_PU列
        if 'Shift_PU' in filtered_data.columns:
            table_data['Shift_PU'] = filtered_data['Shift_PU'].fillna('').astype(str)
        else:
            table_data['Shift_PU'] = ''
        
        # 定义基础分数计算函数（Excel表格专用）
        def calculate_basic_scores_excel(row):
            """计算单个票据的基础各维度分数（不包括非线性调整）"""
            scores = {
                'matrix': 0, 'classification': 0, 'ecu_transfer': 0, 'domain_transfer': 0,
                'parent_complexity': 0, 'child_complexity': 0, 'processing_cycle': 0, 'shift_pu': 0
            }
            
            # Matrix分数
            matrix = row.get('matrix', '')
            if isinstance(matrix, str) and matrix:
                matrix_scores = {
                    'matrix-1a': 30, 'matrix-1b': 28, 'matrix-1c': 26, 'matrix-1d': 24, 'matrix-1e': 22,
                    'matrix-2a': 20, 'matrix-2b': 18, 'matrix-3a': 16, 'matrix-2d': 14, 'matrix-2e': 12,
                    'matrix-3b': 10, 'matrix-3c': 8, 'matrix-3d': 6, 'matrix-4a': 4,
                    'matrix-3e': 2, 'matrix-4b': 2, 'matrix-4c': 2, 'matrix-4d': 2, 'matrix-4e': 2
                }
                scores['matrix'] = matrix_scores.get(matrix.lower(), 0)
            
            # Classification分数
            classification = row.get('classification', [])
            if isinstance(classification, list):
                if 'Showstopper_Confirmed' in classification or 'Preventing Maturity Grade ConDrive' in classification:
                    scores['classification'] = 30
                elif 'Showstopper_Candidate' in classification:
                    scores['classification'] = 20
                elif 'Obstructing Maturity Grade ConDrive' in classification or 'Homologation L-labelled' in classification:
                    scores['classification'] = 10
            
            # ECU Transfer分数 - 使用实际流转路径次数
            ecu_path = row.get('ecu_pingpong_display', '')
            if ecu_path and ecu_path != 'No change':
                # 从显示字符串中提取次数（格式："次数, 路径"）
                if ',' in ecu_path:
                    try:
                        ecu_transfer = int(ecu_path.split(',')[0].strip())
                    except:
                        ecu_transfer = ecu_path.count(' -> ')
                else:
                    ecu_transfer = ecu_path.count(' -> ')
                
                if ecu_transfer >= 5: scores['ecu_transfer'] = 30
                elif ecu_transfer >= 3: scores['ecu_transfer'] = 24
                elif ecu_transfer >= 1: scores['ecu_transfer'] = 20
            
            # Domain Transfer分数 - 使用实际流转路径次数
            domain_path = row.get('domain_pingpong_display', '')
            if domain_path and domain_path != 'No change':
                # 从显示字符串中提取次数（格式："次数, 路径"）
                if ',' in domain_path:
                    try:
                        domain_transfer = int(domain_path.split(',')[0].strip())
                    except:
                        domain_transfer = domain_path.count(' -> ')
                else:
                    domain_transfer = domain_path.count(' -> ')
                
                if domain_transfer >= 5: scores['domain_transfer'] = 20
                elif domain_transfer >= 3: scores['domain_transfer'] = 14
                elif domain_transfer >= 1: scores['domain_transfer'] = 10
            
            # Parent Complexity分数
            if row.get('parent_child', '') == 'Parent':
                child_count = row.get('子票数量', 0)
                if pd.notna(child_count):
                    if child_count >= 5: scores['parent_complexity'] = 30
                    elif child_count >= 3: scores['parent_complexity'] = 20
                    elif child_count >= 1: scores['parent_complexity'] = 10
            
            # Child Complexity分数
            elif row.get('parent_child', '') == 'Child':
                master_child_count = row.get('子票数量', 0)
                if pd.notna(master_child_count):
                    if master_child_count >= 5: scores['child_complexity'] = 30
                    elif master_child_count >= 3: scores['child_complexity'] = 20
                    elif master_child_count >= 1: scores['child_complexity'] = 10
            
            # Processing Cycle分数
            processing_days = row.get('processing_cycle_days', 0)
            if pd.notna(processing_days):
                if processing_days >= 30: scores['processing_cycle'] = 20
                elif processing_days >= 15: scores['processing_cycle'] = 14
                elif processing_days >= 7: scores['processing_cycle'] = 6
            
            # Shift PU分数
            shift_pu = row.get('Shift_PU', '')
            if shift_pu and str(shift_pu).strip():
                scores['shift_pu'] = 10
            
            return scores
        
        # 检查并添加topissue_recommend_reason字段 - 格式化为5行显示
        def format_topissue_recommendation_excel(reason_str, row):
            """格式化TopIssue推荐理由为5行清晰显示，包含实际分数计算"""
            if pd.isna(reason_str) or not reason_str or reason_str.strip() == '':
                return 'No recommendation available'
            
            # 如果已经是格式化的字符串，直接返回
            if '1. Severity:' in str(reason_str):
                return str(reason_str)
            
            # 尝试解析原始的推荐理由并格式化
            try:
                reason_text = str(reason_str).strip()
                if reason_text == 'No recommendation available':
                    return reason_text
                
                # 初始化4个因素的默认值
                severity_info = "Not detected"
                high_runner_info = "Not detected"
                complexity_info = "Not detected"
                processing_efficiency_info = "Not detected"
                
                # 按行分割原始推荐理由
                lines = reason_text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('SEVERITY:'):
                        severity_info = line.replace('SEVERITY:', '').strip()
                    elif line.startswith('COMPLEXITY:'):
                        high_runner_info = line.replace('COMPLEXITY:', '').strip()
                    elif line.startswith('HIGH RUNNER:'):
                        complexity_info = line.replace('HIGH RUNNER:', '').strip()
                    elif line.startswith('LONG RUNNER:'):
                        processing_efficiency_info = line.replace('LONG RUNNER:', '').strip()
                
                # 重新生成COMPLEXITY信息，使用当前行的最新格式化数据（Excel版本）
                updated_complexity_items = []
                
                # 使用最新的ECU转移次数信息（只显示次数，不显示路径）
                ecu_path = row.get('ecu_pingpong_display', '')
                if ecu_path and str(ecu_path) != 'No change' and str(ecu_path).strip():
                    if ',' in str(ecu_path):
                        ecu_count = str(ecu_path).split(',')[0].strip()
                        updated_complexity_items.append(f"ECU {ecu_count}次转移")
                
                # 使用最新的Domain转移次数信息（只显示次数，不显示路径）  
                domain_path = row.get('domain_pingpong_display', '')
                if domain_path and str(domain_path) != 'No change' and str(domain_path).strip():
                    if ',' in str(domain_path):
                        domain_count = str(domain_path).split(',')[0].strip()
                        updated_complexity_items.append(f"Domain {domain_count}次转移")
                
                # 如果有更新的COMPLEXITY信息，使用它
                if updated_complexity_items:
                    complexity_info = '; '.join(updated_complexity_items)
                elif complexity_info == "Not detected":
                    # 如果没有检测到，保持原有逻辑
                    pass
                
                # 获取实际的Risk Score和分数分解
                actual_risk_score = row.get('topissue_risk_score', 0)
                if pd.isna(actual_risk_score):
                    actual_risk_score = 0
                
                # 计算基础维度分数（用于显示分解）
                basic_scores = calculate_basic_scores_excel(row)
                basic_total = sum([basic_scores[key] for key in basic_scores])
                nonlinear_adjustment = max(0, actual_risk_score - basic_total)
                
                # 构建分数分解显示
                score_breakdown = f"Matrix {basic_scores['matrix']}pts + Classification {basic_scores['classification']}pts + ECU Transfer {basic_scores['ecu_transfer']}pts + Domain Transfer {basic_scores['domain_transfer']}pts + Parent Complexity {basic_scores['parent_complexity']}pts + Child Complexity {basic_scores['child_complexity']}pts + Processing Cycle {basic_scores['processing_cycle']}pts + Shift PU {basic_scores['shift_pu']}pts"
                
                if nonlinear_adjustment > 0:
                    score_breakdown += f" + Adjustments {nonlinear_adjustment:.0f}pts"
                
                score_breakdown += f" = Total {actual_risk_score}pts"
                
                # 创建格式化的5行推荐理由
                formatted_reason = f"1. Severity: {severity_info}\n"
                formatted_reason += f"2. High Runner: {high_runner_info}\n"
                formatted_reason += f"3. Complexity: {complexity_info}\n"
                formatted_reason += f"4. Processing Efficiency: {processing_efficiency_info}\n"
                formatted_reason += f"5. Risk Score Calculation: {score_breakdown}"
                
                return formatted_reason
            except:
                return 'No recommendation available'
        
        # 处理TopIssue推荐理由字段
        if 'topissue_recommend_reason' not in filtered_data.columns:
            print("Warning: topissue_recommend_reason column not found, checking for alternative fields")
            # 如果没有topissue_recommend_reason字段，尝试使用其他可能的字段名
            if 'recommend_reason' in filtered_data.columns:
                filtered_data['topissue_recommend_reason'] = filtered_data['recommend_reason']
            else:
                filtered_data['topissue_recommend_reason'] = 'No recommendation available'
        
        # 检查数据情况
        non_null_count = filtered_data['topissue_recommend_reason'].notna().sum()
        
        # 应用格式化函数 - 使用table_data确保有最新的ecu_pingpong_display和domain_pingpong_display字段
        table_data['topissue_recommend_reason'] = table_data.apply(lambda row: format_topissue_recommendation_excel(row.get('topissue_recommend_reason', ''), row), axis=1)
        
        # 创建topissue_display列
        def format_topissue_display(row):
            # 检查是否已经有topissue_display列，如果有就直接使用
            if 'topissue_display' in row and row['topissue_display']:
                if 'is_topissue' in row and row['is_topissue'] == 1:
                    return f"★ {row['topissue_display']}"
                else:
                    return str(row['topissue_display'])
            # 如果没有topissue_display，则使用topissue_risk_score
            elif 'topissue_risk_score' in row:
                if 'is_topissue' in row and row['is_topissue'] == 1:
                    return f"★ {row['topissue_risk_score']:.1f}"
                else:
                    return f"{row['topissue_risk_score']:.1f}"
            else:
                return "0.0"
        
        table_data['topissue_display'] = table_data.apply(format_topissue_display, axis=1)
        
        # 按照 topissue_risk_score 降序排列
        if 'topissue_risk_score' in table_data.columns:
            table_data = table_data.sort_values('topissue_risk_score', ascending=False)
        elif 'topissue_display' in table_data.columns:
            # 如果没有topissue_risk_score，则提取topissue_display中的数值进行排序
            def extract_numeric_score(score_str):
                if pd.isna(score_str) or score_str == '':
                    return 0
                # 移除星号和其他非数字字符，只保留数字和小数点
                import re
                numeric_str = re.sub(r'[^\d.]', '', str(score_str))
                try:
                    return float(numeric_str) if numeric_str else 0
                except ValueError:
                    return 0
            
            table_data['topissue_score_numeric'] = table_data['topissue_display'].apply(extract_numeric_score)
            table_data = table_data.sort_values('topissue_score_numeric', ascending=False)
        
        # 确保所有需要的列都存在
        required_columns = ['id', 'name', 'ecu', 'creation_time', 'matrix_display', 'classification_display', 
                          'ecu_pingpong_display', 'domain_pingpong_display', 'parent_child_display', 
                          'child_count_display', 'parent_child_count_display', 'parent_ticket_info', 
                          'processing_cycle_days', 'pu', 'Shift_PU', 'topissue_display', 
                          'topissue_recommend_reason', 'aida_english', 'status_phase', 'master_status', 'tester']
        
        # 检查缺失的列并填充默认值
        for col in required_columns:
            if col not in table_data.columns:
                table_data[col] = ''
        
        # 移除原始的classification列，只保留需要显示的列
        table_data_final = table_data[required_columns]
        
        # 填充任何NaN值
        table_data_final = table_data_final.fillna('')
        
        # 生成工具提示数据
        tooltip_data = []
        for index, row in table_data_final.iterrows():
            tooltip_row = {}
            # 为重要的长文本列添加工具提示
            tooltip_row['name'] = {'value': str(row['name']), 'type': 'text'}
            tooltip_row['classification_display'] = {'value': str(row['classification_display']), 'type': 'text'}
            tooltip_row['ecu_pingpong_display'] = {'value': str(row['ecu_pingpong_display']), 'type': 'text'}
            tooltip_row['domain_pingpong_display'] = {'value': str(row['domain_pingpong_display']), 'type': 'text'}
            tooltip_row['parent_ticket_info'] = {'value': str(row['parent_ticket_info']), 'type': 'text'}
            tooltip_row['topissue_recommend_reason'] = {'value': str(row['topissue_recommend_reason']), 'type': 'text'}
            tooltip_data.append(tooltip_row)
        
        return table_data_final.to_dict('records'), tooltip_data
    
    except Exception as e:
        print(f"Excel表格更新错误: {str(e)}")
        return [], []


# KPI卡片回调
@app.callback(
    Output('testing-kpi-cards', 'children'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value'),
     Input('team-market-dropdown', 'value')]
)
def update_testing_kpi_cards(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, severe_matrices, severe_classifications, markets):
    try:
        # 检查数据是否有效
        if df is None or df.empty:
            return html.Div("数据加载中...", style={'textAlign': 'center', 'padding': '20px'})
        
        # 如果statuses为None，使用默认的状态筛选值
        if statuses is None:
            statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
        
        # 使用通用筛选函数
        filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets)

        from analysis_utils import compute_defect_explore_kpis

        kpis = compute_defect_explore_kpis(filtered_data, start_date=start_date, end_date=end_date)
        total_defects = kpis["total_defects"]
        total_testers = kpis["total_testers"]
        severe_rate = kpis["severe_rate"]
        daily_avg = kpis["daily_avg"]
        top_tester = kpis["top_tester"]
    except Exception as e:
        print(f"testing-kpi-cards 回调错误: {e}")
        return html.Div(f"数据处理错误: {str(e)}", style={'textAlign': 'center', 'padding': '20px', 'color': 'red'})
    
    # 创建KPI卡片
    cards = html.Div([
        html.Div([
            html.H4(f"{total_defects}", style={'margin': '0', 'color': '#2c3e50'}),
            html.P("总缺陷数", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'borderRadius': '8px', 'width': '18%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{total_testers}", style={'margin': '0', 'color': '#27ae60'}),
            html.P("活跃测试人员", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#d5f4e6', 'borderRadius': '8px', 'width': '18%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{severe_rate:.1f}%", style={'margin': '0', 'color': '#e74c3c'}),
            html.P("严重缺陷率", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fadbd8', 'borderRadius': '8px', 'width': '18%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{daily_avg:.1f}", style={'margin': '0', 'color': '#3498db'}),
            html.P("日均发现缺陷", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#d6eaf8', 'borderRadius': '8px', 'width': '18%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{top_tester}", style={'margin': '0', 'color': '#9b59b6', 'fontSize': '13px',
                            'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                            'border': '1px solid #f3f4f6',
                            'color': '#374151'}),
            html.P("最活跃测试员", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#ebdef0', 'borderRadius': '8px', 'width': '18%', 'display': 'inline-block', 'margin': '1%'})
    ])
    
    return cards

# 测试人员效率图表回调
@app.callback(
    Output('tester-efficiency-chart', 'figure'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-market-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value')]
)
def update_tester_efficiency_chart(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets)  # markets=None as Market column is not available
    
    # 按测试人员和严重性分组
    tester_stats = filtered_data.groupby(['tester', 'severity_group']).size().reset_index(name='缺陷数量')
    
    # 取前15个最活跃的测试人员
    top_testers = filtered_data['tester'].value_counts().head(15).index
    tester_stats = tester_stats[tester_stats['tester'].isin(top_testers)]
    
    # 创建堆叠条形图
    fig = px.bar(
        tester_stats,
        x='tester',
        y='缺陷数量',
        color='severity_group',
        barmode='stack',
        color_discrete_map=SEVERITY_COLORS,
        title="测试人员缺陷发现效率（前15名）"
    )
    
    fig = apply_chart_style(
        fig,
        title="测试人员缺陷发现效率（前15名）",
        x_title="测试人员",
        y_title="缺陷数量"
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 缺陷发现趋势图表回调
@app.callback(
    Output('defect-discovery-trend-chart', 'figure'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-market-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value')]
)
def update_defect_discovery_trend_chart(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets)
    
    # 按日期分组
    filtered_data['date'] = pd.to_datetime(filtered_data['creation_time']).dt.date
    trend_data = filtered_data.groupby(['date', 'severity_group']).size().reset_index(name='缺陷数量')
    
    # 创建折线图
    fig = px.line(
        trend_data,
        x='date',
        y='缺陷数量',
        color='severity_group',
        markers=True,
        color_discrete_map=SEVERITY_COLORS,
        title="缺陷发现趋势"
    )
    
    fig = apply_chart_style(
        fig,
        title="缺陷发现趋势",
        x_title="日期",
        y_title="缺陷数量"
    )
    
    return fig

# 测试人员严重缺陷发现分布回调
@app.callback(
    Output('tester-severity-chart', 'figure'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-market-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value')]
)
def update_tester_severity_chart(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets)
    
    # 计算每个测试人员的严重缺陷比例
    tester_stats = filtered_data.groupby('tester').agg({
        'severity_group': lambda x: (x == 'Critical Issues').sum() / len(x) * 100
    }).reset_index()
    tester_stats.columns = ['tester', 'severe_rate']
    
    # 同时计算总缺陷数用于气泡大小
    total_counts = filtered_data['tester'].value_counts().reset_index()
    total_counts.columns = ['tester', 'total_defects']
    
    # 合并数据
    bubble_data = pd.merge(tester_stats, total_counts, on='tester')
    
    # 取前20个最活跃的测试人员
    top_testers = total_counts.head(20)['tester'].tolist()
    bubble_data = bubble_data[bubble_data['tester'].isin(top_testers)]
    
    # 创建气泡图
    fig = px.scatter(
        bubble_data,
        x='tester',
        y='severe_rate',
        size='total_defects',
        color='severe_rate',
        color_continuous_scale='Reds',
        title="测试人员严重缺陷发现率",
        hover_data=['total_defects']
    )
    
    fig = apply_chart_style(
        fig,
        title="测试人员严重缺陷发现率",
        x_title="测试人员",
        y_title="严重缺陷率 (%)"
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 缺陷状态分布回调
@app.callback(
    Output('defect-status-distribution-chart', 'figure'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-market-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value')]
)
def update_defect_status_distribution_chart(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, None)  # markets=None as Market column is not available
    
    # 按状态分组
    status_counts = filtered_data['status_phase'].value_counts().reset_index()
    status_counts.columns = ['status_phase', 'count']
    
    # 创建饼图
    fig = px.pie(
        status_counts,
        values='count',
        names='status_phase',
        title="缺陷状态分布"
    )
    
    fig = apply_chart_style(
        fig,
        title="缺陷状态分布"
    )
    
    return fig

# AIDA领域覆盖回调
@app.callback(
    Output('aida-coverage-chart', 'figure'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-market-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value')]
)
def update_aida_coverage_chart(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, None)  # markets=None as Market column is not available
    
    # 按AIDA和严重性分组
    aida_data = filtered_data.groupby(['aida_english', 'severity_group']).size().reset_index(name='缺陷数量')
    
    # 创建堆叠条形图
    fig = px.bar(
        aida_data,
        x='aida_english',
        y='缺陷数量',
        color='severity_group',
        barmode='stack',
        color_discrete_map=SEVERITY_COLORS,
        title="AIDA领域测试覆盖"
    )
    
    fig = apply_chart_style(
        fig,
        title="AIDA领域测试覆盖",
        x_title="AIDA领域",
        y_title="缺陷数量"
    )
    
    return fig


# 项目缺陷贡献回调
@app.callback(
    Output('project-contribution-chart', 'figure'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-market-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value')]
)
def update_project_contribution_chart(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, markets, severe_matrices, severe_classifications):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, None)  # markets=None as Market column is not available
    
    # 按项目分组，取前10个
    project_counts = filtered_data['ecu'].value_counts().head(10).reset_index()
    project_counts.columns = ['ecu', 'count']
    
    # 创建水平条形图
    fig = px.bar(
        project_counts,
        y='ecu',
        x='count',
        orientation='h',
        color='count',
        color_continuous_scale='Blues',
        title="项目缺陷发现贡献（前10）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目缺陷发现贡献（前10）",
        x_title="缺陷数量",
        y_title="项目"
    )
    
    return fig

# 测试人员统计表格回调
@app.callback(
    Output('tester-stats-table', 'data'),
    [Input('team-year-dropdown', 'value'),
     Input('team-project-dropdown', 'value'),
     Input('team-date-range-picker-main', 'start_date'),
     Input('team-date-range-picker-main', 'end_date'),
     Input('team-aida-dropdown', 'value'),
     Input('team-status-dropdown', 'value'),
     Input('team-pu-dropdown', 'value'),
     Input('team-tester-dropdown-main', 'value'),
     Input('team-fv-dropdown', 'value'),
     Input('team-ecu-dropdown', 'value'),
     Input('team-lead-model-dropdown', 'value'),
     Input('team-fvp-dropdown', 'value'),
     Input('team-severe-matrix-dropdown', 'value'),
     Input('team-severe-classification-dropdown', 'value'),
     Input('team-market-dropdown', 'value')]
)
def update_tester_stats_table(years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, severe_matrices, severe_classifications, markets):
    # 如果statuses为None，使用默认的状态筛选值
    if statuses is None:
        statuses = ['01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification']
    
    # 使用通用筛选函数
    filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, selected_testers, fvs, ecus, lead_models, fvps, None)
    
    # 计算日期差
    if start_date and end_date:
        date_diff = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    else:
        date_diff = 1
    
    # 计算每个测试人员的统计信息
    stats_list = []
    for tester in filtered_data['tester'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique():
        if pd.isna(tester) or tester == '':
            continue
            
        tester_data = filtered_data[filtered_data['tester'] == tester]
        
        total_defects = len(tester_data)
        severe_defects = len(tester_data[tester_data['severity_group'] == 'Critical Issues'])
        severe_rate = (severe_defects / total_defects * 100) if total_defects > 0 else 0
        daily_avg = total_defects / date_diff if date_diff > 0 else 0
        
        # 主要AIDA领域
        main_aida = tester_data['aida_english'].value_counts().index[0] if not tester_data.empty else "无"
        
        # 主要项目
        main_project = tester_data['ecu'].value_counts().index[0] if not tester_data.empty else "无"
        
        stats_list.append({
            'tester': tester,
            'total_defects': total_defects,
            'severe_defects': severe_defects,
            'severe_rate': round(severe_rate, 1),
            'daily_avg': round(daily_avg, 2),
            'main_aida': main_aida,
            'main_project': main_project
        })
    
    # 按总缺陷数排序
    stats_list.sort(key=lambda x: x['total_defects'], reverse=True)
    
    return stats_list

# 测试效率与质量 - KPI指标卡回调
def filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus=None, markets=None):
    filtered_data = filter_dataframe(
        df=df,
        years=selected_years or [],
        projects=selected_projects or [],
        start_date=start_date,
        end_date=end_date,
        aidas=selected_aidas or [],
        statuses=selected_statuses or [],
        pus=selected_pus or [],
        testers=[],
        fvs=[],
        ecus=[],
        lead_models=[],
        fvps=[],
        markets=markets or []
    ).copy()
    for col in ['project', 'top_aida', 'pu', 'status_phase', 'phase', 'blocking_reason', 'blocking_reason_udf']:
        if col in filtered_data.columns:
            filtered_data[col] = filtered_data[col].apply(extract_filter_value)
    return filtered_data


@app.callback(
    Output('efficiency-kpi-cards', 'children'),
    [Input('efficiency-year-dropdown', 'value'),
     Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value'),
     Input('efficiency-pu-dropdown', 'value'),
     Input('efficiency-market-dropdown', 'value')]
)
def update_efficiency_kpi_cards(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets):
    try:
        # 检查数据是否有效
        if df is None or df.empty:
            return html.Div("数据加载中...", style={'textAlign': 'center', 'padding': '20px'})
        
        filtered_data = filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets)
        
        if start_date and end_date:
            date_diff = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
        else:
            date_diff = 1
            
    except Exception as e:
        print(f"efficiency-kpi-cards 回调错误: {e}")
        return html.Div(f"数据处理错误: {str(e)}", style={'textAlign': 'center', 'padding': '20px', 'color': 'red'})
    
    # 计算KPI指标
    total_defects = len(filtered_data)
    severe_defects = len(filtered_data[filtered_data['severity_group'] == 'Critical Issues'])
    severe_rate = (severe_defects / total_defects * 100) if total_defects > 0 else 0
    daily_avg = total_defects / date_diff if date_diff > 0 else 0
    
    # 测试覆盖的AIDA领域数
    aida_coverage = len(filtered_data['aida_english'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
    total_aidas = len(df['aida_english'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
    coverage_rate = (aida_coverage / total_aidas * 100) if total_aidas > 0 else 0
    
    # 缺陷密度（每个项目平均缺陷数）
    project_count = len(filtered_data['ecu'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()) if len(filtered_data) > 0 else 1
    defect_density = total_defects / project_count
    
    # 平均解决时间（简化计算）
    avg_resolution_time = 5.2  # 示例值
    
    cards = html.Div([
        html.Div([
            html.H4(f"{total_defects:,}", style={'margin': '0', 'color': '#2c3e50', 'fontSize': '28px'}),
            html.P("总缺陷数", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
        ], style={'textAlign': 'center', 'backgroundColor': '#ecf0f1', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4(f"{severe_rate:.1f}%", style={'margin': '0', 'color': '#e74c3c', 'fontSize': '28px'}),
            html.P("严重缺陷率", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
        ], style={'textAlign': 'center', 'backgroundColor': '#fadbd8', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4(f"{daily_avg:.1f}", style={'margin': '0', 'color': '#3498db', 'fontSize': '28px'}),
            html.P("日均发现缺陷", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
        ], style={'textAlign': 'center', 'backgroundColor': '#d6eaf8', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4(f"{coverage_rate:.1f}%", style={'margin': '0', 'color': '#27ae60', 'fontSize': '28px'}),
            html.P("AIDA覆盖率", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
        ], style={'textAlign': 'center', 'backgroundColor': '#d5f4e6', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4(f"{defect_density:.1f}", style={'margin': '0', 'color': '#f39c12', 'fontSize': '28px'}),
            html.P("缺陷密度", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
        ], style={'textAlign': 'center', 'backgroundColor': '#fdeaa7', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        
        html.Div([
            html.H4(f"{avg_resolution_time:.1f}天", style={'margin': '0', 'color': '#9b59b6', 'fontSize': '28px'}),
            html.P("平均解决时间", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
        ], style={'textAlign': 'center', 'backgroundColor': '#e8daef', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
    ], style={'display': 'flex', 'flexWrap': 'wrap', 'justifyContent': 'space-around'})
    
    return cards



# 缺陷矩阵分布图表回调
@app.callback(
    Output('defect-matrix-chart', 'figure'),
    [Input('efficiency-year-dropdown', 'value'),
     Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value'),
     Input('efficiency-pu-dropdown', 'value'),
     Input('efficiency-market-dropdown', 'value')]
)
def update_defect_matrix_chart(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets):
    filtered_data = filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets)
    
    # 构建过滤描述
    filter_desc = []
    if selected_projects:
        filter_desc.append(f"项目: {', '.join(selected_projects)}")
    if selected_aidas:
        filter_desc.append(f"AIDA: {', '.join(selected_aidas)}")
    if selected_statuses:
        filter_desc.append(f"状态: {', '.join(selected_statuses)}")
    if selected_pus:
        filter_desc.append(f"PU: {', '.join(selected_pus)}")
    if markets:
        filter_desc.append(f"市场: {', '.join(markets)}")
    if start_date and end_date:
        filter_desc.append(f"时间: {start_date} 到 {end_date}")
    
    filter_description = " | ".join(filter_desc) if filter_desc else None
    
    # 使用defect_matrix.py中的函数创建矩阵图
    return create_matrix_figure_flipped(filtered_data, filtered_by=filter_description)

# Inflow/Outflow趋势图表回调
@app.callback(
    Output('inflow-outflow-chart', 'figure'),
    [Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date')]
)
def update_inflow_outflow_chart(start_date, end_date):
    try:
        # 计算周数范围（基于选择的日期范围）
        if start_date and end_date:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            weeks_range = max(4, int((end_dt - start_dt).days / 7))
        else:
            weeks_range = 52  # 默认52周
        
        # 获取inflow/outflow数据
        trends_df = calculate_inflow_outflow_trends(date_range_weeks=weeks_range)
        
        if trends_df.empty:
            # 如果没有数据，创建空图表
            fig = go.Figure()
            fig.add_annotation(
                text="暂无Inflow/Outflow数据",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            fig.update_layout(
                title="Ticket收敛趋势 (Inflow/Outflow)",
                height=550,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            return fig
        
        # 确保数据按时间顺序排序
        def parse_week_key(week_key):
            """将周期键转换为可排序的元组 (year, week)"""
            try:
                year, week = week_key.split('-W')
                return (int(year), int(week))
            except:
                return (0, 0)
        
        # 按时间顺序重新排序数据
        trends_df = trends_df.sort_values('week', key=lambda x: x.map(parse_week_key))
        trends_df = trends_df.reset_index(drop=True)
        years_present = trends_df['week'].astype(str).str.extract(r'(\d{4})-W')[0].dropna().unique().tolist()
        show_year = len(years_present) > 1
        def format_week_label(week_str):
            text = str(week_str)
            if '-W' in text:
                year, week_num = text.split('-W')
                return f"{year}-CW{week_num}" if show_year else f"CW{week_num}"
            return text
        week_labels = [format_week_label(week) for week in trends_df['week']]
        
        # 创建线图
        fig = go.Figure()

        # 禁用连接空值
        fig.update_traces(connectgaps=False)
        
        # 添加Inflow线
        fig.add_trace(go.Scatter(
            x=week_labels,
            y=trends_df['inflow'],
            mode='lines+markers',
            name='Inflow (00→01)',
            line=dict(color='#2E86AB', width=3),
            marker=dict(size=6),
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Week: %{x}<br>' +
                         'Count: %{y}<extra></extra>'
        ))
        
        # 添加Outflow线
        fig.add_trace(go.Scatter(
            x=week_labels,
            y=trends_df['outflow'],
            mode='lines+markers',
            name='Outflow (→06/09)',
            line=dict(color='#A23B72', width=3),
            marker=dict(size=6),
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Week: %{x}<br>' +
                         'Count: %{y}<extra></extra>'
        ))
        
        # 添加净收敛线 (inflow - outflow)
        net_convergence = (trends_df['inflow'] - trends_df['outflow']).cumsum()
        fig.add_trace(go.Scatter(
            x=week_labels,
            y=net_convergence,
            mode='lines',
            name='Net Accumulation',
            line=dict(color='#F18F01', width=2, dash='dot'),
            hovertemplate='<b>%{fullData.name}</b><br>' +
                         'Week: %{x}<br>' +
                         'Net: %{y}<extra></extra>'
        ))
        
        # 添加零线
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # 更新布局
        fig.update_layout(
            title="",
            xaxis_title="周",
            yaxis_title="Ticket数量",
            height=550,
            plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='x unified'
        )
        
        # 旋转x轴标签以避免重叠
        fig.update_xaxes(tickangle=45)
        
        return fig
        
    except Exception as e:
        print(f"更新Inflow/Outflow图表时出错: {e}")
        # 返回错误图表
        fig = go.Figure()
        fig.add_annotation(
            text=f"加载数据时出错: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font=dict(size=16, color="red")
        )
        fig.update_layout(
            title="Ticket收敛趋势 (Inflow/Outflow)",
            height=550,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        return fig

# 缺陷密度分析图表回调
@app.callback(
    Output('defect-density-chart', 'figure'),
    [Input('efficiency-year-dropdown', 'value'),
     Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value'),
     Input('efficiency-pu-dropdown', 'value'),
     Input('efficiency-market-dropdown', 'value')]
)
def update_defect_density_chart(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets):
    filtered_data = filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets)
    
    # 计算各项目的缺陷密度
    project_density = filtered_data.groupby(['ecu', 'severity_group']).size().reset_index(name='count')
    
    # 取前15个项目
    top_projects = project_density.groupby('ecu')['count'].sum().nlargest(15).index
    project_density = project_density[project_density['ecu'].isin(top_projects)]
    
    # 创建气泡图
    fig = px.scatter(
        project_density,
        x='ecu',
        y='count',
        size='count',
        color='severity_group',
        color_discrete_map=SEVERITY_COLORS,
        title="项目缺陷密度分析（前15个项目）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目缺陷密度分析（前15个项目）",
        x_title="项目",
        y_title="缺陷数量"
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig



# 测试执行状态分布图表回调
@app.callback(
    Output('test-execution-status-chart', 'figure'),
    [Input('efficiency-year-dropdown', 'value'),
     Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value'),
     Input('efficiency-pu-dropdown', 'value'),
     Input('efficiency-market-dropdown', 'value')]
)
def update_test_execution_status_chart(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets):
    try:
        # 使用缺陷数据 (df) 分析CWA票
        if df is None or df.empty:
            # 创建空图表
            fig = go.Figure()
            fig.add_annotation(
                text="缺陷数据未加载",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16, color="gray")
            )
            fig.update_layout(
                title="CWA票据分析",
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=False, showticklabels=False),
                plot_bgcolor='white'
            )
            return fig
        
        # CWA 图固定分析 phase 09，避免被状态下拉先过滤掉导致空结果
        filtered_data = filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, [], selected_pus, markets)
        
        # 筛选phase为'09-Concluded without action'的票
        if 'phase' in filtered_data.columns:
            # 处理phase字段，如果是dict则提取name字段
            filtered_data['phase_extracted'] = filtered_data['phase'].apply(
                lambda x: x.get('name', '') if isinstance(x, dict) and 'name' in x else str(x) if x else ''
            )
            filtered_data = filtered_data[filtered_data['phase_extracted'].str.startswith('09-', na=False)]
        else:
            # 如果没有phase列，尝试使用status_phase
            if 'status_phase' in filtered_data.columns:
                # 处理status_phase字段，如果是dict则提取name字段
                filtered_data['status_phase_extracted'] = filtered_data['status_phase'].apply(
                    lambda x: x.get('name', '') if isinstance(x, dict) and 'name' in x else str(x) if x else ''
                )
                filtered_data = filtered_data[filtered_data['status_phase_extracted'].str.startswith('09-', na=False)]
            else:
                # 创建空图表
                fig = go.Figure()
                fig.add_annotation(
                    text="未找到phase字段",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5, xanchor='center', yanchor='middle',
                    showarrow=False, font=dict(size=16, color="gray")
                )
                fig.update_layout(
                    title="CWA票据分析",
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(showgrid=False, showticklabels=False),
                    plot_bgcolor='white'
                )
                return fig
        
        # 检查是否有数据；若当前年份筛选无结果，回退尝试全部年份
        cwa_fallback_note = ""
        if filtered_data.empty and selected_years:
            fallback_data = filter_efficiency_data([], start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets)
            if 'phase' in fallback_data.columns:
                fallback_data['phase_extracted'] = fallback_data['phase'].apply(
                    lambda x: x.get('name', '') if isinstance(x, dict) and 'name' in x else str(x) if x else ''
                )
                fallback_data = fallback_data[fallback_data['phase_extracted'].str.startswith('09-', na=False)]
            elif 'status_phase' in fallback_data.columns:
                fallback_data['status_phase_extracted'] = fallback_data['status_phase'].apply(
                    lambda x: x.get('name', '') if isinstance(x, dict) and 'name' in x else str(x) if x else ''
                )
                fallback_data = fallback_data[fallback_data['status_phase_extracted'].str.startswith('09-', na=False)]

            if not fallback_data.empty:
                filtered_data = fallback_data
                cwa_fallback_note = "（当前年份无数据，已回退展示全部年份）"

        if filtered_data.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="没有符合条件的CWA票据",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16, color="gray")
            )
            fig.update_layout(
                title="CWA票据分析",
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=False, showticklabels=False),
                plot_bgcolor='white'
            )
            return fig
        
        # 处理blocking_reason和ticket_quality字段
        blocking_reason_col = None
        ticket_quality_col = None
        
        # 查找blocking_reason字段
        if 'blocking_reason' in filtered_data.columns:
            blocking_reason_col = 'blocking_reason'
        elif 'blocking_reason_udf' in filtered_data.columns:
            # 如果是原始字段，需要提取name
            filtered_data['blocking_reason_extracted'] = filtered_data['blocking_reason_udf'].apply(
                lambda x: x.get('name', '') if isinstance(x, dict) and 'name' in x else str(x) if x else '未知原因'
            )
            blocking_reason_col = 'blocking_reason_extracted'
        if blocking_reason_col and blocking_reason_col in filtered_data.columns:
            filtered_data[blocking_reason_col] = filtered_data[blocking_reason_col].apply(extract_filter_value).replace('', '未知原因')
        
        # 查找ticket_quality字段
        if 'ticket_quality' in filtered_data.columns:
            # ticket_quality是列表，需要处理 - 按前缀分类，每个票据的多个标签都统计到各自分类中
            def extract_quality_categories(quality_list):
                if not isinstance(quality_list, list) or not quality_list:
                    return ['未分类']
                
                # 提取所有状态编号（前两位数字）
                codes = set()
                for item in quality_list:
                    if isinstance(item, str) and len(item) >= 2:
                        # 提取前两位数字作为状态编号
                        code = item[:2]
                        if code.isdigit():
                            codes.add(code)
                
                if codes:
                    # 按数字排序并添加描述
                    sorted_codes = sorted(codes)
                    descriptions = []
                    for code in sorted_codes:
                        if code == '01':
                            descriptions.append('01-well created defect')
                        elif code == '02':
                            descriptions.append('02-not ok error description')
                        elif code == '03':
                            descriptions.append('03-not ok preconditions')
                        elif code == '04':
                            descriptions.append('04-not ok platform config')
                        elif code == '05':
                            descriptions.append('05-not ok preanalysis')
                        elif code == '06':
                            descriptions.append('06-not ok traces')
                        elif code == '07':
                            descriptions.append('07-specific traces not available')
                        elif code == '08':
                            descriptions.append('08-invalid sw version')
                        elif code == '09':
                            descriptions.append('09-wrong interpretation of testcase')
                        else:
                            descriptions.append(f'{code}-其他')
                    return descriptions
                else:
                    return ['未分类']
            
            # 展开数据：每个票据的每个质量分类都创建一行
            expanded_rows = []
            for idx, row in filtered_data.iterrows():
                quality_categories = extract_quality_categories(row['ticket_quality'])
                for category in quality_categories:
                    new_row = row.copy()
                    new_row['ticket_quality_str'] = category
                    expanded_rows.append(new_row)
            
            # 重新创建DataFrame
            if expanded_rows:
                filtered_data = pd.DataFrame(expanded_rows)
            else:
                filtered_data['ticket_quality_str'] = '未分类'
            
            ticket_quality_col = 'ticket_quality_str'
        elif 'tqr_udf' in filtered_data.columns:
            # 如果是原始字段，需要提取
            def extract_quality_categories_from_udf(tqr_data):
                if not isinstance(tqr_data, dict) or 'data' not in tqr_data:
                    return ['未分类']
                
                data_list = tqr_data.get('data', [])
                if not isinstance(data_list, list) or not data_list:
                    return ['未分类']
                
                # 提取所有状态编号（前两位数字）
                codes = set()
                for item in data_list:
                    if isinstance(item, dict) and 'name' in item:
                        name = item.get('name', '')
                        if isinstance(name, str) and len(name) >= 2:
                            code = name[:2]
                            if code.isdigit():
                                codes.add(code)
                
                if codes:
                    # 按数字排序并添加描述
                    sorted_codes = sorted(codes)
                    descriptions = []
                    for code in sorted_codes:
                        if code == '01':
                            descriptions.append('01-well created defect')
                        elif code == '02':
                            descriptions.append('02-not ok error description')
                        elif code == '03':
                            descriptions.append('03-not ok preconditions')
                        elif code == '04':
                            descriptions.append('04-not ok platform config')
                        elif code == '05':
                            descriptions.append('05-not ok preanalysis')
                        elif code == '06':
                            descriptions.append('06-not ok traces')
                        elif code == '07':
                            descriptions.append('07-specific traces not available')
                        elif code == '08':
                            descriptions.append('08-invalid sw version')
                        elif code == '09':
                            descriptions.append('09-wrong interpretation of testcase')
                        else:
                            descriptions.append(f'{code}-其他')
                    return descriptions
                else:
                    return ['未分类']
            
            # 展开数据：每个票据的每个质量分类都创建一行
            expanded_rows = []
            for idx, row in filtered_data.iterrows():
                quality_categories = extract_quality_categories_from_udf(row['tqr_udf'])
                for category in quality_categories:
                    new_row = row.copy()
                    new_row['ticket_quality_extracted'] = category
                    expanded_rows.append(new_row)
            
            # 重新创建DataFrame
            if expanded_rows:
                filtered_data = pd.DataFrame(expanded_rows)
            else:
                filtered_data['ticket_quality_extracted'] = '未分类'
            
            ticket_quality_col = 'ticket_quality_extracted'
        
        # 如果找不到必要字段，显示错误
        if not blocking_reason_col:
            fig = go.Figure()
            fig.add_annotation(
                text="未找到blocking_reason字段",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16, color="red")
            )
            fig.update_layout(
                title="CWA票据分析",
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=False, showticklabels=False),
                plot_bgcolor='white'
            )
            return fig
        
        # 如果没有ticket_quality，使用默认值
        if not ticket_quality_col:
            filtered_data['ticket_quality_default'] = '未分类'
            ticket_quality_col = 'ticket_quality_default'
        
        # 统计数据：按blocking_reason和ticket_quality分组
        grouped_data = filtered_data.groupby([blocking_reason_col, ticket_quality_col]).size().reset_index(name='count')
        
        # 创建堆叠柱状图
        fig = px.bar(
            grouped_data,
            x=blocking_reason_col,
            y='count',
            color=ticket_quality_col,
            title=f"CWA票据分析 - 按阻塞原因和票据质量分布{cwa_fallback_note}",
            labels={
                blocking_reason_col: '阻塞原因',
                'count': '票据数量',
                ticket_quality_col: '票据质量'
            },
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        # 应用样式
        fig = apply_chart_style(
            fig,
            title="CWA票据分析 - 按阻塞原因和票据质量分布",
            x_title="阻塞原因",
            y_title="票据数量"
        )
        
        # 调整x轴标签角度以便阅读
        fig.update_layout(
            xaxis_tickangle=-45,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02
            )
        )
        
        return fig
            
    except Exception as e:
        # 创建错误图表
        fig = go.Figure()
        fig.add_annotation(
            text=f"图表生成错误: {str(e)}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font=dict(size=16, color="red")
        )
        fig.update_layout(
            title="CWA票据分析",
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False),
            plot_bgcolor='white'
        )
        return fig

# 测试周期效率图表回调
@app.callback(
    Output('test-cycle-efficiency-chart', 'figure'),
    [Input('efficiency-year-dropdown', 'value'),
     Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value'),
     Input('efficiency-pu-dropdown', 'value'),
     Input('efficiency-market-dropdown', 'value')]
)
def update_test_cycle_efficiency_chart(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets):
    filtered_data = filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets)
    cycle_efficiency = filtered_data.groupby(['test_week', 'severity_group']).size().reset_index(name='count')
    week_order = sort_weeks_with_year(cycle_efficiency['test_week'].tolist())
    
    fig = px.bar(
        cycle_efficiency,
        x='test_week',
        y='count',
        color='severity_group',
        color_discrete_map=SEVERITY_COLORS,
        category_orders={'test_week': week_order},
        title="测试周期效率分析"
    )
    
    fig = apply_chart_style(
        fig,
        title="测试周期效率分析",
        x_title="测试周",
        y_title="缺陷数量"
    )
    
    return fig

# 高复杂度缺陷AIDA词云回调
@app.callback(
    Output('defect-aida-wordcloud', 'figure'),
    [Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value')]
)
def update_defect_aida_wordcloud(start_date, end_date, selected_projects, selected_aidas, selected_statuses):
    try:
        # 使用缺陷数据 (df)
        if 'df' not in globals() or df.empty:
            return generate_wordcloud_figure(pd.Series([]), "DDF热词AIDA词云 (缺陷数据未加载)", width=1200, height=600)
        
        filtered_data = df.copy()
        
        # 应用筛选器
        if start_date and end_date:
            filtered_data = filtered_data[
                (pd.to_datetime(filtered_data['creation_time']).dt.date >= pd.to_datetime(start_date).date()) &
                (pd.to_datetime(filtered_data['creation_time']).dt.date <= pd.to_datetime(end_date).date())
            ]
        
        if selected_projects:
            filtered_data = filtered_data[filtered_data['project'].isin(selected_projects)]
        
        if selected_aidas and 'aida_english' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['aida_english'].isin(selected_aidas)]
        elif selected_aidas and 'top_aida' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['top_aida'].isin(selected_aidas)]
        
        if selected_statuses:
            filtered_data = filtered_data[filtered_data['status_phase'].isin(selected_statuses)]
        
        # 使用完整的DDF数据，不再只筛选高复杂度缺陷
        ddf_data = filtered_data
        
        # 使用top_aida或aida_english列生成词云
        if 'top_aida' in ddf_data.columns:
            return generate_wordcloud_figure(ddf_data['top_aida'], "DDF热词AIDA词云", width=1200, height=600)
        elif 'aida_english' in ddf_data.columns:
            return generate_wordcloud_figure(ddf_data['aida_english'], "DDF热词AIDA词云", width=1200, height=600)
        else:
            return generate_wordcloud_figure(pd.Series([]), "DDF热词AIDA词云 (缺少AIDA列)", width=1200, height=600)
            
    except Exception as e:
        return generate_wordcloud_figure(pd.Series([]), f"DDF热词AIDA词云 (错误: {str(e)})", width=1200, height=600)

# 缺陷状态转换效率图表回调
@app.callback(
    Output('status-transition-efficiency-chart', 'figure'),
    [Input('efficiency-year-dropdown', 'value'),
     Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value'),
     Input('efficiency-pu-dropdown', 'value'),
     Input('efficiency-market-dropdown', 'value')]
)
def update_status_transition_efficiency_chart(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets):
    filtered_data = filter_efficiency_data(selected_years, start_date, end_date, selected_projects, selected_aidas, selected_statuses, selected_pus, markets)
    status_counts = filtered_data.groupby(['status_phase', 'severity_group']).size().reset_index(name='count')
    
    # 创建堆叠条形图
    fig = px.bar(
        status_counts,
        x='status_phase',
        y='count',
        color='severity_group',
        color_discrete_map=SEVERITY_COLORS,
        title="缺陷状态转换效率"
    )
    
    fig = apply_chart_style(
        fig,
        title="缺陷状态转换效率",
        x_title="AIDA领域",
        y_title="缺陷数量"
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# AIDA领域生产力图表回调
@app.callback(
    Output('aida-productivity-chart', 'figure'),
    [Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value')]
)
def update_aida_productivity_chart(start_date, end_date, selected_projects, selected_aidas, selected_statuses):
    # 筛选数据
    filtered_data = df.copy()
    
    if start_date and end_date:
        filtered_data = filtered_data[
            (pd.to_datetime(filtered_data['creation_time']).dt.date >= pd.to_datetime(start_date).date()) &
            (pd.to_datetime(filtered_data['creation_time']).dt.date <= pd.to_datetime(end_date).date())
        ]
        date_diff = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    else:
        date_diff = 1
    
    if selected_projects:
        filtered_data = filtered_data[filtered_data['project'].isin(selected_projects)]
    
    if selected_aidas:
        filtered_data = filtered_data[filtered_data['aida_english'].isin(selected_aidas)]
    
    if selected_statuses:
        filtered_data = filtered_data[filtered_data['status_phase'].isin(selected_statuses)]
    
    # 计算各AIDA领域的生产力（缺陷数/天）
    aida_counts = filtered_data.groupby('aida_english').size().reset_index(name='total_count')
    aida_counts['daily_productivity'] = aida_counts['total_count'] / date_diff
    
    # 按生产力排序，取前10
    aida_counts = aida_counts.nlargest(10, 'daily_productivity')
    
    # 创建条形图
    fig = px.bar(
        aida_counts,
        x='aida_english',
        y='daily_productivity',
        color='daily_productivity',
        color_continuous_scale='Blues',
        title="AIDA领域生产力（前10）"
    )
    
    fig = apply_chart_style(
        fig,
        title="AIDA领域生产力（前10）",
        x_title="AIDA领域",
        y_title="日均缺陷数"
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 质量评估表格回调
@app.callback(
    Output('quality-assessment-table', 'data'),
    [Input('efficiency-date-range-picker-main', 'start_date'),
     Input('efficiency-date-range-picker-main', 'end_date'),
     Input('efficiency-project-dropdown', 'value'),
     Input('efficiency-aida-dropdown', 'value'),
     Input('efficiency-status-dropdown', 'value')]
)
def update_quality_assessment_table(start_date, end_date, selected_projects, selected_aidas, selected_statuses):
    # 筛选数据
    filtered_data = df.copy()
    
    if start_date and end_date:
        filtered_data = filtered_data[
            (pd.to_datetime(filtered_data['creation_time']).dt.date >= pd.to_datetime(start_date).date()) &
            (pd.to_datetime(filtered_data['creation_time']).dt.date <= pd.to_datetime(end_date).date())
        ]
        date_diff = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
    else:
        date_diff = 1
    
    if selected_projects:
        filtered_data = filtered_data[filtered_data['project'].isin(selected_projects)]
    
    if selected_aidas:
        filtered_data = filtered_data[filtered_data['aida_english'].isin(selected_aidas)]
    
    if selected_statuses:
        filtered_data = filtered_data[filtered_data['status_phase'].isin(selected_statuses)]
    
    # 计算每个项目的质量指标
    quality_stats = []
    for project in filtered_data['project'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique():
        if pd.isna(project) or project == '':
            continue
            
        project_data = filtered_data[filtered_data['project'] == project]
        
        total_defects = len(project_data)
        severe_defects = len(project_data[project_data['severity_group'] == 'Critical Issues'])
        
        # 计算缺陷密度（简化为总缺陷数）
        defect_density = total_defects
        
        # 平均发现时间（简化计算）
        avg_discovery_time = np.random.uniform(3, 10)  # 示例值
        
        # AIDA覆盖率
        project_aidas = len(project_data['aida_english'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
        total_aidas = len(df['aida_english'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
        aida_coverage = (project_aidas / total_aidas * 100) if total_aidas > 0 else 0
        
        # 质量得分（基于多个指标的综合评分）
        severity_score = max(0, 100 - (severe_defects / total_defects * 100)) if total_defects > 0 else 100
        density_score = max(0, 100 - (defect_density / 10))  # 假设10个缺陷为满分扣除点
        coverage_score = aida_coverage
        quality_score = (severity_score + density_score + coverage_score) / 3
        
        quality_stats.append({
            'project': project,
            'total_defects': total_defects,
            'severe_defects': severe_defects,
            'defect_density': round(defect_density, 2),
            'avg_discovery_time': round(avg_discovery_time, 1),
            'aida_coverage': round(aida_coverage, 1),
            'quality_score': round(quality_score, 1)
        })
    
    # 按质量得分排序
    quality_stats.sort(key=lambda x: x['quality_score'], reverse=True)
    
    return quality_stats

# 主题切换回调
@app.callback(
    [Output('main-container', 'style'),
     Output('global-theme-switcher', 'labelStyle'),
     Output('main-title', 'style')],
    [Input('global-theme-switcher', 'value')],
    prevent_initial_call=False
)
def update_theme(selected_theme):
    try:
        current_main_style = MAIN_CONTAINER_STYLE 
        current_label_color = TEXT_COLOR 
        current_title_style = {'textAlign': 'center', 'color': TEXT_COLOR}

        if selected_theme == 'light':
            current_main_style = LIGHT_MAIN_CONTAINER_STYLE
            current_label_color = LIGHT_TEXT_COLOR
            current_title_style = {'textAlign': 'center', 'color': LIGHT_TEXT_COLOR}
            theme_manager.set_theme('light')
        elif selected_theme == 'dark':
            theme_manager.set_theme('dark')
        else: 
            theme_manager.set_theme('dark')

        label_style = {
            'display': 'inline-block', 
            'marginRight': '15px', 
            'color': current_label_color,
                            'cursor': 'pointer'
                        }
        
        return current_main_style, label_style, current_title_style
    except Exception as e:
        # 如果出现错误，返回默认值
        print(f"主题更新错误: {e}")
        return MAIN_CONTAINER_STYLE, {'display': 'inline-block', 'marginRight': '15px', 'color': TEXT_COLOR}, {'textAlign': 'center', 'color': TEXT_COLOR}

# AI聊天模态框控制回调函数
@app.callback(
    Output('ai-chat-modal', 'style'),
    [Input('ai-chat-toggle-btn', 'n_clicks'),
     Input('ai-chat-modal-close', 'n_clicks'),
     Input('ai-chat-modal-overlay', 'n_clicks')],
    [State('ai-chat-modal', 'style')],
    prevent_initial_call=True
)
def toggle_ai_chat_modal(toggle_clicks, close_clicks, overlay_clicks, current_style):
    """控制AI聊天模态框的显示和隐藏"""
    from dash import callback_context, no_update
    from dash.exceptions import PreventUpdate
    
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 默认隐藏样式
    modal_close_style = {
        'display': 'none',
        'position': 'fixed',
        'zIndex': '2000',
        'left': '0',
        'top': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.6)',
        'justifyContent': 'center',
        'alignItems': 'center',
        'backdropFilter': 'blur(3px)'
    }
    
    # 只有在打开按钮被有效点击时才显示
    if trigger_id == 'ai-chat-toggle-btn' and toggle_clicks and toggle_clicks > 0:
        # 定义模态框显示样式
        modal_open_style = {
            'display': 'flex',
            'position': 'fixed',
            'zIndex': '2000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.6)',
            'justifyContent': 'center',
            'alignItems': 'center',
            'backdropFilter': 'blur(3px)'
        }
        # 如果当前是关闭状态，则打开
        if current_style and current_style.get('display') == 'none':
            return modal_open_style
        # 如果当前是打开状态，则关闭
        else:
            return modal_close_style
            
    # 如果是关闭按钮或遮罩层被点击，则关闭
    if trigger_id in ['ai-chat-modal-close', 'ai-chat-modal-overlay']:
        return modal_close_style
        
    # 其他情况不更新
    return no_update

# 全局搜索回调函数
@app.callback(
    [Output('defect-modal', 'style', allow_duplicate=True),
     Output('modal-defect-table', 'data', allow_duplicate=True),
     Output('modal-info', 'children', allow_duplicate=True),
     Output('search-results-info', 'children')],
    [Input('search-button', 'n_clicks'),
     Input('global-search-input', 'n_submit'),
     Input('close-modal-btn', 'n_clicks'),
     Input('defect-modal-overlay', 'n_clicks')],
    [State('global-search-input', 'value')],
    prevent_initial_call=True
)
def global_search(search_clicks, search_submit, close_clicks, overlay_clicks, search_value):
    """全局搜索功能"""
    from dash import callback_context
    
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    # 获取触发的输入
    triggered_input = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 如果点击了关闭按钮或遮罩层，隐藏Modal
    if triggered_input in ['close-modal-btn', 'defect-modal-overlay']:
        modal_style = {
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        return modal_style, [], "", ""
    
    # 检查是否有搜索值
    if not search_value or search_value.strip() == '':
        modal_style = {
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        return modal_style, [], "", ""
    
    search_term = search_value.strip().lower()
    
    search_mask = (
        df['id'].astype(str).str.lower().str.contains(search_term, na=False) |
        df['name'].astype(str).str.lower().str.contains(search_term, na=False)
    )
    if 'topissue_display' in df.columns:
        search_mask = search_mask | df['topissue_display'].astype(str).str.lower().str.contains(search_term, na=False)
    if 'topissue_recommend_reason' in df.columns:
        search_mask = search_mask | df['topissue_recommend_reason'].astype(str).str.lower().str.contains(search_term, na=False)
    if 'aida_english' in df.columns:
        search_mask = search_mask | df['aida_english'].astype(str).str.lower().str.contains(search_term, na=False)
    if 'ecu' in df.columns:
        search_mask = search_mask | df['ecu'].astype(str).str.lower().str.contains(search_term, na=False)
    search_results = df[search_mask].copy()
    
    if search_results.empty:
        modal_style = {
            'display': 'none',
            'position': 'fixed',
            'zIndex': '1000',
            'left': '0',
            'top': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.5)',
            'justifyContent': 'center',
            'alignItems': 'center'
        }
        return modal_style, [], "", f"未找到包含 '{search_value}' 的缺陷记录"
    
    # 显示Modal
    modal_style = {
        'display': 'flex',
        'position': 'fixed',
        'zIndex': '1000',
        'left': '0',
        'top': '0',
        'width': '100%',
        'height': '100%',
        'backgroundColor': 'rgba(0,0,0,0.5)',
        'justifyContent': 'center',
        'alignItems': 'center'
    }
    
    # 处理搜索结果数据，使用与modal回调相同的逻辑
    if 'topissue_risk_score' in search_results.columns:
        search_results = search_results.sort_values('topissue_risk_score', ascending=False)
    elif 'topissue_display' in search_results.columns:
        search_results = search_results.sort_values('topissue_display', ascending=False)
    elif 'matrix_order' in search_results.columns:
        search_results = search_results.sort_values('matrix_order')
    
    # 限制结果数量
    search_results = search_results.head(100)
    
    # 选择要显示的列
    table_data = search_results[['id', 'name', 'ecu', 'creation_time', 'matrix_display', 'topissue_display', 'aida_english', 'status_phase', 'tester', 'severity_group', 'is_topissue', 'classification']].copy()
    table_data['tester'] = table_data['tester'].apply(extract_filter_value).replace('', 'Unknown Tester')
    
    # 处理classification列表
    table_data['classification_display'] = table_data['classification'].apply(lambda x: ', '.join(x) if isinstance(x, list) else str(x) if x is not None else '未分类')
    
    # 将ID转换为超链接格式
    table_data['id'] = table_data['id'].apply(make_ticket_link)
    
    # 处理ECU变更次数 - 使用完整流转路径
    def get_ecu_flow_path_global(row):
        """获取ECU流转路径（global search版本）"""
        defect_id = str(row.get('id', ''))
        if defect_id:
            try:
                path = get_ecu_transition_path(defect_id)
                if path and path != "No change":
                    return path
                return "No change"
            except Exception as e:
                return "No change"
        return "No change"
    
    table_data['ecu_pingpong_display'] = search_results.apply(get_ecu_flow_path_global, axis=1)
    
    # 处理Solution Cluster乒乓值 - 使用完整流转路径
    def get_domain_flow_path_global(row):
        """获取Domain流转路径（global search版本）"""
        defect_id = str(row.get('id', ''))
        if defect_id:
            try:
                path = get_solution_cluster_transition_path(defect_id)
                if path and path != "No change":
                    return path
                return "No change"
            except Exception as e:
                return "No change"
        return "No change"
    
    table_data['domain_pingpong_display'] = search_results.apply(get_domain_flow_path_global, axis=1)
    
    # 处理Parent/Child字段
    if 'parent_child' in search_results.columns:
        table_data['parent_child_display'] = search_results['parent_child'].fillna('Unknown')
    else:
        if 'master_id' in search_results.columns:
            # 如果没有parent_child字段，设置为Unknown
            table_data['parent_child_display'] = 'Unknown'
    
    # 处理Child Count字段
    if 'child_count_of_master' in search_results.columns:
        table_data['child_count_display'] = search_results.apply(
            lambda row: row['child_count_of_master'] if row.get('parent_child') in ['Child', 'Child (candidate)'] else 0,
            axis=1
        ).fillna(0).astype(int)
    else:
        table_data['child_count_display'] = 0
    
    # 处理Parent Child Count字段 - 当ticket是父票时，显示它自己作为主票链接了多少个子票
    # 修复逻辑：对于父票，应该计算relation_to_udf中的缺陷数量，而不是依赖linked_defect_count字段
    def count_linked_defects_for_parent(relation_str):
        """计算relation_to_udf中的缺陷数量 - 用于父票"""
        if not relation_str or pd.isna(relation_str):
            return 0
        try:
            # relation_to_udf是逗号分隔的ID列表
            ids = str(relation_str).split(',')
            return len([id.strip() for id in ids if id.strip()])
        except:
            return 0
    
    # 对于父票，使用relation_to_udf计算子票数量；对于非父票，显示0
    table_data['parent_child_count_display'] = search_results.apply(
        lambda row: count_linked_defects_for_parent(row.get('relation_to_udf', '')) if row.get('parent_child') == 'Parent' else 0,
        axis=1
    ).astype(int)
    
    # 新增：处理父票信息展示 - 当票据是子票时，显示其父票的详细信息
    def get_parent_ticket_info(row):
        """获取父票信息"""
        if row.get('parent_child') not in ['Child', 'Child (candidate)']:
            return ""
        
        master_id = row.get('master_id')
        if not master_id or pd.isna(master_id):
            return ""
        
        # 首先从全局的master_df中查找父票信息
        global master_df
        if master_df is not None and not master_df.empty:
            # 确保ID类型匹配
            master_df_copy = master_df.copy()
            master_df_copy['id'] = master_df_copy['id'].astype(str)
            master_id_str = str(master_id)
            
            parent_info = master_df_copy[master_df_copy['id'] == master_id_str]
            if not parent_info.empty:
                parent_row = parent_info.iloc[0]
                # 构建父票信息字符串，包含ID、名称、项目、状态等关键信息
                parent_info_str = f"ID: {parent_row.get('id', 'N/A')}"
                if parent_row.get('name'):
                    parent_info_str += f" | Name: {parent_row.get('name', 'N/A')[:50]}..."  # 限制长度
                if parent_row.get('ecu'):
                    parent_info_str += f" | Project: {parent_row.get('ecu', 'N/A')}"
                if parent_row.get('status_phase'):
                    parent_info_str += f" | Status: {parent_row.get('status_phase', 'N/A')}"
                if parent_row.get('matrix_display'):
                    parent_info_str += f" | Matrix: {parent_row.get('matrix_display', 'N/A')}"
                return parent_info_str
        
        # 如果在master_df中找不到，尝试在当前数据中查找
        parent_in_current = search_results[search_results['id'] == str(master_id)]
        if not parent_in_current.empty:
            parent_row = parent_in_current.iloc[0]
            parent_info_str = f"ID: {parent_row.get('id', 'N/A')}"
            if parent_row.get('name'):
                parent_info_str += f" | Name: {parent_row.get('name', 'N/A')[:50]}..."
            if parent_row.get('ecu'):
                parent_info_str += f" | Project: {parent_row.get('ecu', 'N/A')}"
            if parent_row.get('status_phase'):
                parent_info_str += f" | Status: {parent_row.get('status_phase', 'N/A')}"
            return parent_info_str
        
        return f"Parent Ticket ID: {master_id} (Details not found)"
    
    # 添加父票信息列
    table_data['parent_ticket_info'] = search_results.apply(get_parent_ticket_info, axis=1)
    
    # 新增：获取主票状态的专用函数
    def get_master_status(row):
        """获取主票状态"""
        if row.get('parent_child') not in ['Child', 'Child (candidate)']:
            return ""
        
        master_id = row.get('master_id')
        if not master_id or pd.isna(master_id):
            return ""
        
        # 首先从全局的master_df中查找主票状态
        global master_df
        if master_df is not None and not master_df.empty:
            # 确保ID类型匹配
            master_df_copy = master_df.copy()
            master_df_copy['id'] = master_df_copy['id'].astype(str)
            master_id_str = str(master_id)
            
            parent_info = master_df_copy[master_df_copy['id'] == master_id_str]
            if not parent_info.empty:
                parent_row = parent_info.iloc[0]
                # 从phase.name字段获取状态
                phase_name = parent_row.get('phase.name', '')
                if phase_name:
                    return phase_name
                # 如果phase.name为空，尝试其他可能的字段
                return parent_row.get('status_phase', '')
        
        # 如果在master_df中找不到，尝试在当前数据中查找
        parent_in_current = search_results[search_results['id'] == str(master_id)]
        if not parent_in_current.empty:
            parent_row = parent_in_current.iloc[0]
            return parent_row.get('status_phase', '')
        
        return ""
    
    # 添加主票状态列
    table_data['master_status'] = search_results.apply(get_master_status, axis=1)
    
    # 添加处理周期（天数）列
    def calculate_processing_cycle_display(row):
        """为表格显示计算处理周期"""
        return calculate_processing_cycle_days(
            row.get('id'),
            row.get('status_phase'),
            row.get('creation_time')
        )
    
    table_data['processing_cycle_days'] = search_results.apply(calculate_processing_cycle_display, axis=1)
    
    # 添加pu和Shift_PU列
    # 如果原数据中有pu列，则直接使用
    if 'pu' in search_results.columns:
        table_data['pu'] = search_results['pu']
    else:
        table_data['pu'] = '未知'
    
    # 添加Shift_PU列，直接使用数据处理器添加的Shift_PU列
    if 'Shift_PU' in search_results.columns:
        table_data['Shift_PU'] = search_results['Shift_PU'].fillna('').astype(str)
    else:
        table_data['Shift_PU'] = ''
    
    # 检查并添加topissue_recommend_reason字段
    if 'topissue_recommend_reason' not in search_results.columns:
        table_data['topissue_recommend_reason'] = 'No recommendation available'
    else:
        table_data['topissue_recommend_reason'] = search_results['topissue_recommend_reason'].fillna('No recommendation available')
    
    # 添加数值型的Risk Score字段用于正确排序
    def extract_numeric_score(display_score):
        """从topissue_display中提取数值分数"""
        if pd.isna(display_score) or display_score == '' or display_score == '0':
            return 0
        # 移除星号和其他非数字字符，只保留数字
        import re
        numbers = re.findall(r'\d+', str(display_score))
        return int(numbers[0]) if numbers else 0
    
    table_data['topissue_score_numeric'] = table_data['topissue_display'].apply(extract_numeric_score)
    
    # 先按Risk Score数值降序排序
    table_data = table_data.sort_values('topissue_score_numeric', ascending=False)
    
    # 移除原始的classification列，只保留需要显示的列，并添加处理周期列
    final_columns = ['id', 'name', 'ecu', 'creation_time', 'matrix_display', 'classification_display', 'ecu_pingpong_display', 'domain_pingpong_display', 'parent_child_display', 'child_count_display', 'parent_child_count_display', 'parent_ticket_info', 'processing_cycle_days', 'pu', 'Shift_PU', 'topissue_display', 'topissue_recommend_reason', 'aida_english', 'status_phase', 'master_status', 'tester', 'severity_group', 'is_topissue']
    table_data_final = table_data[final_columns]
    
    # 信息文本
    info_text = f"搜索关键词: '{search_value}' | 找到 {len(search_results)} 条匹配记录"
    search_info = f"✓ 找到 {len(search_results)} 条匹配记录"
    
    return modal_style, table_data_final.to_dict('records'), info_text, search_info

# 项目KPI卡片回调
@app.callback(
    Output('project-kpi-cards', 'children'),
    [Input('current-nav-item', 'data')]  # 使用current-nav-item作为触发器，确保在切换到项目分析时更新
)
def update_project_kpi_cards(tab):
    try:
        if tab != 'tab-project-analysis':
            return []
        
        # 检查数据是否有效
        if df is None or df.empty:
            return [html.Div("数据加载中...", style={'textAlign': 'center', 'padding': '20px'})]
        
        # 计算整体项目KPI指标
        total_projects = df['ecu'].nunique()
        total_defects = len(df)
    except Exception as e:
        print(f"project-kpi-cards 回调错误: {e}")
        return [html.Div(f"数据处理错误: {str(e)}", style={'textAlign': 'center', 'padding': '20px', 'color': 'red'})]
    
    # 计算严重缺陷（需要先定义严重性分组）
    df_copy = df.copy()
    
    # 定义严重缺陷的判断逻辑
    def is_severe_defect(row):
        # 默认的严重Matrix定义
        severe_matrices = ['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E', 
                          'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-3A']
        # 默认的严重Classification定义
        severe_classifications = ['Showstopper_Candidate', 'Showstopper_Confirmed', 
                                'Preventing Maturity Grade ConDrive', 'Obstructing Maturity Grade ConDrive']
        
        # 检查Matrix是否为严重
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        
        # 检查Classification是否为严重
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        return matrix_severe or classification_severe
    
    df_copy['severity_group'] = df_copy.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    severe_defects = len(df_copy[df_copy['severity_group'] == 'Critical Issues'])
    severe_rate = (severe_defects / total_defects * 100) if total_defects > 0 else 0
    
    # 计算已解决缺陷
    resolved_statuses = ['06-Resolved', '07-Closed', '08-Verified']
    resolved_defects = len(df[df['status_phase'].isin(resolved_statuses)])
    resolution_rate = (resolved_defects / total_defects * 100) if total_defects > 0 else 0
    
    # 计算AIDA覆盖度
    total_aidas = df['aida_english'].nunique()
    
    # 计算平均每个项目的缺陷数
    avg_defects_per_project = total_defects / total_projects if total_projects > 0 else 0
    
    # 创建KPI卡片列表
    return [
        html.Div([
            html.H4(f"{total_projects}", style={'margin': '0', 'color': '#2c3e50'}),
            html.P("总项目数", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#ecf0f1', 'borderRadius': '8px', 'width': '15%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{total_defects}", style={'margin': '0', 'color': '#3498db'}),
            html.P("总缺陷数", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#d6eaf8', 'borderRadius': '8px', 'width': '15%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{severe_rate:.1f}%", style={'margin': '0', 'color': '#e74c3c'}),
            html.P("严重缺陷率", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fadbd8', 'borderRadius': '8px', 'width': '15%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{resolution_rate:.1f}%", style={'margin': '0', 'color': '#27ae60'}),
            html.P("缺陷解决率", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#d5f4e6', 'borderRadius': '8px', 'width': '15%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{total_aidas}", style={'margin': '0', 'color': '#9b59b6'}),
            html.P("AIDA领域数", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#ebdef0', 'borderRadius': '8px', 'width': '15%', 'display': 'inline-block', 'margin': '1%'}),
        
        html.Div([
            html.H4(f"{avg_defects_per_project:.1f}", style={'margin': '0', 'color': '#f39c12'}),
            html.P("平均项目缺陷数", style={'margin': '0', 'fontSize': '14px', 'color': '#7f8c8d'})
        ], style={'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#fdeaa7', 'borderRadius': '8px', 'width': '15%', 'display': 'inline-block', 'margin': '1%'})
    ]

# 项目缺陷总量对比图表
@app.callback(
    Output('project-defect-volume-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_defect_volume_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 计算每个项目的缺陷数量和严重性分组
    df_copy = df.copy()
    
    # 定义严重缺陷的判断逻辑
    def is_severe_defect(row):
        severe_matrices = ['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E', 
                          'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-3A']
        severe_classifications = ['Showstopper_Candidate', 'Showstopper_Confirmed', 
                                'Preventing Maturity Grade ConDrive', 'Obstructing Maturity Grade ConDrive']
        
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        return matrix_severe or classification_severe
    
    df_copy['severity_group'] = df_copy.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 按项目和严重性分组
    project_data = df_copy.groupby(['ecu', 'severity_group']).size().reset_index(name='缺陷数量')
    
    # 取前20个缺陷最多的项目
    top_projects = df_copy['ecu'].value_counts().head(20).index
    project_data = project_data[project_data['ecu'].isin(top_projects)]
    
    # 创建堆叠条形图
    fig = px.bar(
        project_data,
        x='ecu',
        y='缺陷数量',
        color='severity_group',
        barmode='stack',
        color_discrete_map=SEVERITY_COLORS,
        title="项目缺陷总量对比（前20名）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目缺陷总量对比（前20名）",
        x_title="项目",
        y_title="缺陷数量",
        height=450
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 项目严重缺陷率对比图表
@app.callback(
    Output('project-severity-rate-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_severity_rate_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 计算每个项目的严重缺陷率
    df_copy = df.copy()
    
    def is_severe_defect(row):
        severe_matrices = ['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E', 
                          'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-3A']
        severe_classifications = ['Showstopper_Candidate', 'Showstopper_Confirmed', 
                                'Preventing Maturity Grade ConDrive', 'Obstructing Maturity Grade ConDrive']
        
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        return matrix_severe or classification_severe
    
    df_copy['severity_group'] = df_copy.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 计算每个项目的严重缺陷率
    project_stats = df_copy.groupby('ecu').agg({
        'severity_group': lambda x: (x == 'Critical Issues').sum() / len(x) * 100
    }).reset_index()
    project_stats.columns = ['ecu', 'severe_rate']
    
    # 同时计算总缺陷数用于气泡大小
    total_counts = df_copy['ecu'].value_counts().reset_index()
    total_counts.columns = ['ecu', 'total_defects']
    
    # 合并数据
    bubble_data = pd.merge(project_stats, total_counts, on='ecu')
    
    # 取前20个最活跃的项目
    top_projects = total_counts.head(20)['ecu'].tolist()
    bubble_data = bubble_data[bubble_data['ecu'].isin(top_projects)]
    
    # 创建气泡图
    fig = px.scatter(
        bubble_data,
        x='ecu',
        y='severe_rate',
        size='total_defects',
        color='severe_rate',
        color_continuous_scale='Reds',
        title="项目严重缺陷率对比（前20名）",
        hover_data=['total_defects']
    )
    
    fig = apply_chart_style(
        fig,
        title="项目严重缺陷率对比（前20名）",
        x_title="项目",
        y_title="严重缺陷率 (%)",
        height=450
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 项目状态分布对比图表
@app.callback(
    Output('project-status-distribution-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_status_distribution_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 计算每个项目的状态分布
    df_copy = df.copy()
    
    # 定义严重缺陷的判断逻辑
    def is_severe_defect(row):
        severe_matrices = ['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E', 
                          'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-3A']
        severe_classifications = ['Showstopper_Candidate', 'Showstopper_Confirmed', 
                                'Preventing Maturity Grade ConDrive', 'Obstructing Maturity Grade ConDrive']
        
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        return matrix_severe or classification_severe
    
    df_copy['severity_group'] = df_copy.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 按项目和状态分组
    status_data = df_copy.groupby(['ecu', 'status_phase']).size().reset_index(name='缺陷数量')
    
    # 取前15个缺陷最多的项目
    top_projects = df_copy['ecu'].value_counts().head(15).index
    status_data = status_data[status_data['ecu'].isin(top_projects)]
    
    # 创建堆叠条形图
    fig = px.bar(
        status_data,
        x='ecu',
        y='缺陷数量',
        color='status_phase',
        barmode='stack',
        title="项目缺陷状态分布对比（前15名）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目缺陷状态分布对比（前15名）",
        x_title="项目",
        y_title="缺陷数量",
        height=450
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 项目AIDA覆盖度对比图表
@app.callback(
    Output('project-aida-coverage-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_aida_coverage_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 计算每个项目的AIDA覆盖度
    aida_coverage = df.groupby('ecu')['aida_english'].nunique().reset_index()
    aida_coverage.columns = ['ecu', 'aida_count']
    
    # 同时计算总缺陷数
    total_counts = df['ecu'].value_counts().reset_index()
    total_counts.columns = ['ecu', 'total_defects']
    
    # 合并数据
    coverage_data = pd.merge(aida_coverage, total_counts, on='ecu')
    
    # 取前20个最活跃的项目
    top_projects = total_counts.head(20)['ecu'].tolist()
    coverage_data = coverage_data[coverage_data['ecu'].isin(top_projects)]
    
    # 创建气泡图
    fig = px.scatter(
        coverage_data,
        x='ecu',
        y='aida_count',
        size='total_defects',
        color='aida_count',
        color_continuous_scale='Viridis',
        title="项目AIDA领域覆盖度对比（前20名）",
        hover_data=['total_defects']
    )
    
    fig = apply_chart_style(
        fig,
        title="项目AIDA领域覆盖度对比（前20名）",
        x_title="项目",
        y_title="AIDA领域数量",
        height=450
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 项目缺陷发现趋势对比图表
@app.callback(
    Output('project-trend-comparison-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_trend_comparison_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 使用creation_time进行趋势分析
    df_copy = df.copy()
    
    # 检查是否有日期字段
    date_fields = ['creation_time', 'detected_on', 'modified_on']
    date_field = next((field for field in date_fields if field in df_copy.columns), None)
    
    if not date_field:
        return go.Figure().update_layout(title="没有日期数据可用于趋势分析")
    
    df_copy['date'] = pd.to_datetime(df_copy[date_field]).dt.date
    
    # 取前10个缺陷最多的项目
    top_projects = df_copy['ecu'].value_counts().head(10).index
    df_filtered = df_copy[df_copy['ecu'].isin(top_projects)]
    
    # 按日期和项目分组
    trend_data = df_filtered.groupby(['date', 'ecu']).size().reset_index(name='缺陷数量')
    
    # 创建折线图
    fig = px.line(
        trend_data,
        x='date',
        y='缺陷数量',
        color='ecu',
        markers=True,
        title="项目缺陷发现趋势对比（前10名）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目缺陷发现趋势对比（前10名）",
        x_title="日期",
        y_title="缺陷数量",
        height=450
    )
    
    return fig

# 项目阻塞原因分析对比图表
@app.callback(
    Output('project-blocking-comparison-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_blocking_comparison_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 筛选有阻塞原因的数据
    blocking_data = df[df['blocking_reason'].notna() & (df['blocking_reason'] != '')]
    
    if blocking_data.empty:
        return go.Figure().update_layout(title="没有阻塞原因数据")
    
    # 取前10个有阻塞问题最多的项目
    top_blocking_projects = blocking_data['ecu'].value_counts().head(10).index
    blocking_filtered = blocking_data[blocking_data['ecu'].isin(top_blocking_projects)]
    
    # 按项目和阻塞原因分组
    blocking_stats = blocking_filtered.groupby(['ecu', 'blocking_reason']).size().reset_index(name='阻塞数量')
    
    # 创建堆叠条形图
    fig = px.bar(
        blocking_stats,
        x='ecu',
        y='阻塞数量',
        color='blocking_reason',
        barmode='stack',
        title="项目阻塞原因分析对比（前10名）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目阻塞原因分析对比（前10名）",
        x_title="项目",
        y_title="阻塞缺陷数量",
        height=450
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 项目Matrix分布对比图表
@app.callback(
    Output('project-matrix-distribution-chart', 'figure'),
    [Input('current-nav-item', 'data')]
)
def update_project_matrix_distribution_chart(tab):
    if tab != 'tab-project-analysis':
        return go.Figure()
    
    # 筛选有Matrix数据的记录
    matrix_data = df[df['matrix'].notna() & (df['matrix'] != '')]
    
    if matrix_data.empty:
        return go.Figure().update_layout(title="没有Matrix数据")
    
    # 取前15个缺陷最多的项目
    top_projects = matrix_data['ecu'].value_counts().head(15).index
    matrix_filtered = matrix_data[matrix_data['ecu'].isin(top_projects)]
    
    # 按项目和Matrix分组
    matrix_stats = matrix_filtered.groupby(['ecu', 'matrix']).size().reset_index(name='缺陷数量')
    
    # 创建堆叠条形图
    fig = px.bar(
        matrix_stats,
        x='ecu',
        y='缺陷数量',
        color='matrix',
        barmode='stack',
        title="项目Matrix分布对比（前15名）"
    )
    
    fig = apply_chart_style(
        fig,
        title="项目Matrix分布对比（前15名）",
        x_title="项目",
        y_title="缺陷数量",
        height=500
    )
    
    fig.update_layout(xaxis_tickangle=-45)
    
    return fig

# 项目详细统计表
@app.callback(
    Output('project-stats-table', 'data'),
    [Input('current-nav-item', 'data')]
)
def update_project_stats_table(tab):
    if tab != 'tab-project-analysis':
        return []
    
    # 计算每个项目的详细统计
    df_copy = df.copy()
    
    # 定义严重缺陷的判断逻辑
    def is_severe_defect(row):
        severe_matrices = ['Matrix-1A', 'Matrix-1B', 'Matrix-1C', 'Matrix-1D', 'Matrix-1E', 
                          'Matrix-2A', 'Matrix-2B', 'Matrix-2C', 'Matrix-3A']
        severe_classifications = ['Showstopper_Candidate', 'Showstopper_Confirmed', 
                                'Preventing Maturity Grade ConDrive', 'Obstructing Maturity Grade ConDrive']
        
        matrix_severe = row['matrix'] in severe_matrices if row['matrix'] else False
        classification_severe = False
        if isinstance(row['classification'], list):
            classification_severe = any(cls in severe_classifications for cls in row['classification'])
        
        return matrix_severe or classification_severe
    
    df_copy['severity_group'] = df_copy.apply(
        lambda row: "Critical Issues" if is_severe_defect(row) else "General Issues", axis=1
    )
    
    # 定义已解决状态
    resolved_statuses = ['06-Resolved', '07-Closed', '08-Verified']
    
    # 按项目分组计算统计指标
    project_stats = []
    
    for project in df_copy['ecu'].apply(lambda x: str(x) if isinstance(x, dict) else x).unique():
        if not project:
            continue
            
        project_data = df_copy[df_copy['ecu'] == project]
        
        total_defects = len(project_data)
        severe_defects = len(project_data[project_data['severity_group'] == 'Critical Issues'])
        severe_rate = (severe_defects / total_defects * 100) if total_defects > 0 else 0
        
        resolved_defects = len(project_data[project_data['status_phase'].isin(resolved_statuses)])
        resolution_rate = (resolved_defects / total_defects * 100) if total_defects > 0 else 0
        
        aida_coverage = project_data['aida_english'].nunique()
        
        # 计算平均处理时间（如果有日期字段）
        avg_resolution_time = 0
        if 'creation_time' in project_data.columns and 'modified_on' in project_data.columns:
            resolved_data = project_data[project_data['status_phase'].isin(resolved_statuses)]
            if not resolved_data.empty:
                try:
                    creation_times = pd.to_datetime(resolved_data['creation_time'])
                    modified_times = pd.to_datetime(resolved_data['modified_on'])
                    time_diffs = (modified_times - creation_times).dt.days
                    avg_resolution_time = time_diffs.mean()
                    if pd.isna(avg_resolution_time):
                        avg_resolution_time = 0
                except:
                    avg_resolution_time = 0
        
        blocked_defects = len(project_data[project_data['blocking_reason'].notna() & (project_data['blocking_reason'] != '')])
        
        project_stats.append({
            'ecu': project,
            'total_defects': total_defects,
            'severe_defects': severe_defects,
            'severe_rate': round(severe_rate, 1),
            'resolved_defects': resolved_defects,
            'resolution_rate': round(resolution_rate, 1),
            'aida_coverage': aida_coverage,
            'avg_resolution_time': round(avg_resolution_time, 1),
            'blocked_defects': blocked_defects
        })
    
    # 按总缺陷数排序
    project_stats = sorted(project_stats, key=lambda x: x['total_defects'], reverse=True)
    
    return project_stats

# Excel导出功能回调
@app.callback(
    [Output('download-excel', 'data'),
     Output('export-status', 'children')],
    [Input('export-excel-btn', 'n_clicks')],
    [State('year-dropdown', 'value'),
     State('project-dropdown', 'value'),
     State('date-range-picker-main', 'start_date'),
     State('date-range-picker-main', 'end_date'),
     State('aida-dropdown', 'value'),
     State('status-dropdown', 'value'),
     State('pu-dropdown', 'value'),
     State('tester-dropdown-main', 'value'),
     State('fv-dropdown', 'value'),
     State('ecu-dropdown', 'value'),
     State('lead-model-dropdown', 'value'),
     State('fvp-dropdown', 'value'),
     State('severe-matrix-dropdown', 'value'),
     State('severe-classification-dropdown', 'value'),
     State('market-dropdown', 'value')],
    prevent_initial_call=True
)
def export_to_excel(n_clicks, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, severe_matrices, severe_classifications, markets):
    """
    根据当前筛选条件导出缺陷数据到Excel文件
    """
    if not n_clicks:
        raise PreventUpdate
    
    try:
        # 使用通用筛选函数
        filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
        
        if filtered_data.empty:
            return no_update, "没有数据可导出"
        
        # 定义严重缺陷判断函数
        def is_severe_defect(row):
            # 检查Matrix是否为严重
            matrix_severe = False
            if severe_matrices and row['matrix'] in severe_matrices:
                matrix_severe = True
            
            # 检查Classification是否为严重
            classification_severe = False
            if severe_classifications and isinstance(row['classification'], list):
                if any(cls in severe_classifications for cls in row['classification']):
                    classification_severe = True
            
            return matrix_severe or classification_severe
        
        # 添加严重性标记
        filtered_data['severity_group'] = filtered_data.apply(
            lambda row: 'Critical Issues' if is_severe_defect(row) else 'General Issues', axis=1
        )
        
        # 处理ECU变更次数 - 改为显示流转路径
        def get_ecu_flow_path(row):
            defect_id = str(row.get('id', ''))
            if defect_id:
                try:
                    path = get_ecu_transition_path(defect_id)
                    if path and path != "No change":
                        # path已经包含了次数和路径，直接返回
                        return path
                    return "No change"
                except Exception as e:
                    return "No change"
            return "No change"
        
        filtered_data['ecu_pingpong_display'] = filtered_data.apply(get_ecu_flow_path, axis=1)

        # 处理Domain变更次数 - 改为显示流转路径
        def get_solution_cluster_flow_path(row):
            defect_id = str(row.get('id', ''))
            if defect_id:
                try:
                    path = get_solution_cluster_transition_path(defect_id)
                    if path and path != "No change":
                        # path已经包含了次数和路径，直接返回
                        return path
                    return "No change"
                except Exception as e:
                    return "No change"
            return "No change"
        
        filtered_data['domain_pingpong_display'] = filtered_data.apply(get_solution_cluster_flow_path, axis=1)
        
        # 处理Parent/Child关系
        def count_linked_defects_for_parent(relation_str):
            if not relation_str or pd.isna(relation_str):
                return 0
            try:
                ids = str(relation_str).split(',')
                return len([id.strip() for id in ids if id.strip()])
            except:
                return 0
        
        def get_parent_ticket_info(row):
            if pd.isna(row.get('relation_to_udf')) or not row.get('relation_to_udf'):
                return '无'
            
            try:
                global master_df
                parent_ids = str(row['relation_to_udf']).split(',')
                parent_info_list = []
                
                for parent_id in parent_ids:
                    parent_id = parent_id.strip()
                    if parent_id and master_df is not None and not master_df.empty:
                        # 确保ID类型匹配
                        master_df_copy = master_df.copy()
                        master_df_copy['id'] = master_df_copy['id'].astype(str)
                        parent_id_str = str(parent_id)
                        
                        parent_row = master_df_copy[master_df_copy['id'] == parent_id_str]
                        if not parent_row.empty:
                            parent_name = parent_row.iloc[0].get('name', '未知')
                            parent_status = parent_row.iloc[0].get('status_phase', '未知')
                            parent_info_list.append(f"{parent_id}({parent_name}-{parent_status})")
                        else:
                            parent_info_list.append(f"{parent_id}(未找到详情)")
                    elif parent_id:
                        parent_info_list.append(f"{parent_id}(无详情)")
                
                return '; '.join(parent_info_list) if parent_info_list else '无'
            except Exception as e:
                return f'解析错误: {str(e)}'
        
        # 处理Parent/Child显示
        if 'parent_child' in filtered_data.columns:
            filtered_data['parent_child_display'] = filtered_data['parent_child'].fillna('Unknown')
        else:
            # 如果没有parent_child字段，基于relation_to_udf和child_count_of_master判断
            filtered_data['parent_child_display'] = filtered_data.apply(
                lambda row: f"Parent({count_linked_defects_for_parent(row.get('relation_to_udf', ''))})" 
                           if not pd.isna(row.get('relation_to_udf')) and row.get('relation_to_udf') 
                           else f"Child({row.get('child_count_of_master', 0)})" 
                           if row.get('child_count_of_master', 0) > 0 
                           else "Independent", axis=1
            )
        
        # 处理子票数量显示
        filtered_data['child_count_display'] = filtered_data.apply(
            lambda row: row['child_count_of_master'] if row.get('parent_child') in ['Child', 'Child (candidate)'] else 0,
            axis=1
        ).fillna(0).astype(int)
        
        # 处理Parent Child Count
        filtered_data['parent_child_count_display'] = filtered_data.apply(
            lambda row: count_linked_defects_for_parent(row.get('relation_to_udf', '')) if row.get('parent_child') == 'Parent' else 0,
            axis=1
        ).astype(int)
        
        # 处理父票信息
        filtered_data['parent_ticket_info'] = filtered_data.apply(get_parent_ticket_info, axis=1)
        
        # 处理主票状态
        def get_master_status(row):
            if row.get('parent_child') not in ['Child', 'Child (candidate)']:
                return ""
            
            master_id = row.get('master_id')
            if not master_id or pd.isna(master_id):
                return ""
            
            # 首先从全局的master_df中查找主票状态
            global master_df
            if master_df is not None and not master_df.empty:
                # 确保ID类型匹配
                master_df_copy = master_df.copy()
                master_df_copy['id'] = master_df_copy['id'].astype(str)
                master_id_str = str(master_id)
                
                parent_info = master_df_copy[master_df_copy['id'] == master_id_str]
                if not parent_info.empty:
                    parent_row = parent_info.iloc[0]
                    # 从phase.name字段获取状态
                    phase_name = parent_row.get('phase.name', '')
                    if phase_name:
                        return phase_name
                    # 如果phase.name为空，尝试其他可能的字段
                    return parent_row.get('status_phase', '')
            
            # 如果在master_df中找不到，尝试在当前数据中查找
            parent_in_current = filtered_data[filtered_data['id'] == str(master_id)]
            if not parent_in_current.empty:
                parent_row = parent_in_current.iloc[0]
                return parent_row.get('status_phase', '')
            
            return ""
        
        filtered_data['master_status'] = filtered_data.apply(get_master_status, axis=1)
        
        # 处理周期显示
        def calculate_processing_cycle_display(row):
            cycle_days = calculate_processing_cycle_days(
                row['id'], 
                row['status_phase'], 
                row['creation_time']
            )
            return f"{cycle_days}天"
        filtered_data['processing_cycle_days'] = filtered_data.apply(calculate_processing_cycle_display, axis=1)
        
        # 处理PU和Shift_PU
        if 'pu' in filtered_data.columns:
            filtered_data['pu_display'] = filtered_data['pu'].fillna('未知')
        else:
            filtered_data['pu_display'] = '未知'
        
        if 'Shift_PU' in filtered_data.columns:
            filtered_data['shift_pu_display'] = filtered_data['Shift_PU'].fillna('').astype(str)
        else:
            filtered_data['shift_pu_display'] = ''
        
        # 检查并添加topissue_recommend_reason字段
        if 'topissue_recommend_reason' not in filtered_data.columns:
            filtered_data['topissue_recommend_reason'] = 'No recommendation available'
        else:
            filtered_data['topissue_recommend_reason'] = filtered_data['topissue_recommend_reason'].fillna('No recommendation available')
        
        # 处理TopIssue推荐理由 - 应用与弹框相同的格式化
        def format_topissue_recommendation_for_export(reason_str, row):
            """Excel导出专用的TopIssue推荐理由格式化"""
            if pd.isna(reason_str) or not reason_str or reason_str.strip() == '':
                return 'No recommendation available'
            
            # 如果已经是格式化的字符串，直接返回
            if '1. Severity:' in str(reason_str):
                return str(reason_str)
            
            # 尝试解析原始的推荐理由并格式化
            try:
                reason_text = str(reason_str).strip()
                if reason_text == 'No recommendation available':
                    return reason_text
                
                # 初始化4个因素的默认值
                severity_info = "Not detected"
                high_runner_info = "Not detected"
                complexity_info = "Not detected"
                processing_efficiency_info = "Not detected"
                
                # 按行分割原始推荐理由
                lines = reason_text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('SEVERITY:'):
                        severity_info = line.replace('SEVERITY:', '').strip()
                    elif line.startswith('COMPLEXITY:'):
                        high_runner_info = line.replace('COMPLEXITY:', '').strip()
                    elif line.startswith('HIGH RUNNER:'):
                        complexity_info = line.replace('HIGH RUNNER:', '').strip()
                    elif line.startswith('LONG RUNNER:'):
                        processing_efficiency_info = line.replace('LONG RUNNER:', '').strip()
                
                # 重新生成COMPLEXITY信息，使用当前行的最新格式化数据
                updated_complexity_items = []
                
                # 使用最新的ECU转移次数信息（只显示次数，不显示路径）
                ecu_path = row.get('ecu_pingpong_display', '')
                if ecu_path and str(ecu_path) != 'No change' and str(ecu_path).strip():
                    if ',' in str(ecu_path):
                        ecu_count = str(ecu_path).split(',')[0].strip()
                        updated_complexity_items.append(f"ECU {ecu_count}次转移")
                
                # 使用最新的Domain转移次数信息（只显示次数，不显示路径）  
                domain_path = row.get('domain_pingpong_display', '')
                if domain_path and str(domain_path) != 'No change' and str(domain_path).strip():
                    if ',' in str(domain_path):
                        domain_count = str(domain_path).split(',')[0].strip()
                        updated_complexity_items.append(f"Domain {domain_count}次转移")
                
                # 如果有更新的COMPLEXITY信息，使用它
                if updated_complexity_items:
                    complexity_info = '; '.join(updated_complexity_items)
                elif complexity_info == "Not detected":
                    # 如果没有检测到，保持原有逻辑
                    pass
                
                # 获取实际的Risk Score和分数分解
                actual_risk_score = row.get('topissue_risk_score', 0)
                if pd.isna(actual_risk_score):
                    actual_risk_score = 0
                
                # 计算基础维度分数（用于显示分解）
                basic_scores = calculate_basic_scores(row)
                basic_total = sum([basic_scores[key] for key in basic_scores if key != 'nonlinear'])
                nonlinear_adjustment = max(0, actual_risk_score - basic_total)
                
                # 构建分数分解显示
                score_breakdown = f"Matrix {basic_scores['matrix']}pts + Classification {basic_scores['classification']}pts + ECU Transfer {basic_scores['ecu_transfer']}pts + Domain Transfer {basic_scores['domain_transfer']}pts + Parent Complexity {basic_scores['parent_complexity']}pts + Child Complexity {basic_scores['child_complexity']}pts + Processing Cycle {basic_scores['processing_cycle']}pts + Shift PU {basic_scores['shift_pu']}pts"
                
                if nonlinear_adjustment > 0:
                    score_breakdown += f" + Adjustments {nonlinear_adjustment:.0f}pts"
                
                score_breakdown += f" = Total {actual_risk_score}pts"
                
                # 创建格式化的5行推荐理由
                formatted_reason = f"1. Severity: {severity_info}\n"
                formatted_reason += f"2. High Runner: {high_runner_info}\n"
                formatted_reason += f"3. Complexity: {complexity_info}\n"
                formatted_reason += f"4. Processing Efficiency: {processing_efficiency_info}\n"
                formatted_reason += f"5. Risk Score Calculation: {score_breakdown}"
                
                return formatted_reason
            except:
                return 'No recommendation available'
        
        # 应用TopIssue推荐理由格式化
        if 'topissue_recommend_reason' not in filtered_data.columns:
            filtered_data['topissue_recommend_reason'] = 'No recommendation available'
        else:
            filtered_data['topissue_recommend_reason'] = filtered_data.apply(lambda row: format_topissue_recommendation_for_export(row.get('topissue_recommend_reason', ''), row), axis=1)
        
        # 处理Solution Cluster/Domain字段
        if 'domain' in filtered_data.columns:
            filtered_data['solution_cluster'] = filtered_data['domain'].fillna('未分配')
        else:
            filtered_data['solution_cluster'] = '未分配'
        
        # 选择要导出的列（包含所有缺陷详情中的信息）
        export_columns = [
            'id', 'name', 'ecu', 'fv', 'matrix_display', 'classification_display', 
        'ecu_pingpong_display', 'domain_pingpong_display', 'parent_child_display', 
        'child_count_display', 'parent_child_count_display', 'parent_ticket_info', 
            'processing_cycle_days', 'pu_display', 'shift_pu_display', 'topissue_display', 'topissue_recommend_reason',
            'aida_english', 'status_phase', 'master_status', 'tester', 'severity_group', 'is_topissue', 'solution_cluster'
        ]
        
        # 确保所有列都存在
        available_columns = [col for col in export_columns if col in filtered_data.columns]
        export_data = filtered_data[available_columns].copy()
        
        # 重命名列为中文
        column_mapping = {
            'id': 'ID',
            'name': 'Name',
            'ecu': 'Project',
            'fv': 'FV (Feature Team)',
            'matrix_display': 'Matrix',
            'classification_display': 'Classification',
            'ecu_pingpong_display': 'ECU变更次数',
            'domain_pingpong_display': 'Solution Cluster变更次数',
            'parent_child_display': 'Parent/Child',
            'child_count_display': 'Child Count',
            'parent_child_count_display': 'Parent Child Count',
            'parent_ticket_info': 'Master Ticket Info',
            'processing_cycle_days': 'Process Days',
            'pu_display': 'PU',
            'shift_pu_display': 'Shift_PU',
            'topissue_display': 'Risk Score',
            'topissue_recommend_reason': 'Top Issue Recommendation',
            'aida_english': 'AIDA',
            'status_phase': 'Status',
            'master_status': 'Master Status',
            'tester': '测试人员',
            'severity_group': '严重程度',
            'is_topissue': '是否Top Issue',
            'solution_cluster': 'Solution Cluster'
        }
        
        export_data = export_data.rename(columns=column_mapping)
        
        # 生成文件名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"缺陷数据导出_{timestamp}.xlsx"
        
        # 创建Excel文件
        import io
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 写入主数据表
            export_data.to_excel(writer, sheet_name='缺陷数据', index=False)
            
            # 添加筛选条件说明表
            filter_info = []
            if projects:
                filter_info.append(['项目筛选', ', '.join(projects)])
            if start_date or end_date:
                filter_info.append(['日期范围筛选', f"{start_date or 'Beginning'} to {end_date or 'Now'}"])
            if aidas:
                filter_info.append(['AIDA筛选', ', '.join(aidas)])
            if statuses:
                filter_info.append(['状态筛选', ', '.join(statuses)])
            if pus:
                filter_info.append(['PU筛选', ', '.join(pus)])
            if fvs:
                filter_info.append(['FV筛选', ', '.join(fvs)])
            if severe_matrices:
                filter_info.append(['严重Matrix定义', ', '.join(severe_matrices)])
            if severe_classifications:
                filter_info.append(['严重Classification定义', ', '.join(severe_classifications)])
            
            filter_info.append(['导出时间', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            filter_info.append(['总记录数', len(export_data)])
            
            filter_df = pd.DataFrame(filter_info, columns=['筛选条件', '值'])
            filter_df.to_excel(writer, sheet_name='筛选条件', index=False)
        
        output.seek(0)
        
        return dcc.send_bytes(output.getvalue(), filename), f"成功导出 {len(export_data)} 条记录"
        
    except Exception as e:
        return no_update, f"导出失败: {str(e)}"

# Solution Cluster Excel导出功能回调
@app.callback(
    [Output('download-cluster-excel', 'data'),
     Output('export-cluster-status', 'children')],
    [Input('export-cluster-excel-btn', 'n_clicks')],
    [State('year-dropdown', 'value'),
     State('project-dropdown', 'value'),
     State('date-range-picker-main', 'start_date'),
     State('date-range-picker-main', 'end_date'),
     State('aida-dropdown', 'value'),
     State('status-dropdown', 'value'),
     State('pu-dropdown', 'value'),
     State('tester-dropdown-main', 'value'),
     State('fv-dropdown', 'value'),
     State('ecu-dropdown', 'value'),
     State('lead-model-dropdown', 'value'),
     State('fvp-dropdown', 'value'),
     State('severe-matrix-dropdown', 'value'),
     State('severe-classification-dropdown', 'value'),
     State('market-dropdown', 'value')],
    prevent_initial_call=True
)
def export_cluster_to_excel(n_clicks, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, severe_matrices, severe_classifications, markets):
    """
    根据当前筛选条件导出Solution Cluster分布数据到Excel文件
    """
    if not n_clicks:
        raise PreventUpdate
    
    try:
        # 使用通用筛选函数
        filtered_data = filter_dataframe(df, years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, lead_models, fvps, markets)
        
        if filtered_data.empty:
            return no_update, "没有数据可导出"
        
        # 定义严重缺陷判断函数
        def is_severe_defect(row):
            # 检查Matrix是否为严重
            matrix_severe = False
            if severe_matrices and row['matrix'] in severe_matrices:
                matrix_severe = True
            
            # 检查Classification是否为严重
            classification_severe = False
            if severe_classifications and isinstance(row['classification'], list):
                if any(cls in severe_classifications for cls in row['classification']):
                    classification_severe = True
            
            return matrix_severe or classification_severe
        
        # 执行智能分配逻辑
        def reassign_unassigned_clusters(data):
            # 找到未分配的缺陷
            unassigned_mask = (data['domain'].isna()) | (data['domain'] == '') | (data['domain'].str.strip() == '')
            unassigned_data = data[unassigned_mask].copy()
            assigned_data = data[~unassigned_mask].copy()
            
            if len(unassigned_data) == 0:
                return data
            
            # 为每个AIDA领域建立Solution Cluster映射
            aida_to_cluster_map = {}
            for _, row in assigned_data.iterrows():
                aida = row.get('aida_english', '')
                cluster = row.get('domain', '')
                if aida and cluster:
                    if aida not in aida_to_cluster_map:
                        aida_to_cluster_map[aida] = {}
                    if cluster not in aida_to_cluster_map[aida]:
                        aida_to_cluster_map[aida][cluster] = 0
                    aida_to_cluster_map[aida][cluster] += 1
            
            # 定义AIDA到合理Solution Cluster的预期映射（基于领域知识）
            expected_aida_cluster_mapping = {
                'videostreaming': ['multimedia', 'streaming', 'video', 'display', 'camera'],
                'audio': ['audio', 'multimedia', 'sound', 'speaker'],
                'communication': ['communication', 'network', 'connectivity', 'radio'],
                'navigation': ['navigation', 'gps', 'maps', 'routing'],
                'vehicle_control': ['vehicle', 'control', 'drive', 'chassis'],
                'safety': ['safety', 'security', 'protection', 'airbag'],
                'infotainment': ['infotainment', 'entertainment', 'multimedia', 'hmi'],
                'diagnosis': ['diagnosis', 'diagnostic', 'system', 'obd'],
                'climate': ['climate', 'hvac', 'temperature', 'air'],
                'lighting': ['lighting', 'light', 'illumination', 'led'],
                'body': ['body', 'door', 'window', 'seat'],
                'powertrain': ['powertrain', 'engine', 'transmission', 'hybrid'],
                'connectivity': ['connectivity', 'bluetooth', 'wifi', 'cellular']
            }
            
            # 为每个AIDA选择最合理的Solution Cluster
            aida_preferred_cluster = {}
            for aida, clusters in aida_to_cluster_map.items():
                if clusters:
                    # 首先检查是否有符合预期的映射
                    expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                    
                    best_cluster = None
                    best_score = 0
                    best_count = 0
                    
                    for cluster, count in clusters.items():
                        score = 0
                        cluster_lower = cluster.lower()
                        
                        # 计算匹配分数：如果cluster名称包含预期关键词，给予额外分数
                        for keyword in expected_keywords:
                            if keyword in cluster_lower:
                                score += 10  # 预期匹配给高分
                        
                        # 添加出现频次作为基础分数
                        score += count
                        
                        # 选择分数最高的cluster
                        if score > best_score or (score == best_score and count > best_count):
                            best_cluster = cluster
                            best_score = score
                            best_count = count
                    
                    if best_cluster:
                        aida_preferred_cluster[aida] = best_cluster
            
            # 重新分配未分配的缺陷
            data_copy = data.copy()
            assigned_count = 0
            skipped_count = 0
            for idx, row in unassigned_data.iterrows():
                aida = row.get('aida_english', '')
                if aida in aida_preferred_cluster:
                    # 额外验证：如果分配结果明显不合理，跳过自动分配
                    preferred_cluster = aida_preferred_cluster[aida]
                    expected_keywords = expected_aida_cluster_mapping.get(aida.lower(), [])
                    
                    # 对于有预期映射的AIDA，验证分配的合理性
                    should_assign = True
                    if expected_keywords:
                        match_found = any(keyword in preferred_cluster.lower() for keyword in expected_keywords)
                        if not match_found:
                            # 如果分配明显不合理，保持未分配状态
                            should_assign = False
                            skipped_count += 1
                    
                    if should_assign:
                        data_copy.at[idx, 'domain'] = preferred_cluster
                        assigned_count += 1
            
                return data_copy
        
        # 应用智能分配
        filtered_data = reassign_unassigned_clusters(filtered_data)
        
        # 处理严重性标记
        filtered_data['severity_group'] = filtered_data.apply(
            lambda row: 'Critical Issues' if is_severe_defect(row) else 'General Issues', axis=1
        )
        
        # 生成Solution Cluster统计数据
        cluster_stats = []
        
        # 按Solution Cluster分组统计
        for cluster in filtered_data['domain'].apply(lambda x: str(x) if isinstance(x, dict) else x).unique():
            if pd.isna(cluster) or cluster == '':
                cluster = '未分配'
            
            cluster_data = filtered_data[filtered_data['domain'] == cluster] if cluster != '未分配' else filtered_data[(filtered_data['domain'].isna()) | (filtered_data['domain'] == '')]
            
            total_count = len(cluster_data)
            severe_count = len(cluster_data[cluster_data['severity_group'] == 'Critical Issues'])
            general_count = total_count - severe_count
            
            # 状态分布
            status_dist = cluster_data['status_phase'].value_counts().to_dict()
            
            # AIDA分布
            aida_dist = cluster_data['aida_english'].value_counts().to_dict()
            
            # 项目分布
            project_dist = cluster_data['ecu'].value_counts().to_dict()
            
            cluster_stats.append({
                'Solution Cluster': cluster,
                '总缺陷数': total_count,
                '严重缺陷数': severe_count,
                '一般缺陷数': general_count,
                '严重缺陷率(%)': round(severe_count / total_count * 100, 2) if total_count > 0 else 0,
                '主要状态': ', '.join([f"{k}({v})" for k, v in sorted(status_dist.items(), key=lambda x: x[1], reverse=True)[:3]]),
                '主要AIDA': ', '.join([f"{k}({v})" for k, v in sorted(aida_dist.items(), key=lambda x: x[1], reverse=True)[:3]]),
                '主要项目': ', '.join([f"{k}({v})" for k, v in sorted(project_dist.items(), key=lambda x: x[1], reverse=True)[:3]])
            })
        
        # 按缺陷数量排序
        cluster_stats_df = pd.DataFrame(cluster_stats)
        cluster_stats_df = cluster_stats_df.sort_values('总缺陷数', ascending=False)
        
        # 处理ECU变更次数 - 使用完整流转路径
        def get_ecu_flow_path_cluster(row):
            """获取ECU流转路径（cluster分析版本）"""
            defect_id = str(row.get('id', ''))
            if defect_id:
                try:
                    path = get_ecu_transition_path(defect_id)
                    if path and path != "No change":
                        return path
                    return "No change"
                except Exception as e:
                    return "No change"
            return "No change"
        
        filtered_data['ecu_pingpong_display'] = filtered_data.apply(get_ecu_flow_path_cluster, axis=1)
        
        # 处理Domain变更次数 - 使用完整流转路径  
        def get_domain_flow_path_cluster(row):
            """获取Domain流转路径（cluster分析版本）"""
            defect_id = str(row.get('id', ''))
            if defect_id:
                try:
                    path = get_solution_cluster_transition_path(defect_id)
                    if path and path != "No change":
                        return path
                    return "No change"
                except Exception as e:
                    return "No change"
            return "No change"
        
        filtered_data['domain_pingpong_display'] = filtered_data.apply(get_domain_flow_path_cluster, axis=1)
        
        # 处理Parent/Child关系函数
        def count_linked_defects_for_parent_cluster(relation_str):
            if not relation_str or pd.isna(relation_str):
                return 0
            try:
                ids = str(relation_str).split(',')
                return len([id.strip() for id in ids if id.strip()])
            except:
                return 0
        
        def get_parent_ticket_info_cluster(row):
            if pd.isna(row.get('relation_to_udf')) or not row.get('relation_to_udf'):
                return '无'
            
            try:
                global master_df
                parent_ids = str(row['relation_to_udf']).split(',')
                parent_info_list = []
                
                for parent_id in parent_ids:
                    parent_id = parent_id.strip()
                    if parent_id and master_df is not None and not master_df.empty:
                        master_df_copy = master_df.copy()
                        master_df_copy['id'] = master_df_copy['id'].astype(str)
                        parent_id_str = str(parent_id)
                        
                        parent_row = master_df_copy[master_df_copy['id'] == parent_id_str]
                        if not parent_row.empty:
                            parent_name = parent_row.iloc[0].get('name', '未知')
                            parent_status = parent_row.iloc[0].get('status_phase', '未知')
                            parent_info_list.append(f"{parent_id}({parent_name}-{parent_status})")
                        else:
                            parent_info_list.append(f"{parent_id}(未找到详情)")
                    elif parent_id:
                        parent_info_list.append(f"{parent_id}(无详情)")
                
                return '; '.join(parent_info_list) if parent_info_list else '无'
            except Exception as e:
                return f'解析错误: {str(e)}'
        
        def get_master_status_cluster(row):
            if row.get('parent_child') not in ['Child', 'Child (candidate)']:
                return ""
            
            master_id = row.get('master_id')
            if not master_id or pd.isna(master_id):
                return ""
            
            global master_df
            if master_df is not None and not master_df.empty:
                master_df_copy = master_df.copy()
                master_df_copy['id'] = master_df_copy['id'].astype(str)
                master_id_str = str(master_id)
                
                parent_info = master_df_copy[master_df_copy['id'] == master_id_str]
                if not parent_info.empty:
                    parent_row = parent_info.iloc[0]
                    phase_name = parent_row.get('phase.name', '')
                    if phase_name:
                        return phase_name
                    return parent_row.get('status_phase', '')
            
            parent_in_current = filtered_data[filtered_data['id'] == str(master_id)]
            if not parent_in_current.empty:
                parent_row = parent_in_current.iloc[0]
                return parent_row.get('status_phase', '')
            
            return ""
        
        def calculate_processing_cycle_display_cluster(row):
            cycle_days = calculate_processing_cycle_days(
                row['id'], 
                row['status_phase'], 
                row['creation_time']
            )
            return f"{cycle_days}天"
        
        # 处理Parent/Child显示
        if 'parent_child' in filtered_data.columns:
            filtered_data['parent_child_display'] = filtered_data['parent_child'].fillna('Unknown')
        else:
            filtered_data['parent_child_display'] = filtered_data.apply(
                lambda row: f"Parent({count_linked_defects_for_parent_cluster(row.get('relation_to_udf', ''))})" 
                           if not pd.isna(row.get('relation_to_udf')) and row.get('relation_to_udf') 
                           else f"Child({row.get('child_count_of_master', 0)})" 
                           if row.get('child_count_of_master', 0) > 0 
                           else "Independent", axis=1
            )
        
        # 处理子票数量显示
        filtered_data['child_count_display'] = filtered_data.apply(
            lambda row: row['child_count_of_master'] if row.get('parent_child') in ['Child', 'Child (candidate)'] else 0,
            axis=1
        ).fillna(0).astype(int)
        
        # 处理Parent Child Count
        filtered_data['parent_child_count_display'] = filtered_data.apply(
            lambda row: count_linked_defects_for_parent_cluster(row.get('relation_to_udf', '')) if row.get('parent_child') == 'Parent' else 0,
            axis=1
        ).astype(int)
        
        # 处理父票信息
        filtered_data['parent_ticket_info'] = filtered_data.apply(get_parent_ticket_info_cluster, axis=1)
        
        # 处理主票状态
        filtered_data['master_status'] = filtered_data.apply(get_master_status_cluster, axis=1)
        
        # 处理周期显示
        filtered_data['processing_cycle_days'] = filtered_data.apply(calculate_processing_cycle_display_cluster, axis=1)
        
        # 处理Shift_PU
        if 'Shift_PU' in filtered_data.columns:
            filtered_data['shift_pu_display'] = filtered_data['Shift_PU'].fillna('').astype(str)
        else:
            filtered_data['shift_pu_display'] = ''
        
        # 处理TopIssue推荐理由 - 应用与弹框相同的格式化
        def format_topissue_recommendation_for_cluster_export(reason_str, row):
            """Solution Cluster Excel导出专用的TopIssue推荐理由格式化"""
            if pd.isna(reason_str) or not reason_str or reason_str.strip() == '':
                return 'No recommendation available'
            
            # 如果已经是格式化的字符串，直接返回
            if '1. Severity:' in str(reason_str):
                return str(reason_str)
            
            # 尝试解析原始的推荐理由并格式化
            try:
                reason_text = str(reason_str).strip()
                if reason_text == 'No recommendation available':
                    return reason_text
                
                # 初始化4个因素的默认值
                severity_info = "Not detected"
                high_runner_info = "Not detected"
                complexity_info = "Not detected"
                processing_efficiency_info = "Not detected"
                
                # 按行分割原始推荐理由
                lines = reason_text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if line.startswith('SEVERITY:'):
                        severity_info = line.replace('SEVERITY:', '').strip()
                    elif line.startswith('COMPLEXITY:'):
                        high_runner_info = line.replace('COMPLEXITY:', '').strip()
                    elif line.startswith('HIGH RUNNER:'):
                        complexity_info = line.replace('HIGH RUNNER:', '').strip()
                    elif line.startswith('LONG RUNNER:'):
                        processing_efficiency_info = line.replace('LONG RUNNER:', '').strip()
                
                # 重新生成COMPLEXITY信息，使用当前行的最新格式化数据
                updated_complexity_items = []
                
                # 使用最新的ECU转移次数信息（只显示次数，不显示路径）
                ecu_path = row.get('ecu_pingpong_display', '')
                if ecu_path and str(ecu_path) != 'No change' and str(ecu_path).strip():
                    if ',' in str(ecu_path):
                        ecu_count = str(ecu_path).split(',')[0].strip()
                        updated_complexity_items.append(f"ECU {ecu_count}次转移")
                
                # 使用最新的Domain转移次数信息（只显示次数，不显示路径）  
                domain_path = row.get('domain_pingpong_display', '')
                if domain_path and str(domain_path) != 'No change' and str(domain_path).strip():
                    if ',' in str(domain_path):
                        domain_count = str(domain_path).split(',')[0].strip()
                        updated_complexity_items.append(f"Domain {domain_count}次转移")
                
                # 如果有更新的COMPLEXITY信息，使用它
                if updated_complexity_items:
                    complexity_info = '; '.join(updated_complexity_items)
                elif complexity_info == "Not detected":
                    # 如果没有检测到，保持原有逻辑
                    pass
                
                # 获取实际的Risk Score和分数分解
                actual_risk_score = row.get('topissue_risk_score', 0)
                if pd.isna(actual_risk_score):
                    actual_risk_score = 0
                
                # 计算基础维度分数（用于显示分解）
                basic_scores = calculate_basic_scores(row)
                basic_total = sum([basic_scores[key] for key in basic_scores if key != 'nonlinear'])
                nonlinear_adjustment = max(0, actual_risk_score - basic_total)
                
                # 构建分数分解显示
                score_breakdown = f"Matrix {basic_scores['matrix']}pts + Classification {basic_scores['classification']}pts + ECU Transfer {basic_scores['ecu_transfer']}pts + Domain Transfer {basic_scores['domain_transfer']}pts + Parent Complexity {basic_scores['parent_complexity']}pts + Child Complexity {basic_scores['child_complexity']}pts + Processing Cycle {basic_scores['processing_cycle']}pts + Shift PU {basic_scores['shift_pu']}pts"
                
                if nonlinear_adjustment > 0:
                    score_breakdown += f" + Adjustments {nonlinear_adjustment:.0f}pts"
                
                score_breakdown += f" = Total {actual_risk_score}pts"
                
                # 创建格式化的5行推荐理由
                formatted_reason = f"1. Severity: {severity_info}\n"
                formatted_reason += f"2. High Runner: {high_runner_info}\n"
                formatted_reason += f"3. Complexity: {complexity_info}\n"
                formatted_reason += f"4. Processing Efficiency: {processing_efficiency_info}\n"
                formatted_reason += f"5. Risk Score Calculation: {score_breakdown}"
                
                return formatted_reason
            except:
                return 'No recommendation available'
        
        # 应用TopIssue推荐理由格式化
        if 'topissue_recommend_reason' not in filtered_data.columns:
            filtered_data['topissue_recommend_reason'] = 'No recommendation available'
        else:
            filtered_data['topissue_recommend_reason'] = filtered_data.apply(lambda row: format_topissue_recommendation_for_cluster_export(row.get('topissue_recommend_reason', ''), row), axis=1)
    
        # 生成详细的缺陷列表 - 包含所有字段
        detail_columns = [
            'id', 'name', 'ecu', 'fv', 'matrix_display', 'classification_display', 
            'ecu_pingpong_display', 'domain_pingpong_display', 'parent_child_display', 
            'child_count_display', 'parent_child_count_display', 'parent_ticket_info', 
            'processing_cycle_days', 'pu', 'shift_pu_display', 'topissue_display', 'topissue_recommend_reason',
            'aida_english', 'status_phase', 'master_status', 'tester', 'severity_group', 'is_topissue',
            'domain', 'creation_time', 'test_week'
        ]
        
        # 确保所有列都存在
        available_columns = [col for col in detail_columns if col in filtered_data.columns]
        detail_data = filtered_data[available_columns].copy()
        
        # 重命名列为中文
        column_mapping = {
            'id': 'ID',
            'name': 'Name',
            'ecu': 'Project',
            'fv': 'FV (Feature Team)',
            'matrix_display': 'Matrix',
            'classification_display': 'Classification',
            'ecu_pingpong_display': 'ECU变更次数',
            'domain_pingpong_display': 'Solution Cluster变更次数',
            'parent_child_display': 'Parent/Child',
            'child_count_display': 'Child Count',
            'parent_child_count_display': 'Parent Child Count',
            'parent_ticket_info': 'Master Ticket Info',
            'processing_cycle_days': 'Process Days',
            'pu': 'PU',
            'shift_pu_display': 'Shift_PU',
            'topissue_display': 'Risk Score',
            'topissue_recommend_reason': 'Top Issue Recommendation',
            'aida_english': 'AIDA',
            'status_phase': 'Status',
            'master_status': 'Master Status',
            'tester': 'Reporter',
            'severity_group': '严重性分组',
            'is_topissue': '是否Top Issue',
            'domain': 'Solution Cluster',
            'creation_time': '创建时间',
            'test_week': '测试周'
        }
        
        detail_data = detail_data.rename(columns=column_mapping)
        
        # 填充空的Solution Cluster
        detail_data['Solution Cluster'] = detail_data['Solution Cluster'].fillna('未分配')
        
        # 生成文件名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Solution_Cluster分布数据_{timestamp}.xlsx"
        
        # 创建Excel文件
        import io
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 写入统计汇总表
            cluster_stats_df.to_excel(writer, sheet_name='Solution Cluster统计', index=False)
            
            # 写入详细数据表
            detail_data.to_excel(writer, sheet_name='详细缺陷数据', index=False)
            
            # 添加筛选条件说明表
            filter_info = []
            if projects:
                filter_info.append(['项目筛选', ', '.join(projects)])
            if start_date or end_date:
                filter_info.append(['日期范围筛选', f"{start_date or 'Beginning'} to {end_date or 'Now'}"])
            if aidas:
                filter_info.append(['AIDA筛选', ', '.join(aidas)])
            if statuses:
                filter_info.append(['状态筛选', ', '.join(statuses)])
            if pus:
                filter_info.append(['PU筛选', ', '.join(pus)])
            if fvs:
                filter_info.append(['FV筛选', ', '.join(fvs)])
            if severe_matrices:
                filter_info.append(['严重Matrix定义', ', '.join(severe_matrices)])
            if severe_classifications:
                filter_info.append(['严重Classification定义', ', '.join(severe_classifications)])
            
            filter_info.append(['导出时间', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            filter_info.append(['总记录数', len(detail_data)])
            filter_info.append(['Solution Cluster数量', len(cluster_stats_df)])
            
            filter_df = pd.DataFrame(filter_info, columns=['筛选条件', '值'])
            filter_df.to_excel(writer, sheet_name='筛选条件', index=False)
        
        output.seek(0)
        
        return dcc.send_bytes(output.getvalue(), filename), f"成功导出 {len(cluster_stats_df)} 个Solution Cluster，{len(detail_data)} 条缺陷记录"
        
    except Exception as e:
        return no_update, f"导出失败: {str(e)}"

# 注册测试覆盖率回调函数 - 条件调用
if register_test_coverage_callbacks:
    register_test_coverage_callbacks(app, prefix="de-tc")
    print("测试覆盖率回调函数已注册 (前缀: de-tc)")
else:
    print("跳过测试覆盖率回调函数注册 (reloader进程)")

# ========================================
# Long Runner Analysis 回调函数
# ========================================

# 全局变量存储Phase Duration数据
global_phase_df = pd.DataFrame()
global_phase_ticket_details = {}

def create_phase_duration_bar_chart_lr(df, show_all=True):
    """
    创建phase transition平均时间柱状图 - 显示所有数据
    """
    required_cols = {'Phase_Transition', 'Avg_Days', 'Count', 'Min_Hours', 'Max_Hours'}
    if df.empty or not required_cols.issubset(set(df.columns)):
        return go.Figure().add_annotation(
            text="暂无数据，请点击'加载/刷新数据'按钮",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16)
        )
    
    # 显示所有数据，按平均耗时排序
    df_top = df.sort_values('Avg_Days', ascending=True).copy()  # 从小到大排序，便于柱状图显示
    
    # 创建颜色映射：高耗时为红色，中等为橙色，低耗时为绿色
    max_days = df_top['Avg_Days'].max()
    colors = []
    for days in df_top['Avg_Days']:
        if days > max_days * 0.7:
            colors.append('#e74c3c')  # 红色
        elif days > max_days * 0.3:
            colors.append('#f39c12')  # 橙色
        else:
            colors.append('#27ae60')  # 绿色
    
    fig = go.Figure(data=[
        go.Bar(
            y=df_top['Phase_Transition'],
            x=df_top['Avg_Days'],
            orientation='h',
            marker_color=colors,
            text=[f'{days:.1f}天 ({count}个样本)' for days, count in zip(df_top['Avg_Days'], df_top['Count'])],
            textposition='auto',
            hovertemplate='<b>%{y}</b><br>' +
                         '平均耗时: %{x:.1f}天<br>' +
                         '样本数量: %{customdata[0]}<br>' +
                         '最小耗时: %{customdata[1]:.1f}小时<br>' +
                         '最大耗时: %{customdata[2]:.1f}小时<br>' +
                         '<extra></extra>',
            customdata=df_top[['Count', 'Min_Hours', 'Max_Hours']].values
        )
    ])
    
    # 动态调整图表高度，确保所有数据都能显示
    chart_height = max(600, len(df_top) * 25)
    
    fig.update_layout(
        title=f'Phase Transition 平均耗时排名 (共{len(df_top)}个)',
        xaxis_title='平均耗时 (天)',
        yaxis_title='Phase Transition',
        height=chart_height,
        margin=dict(l=300, r=50, t=60, b=50),
        template='plotly_white',
        showlegend=False
    )
    
    return fig

def load_defect_info_lr():
    """从defect数据文件加载ticket名称和tester信息"""
    defect_info = {}

    def _normalize_tester(tester_value):
        tester_text = extract_filter_value(tester_value)
        if tester_text.lower() in {'', 'unknown', 'unknown tester', 'none', 'nan'}:
            return 'Unknown'
        return tester_text

    try:
        if isinstance(df, pd.DataFrame) and not df.empty and 'id' in df.columns:
            required_cols = [col for col in ['id', 'name', 'tester', 'detected_by', 'author'] if col in df.columns]
            source_df = df[required_cols].copy()
            for _, row in source_df.iterrows():
                ticket_id = extract_filter_value(row.get('id'))
                if not ticket_id:
                    continue
                ticket_name = extract_filter_value(row.get('name')) or f'Ticket {ticket_id}'
                tester = _normalize_tester(row.get('tester'))
                if tester == 'Unknown':
                    tester = _normalize_tester(row.get('detected_by'))
                if tester == 'Unknown':
                    tester = _normalize_tester(row.get('author'))
                defect_info[ticket_id] = {'name': ticket_name[:100], 'tester': tester}
            if defect_info:
                return defect_info
    except Exception as e:
        print(f"从主数据构建Long Runner ticket信息失败: {e}")
    
    try:
        defect_files = [
            os.path.join('defect', file_name)
            for file_name in os.listdir('defect')
            if file_name.endswith('_defect.json')
        ]
    except Exception:
        defect_files = []

    for defect_file in defect_files:
        if not os.path.exists(defect_file):
            continue
        try:
            with open(defect_file, 'r', encoding='utf-8') as f:
                loaded_json = json.load(f)

            if isinstance(loaded_json, dict) and 'data' in loaded_json and isinstance(loaded_json['data'], list):
                defects = loaded_json['data']
            elif isinstance(loaded_json, list):
                defects = loaded_json
            else:
                continue

            for defect in defects:
                ticket_id = str(defect.get('id', '')).strip()
                if not ticket_id:
                    continue
                ticket_name = extract_filter_value(defect.get('name')) or f'Ticket {ticket_id}'
                tester = _normalize_tester(defect.get('tester'))
                if tester == 'Unknown':
                    tester = _normalize_tester(defect.get('detected_by'))
                if tester == 'Unknown':
                    detected_by = defect.get('detected_by', {})
                    if isinstance(detected_by, dict):
                        tester = _normalize_tester(detected_by.get('full_name') or detected_by.get('name'))
                defect_info[ticket_id] = {'name': ticket_name[:100], 'tester': tester}
        except Exception as e:
            print(f"加载defect信息时出错 ({defect_file}): {e}")

    return defect_info

def bulk_analyze_phases_live_lr(history_folder: str = 'history', ticket_ids=None) -> dict:
    """实时批量分析所有ticket的phase duration"""
    print("开始从真实数据源分析phase durations...")
    
    # 加载defect信息（名称和tester）
    defect_info = load_defect_info_lr()
    
    # 获取所有ticket IDs
    if ticket_ids is None:
        ticket_ids = get_all_ticket_ids(history_folder)
    else:
        ticket_ids = [str(tid) for tid in ticket_ids if str(tid).strip()]
    
    all_durations = defaultdict(list)  # phase_name -> [duration1, duration2, ...]
    ticket_details = defaultdict(list)  # phase_name -> [ticket_detail1, ticket_detail2, ...]
    successful_analyses = 0
    failed_analyses = 0
    
    for i, ticket_id in enumerate(ticket_ids):
        if i % 500 == 0:
            print(f"进度: {i+1}/{len(ticket_ids)}")
        
        result = analyze_ticket_phases(ticket_id, history_folder)
        
        if 'error' in result:
            failed_analyses += 1
            continue
            
        successful_analyses += 1
        
        # 收集每个phase的duration数据和详细信息
        for duration in result.get('phase_durations', []):
            phase_transition = f"{duration['from_phase']} → {duration['to_phase']}"
            all_durations[phase_transition].append(duration['duration_hours'])
            
            # 获取真实的ticket信息
            ticket_info = defect_info.get(ticket_id, {'name': f"Ticket {ticket_id}", 'tester': 'Unknown'})
            ticket_name = ticket_info['name']
            tester = ticket_info['tester']
            
            # 保存详细的ticket信息
            ticket_details[phase_transition].append({
                'ticket_id': ticket_id,
                'ticket_name': ticket_name,
                'duration_hours': duration['duration_hours'],
                'duration_days': round(duration['duration_hours'] / 24, 2),
                'start_time': duration['start_time'],
                'end_time': duration['end_time'],
                'changed_by': duration['changed_by'],
                'tester': tester,
                'from_phase': duration['from_phase'],
                'to_phase': duration['to_phase']
            })
    
    print(f"分析完成! 成功: {successful_analyses}, 失败: {failed_analyses}")
    
    return {
        'phase_durations': dict(all_durations),
        'ticket_details': dict(ticket_details),
        'successful_count': successful_analyses,
        'failed_count': failed_analyses
    }

def calculate_phase_statistics_live_lr(phase_durations: dict) -> pd.DataFrame:
    """从实时数据计算phase transition统计信息"""
    statistics_data = []
    
    for phase_transition, durations in phase_durations.items():
        if durations:
            avg_hours = sum(durations) / len(durations)
            stats = {
                'Phase_Transition': phase_transition,
                'Count': len(durations),
                'Avg_Hours': round(avg_hours, 2),
                'Avg_Days': round(avg_hours / 24, 2),
                'Min_Hours': round(min(durations), 2),
                'Max_Hours': round(max(durations), 2),
                'Median_Hours': round(sorted(durations)[len(durations)//2], 2),
                'Phase_From': phase_transition.split(' → ')[0],
                'Phase_To': phase_transition.split(' → ')[1],
                'Total_Hours': round(avg_hours * len(durations), 2)
            }
            statistics_data.append(stats)
    
    expected_cols = [
        'Phase_Transition', 'Count', 'Avg_Hours', 'Avg_Days',
        'Min_Hours', 'Max_Hours', 'Median_Hours', 'Phase_From', 'Phase_To', 'Total_Hours'
    ]
    if not statistics_data:
        return pd.DataFrame(columns=expected_cols)

    df = pd.DataFrame(statistics_data)
    if 'Avg_Days' not in df.columns:
        return pd.DataFrame(columns=expected_cols)
    return df.sort_values('Avg_Days', ascending=False)

# 合并的数据加载和筛选回调
@app.callback(
    [Output('phase-data-status', 'children'),
     Output('phase-duration-bar-chart-lr', 'figure'),
     Output('phase-stats-table-lr', 'data')],
    [Input('phase-min-count-slider', 'value'),
     Input('phase-type-dropdown', 'value'),
     Input('long-runner-year-dropdown', 'value'),
     Input('current-nav-item', 'data')],  # 添加导航状态监听
    prevent_initial_call=False  # 允许初始调用
)
def update_phase_data_and_charts(min_count, phase_type, selected_years, current_nav):
    """处理数据加载和筛选更新"""
    global global_phase_df, global_phase_ticket_details
    
    ctx = callback_context
    
    # 如果不是Long Runner Analysis页面，返回空
    if current_nav != 'tab-defect-long-runner':
        return html.Div(), go.Figure(), []
    
    # 如果没有触发或者是首次加载Long Runner Analysis页面
    if not ctx.triggered:
        trigger_id = 'auto-load'  # 自动加载
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 如果是首次打开页面或者切换到该页面且还没有数据，需要加载数据
    if global_phase_df.empty or trigger_id == 'current-nav-item' or trigger_id == 'auto-load':
        # 需要重新加载数据
        try:
            all_years = set(extract_year_series(df).dropna().astype(int).tolist()) if not df.empty else set()
            if selected_years is None:
                effective_years = [2026] if 2026 in all_years else []
            else:
                effective_years = selected_years

            scoped_df = filter_dataframe(df, years=effective_years)
            scoped_ticket_ids = scoped_df['id'].apply(lambda x: str(x).strip()).replace('', pd.NA).dropna().unique().tolist() if 'id' in scoped_df.columns else []
            cache_key = None
            bulk_results = None
            if CACHE_MANAGER_AVAILABLE and default_cache_manager:
                cache_years = sorted([int(y) for y in effective_years]) if effective_years else []
                cache_key = f"long_runner_phase_data_v2_{hashlib.md5(json.dumps({'years': cache_years}, sort_keys=True).encode('utf-8')).hexdigest()}"
                bulk_results = default_cache_manager.get(cache_key)
            if bulk_results is None:
                bulk_results = bulk_analyze_phases_live_lr(ticket_ids=scoped_ticket_ids)
                if CACHE_MANAGER_AVAILABLE and default_cache_manager and cache_key:
                    default_cache_manager.set(cache_key, bulk_results, timeout=LONG_RUNNER_CACHE_TTL_SECONDS)
            
            # 计算统计信息
            global_phase_df = calculate_phase_statistics_live_lr(bulk_results['phase_durations'])
            global_phase_ticket_details = bulk_results['ticket_details']
            
            if global_phase_df.empty:
                status_msg = html.Div([
                    html.I(className="fas fa-exclamation-triangle", style={'color': '#e74c3c', 'marginRight': '8px'}),
                    html.Span("没有找到数据", style={'color': '#e74c3c', 'fontSize': '14px'})
                ])
                return status_msg, go.Figure(), []
        
        except Exception as e:
            print(f"加载数据时出错: {e}")
            status_msg = html.Div([
                html.I(className="fas fa-exclamation-triangle", style={'color': '#e74c3c', 'marginRight': '8px'}),
                html.Span(f"加载失败: {str(e)}", style={'color': '#e74c3c', 'fontSize': '14px'})
            ])
            return status_msg, go.Figure(), []
        
        # 设置状态消息
        status_msg = html.Div([
            html.I(className="fas fa-check-circle", style={'color': '#27ae60', 'marginRight': '8px'}),
            html.Span(f"成功加载 {len(global_phase_df)} 个Phase Transitions", 
                     style={'color': '#27ae60', 'fontSize': '14px'})
        ])
    else:
        # 筛选条件变化，保持原有的status message
        if global_phase_df.empty:
            status_msg = html.Div([
                html.I(className="fas fa-info-circle", style={'color': '#3498db', 'marginRight': '8px'}),
                html.Span("请先点击'加载/刷新数据'按钮", style={'color': '#3498db', 'fontSize': '14px'})
            ])
            return status_msg, go.Figure(), []
        else:
            status_msg = html.Div([
                html.I(className="fas fa-check-circle", style={'color': '#27ae60', 'marginRight': '8px'}),
                html.Span(f"已加载 {len(global_phase_df)} 个Phase Transitions", 
                         style={'color': '#27ae60', 'fontSize': '14px'})
            ])
    
    # 应用筛选条件
    if not global_phase_df.empty:
        df_filtered = global_phase_df[global_phase_df['Count'] >= min_count].copy()
        
        # 根据phase类型筛选
        if phase_type == 'normal':
            # 正常流程（不包含回退和结束）
            df_filtered = df_filtered[
                ~df_filtered['Phase_Transition'].str.contains('09-Concluded without action|→ 01-New|→ 02-In Pre-Analysis')
            ]
        elif phase_type == 'rollback':
            # 回退流程
            df_filtered = df_filtered[
                df_filtered['Phase_Transition'].str.contains('→ 01-New|→ 02-In Pre-Analysis') &
                ~df_filtered['Phase_Transition'].str.contains('09-Concluded without action')
            ]
        elif phase_type == 'conclusion':
            # 结束流程
            df_filtered = df_filtered[
                df_filtered['Phase_Transition'].str.contains('09-Concluded without action|06-Concluded')
            ]
        
        # 更新图表
        bar_chart = create_phase_duration_bar_chart_lr(df_filtered)
        
        # 更新表格数据
        table_data = df_filtered.sort_values('Avg_Days', ascending=False).to_dict('records')
        
        return status_msg, bar_chart, table_data
    else:
        return status_msg, go.Figure(), []

# 柱状图点击事件回调 - 打开模态框
@app.callback(
    [Output('ticket-details-modal-lr', 'style'),
     Output('modal-title-lr', 'children'),
     Output('modal-phase-info-lr', 'children'),
     Output('modal-ticket-details-table-lr', 'data'),
     Output('phase-click-info-lr', 'children')],
    Input('phase-duration-bar-chart-lr', 'clickData'),
    prevent_initial_call=True
)
def display_phase_click_data(clickData):
    if not clickData:
        return {'display': 'none'}, "", "", [], ""
    
    global global_phase_ticket_details
    
    try:
        # 获取点击的phase transition
        clicked_phase = clickData['points'][0]['y']
        
        # 从全局数据中获取该phase的详细信息
        if clicked_phase in global_phase_ticket_details:
            tickets = global_phase_ticket_details[clicked_phase]
            
            # 格式化时间字符串
            for ticket in tickets:
                if ticket['start_time']:
                    try:
                        start_time = datetime.fromisoformat(ticket['start_time'].replace('Z', '+00:00'))
                        ticket['start_time'] = start_time.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
                
                if ticket['end_time']:
                    try:
                        end_time = datetime.fromisoformat(ticket['end_time'].replace('Z', '+00:00'))
                        ticket['end_time'] = end_time.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
            
            # 按耗时排序
            tickets_sorted = sorted(tickets, key=lambda x: x['duration_hours'], reverse=True)
            
            # 计算统计信息
            avg_hours = sum(t['duration_hours'] for t in tickets) / len(tickets)
            max_hours = max(t['duration_hours'] for t in tickets)
            min_hours = min(t['duration_hours'] for t in tickets)
            
            # 模态框标题
            modal_title = f"Phase Transition: {clicked_phase}"
            
            # 模态框内容信息
            modal_info = html.Div([
                html.Div([
                    html.Div([
                        html.H5("总计", style={'margin': '0', 'color': '#2c3e50'}),
                        html.P(f"{len(tickets)} 个tickets", style={'margin': '0', 'fontSize': '16px', 'fontWeight': 'bold'})
                    ], style={'textAlign': 'center', 'padding': '10px', 'backgroundColor': '#e8f4f8', 'borderRadius': '5px', 'margin': '5px'}),
                    
                    html.Div([
                        html.H5("平均耗时", style={'margin': '0', 'color': '#2c3e50'}),
                        html.P(f"{avg_hours:.1f} 小时", style={'margin': '0', 'fontSize': '16px', 'fontWeight': 'bold'})
                    ], style={'textAlign': 'center', 'padding': '10px', 'backgroundColor': '#fff2e6', 'borderRadius': '5px', 'margin': '5px'}),
                    
                    html.Div([
                        html.H5("最大耗时", style={'margin': '0', 'color': '#2c3e50'}),
                        html.P(f"{max_hours:.1f} 小时", style={'margin': '0', 'fontSize': '16px', 'fontWeight': 'bold'})
                    ], style={'textAlign': 'center', 'padding': '10px', 'backgroundColor': '#ffe6e6', 'borderRadius': '5px', 'margin': '5px'}),
                    
                    html.Div([
                        html.H5("最小耗时", style={'margin': '0', 'color': '#2c3e50'}),
                        html.P(f"{min_hours:.1f} 小时", style={'margin': '0', 'fontSize': '16px', 'fontWeight': 'bold'})
                    ], style={'textAlign': 'center', 'padding': '10px', 'backgroundColor': '#e6ffe6', 'borderRadius': '5px', 'margin': '5px'})
                ], style={'display': 'flex', 'justifyContent': 'space-around', 'marginBottom': '20px'}),
                
                html.P(f"以下显示所有 {len(tickets)} 个tickets的详细信息，按耗时从高到低排序：", 
                       style={'fontSize': '14px', 'color': '#666', 'fontStyle': 'italic'})
            ])
            
            # 点击提示信息
            click_info = html.Div([
                html.I(className="fas fa-info-circle", style={'color': '#3498db', 'marginRight': '8px'}),
                html.Span(f"点击了: {clicked_phase} (共{len(tickets)}个tickets，已在弹窗中显示)", 
                         style={'fontSize': '14px', 'color': '#2c3e50'})
            ], style={'padding': '10px', 'backgroundColor': '#e8f4f8', 'borderRadius': '5px'})
            
            # 显示模态框
            modal_style = {
                'position': 'fixed',
                'top': '0',
                'left': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0, 0, 0, 0.5)',
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'zIndex': '9999'
            }
            
            return modal_style, modal_title, modal_info, tickets_sorted, click_info
        else:
            click_info = html.Div([
                html.I(className="fas fa-exclamation-triangle", style={'color': '#e74c3c', 'marginRight': '8px'}),
                html.Span("未找到该phase的详细数据", style={'color': '#e74c3c'})
            ])
            return {'display': 'none'}, "", "", [], click_info
    
    except Exception as e:
        print(f"处理点击事件时出错: {e}")
        click_info = html.Div([
            html.I(className="fas fa-exclamation-triangle", style={'color': '#e74c3c', 'marginRight': '8px'}),
            html.Span("处理点击事件时出错", style={'color': '#e74c3c'})
        ])
        return {'display': 'none'}, "", "", [], click_info

# 关闭模态框回调
@app.callback(
    Output('ticket-details-modal-lr', 'style', allow_duplicate=True),
    [Input('close-modal-lr', 'n_clicks'),
     Input('ticket-details-modal-lr-overlay', 'n_clicks')],
    prevent_initial_call=True
)
def close_modal(close_clicks, overlay_clicks):
    from dash import callback_context
    
    ctx = callback_context
    if ctx.triggered:
        return {'display': 'none'}
    return {'display': 'none'}

# 测试模态框按钮回调

# 为AI聊天功能更新数据存储
@app.callback(
    Output('filtered-data-store', 'data'),
    [Input('year-dropdown', 'value'),
     Input('project-dropdown', 'value'),
     Input('date-range-picker-main', 'start_date'),
     Input('date-range-picker-main', 'end_date'),
     Input('aida-dropdown', 'value'),
     Input('status-dropdown', 'value'),
     Input('pu-dropdown', 'value'),
     Input('tester-dropdown-main', 'value'),
     Input('fv-dropdown', 'value'),
     Input('ecu-dropdown', 'value'),
     Input('severe-matrix-dropdown', 'value'),
     Input('severe-classification-dropdown', 'value')],
    prevent_initial_call=True
)
def update_filtered_data_store(years, projects, start_date, end_date, aidas, statuses, pus, testers, fvs, ecus, severe_matrices, severe_classifications):
    """更新筛选后的数据存储，供AI聊天功能使用"""
    try:
        return {
            "version": 2,
            "filters": {
                "years": years or [],
                "projects": projects or [],
                "start_date": start_date,
                "end_date": end_date,
                "aidas": aidas or [],
                "statuses": statuses or [],
                "pus": pus or [],
                "testers": testers or [],
                "fvs": fvs or [],
                "ecus": ecus or [],
                "severe_matrices": severe_matrices or [],
                "severe_classifications": severe_classifications or []
            },
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error updating filtered data store: {e}")
        return None

# 注册AI聊天回调函数
if AI_CHAT_AVAILABLE:
    # 定义数据处理函数，将filtered-data-store转换为DataFrame
    def process_filtered_data(filtered_data, question: str = ""):
        """将filtered-data-store的数据转换为DataFrame供Agent使用"""
        try:
            if not filtered_data:
                return {"defects": pd.DataFrame(), "tests": pd.DataFrame()}

            q = (question or "").lower()
            wants_filtered_data = any(k in q for k in ["按筛选", "按过滤", "当前筛选", "当前过滤", "按当前", "仅筛选", "只看筛选", "filtered"])
            wants_full_data = (not wants_filtered_data) or any(k in q for k in [
                "全量", "完整", "不要抽样", "不要采样", "不采样", "不抽样",
                "不要筛选", "不筛选", "不限制", "all", "full", "exact", "accurate", "全面", "准确"
            ]) or any(k in q for k in ["团队", "team", "tester", "谁发现", "发现人", "报告人", "提交人", "fvp", "matrix", "矩阵", "分布", "占比"])

            if wants_full_data and 'df' in globals() and isinstance(df, pd.DataFrame):
                tests_full = pd.DataFrame()
                if 'test_df' in globals() and isinstance(test_df, pd.DataFrame):
                    tests_full = test_df
                return {"defects": df, "tests": tests_full}

            defects_df = pd.DataFrame()

            if isinstance(filtered_data, str):
                defects_df = pd.read_json(StringIO(filtered_data), orient='split')
            elif isinstance(filtered_data, dict):
                if 'filters' in filtered_data:
                    filters = filtered_data.get('filters') or {}
                    try:
                        defects_df = filter_dataframe(
                            df=df,
                            years=filters.get('years') or [],
                            projects=filters.get('projects') or [],
                            start_date=filters.get('start_date'),
                            end_date=filters.get('end_date'),
                            aidas=filters.get('aidas') or [],
                            statuses=filters.get('statuses') or [],
                            pus=filters.get('pus') or [],
                            testers=filters.get('testers') or [],
                            fvs=filters.get('fvs') or [],
                            ecus=filters.get('ecus') or [],
                            lead_models=[],
                            fvps=[]
                        )
                    except Exception:
                        defects_df = df
                elif 'data' in filtered_data:
                    defects_df = pd.read_json(StringIO(filtered_data['data']), orient='split')
                else:
                    defects_df = pd.DataFrame(filtered_data)
            elif isinstance(filtered_data, pd.DataFrame):
                defects_df = filtered_data

            tests_subset = pd.DataFrame()
            if 'test_df' in globals() and isinstance(test_df, pd.DataFrame):
                tests_subset = test_df

                projects = []
                if isinstance(defects_df, pd.DataFrame) and not defects_df.empty:
                    if 'tproject' in defects_df.columns:
                        projects = defects_df['tproject'].dropna().astype(str).unique().tolist()
                    elif 'project' in defects_df.columns:
                        projects = defects_df['project'].dropna().astype(str).unique().tolist()

                if projects and 'project' in tests_subset.columns:
                    tests_subset = tests_subset[tests_subset['project'].isin(projects)]

                if isinstance(defects_df, pd.DataFrame) and not defects_df.empty:
                    if 'tcreationtime' in defects_df.columns:
                        tmin = pd.to_datetime(defects_df['tcreationtime'], errors='coerce').min()
                        tmax = pd.to_datetime(defects_df['tcreationtime'], errors='coerce').max()
                    elif 'creation_time' in defects_df.columns:
                        tmin = pd.to_datetime(defects_df['creation_time'], errors='coerce').min()
                        tmax = pd.to_datetime(defects_df['creation_time'], errors='coerce').max()
                    else:
                        tmin = tmax = None

                    if tmin is not None and pd.notna(tmin) and tmax is not None and pd.notna(tmax):
                        time_col = 'finished_udf_dt' if 'finished_udf_dt' in tests_subset.columns else 'finished_udf' if 'finished_udf' in tests_subset.columns else None
                        if time_col:
                            tseries = pd.to_datetime(tests_subset[time_col], errors='coerce')
                            tests_subset = tests_subset[(tseries >= tmin) & (tseries <= tmax)]

            return {"defects": defects_df if isinstance(defects_df, pd.DataFrame) else pd.DataFrame(), "tests": tests_subset}
        except Exception as e:
            print(f"处理filtered数据时出错: {e}")
            return {"defects": pd.DataFrame(), "tests": pd.DataFrame()}

    # 根据是否为增强版使用不同的注册方式
    if AI_CHAT_ENHANCED:
        # 使用增强版注册（支持Agent）
        ai_chat_manager.register_enhanced_callbacks(
            app=app,
            chat_id_prefix='defect-explore-chat',
            data_store_id='filtered-data-store',
            data_processor_func=process_filtered_data
        )
        ai_chat_manager.register_enhanced_callbacks(
            app=app,
            chat_id_prefix='defect-explore-chat-page',
            data_store_id='filtered-data-store',
            data_processor_func=process_filtered_data
        )
    else:
        # 使用基础版注册（兼容模式）
        ai_chat_manager.register_enhanced_chat_callbacks(
            app=app,
            chat_id_prefix='defect-explore-chat',
            data_store_id='filtered-data-store',
            dashboard_type='defect',
            data_processor_func=process_filtered_data,
            chat_only_mode=False  # 传递本地数据
        )
        ai_chat_manager.register_enhanced_chat_callbacks(
            app=app,
            chat_id_prefix='defect-explore-chat-page',
            data_store_id='filtered-data-store',
            dashboard_type='defect',
            data_processor_func=process_filtered_data,
            chat_only_mode=False
        )

# 添加自定义HTML和CSS样式
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            /* 导航栏样式 */
            .nav-item:hover {
                background-color: #34495e !important;
            }
            
            /* 确保聊天框在全屏模式下正确显示 */
            .ai-chat-fullscreen {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100vw !important;
                height: 100vh !important;
                z-index: 9999 !important;
                background-color: white !important;
                overflow-y: auto !important;
            }
            
            .nav-toggle-btn:hover {
                background-color: #218838 !important;
                transform: scale(1.05);
            }
            
            /* 边缘条样式 */
            #nav-edge-bar:hover {
                background-color: #34495e !important;
            }
            
            #nav-edge-toggle-btn:hover,
            #nav-edge-toggle-btn-2:hover {
                background-color: rgba(255,255,255,0.2) !important;
            }
            
            /* 导航栏滚动条样式 */
            .sidebar-nav::-webkit-scrollbar {
                width: 6px;
            }
            
            .sidebar-nav::-webkit-scrollbar-track {
                background: #34495e;
            }
            
            .sidebar-nav::-webkit-scrollbar-thumb {
                background: #3498db;
                border-radius: 3px;
            }
            
            .sidebar-nav::-webkit-scrollbar-thumb:hover {
                background: #2980b9;
            }
            
            /* 响应式设计 */
            @media (max-width: 768px) {
                .sidebar-nav {
                    width: 250px !important;
                    left: -250px !important;
                }
                
                .main-content-wrapper.nav-open {
                    margin-left: 0px !important;
                }
            }
            
            /* 主题切换按钮位置调整 */
            .global-theme-switcher {
                position: relative;
                z-index: 500;
            }
            
            /* 优化移动端体验 */
            @media (max-width: 480px) {
                .nav-toggle-btn {
                    top: 10px !important;
                    left: 10px !important;
                    padding: 10px !important;
                }
                
                .sidebar-nav {
                    width: 90vw !important;
                    left: -90vw !important;
                }
            }
            
            /* 确保内容不被导航按钮遮挡 */
            .main-content-wrapper {
                padding-top: 10px;
            }
            
            /* 防止内容溢出 */
            html, body {
                overflow-x: hidden;
            }
            
            /* AI助手按钮悬停效果 */
            #ai-chat-toggle-btn:hover {
                transform: scale(1.05);
                box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
                background-color: rgba(240, 240, 240, 0.8) !important;
            }
            
            /* Monica头像圆形效果 */
            #ai-chat-toggle-btn img {
                transition: transform 0.3s ease;
            }
            
            #ai-chat-toggle-btn:hover img {
                transform: scale(1.1);
            }
            
            /* AI模态框样式 */
            .ai-modal-content {
                animation: modalFadeIn 0.3s ease-in-out;
            }
            
            @keyframes modalFadeIn {
                from {
                    opacity: 0;
                    transform: translateY(-20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            /* 添加AI聊天界面的CSS样式 */
            ''' + (get_chat_css_styles() if AI_CHAT_AVAILABLE else "") + '''
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


# Test Status Analysis数据存储回调 - 管理数据缓存
@app.callback(
    Output('test-status-store-main', 'data'),
    [Input('current-nav-item', 'data')],
    [State('test-status-store-main', 'data')],
    prevent_initial_call=False
)
def update_test_status_data_store(current_nav, stored_data):
    """管理Test Status Analysis页面的数据存储，只在首次访问或数据为空时加载"""
    # 只在切换到test-status标签页时检查数据
    if current_nav != 'tab-test-status':
        raise PreventUpdate
    
    # 如果已有数据且不为空，直接返回
    if stored_data and stored_data.get('test_data') and len(stored_data['test_data']) > 0:
        return stored_data
    
    try:
        # 加载测试数据 - 使用缓存版本提升性能
        test_data = _cached_load_test_data()
        if test_data.empty:
            return {'test_data': [], 'loaded_at': datetime.now().isoformat()}
        
        # 将DataFrame转换为字典格式存储
        return {
            'test_data': test_data.to_dict('records'),
            'loaded_at': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"加载测试数据失败: {e}")
        return {'test_data': [], 'loaded_at': datetime.now().isoformat(), 'error': str(e)}

# Test Status Analysis回调函数 - 包含Phase 1新图表
@app.callback(
    [Output('ts-status-distribution-pie', 'figure'),      # Phase 1: 状态分布饼图（移到最上方）
     Output('ts-pass-rate-trend-chart', 'figure'),        # Phase 1: 测试通过率趋势图
     Output('ts-aida-wordcloud', 'figure'),        # Phase 1: 测试热点AIDA词云图  
     Output('test-status-fv-chart-main', 'figure'),
     Output('test-release-trend-chart-main', 'figure'),
     Output('test-project-count-chart-main', 'figure'),
     Output('ts-kpi-indicators', 'children')],             # KPI指标
    [Input('current-nav-item', 'data'),
     Input('ts-year-dropdown', 'value'),
     Input('ts-project-dropdown', 'value'),
     Input('ts-testweek-dropdown', 'value'),
     Input('ts-fv-dropdown', 'value'),
     Input('ts-status-dropdown', 'value'),
     Input('ts-aida-dropdown', 'value'),
     Input('test-status-store-main', 'data')],            # 使用存储的数据
    prevent_initial_call=False
)
def update_test_status_charts(current_nav, years, projects, test_weeks, fvs, statuses, aidas, stored_data):
    """更新Test Status Analysis页面的图表"""
    from dash import callback_context
    
    # 只在切换到test-status标签页时更新
    if current_nav != 'tab-test-status':
        raise PreventUpdate
    
    # 生成缓存键（基于筛选条件）
    cache_key = f"test_status_charts_{hash(str([years, projects, test_weeks, fvs, statuses, aidas]))}"
    
    # 尝试从统一缓存获取图表结果
    if CACHE_MANAGER_AVAILABLE and default_cache_manager:
        cached_charts = default_cache_manager.get(cache_key)
        if cached_charts is not None:
            print(f"从缓存加载测试状态图表: {cache_key[:20]}...")
            return cached_charts
    
    try:
        # 从存储中获取测试数据
        if not stored_data or not stored_data.get('test_data'):
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="暂无测试数据", x=0.5, y=0.5, showarrow=False)
            empty_fig.update_layout(height=400)
            empty_kpi = html.Div("暂无测试数据", style={'textAlign': 'center', 'color': '#666'})
            empty_result = (empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_kpi)
            
            # 缓存空结果（缓存5分钟）
            if CACHE_MANAGER_AVAILABLE and default_cache_manager:
                default_cache_manager.set(cache_key, empty_result, timeout=300)
            
            return empty_result
        
        # 将存储的数据转换回DataFrame
        test_data = pd.DataFrame(stored_data['test_data'])
        if test_data.empty:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="暂无测试数据", x=0.5, y=0.5, showarrow=False)
            empty_fig.update_layout(height=400)
            empty_kpi = html.Div("暂无测试数据", style={'textAlign': 'center', 'color': '#666'})
            return empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_kpi
        
        # 应用筛选器 - 先清理数据中的字典类型
        filtered_data = test_data.copy()
        
        # 清理数据：提取字典中的有用信息
        print(f"Debug: 原始数据shape: {filtered_data.shape}")
        
        def extract_value_from_dict(x):
            """从字典中提取有用的值"""
            if isinstance(x, dict):
                # 优先提取 'name' 字段
                if 'name' in x:
                    return x['name']
                # 如果没有 'name'，尝试提取 'value' 字段
                elif 'value' in x:
                    return x['value']
                # 如果都没有，返回字典的字符串表示
                else:
                    return str(x)
            return x
        
        # 状态映射逻辑已集成到筛选和图表创建中
        
        for col in filtered_data.columns:
            if filtered_data[col].dtype == 'object':
                # 检查是否有字典类型
                dict_count = filtered_data[col].apply(lambda x: isinstance(x, dict)).sum()
                if dict_count > 0:
                    print(f"Debug: 列 {col} 包含 {dict_count} 个字典类型值")
                    # 提取字典中的有用信息
                    filtered_data[col] = filtered_data[col].apply(extract_value_from_dict)

        year_series = extract_year_series(filtered_data, year_col='year', week_col='test_week')

        # 年份筛选
        if years and len(years) > 0 and not year_series.dropna().empty:
            filtered_data = filtered_data[
                year_series.astype('Int64').isin([int(y) for y in years])
            ]
        
        # 注意：状态映射现在在筛选和图表创建时进行，避免重复处理
        
        # 项目筛选
        if projects and len(projects) > 0 and 'project' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['project'].astype(str).isin([str(p) for p in projects])]
        
        # 测试周筛选
        if test_weeks and len(test_weeks) > 0 and 'test_week' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['test_week'].astype(str).isin([str(w) for w in test_weeks])]
        
        # FV筛选
        if fvs and len(fvs) > 0 and 'all' not in fvs and 'fv' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['fv'].astype(str).isin([str(f) for f in fvs])]
        
        # 状态筛选 - 优先使用native_status
        status_col = None
        if 'native_status' in filtered_data.columns:
            status_col = 'native_status'
        elif 'status' in filtered_data.columns:
            status_col = 'status'
        elif 'run_status' in filtered_data.columns:
            status_col = 'run_status'
        elif 'execution_status' in filtered_data.columns:
            status_col = 'execution_status'
        
        if statuses and len(statuses) > 0 and status_col:
            # 处理状态筛选 - 如果是字典格式，提取name字段并应用映射
            status_data = filtered_data[status_col].copy()
            if status_data.dtype == 'object':
                status_data = status_data.apply(lambda x: x.get('name', str(x)) if isinstance(x, dict) else str(x))
            
            # 状态映射
            status_mapping = {
                'passed': 'Passed',
                'failed': 'Failed', 
                'blocked': 'Blocked',
                'planned': 'Planned',
                'not_completed': 'In Progress'
            }
            
            # 应用状态映射
            mapped_status = status_data.map(status_mapping).fillna(status_data)
            
            # 筛选数据
            filtered_data = filtered_data[mapped_status.isin([str(s) for s in statuses])]
        
        # AIDA筛选
        if aidas and len(aidas) > 0 and 'top_aida' in filtered_data.columns:
            filtered_data = filtered_data[filtered_data['top_aida'].astype(str).isin([str(a) for a in aidas])]
        
        if filtered_data.empty:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="筛选后无数据", x=0.5, y=0.5, showarrow=False)
            empty_fig.update_layout(height=400)
            empty_kpi = html.Div("暂无测试数据", style={'textAlign': 'center', 'color': '#666'})
            return empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_kpi
        
        # 创建FV vs 测试用例数量的堆叠柱状图
        def create_fv_stacked_chart():
            try:
                # 检查FV列
                if 'fv' not in filtered_data.columns:
                    fig = go.Figure()
                    fig.add_annotation(text="缺少FV列", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="FV vs 测试用例数量", height=400)
                    return fig
                
                # 找到状态列 - 优先使用native_status
                status_col = None
                if 'native_status' in filtered_data.columns:
                    status_col = 'native_status'
                elif 'status' in filtered_data.columns:
                    status_col = 'status'
                elif 'run_status' in filtered_data.columns:
                    status_col = 'run_status'
                elif 'execution_status' in filtered_data.columns:
                    status_col = 'execution_status'
                
                if not status_col:
                    fig = go.Figure()
                    fig.add_annotation(text="缺少状态列", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="FV vs 测试用例数量", height=400)
                    return fig
                
                # 找到计数列
                count_col = None
                if 'test_case_id' in filtered_data.columns:
                    count_col = 'test_case_id'
                elif 'id' in filtered_data.columns:
                    count_col = 'id'
                else:
                    # 如果没有专门的计数列，使用行数统计
                    grouped = filtered_data.groupby(['fv', status_col]).size().reset_index(name='count')
                    
                    # 定义状态颜色映射（根据图片中的颜色方案）
                    status_colors = {
                        'Passed': '#2ca02c',     # 绿色
                        'Failed': '#d62728',     # 红色  
                        'Blocked': '#ff7f0e',    # 橙色
                        'In Progress': '#1f77b4', # 蓝色
                        'Planned': '#17becf'     # 青色
                    }
                    
                    fig = px.bar(
                        grouped, 
                        x='fv', 
                        y='count', 
                        color=status_col,
                        title="FV vs 测试用例MR数量 (按执行状态分组)",
                        labels={'count': '测试用例MR数量', 'fv': 'FV', status_col: '执行状态'},
                        barmode='stack',
                        color_discrete_map=status_colors
                    )
                    
                    # 添加总数标签在柱状图顶部
                    fv_totals = grouped.groupby('fv')['count'].sum()
                    for i, fv in enumerate(fv_totals.index):
                        fig.add_annotation(
                            x=fv,
                            y=fv_totals[fv],
                            text=str(fv_totals[fv]),
                            showarrow=False,
                            yshift=10,
                            font=dict(size=10, color='black')
                        )
                    
                    fig.update_layout(
                        height=400,
                        xaxis_title="FV",
                        yaxis_title="测试用例MR数量",
                        showlegend=True,
                        xaxis={'tickangle': -45}
                    )
                    
                    return apply_chart_style(fig, "FV vs 测试用例MR数量", height=400)
                
                # 创建数据副本并确保计数列不包含字典类型数据
                data_for_grouping = filtered_data.copy()
                if count_col in data_for_grouping.columns:
                    # 处理可能的字典类型数据
                    data_for_grouping[count_col] = data_for_grouping[count_col].apply(
                        lambda x: str(x) if isinstance(x, dict) else x
                    )
                
                # 处理状态数据 - 如果是字典格式，提取name字段并应用映射
                if status_col in data_for_grouping.columns:
                    status_data = data_for_grouping[status_col].copy()
                    if status_data.dtype == 'object':
                        status_data = status_data.apply(lambda x: x.get('name', str(x)) if isinstance(x, dict) else str(x))
                    
                    # 状态映射
                    status_mapping = {
                        'passed': 'Passed',
                        'failed': 'Failed', 
                        'blocked': 'Blocked',
                        'planned': 'Planned',
                        'not_completed': 'In Progress'
                    }
                    
                    # 应用状态映射并更新数据
                    data_for_grouping[status_col] = status_data.map(status_mapping).fillna(status_data)
                
                # 按FV和状态分组统计，使用唯一计数
                grouped = data_for_grouping.groupby(['fv', status_col], as_index=False)[count_col].nunique().rename(columns={count_col: 'count'})
                
                if grouped.empty:
                    fig = go.Figure()
                    fig.add_annotation(text="分组后无数据", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="FV vs 测试用例MR数量", height=400)
                    return fig
                
                # 按FV的总数量排序
                fv_totals = grouped.groupby('fv')['count'].sum().sort_values(ascending=False)
                fv_order = fv_totals.index.tolist()
                
                # 定义状态颜色映射
                status_colors = {
                    'Passed': '#2ca02c',     # 绿色
                    'Failed': '#d62728',     # 红色  
                    'Blocked': '#ff7f0e',    # 橙色
                    'In Progress': '#1f77b4', # 蓝色
                    'Planned': '#17becf'     # 青色
                }
                
                fig = px.bar(
                    grouped, 
                    x='fv', 
                    y='count', 
                    color=status_col,
                    title="FV vs 测试用例MR数量 (按执行状态分组)",
                    labels={'count': '测试用例MR数量', 'fv': 'FV', status_col: '执行状态'},
                    barmode='stack',
                    category_orders={'fv': fv_order},
                    color_discrete_map=status_colors
                )
                
                # 添加总数标签在柱状图顶部
                fv_totals = grouped.groupby('fv')['count'].sum()
                for i, fv in enumerate(fv_totals.index):
                    fig.add_annotation(
                        x=fv,
                        y=fv_totals[fv],
                        text=str(fv_totals[fv]),
                        showarrow=False,
                        yshift=10,
                        font=dict(size=10, color='black')
                    )
                
                fig.update_layout(
                    height=400,
                    xaxis_title="FV",
                    yaxis_title="测试用例MR数量",
                    showlegend=True,
                    xaxis={'tickangle': -45},
                    legend_title_text="执行状态"
                )
                
                return apply_chart_style(fig, "FV vs 测试用例MR数量", height=400)
            except Exception as e:
                fig = go.Figure()
                fig.add_annotation(text=f"图表创建失败: {str(e)}", x=0.5, y=0.5, showarrow=False)
                fig.update_layout(title="FV vs 测试用例数量", height=400)
                return fig
        
        # 创建测试执行状态分布柱状图
        def create_status_distribution_chart():
            try:
                # 找到状态列 - 优先使用native_status
                status_col = None
                if 'native_status' in filtered_data.columns:
                    status_col = 'native_status'
                elif 'status' in filtered_data.columns:
                    status_col = 'status'
                elif 'run_status' in filtered_data.columns:
                    status_col = 'run_status'
                elif 'execution_status' in filtered_data.columns:
                    status_col = 'execution_status'
                
                if not status_col:
                    fig = go.Figure()
                    fig.add_annotation(text="缺少状态列", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="测试执行状态分布", height=400)
                    return fig
                
                # 处理状态数据 - 如果是字典格式，提取name字段
                status_data = filtered_data[status_col].copy()
                if status_data.dtype == 'object':
                    status_data = status_data.apply(lambda x: x.get('name', str(x)) if isinstance(x, dict) else str(x))
                
                # 状态映射 - 将原始状态映射到显示状态
                status_mapping = {
                    'passed': 'Passed',
                    'failed': 'Failed', 
                    'blocked': 'Blocked',
                    'planned': 'Planned',
                    'not_completed': 'In Progress'
                }
                
                # 应用状态映射
                mapped_status = status_data.map(status_mapping).fillna(status_data)
                status_counts = mapped_status.value_counts()
                
                # 定义状态颜色映射
                status_colors = {
                    'Passed': '#2ca02c',     # 绿色
                    'Failed': '#d62728',     # 红色  
                    'Blocked': '#ff7f0e',    # 橙色
                    'In Progress': '#1f77b4', # 蓝色
                    'Planned': '#17becf'     # 青色
                }
                
                # 为每个状态分配颜色
                colors = [status_colors.get(status, '#7f7f7f') for status in status_counts.index]
                
                fig = go.Figure(data=[
                    go.Bar(
                        x=status_counts.index,
                        y=status_counts.values,
                        marker_color=colors,
                        text=status_counts.values,
                        textposition='auto'
                    )
                ])
                
                fig.update_layout(
                    title="测试执行状态分布",
                    xaxis_title="执行状态",
                    yaxis_title="测试用例数量",
                    height=400
                )
                
                return apply_chart_style(fig, "测试执行状态分布", height=400)
            except Exception as e:
                fig = go.Figure()
                fig.add_annotation(text=f"图表创建失败: {str(e)}", x=0.5, y=0.5, showarrow=False)
                fig.update_layout(title="测试执行状态分布", height=400)
                return fig
        
        # 创建Release趋势图
        def create_release_trend_chart():
            try:
                # 检查是否有日期字段
                df_filtered = filtered_data.copy()
                
                # 尝试找到合适的日期字段
                date_fields = ['date', 'creation_time', 'detected_on', 'modified_on', 'executed_at']
                date_field = None
                for field in date_fields:
                    if field in df_filtered.columns:
                        date_field = field
                        break
                
                # 如果有日期字段，进行日期过滤
                if date_field:
                    try:
                        df_filtered[date_field] = pd.to_datetime(df_filtered[date_field], errors='coerce')
                        # 过滤2025年1月1日之后的数据
                        df_filtered = df_filtered[df_filtered[date_field] >= pd.to_datetime('2025-01-01')]
                        
                        if df_filtered.empty:
                            fig = go.Figure()
                            fig.add_annotation(text="暂无2025年1月1日后的数据", x=0.5, y=0.5, showarrow=False)
                            fig.update_layout(title="Release趋势图", height=400)
                            return fig
                    except:
                        # 如果日期处理失败，使用所有数据
                        pass
                
                # 检查是否有release或test_event字段
                release_field = None
                if 'release' in df_filtered.columns:
                    release_field = 'release'
                elif 'test_event' in df_filtered.columns:
                    release_field = 'test_event'
                else:
                    fig = go.Figure()
                    fig.add_annotation(text="数据中缺少release或test_event字段", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="Release趋势图", height=400)
                    return fig
                
                # 提取release/test_event值
                def extract_release_value(release_value):
                    if pd.isna(release_value):
                        return 'Unknown'
                    
                    # 如果是字典类型，提取name字段
                    if isinstance(release_value, dict):
                        return release_value.get('name', 'Unknown')
                    else:
                        return str(release_value)
                
                df_filtered['release_name'] = df_filtered[release_field].apply(extract_release_value)
                
                # 处理native_status字段，优先使用native_status
                status_column = 'native_status' if 'native_status' in df_filtered.columns else 'status'
                
                # 提取状态值并应用映射
                def extract_and_map_status(status_value):
                    if pd.isna(status_value):
                        return 'Unknown'
                    
                    # 如果是字典类型，提取name字段
                    if isinstance(status_value, dict):
                        status_name = status_value.get('name', 'Unknown')
                    else:
                        status_name = str(status_value)
                    
                    # 应用状态映射
                    status_mapping = {
                        'passed': 'Passed',
                        'failed': 'Failed', 
                        'not_completed': 'In Progress',
                        'skipped': 'Skipped',
                        'blocked': 'Blocked'
                    }
                    
                    return status_mapping.get(status_name.lower(), status_name)
                
                df_filtered['mapped_status'] = df_filtered[status_column].apply(extract_and_map_status)
                
                # 按release_name和mapped_status分组计数
                status_counts = df_filtered.groupby(['release_name', 'mapped_status']).size().unstack(fill_value=0)
                
                if status_counts.empty:
                    fig = go.Figure()
                    fig.add_annotation(text="暂无数据", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="Release趋势图", height=400)
                    return fig
                
                # 定义状态颜色
                status_colors = {
                    'Passed': '#28a745',
                    'Failed': '#dc3545', 
                    'In Progress': '#ffc107',
                    'Skipped': '#6c757d',
                    'Blocked': '#fd7e14',
                    'Unknown': '#e9ecef'
                }
                
                # 创建堆叠柱状图
                fig = go.Figure()
                
                for status in status_counts.columns:
                    color = status_colors.get(status, '#007bff')
                    fig.add_trace(go.Bar(
                        x=status_counts.index,
                        y=status_counts[status],
                        name=status,
                        marker_color=color
                    ))
                
                # 添加总数标签在柱状图顶部
                totals = status_counts.sum(axis=1)
                for i, (release, total) in enumerate(totals.items()):
                    fig.add_annotation(
                        x=release,
                        y=total,
                        text=str(total),
                        showarrow=False,
                        yshift=10,
                        font=dict(size=10, color='black')
                    )
                
                fig.update_layout(
                    barmode='stack',
                    title='Release趋势图',
                    xaxis_title='Release/Test Event',
                    yaxis_title='测试用例数量',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    height=400
                )
                
                return apply_chart_style(fig, "Release趋势图", height=400)
            except Exception as e:
                fig = go.Figure()
                fig.add_annotation(text=f"图表创建失败: {str(e)}", x=0.5, y=0.5, showarrow=False)
                fig.update_layout(title="Release趋势图", height=400)
                return fig
        
        # 创建项目测试数量柱状图
        def create_project_count_chart():
            try:
                if 'project' not in filtered_data.columns:
                    fig = go.Figure()
                    fig.add_annotation(text="缺少项目列", x=0.5, y=0.5, showarrow=False)
                    fig.update_layout(title="项目测试数量", height=400)
                    return fig
                
                project_counts = filtered_data['project'].value_counts().head(10)  # 显示前10个项目
                
                fig = px.bar(
                    x=project_counts.index,
                    y=project_counts.values,
                    title="项目测试数量 (Top 10)",
                    labels={'x': '项目', 'y': '测试用例数量'},
                    text=project_counts.values  # 添加数值标签
                )
                
                # 更新文本显示位置和格式
                fig.update_traces(textposition='outside', textfont_size=10)
                
                fig.update_layout(
                    height=400,
                    xaxis_title="项目",
                    yaxis_title="测试用例数量",
                    xaxis={'tickangle': 45}  # 旋转x轴标签以避免重叠
                )
                
                return apply_chart_style(fig, "项目测试数量", height=400)
            except Exception as e:
                fig = go.Figure()
                fig.add_annotation(text=f"图表创建失败: {str(e)}", x=0.5, y=0.5, showarrow=False)
                fig.update_layout(title="项目测试数量", height=400)
                return fig
        
        # 创建Phase 1新图表（使用test_coverage_components中的函数）
        from test_coverage_components import (
            create_pass_rate_trend_chart,
            create_test_aida_wordcloud, 
            create_enhanced_status_distribution_pie
        )
        
        # 准备适合Phase 1图表的数据格式
        phase1_data = filtered_data.copy()
        # 确保数据列匹配test_coverage_components的期望格式
        if 'run_status' not in phase1_data.columns and 'mapped_status' in phase1_data.columns:
            phase1_data['run_status'] = phase1_data['mapped_status']
        if 'top_aida' not in phase1_data.columns and 'aida' in phase1_data.columns:
            phase1_data['top_aida'] = phase1_data['aida']
        
        # 创建Phase 1图表
        phase1_fig1 = create_pass_rate_trend_chart(phase1_data)
        phase1_fig2 = create_test_aida_wordcloud(phase1_data) 
        phase1_fig3 = create_enhanced_status_distribution_pie(phase1_data)
        
        # 计算KPI指标
        total_count = len(filtered_data)
        if total_count > 0:
            passed_count = len(filtered_data[filtered_data.get('mapped_status', filtered_data.get('run_status', pd.Series(dtype='object'))) == 'Passed'])
            blocked_count = len(filtered_data[filtered_data.get('mapped_status', filtered_data.get('run_status', pd.Series(dtype='object'))) == 'Blocked'])
            planned_count = len(filtered_data[filtered_data.get('mapped_status', filtered_data.get('run_status', pd.Series(dtype='object'))) == 'Planned'])
            executed_count = total_count - planned_count
            
            pass_rate = (passed_count / total_count * 100) if total_count > 0 else 0
            block_rate = (blocked_count / total_count * 100) if total_count > 0 else 0  
            execution_rate = (executed_count / total_count * 100) if total_count > 0 else 0
        else:
            pass_rate = block_rate = execution_rate = 0
        
        # 创建KPI指标显示 - 使用与Testing Efficiency & Quality相同的样式
        kpi_indicators = html.Div([
            html.Div([
                html.H4(f"{total_count:,}", style={'margin': '0', 'color': '#2c3e50', 'fontSize': '28px'}),
                html.P("总用例数", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#ecf0f1', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
            
            html.Div([
                html.H4(f"{pass_rate:.1f}%", style={'margin': '0', 'color': '#27ae60', 'fontSize': '28px'}),
                html.P("通过率", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#d5f4e6', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
            
            html.Div([
                html.H4(f"{100-pass_rate-block_rate:.1f}%", style={'margin': '0', 'color': '#e74c3c', 'fontSize': '28px'}),
                html.P("失败率", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#fadbd8', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
            
            html.Div([
                html.H4(f"{block_rate:.1f}%", style={'margin': '0', 'color': '#f39c12', 'fontSize': '28px'}),
                html.P("阻塞率", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#fdeaa7', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
            
            html.Div([
                html.H4(f"{execution_rate:.1f}%", style={'margin': '0', 'color': '#3498db', 'fontSize': '28px'}),
                html.P("执行率", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#d6eaf8', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
            
            html.Div([
                html.H4(f"{100-execution_rate:.1f}%", style={'margin': '0', 'color': '#9b59b6', 'fontSize': '28px'}),
                html.P("计划中", style={'margin': '0', 'color': '#7f8c8d', 'fontSize': '14px'}),
            ], style={'textAlign': 'center', 'backgroundColor': '#e8daef', 'padding': '20px', 'borderRadius': '8px', 'margin': '10px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
        ], style={'display': 'flex', 'flexWrap': 'wrap', 'justifyContent': 'space-around', 'marginBottom': '25px'})
        
        # 生成图表结果
        chart_results = (phase1_fig3, phase1_fig1, phase1_fig2,
                        create_fv_stacked_chart(), create_release_trend_chart(), create_project_count_chart(), kpi_indicators)
        
        # 缓存图表结果（1小时有效期）
        try:
            if default_cache_manager:
                default_cache_manager.set(cache_key, chart_results, timeout=3600)
        except Exception as cache_error:
            print(f"缓存图表结果失败: {cache_error}")
        
        return chart_results
        
    except Exception as e:
        # 创建错误图表
        error_fig = go.Figure()
        error_fig.add_annotation(text=f"图表更新失败: {str(e)}", x=0.5, y=0.5, showarrow=False)
        error_fig.update_layout(height=400)
        error_kpi = html.Div("图表更新失败", style={'textAlign': 'center', 'color': '#dc3545'})
        return error_fig, error_fig, error_fig, error_fig, error_fig, error_fig, error_kpi

# High Runner 页面的图表回调函数
@app.callback(
    Output('hr-child-complexity-chart', 'figure'),
    [Input('hr-date-range-picker-main', 'start_date'),
     Input('hr-date-range-picker-main', 'end_date'),
     Input('hr-project-dropdown', 'value'),
     Input('hr-aida-dropdown', 'value'),
     Input('hr-status-dropdown', 'value')]
)
def update_hr_child_complexity_chart(start_date, end_date, selected_projects, selected_aidas, selected_statuses):
    try:
        # 检查数据是否有效
        if df is None or df.empty:
            from dash_common_styles import create_empty_figure
            return create_empty_figure("数据加载中...", height=400, theme=theme_manager.get_theme())
        
        # 筛选数据
        filtered_data = df.copy()
        
        # 时间范围筛选
        if start_date and end_date:
            filtered_data = filtered_data[
                (pd.to_datetime(filtered_data['creation_time']).dt.date >= pd.to_datetime(start_date).date()) &
                (pd.to_datetime(filtered_data['creation_time']).dt.date <= pd.to_datetime(end_date).date())
            ]
        
        # 项目筛选
        if selected_projects:
            filtered_data = filtered_data[filtered_data['project'].isin(selected_projects)]
        
        # AIDA 域筛选
        if selected_aidas:
            filtered_data = filtered_data[filtered_data['aida_english'].isin(selected_aidas)]
        
        # 状态筛选
        if selected_statuses:
            filtered_data = filtered_data[filtered_data['status_phase'].isin(selected_statuses)]
        
        # 计算缺陷等级
        if 'child_count_of_master' in filtered_data.columns:
            filtered_data['defect_level'] = filtered_data['child_count_of_master'].apply(categorize_defect_level_hr)
        else:
            filtered_data['child_count_of_master'] = 0
            filtered_data['defect_level'] = 'Low'
        
        # 确保test_week_sortable列存在
        if 'test_week' in filtered_data.columns and 'test_week_sortable' not in filtered_data.columns:
            filtered_data['test_week_sortable'] = filtered_data['test_week']
        
        # 获取相关测试周
        if 'test_week_sortable' in filtered_data.columns:
            relevant_weeks = sorted(filtered_data['test_week_sortable'].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
        else:
            relevant_weeks = []
        
        return create_child_complexity_line_chart_hr(filtered_data, relevant_weeks)
        
    except Exception as e:
        from dash_common_styles import create_empty_figure
        return create_empty_figure(f"图表更新失败: {str(e)}", height=400, theme=theme_manager.get_theme())

@app.callback(
    Output('hr-parent-complexity-chart', 'figure'),
    [Input('hr-date-range-picker-main', 'start_date'),
     Input('hr-date-range-picker-main', 'end_date'),
     Input('hr-project-dropdown', 'value'),
     Input('hr-aida-dropdown', 'value'),
     Input('hr-status-dropdown', 'value')]
)
def update_hr_parent_complexity_chart(start_date, end_date, selected_projects, selected_aidas, selected_statuses):
    try:
        # 检查数据是否有效
        if df is None or df.empty:
            from dash_common_styles import create_empty_figure
            return create_empty_figure("数据加载中...", height=400, theme=theme_manager.get_theme())
        
        # 筛选数据
        filtered_data = df.copy()
        
        # 时间范围筛选
        if start_date and end_date:
            filtered_data = filtered_data[
                (pd.to_datetime(filtered_data['creation_time']).dt.date >= pd.to_datetime(start_date).date()) &
                (pd.to_datetime(filtered_data['creation_time']).dt.date <= pd.to_datetime(end_date).date())
            ]
        
        # 项目筛选
        if selected_projects:
            filtered_data = filtered_data[filtered_data['project'].isin(selected_projects)]
        
        # AIDA 域筛选
        if selected_aidas:
            filtered_data = filtered_data[filtered_data['aida_english'].isin(selected_aidas)]
        
        # 状态筛选
        if selected_statuses:
            filtered_data = filtered_data[filtered_data['status_phase'].isin(selected_statuses)]
        
        # 计算master linked defect level
        if 'relation_to_udf' in filtered_data.columns:
            filtered_data['linked_defect_count'] = filtered_data['relation_to_udf'].apply(count_linked_defects_hr)
            filtered_data['master_linked_defect_level'] = filtered_data['linked_defect_count'].apply(categorize_master_linked_level_hr)
        else:
            filtered_data['linked_defect_count'] = 0
            filtered_data['master_linked_defect_level'] = 'Low'
        
        # 确保test_week_sortable列存在
        if 'test_week' in filtered_data.columns and 'test_week_sortable' not in filtered_data.columns:
            filtered_data['test_week_sortable'] = filtered_data['test_week']
        
        # 获取相关测试周
        if 'test_week_sortable' in filtered_data.columns:
            relevant_weeks = sorted(filtered_data['test_week_sortable'].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
        else:
            relevant_weeks = []
        
        return create_parent_complexity_line_chart_hr(filtered_data, relevant_weeks)
        
    except Exception as e:
        from dash_common_styles import create_empty_figure
        return create_empty_figure(f"图表更新失败: {str(e)}", height=400, theme=theme_manager.get_theme())

# 词云页面的回调函数
@app.callback(
    [Output('main-wordcloud-chart', 'figure'),
     Output('wordcloud-frequency-table', 'data'),
     Output('wordcloud-stats-info', 'children')],
    [Input('wc-project-dropdown', 'value'),
     Input('wc-date-range-picker', 'start_date'),
     Input('wc-date-range-picker', 'end_date'),
     Input('wc-aida-dropdown', 'value'),
     Input('wc-status-dropdown', 'value'),
     Input('wc-severity-dropdown', 'value'),
     Input('wc-text-source-dropdown', 'value'),
     Input('wc-max-words-dropdown', 'value'),
     Input('wc-language-dropdown', 'value')],
    prevent_initial_call=False
)
def update_wordcloud_page(projects, start_date, end_date, aidas, statuses, severity, text_source, max_words, language_filter):
    try:
        ensure_defect_data_for_date_range(start_date, end_date)

        # 检查数据是否有效
        if df is None or df.empty:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="数据加载中...", x=0.5, y=0.5, showarrow=False)
            empty_fig.update_layout(title="词云分析", height=600)
            return empty_fig, [], "数据加载中..."
        
        # 筛选数据
        filtered_data = df.copy()
        
        # 项目筛选
        if projects:
            filtered_data = filtered_data[filtered_data['project'].isin(projects)]
        
        # 时间范围筛选
        if start_date and end_date:
            filtered_data = filtered_data[
                (pd.to_datetime(filtered_data['creation_time']).dt.date >= pd.to_datetime(start_date).date()) &
                (pd.to_datetime(filtered_data['creation_time']).dt.date <= pd.to_datetime(end_date).date())
            ]
        
        # AIDA筛选
        if aidas:
            filtered_data = filtered_data[filtered_data['aida_english'].isin(aidas)]
        
        # 状态筛选
        if statuses:
            filtered_data = filtered_data[filtered_data['status_phase'].isin(statuses)]
        
        # 严重性筛选
        if severity != 'all':
            # 这里需要根据实际的严重性判断逻辑来筛选
            # 暂时使用简单的逻辑，可以根据需要调整
            if severity == 'critical':
                # 假设critical issues有特定的标识
                filtered_data = filtered_data[filtered_data.get('is_critical', False) == True]
            elif severity == 'general':
                filtered_data = filtered_data[filtered_data.get('is_critical', False) == False]
        
        # 检查筛选后是否有数据
        if filtered_data.empty:
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="没有符合条件的数据", x=0.5, y=0.5, showarrow=False)
            empty_fig.update_layout(title="词云分析", height=600)
            return empty_fig, [], "没有符合条件的数据"
        
        # 根据文本源提取文本
        text_data = []
        if text_source == 'defect_name':
            text_data = filtered_data['defect_name'].dropna().astype(str).tolist()
        elif text_source == 'description':
            text_data = filtered_data['description'].dropna().astype(str).tolist()
        elif text_source == 'domain':
            text_data = filtered_data['domain'].dropna().astype(str).tolist()
        elif text_source == 'combined':
            names = filtered_data['defect_name'].dropna().astype(str)
            descriptions = filtered_data['description'].dropna().astype(str)
            text_data = (names + ' ' + descriptions).tolist()
        
        # 语言筛选
        if language_filter != 'all':
            import re
            filtered_text = []
            for text in text_data:
                if language_filter == 'english':
                    # 只保留英文文本
                    english_text = re.sub(r'[^a-zA-Z\s]', ' ', text)
                    if english_text.strip():
                        filtered_text.append(english_text)
                elif language_filter == 'chinese':
                    # 只保留中文文本
                    chinese_text = re.sub(r'[^\u4e00-\u9fff\s]', ' ', text)
                    if chinese_text.strip():
                        filtered_text.append(chinese_text)
            text_data = filtered_text
        
        # 合并所有文本
        combined_text = ' '.join(text_data)
        
        if not combined_text.strip():
            empty_fig = go.Figure()
            empty_fig.add_annotation(text="没有可用的文本数据", x=0.5, y=0.5, showarrow=False)
            empty_fig.update_layout(title="词云分析", height=600)
            return empty_fig, [], "没有可用的文本数据"
        
        # 生成词云
        from word_cloud import generate_wordcloud
        wordcloud_img = generate_wordcloud(combined_text, max_words=max_words)
        
        # 创建词云图表
        import plotly.graph_objects as go
        from PIL import Image
        import numpy as np
        
        # 将词云图像转换为numpy数组
        img_array = np.array(wordcloud_img)
        
        fig = go.Figure()
        fig.add_layout_image(
            dict(
                source=wordcloud_img,
                xref="x",
                yref="y",
                x=0,
                y=img_array.shape[0],
                sizex=img_array.shape[1],
                sizey=img_array.shape[0],
                sizing="stretch",
                opacity=1,
                layer="below"
            )
        )
        
        fig.update_layout(
            title="缺陷关键词词云",
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[0, img_array.shape[1]]),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[0, img_array.shape[0]]),
            height=600,
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        # 生成词频统计表
        from collections import Counter
        import re
        
        # 简单的文本预处理
        words = re.findall(r'\b\w+\b', combined_text.lower())
        
        # 过滤停用词
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
        filtered_words = [word for word in words if word not in stopwords and len(word) > 2]
        
        word_counts = Counter(filtered_words)
        total_words = sum(word_counts.values())
        
        # 创建词频表数据
        frequency_data = []
        for word, count in word_counts.most_common(50):  # 显示前50个词
            percentage = (count / total_words * 100) if total_words > 0 else 0
            frequency_data.append({
                'word': word,
                'frequency': count,
                'percentage': f"{percentage:.1f}%"
            })
        
        # 生成统计信息
        stats_info = html.Div([
            html.P(f"总缺陷数量: {len(filtered_data)}"),
            html.P(f"文本来源: {text_source}"),
            html.P(f"总词汇数: {total_words}"),
            html.P(f"唯一词汇数: {len(word_counts)}"),
            html.P(f"显示词汇数: {min(max_words, len(word_counts))}"),
            html.P(f"语言筛选: {language_filter}")
        ])
        
        return fig, frequency_data, stats_info
        
    except Exception as e:
        error_fig = go.Figure()
        error_fig.add_annotation(text=f"词云生成失败: {str(e)}", x=0.5, y=0.5, showarrow=False)
        error_fig.update_layout(title="词云分析", height=600)
        return error_fig, [], f"错误: {str(e)}"


if __name__ == '__main__':
    # 尝试从环境变量读取配置
    import os
    host = os.environ.get('HOST', '0.0.0.0')  # 默认允许局域网访问
    port = int(os.environ.get('PORT', 8051))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    if DISABLE_RELOADER:
        debug = False
    
    # 检查是否是reloader进程
    if IS_RELOADER:
        print("\n🔄 注意：这是reloader进程，跳过启动信息显示...\n")
    else:
        # 显示网络访问信息
        import socket
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            print("\n" + "="*50)
            print("缺陷探索应用启动信息")
            print("="*50)
            print(f"主机: {host}")
            print(f"端口: {port}")
            print(f"调试模式: {debug}")
            print(f"本机访问: http://localhost:{port}")
            print(f"本机访问: http://127.0.0.1:{port}")
            if host == '0.0.0.0':
                print(f"局域网访问: http://{local_ip}:{port}")
                print(f"主机名访问: http://{hostname}:{port}")
            print("="*50)
            print("团队成员可通过局域网IP访问应用")
            print("请确保防火墙允许{}端口访问".format(port))
            print("="*50 + "\n")
            
        except Exception as e:
            print(f"获取网络信息时出错: {e}")


if __name__ == '__main__':
    # AI聊天回调函数已在前面注册，这里不需要重复注册
    print("🚀 启动Defect Explorer应用...")
    app.run(
        debug=debug,
        host=host,
        port=port,
        threaded=True,
        use_reloader=not DISABLE_RELOADER,
        dev_tools_hot_reload=not DISABLE_RELOADER,
    )
