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
from dash_common_styles import theme_manager, MAIN_CONTAINER_STYLE, LIGHT_MAIN_CONTAINER_STYLE, TEXT_COLOR, LIGHT_TEXT_COLOR, LABEL_STYLE_DARK, LABEL_STYLE_LIGHT, DROPDOWN_STYLE_DARK, DROPDOWN_STYLE_LIGHT, DARK_ACCENT, LIGHT_BORDER_COLOR
import plotly.express as px
import plotly.graph_objects as go
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
from cache_versioning import get_cache_version

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


def normalize_status_text(value):
    raw = extract_status_value(value)
    s = str(raw) if raw is not None else ''
    s = s.strip().lower()
    if '_' in s:
        base, tail = s.rsplit('_', 1)
        if tail in {'critical', 'high', 'medium', 'low', 's1', 's2', 's3', 's4'}:
            s = base
    return s


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

    loaded_years = set()
    if not df.empty:
        try:
            loaded_years = {int(y) for y in extract_year_series(df).dropna().astype(int).tolist()}
        except Exception:
            loaded_years = set()

    discovered_years = set(_discover_defect_years_from_files())
    preloaded_years = set(int(y) for y in _loaded_defect_years) if _loaded_defect_years else set()
    year_options_values = sorted(
        set([DEFAULT_DEFECT_YEAR - 1, DEFAULT_DEFECT_YEAR]).union(loaded_years, discovered_years, preloaded_years)
    )
    if year_options_values:
        year_default = [DEFAULT_DEFECT_YEAR] if DEFAULT_DEFECT_YEAR in year_options_values else [year_options_values[-1]]
    else:
        year_default = []

    return html.Div([
        # 第一行过滤器
        html.Div([
            html.Div([
                html.Label('Year:', style=active_label_style),
                dcc.Dropdown(
                    id=f'{prefix}year-dropdown',
                    options=[{'label': str(y), 'value': int(y)} for y in year_options_values],
                    value=year_default,
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
        ], className='filter-container', style={'marginBottom': '20px', 'marginTop': '20px'}),
        
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
        ], className='filter-container', style={'marginBottom': '20px', 'marginTop': '20px'}),

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
        ], className='filter-container', style={'marginBottom': '20px'}),
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
    # 导入Phase Duration分析模块
    from longrunner_analysis import (
        analyze_ticket_phases, get_all_ticket_ids,
        calculate_phase_duration, extract_phase_changes
    )
else:
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


# 缓存版本号：由数据指纹驱动，数据更新时自动失效
try:
    _DATA_CACHE_VERSION = get_cache_version(
        prefix="v5",
        extra_tag=os.environ.get("APP_CACHE_CODE_VERSION", "defect_explore"),
    )
except Exception as _cache_version_error:
    print(f"⚠️ 数据指纹缓存版本生成失败，使用回退版本: {_cache_version_error}")
    _DATA_CACHE_VERSION = "v5_fallback"
try:
    DEFAULT_DEFECT_YEAR = int(os.environ.get("DEFAULT_DEFECT_YEAR", "2026"))
except (TypeError, ValueError):
    DEFAULT_DEFECT_YEAR = 2026

FAST_START_MODE = os.environ.get("DEFECT_EXPLORE_FAST_START", "1").lower() in ("1", "true", "yes")
OCTANE_TEAM = os.environ.get("OCTANE_TEAM", "DTSV_China")
OCTANE_DATA_SOURCE = os.environ.get("OCTANE_DATA_SOURCE", "db_only").strip().lower()
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


@lru_cache(maxsize=1)
def _discover_defect_years_from_files():
    """扫描 defect 目录，推断可选缺陷年份。"""
    discovered = set()
    try:
        defect_dir = Path("defect")
        if defect_dir.exists():
            for p in defect_dir.glob("*_defect.json"):
                m = re.match(r"(\d{4})_defect\.json$", p.name)
                if m:
                    discovered.add(int(m.group(1)))
    except Exception:
        pass

    return tuple(sorted(discovered))


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
            if OCTANE_DATA_SOURCE == "db_only":
                print(f"⚠️ db_only 模式：{year} 年 master 数据数据库未命中，跳过本地文件回退")
                continue
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


def ensure_defect_data_for_years(years=None):
    """根据年份筛选按需补载缺陷数据。"""
    global df, master_df, _loaded_defect_years

    required_years = set(_normalize_defect_years(years))
    missing_years = sorted(required_years - _loaded_defect_years)
    if not missing_years:
        return

    with _defect_data_load_lock:
        missing_years = sorted(required_years - _loaded_defect_years)
        if not missing_years:
            return

        target_years = _normalize_defect_years(tuple(_loaded_defect_years.union(required_years)))
        print(f"⏳ 检测到年份筛选补载，缺失年份: {missing_years}，当前目标年份集合: {target_years}")
        df = _cached_load_defect_data(target_years, cache_version=_DATA_CACHE_VERSION)
        master_df = _cached_load_master_data(target_years, cache_version=_DATA_CACHE_VERSION)
        _loaded_defect_years = set(target_years)
        print(f"✅ 年份补载完成，已加载年份: {sorted(_loaded_defect_years)}，总行数: {len(df)}")

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
    if years:
        try:
            year_targets = [int(y) for y in years if str(y).strip().isdigit()]
            if year_targets:
                ensure_defect_data_for_years(year_targets)
        except Exception:
            pass
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
            status_norm = filtered_df['status_phase'].apply(normalize_status_text)
            if len(statuses) == 1 and statuses[0] == special_child_status:
                filtered_df = filtered_df[
                    (status_norm == '09-concluded without action') &
                    (filtered_df['blocking_reason'] == 'Child (Duplicate)')
                ]
            else:
                normal_statuses_norm = {normalize_status_text(s) for s in normal_statuses if normalize_status_text(s)}
                filtered_df = filtered_df[status_norm.isin(normal_statuses_norm)]
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

