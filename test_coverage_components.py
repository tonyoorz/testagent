"""
测试覆盖率组件模块
提供可重用的测试覆盖率筛选器和图表组件
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import gc
import numpy as np
from typing import Dict

# 词云图相关导入
try:
    from wordcloud import WordCloud, STOPWORDS
    # 设置matplotlib后端为非GUI模式，避免macOS上的NSWindow线程问题
    import matplotlib
    matplotlib.use('Agg')  # 使用非GUI后端
    import matplotlib.pyplot as plt
    import base64
    from io import BytesIO
    WORDCLOUD_AVAILABLE = True
except ImportError:
    WORDCLOUD_AVAILABLE = False
    print("⚠️ wordcloud 或 matplotlib 未安装，词云图功能将不可用")

# 从 data_processor 导入函数
from data_processor import load_test_data, apply_chart_style, create_empty_figure

# === 全局配置 ===
color_map = {
    "Passed": "lightgreen",
    "Failed": "darkred",
    "Requires Attention": "yellow",
    "Planned": "lightgrey",
}

# 页面级服务端缓存，避免将大体量测试数据通过 dcc.Store 发送到浏览器
_TEST_COVERAGE_DATA_CACHE: Dict[str, pd.DataFrame] = {}


def cache_test_coverage_data(cache_key: str, tdf: pd.DataFrame) -> None:
    """缓存测试覆盖率页面数据，供回调函数在服务端读取。"""
    if not cache_key:
        return
    _TEST_COVERAGE_DATA_CACHE[cache_key] = tdf.copy(deep=False)


def get_cached_test_coverage_data(cache_key: str) -> pd.DataFrame:
    """根据缓存键获取测试覆盖率数据。"""
    if not cache_key:
        return pd.DataFrame()
    cached = _TEST_COVERAGE_DATA_CACHE.get(cache_key)
    if cached is None:
        return pd.DataFrame()
    return cached.copy(deep=False)

# === Feature Region映射函数 ===
def get_feature_region(top_aida):
    """根据Top AIDA确定Feature Region (China Specific或Global)"""
    if pd.isna(top_aida) or top_aida == '':
        return 'Global'
    
    # 中国特有功能的AIDA列表
    china_specific_aidas = [
        'Use App Store China  [01.04.01.06.07]',
        'Traffic Info ASIA [01.04.03.01.02.07]',
        'Use Third Party App Store [01.04.01.05.03.02]',
        'Route planning and management 2.0 [01.04.02.01.01.05.24]',
        'Provide NetEase Cloud Music [01.04.01.06.04.03]',
        'Provide Festival Mode [01.04.02.01.04.08]',
        'Provide 3rd Party Gaming App [01.04.01.02.03.05]',
        'Positioning ASIA [01.04.03.01.02.01.02]',
        'Navigation Destination Input ASIA [01.04.03.01.02.03]',
        'POI Functions ASIA [01.04.03.01.02.05]',
        'Parking Finder China [01.04.03.01.05.02]',
        'Itinerary (Mobile App) [01.04.03.01.01.07.09]',
        'Use Speech operation [01.04.02.01.01.05]',
        'Connected Music China [01.04.01.06.04]',
        'Play audio via Online Services (Connected Music) [01.04.01.01.02]',
        'Voice Interface [01.04.02.01.01.02]',
        'Display map ASIA [01.04.03.01.02.04]',
        'Festival Mode [01.04.02.01.02.01.04]',
        'QQ Music [01.04.01.06.04.02]',
        'Smart Access / Digital Key (Plus) [01.03.03.03.04]',
        'Tencent MiniProgramPlatform (Tencent MPP) [01.04.01.06.01]',
        'Guiding [01.04.03.01.03.02.03]',
        'Guiding 2.0 [01.04.02.01.03.03.07.07]',
        'Guiding ASIA [01.04.03.01.02.08]',
        'Map [01.04.03.01.03.02.01]',
        'Map and Navigation Data update ASIA [01.04.03.01.02.02]',
        'Tencent MPP - MainMenu [01.04.01.06.01.01]',
        'Tencent WeChat [01.04.01.06.02]',
        'Video streaming China [01.04.01.06.05]',
        'WeChat Messaging [01.04.01.06.02.03]',
        'WeChat VoiP Call [01.04.01.06.02.02]',
        'Ximalaya [01.04.01.06.04.01]',
        'Provide Navigation 2.0 [01.04.03.01.03.06]',
        # 新增的中国特有功能
        'Digital Keyring [01.04.01.06.06]',
        'PaDi - Pre-installed China VoD app (iQiyi) [01.04.04.01.05.06]',
        'Component Test -> Downstream',
        'Display weather [01.04.01.05.01.03]',
        'Intelligent Reminder  [01.04.02.01.02.02.01]',
        'Enable Registration, Login, Mapping',
        'IPA Visualization',
        'Provide IPA interactive Elements China',
        'provide HUAWEI HiCar',
        'Provide Karaoke Service',
        'Provisioning International Speller',
        'Provide App Center China',
        'Telephony via customer device',
        'Provide 3rd party gaming enablement',
        'Provide Child Seat App Provisioning International Speller [01.04.02.03.01.01.06]',
        'Telephony via customer device [01.04.01.04.01.01]',
        'Provide Launcher  [01.04.02.03.01.01.09]',
        'BT Child Seat App connection [01.06.02.04.04.04]',
        'My Modes [01.04.02.01.04.03]',
        'Use Co-Driver Entertainment',
        'Use Rear Seat Entertainment',
        'Component Test'
    ]
    
    # 检查是否在中国特有功能列表中
    if str(top_aida).strip() in china_specific_aidas:
        return 'China Specific'
    else:
        return 'Global'

# === 数据加载 ===
def get_test_coverage_data():
    """获取测试覆盖率数据"""
    try:
        print("正在加载测试覆盖率数据...")
        
        # 尝试加载测试数据
        try:
            tdf = load_test_data()
        except Exception as e:
            print(f"加载测试数据失败: {e}")
            # 返回空的DataFrame，避免页面崩溃
            return pd.DataFrame()
        
        # 检查数据是否为空
        if tdf.empty:
            print("警告：测试数据为空")
            return pd.DataFrame()
        
        
        # 添加Feature Region列
        if 'top_aida' in tdf.columns:
            tdf['feature_region'] = tdf['top_aida'].apply(get_feature_region)
            feature_region_dist = tdf['feature_region'].value_counts().to_dict()
            print(f"Feature Region分布: {feature_region_dist}")
        else:
            print("警告: 'top_aida' 列不存在，无法创建 Feature Region 列")
            tdf['feature_region'] = 'Global'  # 默认值
        
        # 强制垃圾回收
        gc.collect()
        
        print(f"成功加载 {len(tdf)} 行测试数据")
        return tdf
        
    except Exception as e:
        print(f"加载测试数据失败: {e}")
        return pd.DataFrame()

# === 筛选逻辑 ===
def filter_test_data(tdf, projects=None, test_weeks=None, pus=None, aidas=None, feature_regions=None, fvps=None, statuses=None):
    """筛选测试数据"""
    if tdf.empty:
        return tdf
    
    filtered_df = tdf.copy()
    
    # 应用筛选条件
    if projects:
        filtered_df = filtered_df[filtered_df['project'].isin(projects)]
    if test_weeks:
        filtered_df = filtered_df[filtered_df['test_week'].isin(test_weeks)]
    if pus:
        filtered_df = filtered_df[filtered_df['pu'].isin(pus)]
    if aidas and 'all' not in aidas:
        filtered_df = filtered_df[filtered_df['top_aida'].isin(aidas)]
    if feature_regions:
        filtered_df = filtered_df[filtered_df['feature_region'].isin(feature_regions)]
    if fvps:
        filtered_df = filtered_df[filtered_df['fvp'].isin(fvps)]
    # lead_models 筛选逻辑已移除
    if statuses:
        # 优先使用native_status的name字段，如果不存在则使用run_status
        if 'native_status' in filtered_df.columns:
            # 从native_status中提取name字段进行筛选
            def extract_status_name(x):
                if isinstance(x, dict) and 'name' in x:
                    return x['name']
                elif isinstance(x, str):
                    return x
                else:
                    return None
            status_names = filtered_df['native_status'].apply(extract_status_name)
            filtered_df = filtered_df[status_names.isin(statuses)]
        else:
            # 如果没有native_status，则使用其他状态字段
            status_column = next((col for col in ['run_status', 'status', 'execution_status'] if col in filtered_df.columns), 'run_status')
            if status_column in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[status_column].isin(statuses)]
    
    return filtered_df

# === 图表生成函数 ===
def create_project_status_chart(filtered_data):
    """创建FV测试状态分布图 - 气泡图"""
    if filtered_data.empty:
        return create_empty_figure("FV测试状态分布 (无数据)", height=400)
    
    try:
        # 优先使用native_status列，如果不存在则使用run_status列
        status_column = None
        if 'native_status' in filtered_data.columns:
            status_column = 'native_status'
        elif 'run_status' in filtered_data.columns:
            status_column = 'run_status'
        else:
            return create_empty_figure("错误: 缺少状态列 ('native_status' 或 'run_status')", height=400)
        
        # 检查必要的列
        required_cols = ['test_week', 'fvp', 'fv', status_column]
        if not all(col in filtered_data.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in filtered_data.columns]
            return create_empty_figure(f"错误: 缺少列 {', '.join(missing_cols)}", height=400)
        
        # 找到计数列
        count_col = None
        if 'test_case_id' in filtered_data.columns:
            count_col = 'test_case_id'
        elif 'id' in filtered_data.columns:
            count_col = 'id'
        else:
            return create_empty_figure("错误：缺少用于计数的列", height=400)
        
        # 创建数据副本并处理可能的字典类型数据
        data_for_grouping = filtered_data.copy()
        if count_col in data_for_grouping.columns:
            data_for_grouping[count_col] = data_for_grouping[count_col].apply(
                lambda x: str(x) if isinstance(x, dict) else x
            )
        
        # 处理状态数据，提取字典中的name字段或直接使用字符串值
        def extract_status_name(status):
            if isinstance(status, dict) and 'name' in status:
                return status['name']
            return str(status) if status is not None else 'Unknown'
        
        # 应用状态提取
        data_for_grouping['processed_status'] = data_for_grouping[status_column].apply(extract_status_name)
        
        # 状态映射（与test status analysis保持一致）
        status_mapping = {
            'passed': 'Passed',
            'failed': 'Failed', 
            'blocked': 'Blocked',
            'planned': 'Planned',
            'not_completed': 'In Progress',
            'skipped': 'Skipped',
            'in_progress': 'In Progress',
            'requires attention': 'Blocked'  # 将Requires Attention映射为Blocked
        }
        
        # 应用状态映射
        data_for_grouping['mapped_status'] = data_for_grouping['processed_status'].map(
            lambda x: status_mapping.get(x.lower() if isinstance(x, str) else str(x).lower(), x)
        )
        
        # 按FV、测试周和状态分组统计
        status_data = data_for_grouping.groupby(['test_week', 'fvp', 'fv', 'mapped_status'], as_index=False)[count_col].nunique().rename(columns={count_col: 'count'})
        
        if status_data.empty:
            return create_empty_figure("FV测试状态分布 (分组后无数据)", height=400)
        
        # 过滤有效的测试周
        extract_pattern = r'(\d{2})-CW(\d{2})'
        valid_week_mask = status_data['test_week'].astype(str).str.match(extract_pattern)
        status_data = status_data[valid_week_mask.fillna(False)]
        
        if status_data.empty:
            return create_empty_figure("FV测试状态分布 (无有效周数据)", height=400)
        
        # 排序
        status_data['test_week_str'] = status_data['test_week'].astype(str)
        extracted_sort_keys = status_data['test_week_str'].str.extract(extract_pattern)
        status_data['sort_year'] = pd.to_numeric(extracted_sort_keys[0], errors='coerce').fillna(99).astype(int)
        status_data['sort_week'] = pd.to_numeric(extracted_sort_keys[1], errors='coerce').fillna(99).astype(int)
        status_data = status_data.sort_values(["sort_year", "sort_week", "fvp", "fv"])
        
        sorted_weeks = status_data['test_week'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        sorted_fvs = status_data.sort_values(['fvp', 'fv'])['fv'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        
        # 创建气泡图
        fig = px.scatter(
            status_data, 
            x='test_week', 
            y='fv', 
            color='mapped_status',
            size='count',
            size_max=40,
            opacity=0.8,
            title="按周和功能分类的测试状态 (气泡图)",
            labels={'count': '测试数量', 'fv': '功能 (FV)', 'mapped_status': '运行状态', 'test_week': '测试周', 'fvp': 'FVP'},
            color_discrete_map=color_map,
            category_orders={'test_week': list(sorted_weeks), 'fv': list(sorted_fvs), 'mapped_status': list(color_map.keys())},
            hover_data={'test_week': True, 'fvp': True, 'fv': True, 'mapped_status': True, 'count': True, 'sort_year': False, 'sort_week': False}
        )
        
        fig.update_layout(
            height=600,
            xaxis={'tickangle': -45},
            xaxis_title="测试周",
            yaxis_title="功能 (FV)",
            legend_title_text="运行状态",
            xaxis_showgrid=True,
            yaxis_showgrid=True,
            plot_bgcolor='rgba(248, 248, 250, 0.5)',
            hoverlabel=dict(bgcolor="white", font_size=12, font_family="Rockwell")
        )
        fig.update_traces(marker=dict(sizemode='area', line_width=1, line_color='black'))
        fig = apply_chart_style(fig, title="按周和功能分类的测试状态", height=600)
        
        return fig
        
    except Exception as e:
        print(f"创建FV状态图表失败: {e}")
        return create_empty_figure("FV测试状态分布 (创建失败)", height=400)

def create_fvp_coverage_chart(filtered_data):
    """创建Top AIDA测试状态分布图 - 气泡图"""
    if filtered_data.empty:
        return create_empty_figure("Top AIDA测试状态分布 (无数据)", height=400)
    
    try:
        # 检查是否有top_aida列
        if 'top_aida' not in filtered_data.columns:
            return create_empty_figure("错误: 缺少 'top_aida' 数据", height=400)
        
        # 优先使用native_status列，如果不存在则使用run_status列
        status_column = None
        if 'native_status' in filtered_data.columns:
            status_column = 'native_status'
        elif 'run_status' in filtered_data.columns:
            status_column = 'run_status'
        else:
            return create_empty_figure("错误: 缺少状态列 ('native_status' 或 'run_status')", height=400)
        
        # 创建数据副本并处理状态数据
        data_for_grouping = filtered_data.copy()
        
        # 处理状态数据，提取字典中的name字段或直接使用字符串值
        def extract_status_name(status):
            if isinstance(status, dict) and 'name' in status:
                return status['name']
            return str(status) if status is not None else 'Unknown'
        
        # 应用状态提取
        data_for_grouping['processed_status'] = data_for_grouping[status_column].apply(extract_status_name)
        
        # 状态映射（与test status analysis保持一致）
        status_mapping = {
            'passed': 'Passed',
            'failed': 'Failed', 
            'blocked': 'Blocked',
            'planned': 'Planned',
            'not_completed': 'In Progress',
            'skipped': 'Skipped',
            'in_progress': 'In Progress',
            'requires attention': 'Blocked'  # 将Requires Attention映射为Blocked
        }
        
        # 应用状态映射
        data_for_grouping['mapped_status'] = data_for_grouping['processed_status'].map(
            lambda x: status_mapping.get(x.lower() if isinstance(x, str) else str(x).lower(), x)
        )
        
        # 按top_aida、测试周和状态分组统计
        aida_data = data_for_grouping.groupby(['test_week', 'top_aida', 'mapped_status']).size().reset_index(name='count')
        
        if aida_data.empty:
            return create_empty_figure("Top AIDA测试状态分布 (分组后无数据)", height=400)
        
        # 过滤有效的测试周
        extract_pattern = r'(\d{2})-CW(\d{2})'
        valid_week_mask = aida_data['test_week'].astype(str).str.match(extract_pattern)
        aida_data = aida_data[valid_week_mask.fillna(False)]
        
        if aida_data.empty:
            return create_empty_figure("Top AIDA测试状态分布 (无有效周数据)", height=400)
        
        # 排序
        aida_data['test_week_str'] = aida_data['test_week'].astype(str)
        extracted_sort_keys = aida_data['test_week_str'].str.extract(extract_pattern)
        aida_data['sort_year'] = pd.to_numeric(extracted_sort_keys[0], errors='coerce').fillna(99).astype(int)
        aida_data['sort_week'] = pd.to_numeric(extracted_sort_keys[1], errors='coerce').fillna(99).astype(int)
        aida_data = aida_data.sort_values(["sort_year", "sort_week", "top_aida"])
        
        sorted_weeks = aida_data['test_week'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        sorted_aidas = sorted(aida_data['top_aida'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique())
        
        # 创建气泡图
        fig = px.scatter(
            aida_data, 
            x='test_week', 
            y='top_aida', 
            color='mapped_status',
            size='count',
            size_max=40,
            opacity=0.8,
            title="按 Top AIDA 和测试周分类的状态 (气泡图)",
            labels={'count': '测试数量', 'top_aida': 'Top AIDA', 'mapped_status': '状态', 'test_week': '测试周'},
            color_discrete_map=color_map,
            category_orders={'test_week': list(sorted_weeks), 'top_aida': sorted_aidas, 'mapped_status': list(color_map.keys())},
            hover_data={'test_week': True, 'top_aida': True, 'mapped_status': True, 'count': True, 'sort_year': False, 'sort_week': False}
        )
        
        fig.update_layout(
            height=max(600, len(sorted_aidas) * 35 + 150),
            xaxis={'tickangle': -45},
            margin=dict(l=200, r=60, t=100, b=80),
            xaxis_title="测试周",
            yaxis_title="Top AIDA",
            legend_title_text="运行状态",
            xaxis_showgrid=True,
            yaxis_showgrid=True,
            plot_bgcolor='rgba(248, 248, 250, 0.5)',
            hoverlabel=dict(bgcolor="white", font_size=12, font_family="Rockwell")
        )
        fig.update_traces(marker=dict(sizemode='area', line_width=1, line_color='black'))
        fig = apply_chart_style(fig, title="按 Top AIDA 和测试周分类的状态", height=max(600, len(sorted_aidas) * 35 + 150))
        
        return fig
        
    except Exception as e:
        print(f"创建Top AIDA图表失败: {e}")
        return create_empty_figure("Top AIDA测试状态分布 (创建失败)", height=400)

def create_testcase_detail_chart(filtered_data, has_active_filters=False):
    """创建测试用例详细分析图 - 支持点击交互"""
    if filtered_data.empty:
        return create_empty_figure("测试用例详细分析 (无数据)", height=600)
    
    try:
        # 优先使用native_status列，如果不存在则使用run_status列
        status_column = None
        if 'native_status' in filtered_data.columns:
            status_column = 'native_status'
        elif 'run_status' in filtered_data.columns:
            status_column = 'run_status'
        else:
            return create_empty_figure("错误: 缺少状态列 ('native_status' 或 'run_status')", height=600)
        
        # 检查必要的列
        required_cols = ['test_id', 'test_name', 'top_aida', 'test_week']
        if not all(col in filtered_data.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in filtered_data.columns]
            return create_empty_figure(f"错误: 缺少列 {', '.join(missing_cols)}", height=600)
        
        # 创建数据副本并处理状态数据
        data_for_processing = filtered_data.copy()
        
        # 处理状态数据，提取字典中的name字段或直接使用字符串值
        def extract_status_name(status):
            if isinstance(status, dict) and 'name' in status:
                return status['name']
            return str(status) if status is not None else 'Unknown'
        
        # 应用状态提取
        data_for_processing['processed_status'] = data_for_processing[status_column].apply(extract_status_name)
        
        # 状态映射（与test status analysis保持一致）
        status_mapping = {
            'passed': 'Passed',
            'failed': 'Failed', 
            'blocked': 'Blocked',
            'planned': 'Planned',
            'not_completed': 'In Progress',
            'skipped': 'Skipped',
            'in_progress': 'In Progress',
            'requires attention': 'Blocked'  # 将Requires Attention映射为Blocked
        }
        
        # 应用状态映射
        data_for_processing['mapped_status'] = data_for_processing['processed_status'].map(
            lambda x: status_mapping.get(x.lower() if isinstance(x, str) else str(x).lower(), x)
        )
        
        # 智能数据限制逻辑：只有在所有筛选器都是默认值时才限制数据量
        MAX_TEST_CASES_DEFAULT = 50  # 默认情况下限制显示的测试用例数量
        unique_test_cases = data_for_processing['test_id'].nunique()
        
        if not has_active_filters and unique_test_cases > MAX_TEST_CASES_DEFAULT:
            # 所有筛选器都是默认值，限制显示数量
            print(f"所有筛选器为默认值，测试用例数量过多({unique_test_cases})，限制显示前{MAX_TEST_CASES_DEFAULT}个最活跃的测试用例")
            # 选择最频繁执行的测试用例
            top_test_cases = data_for_processing['test_id'].value_counts().head(MAX_TEST_CASES_DEFAULT).index
            display_data = data_for_processing[data_for_processing['test_id'].isin(top_test_cases)]
            data_limitation_note = f"注意：共有{unique_test_cases}个测试用例，默认显示前{MAX_TEST_CASES_DEFAULT}个最活跃的用例。使用筛选器可查看完整数据。"
        else:
            # 有筛选条件或数据量不大，显示完整数据
            display_data = data_for_processing
            if has_active_filters:
                data_limitation_note = f"已应用筛选条件，显示{unique_test_cases}个测试用例的完整数据"
            else:
                data_limitation_note = ""
            print(f"显示完整数据：{unique_test_cases}个测试用例")
        
        # 按测试用例和测试周分组，保留更多字段用于hover显示
        groupby_columns = ['test_week', 'test_id', 'test_name', 'mapped_status', 'top_aida']
        
        # 添加hover需要的字段
        extra_columns = []
        if 'project' in display_data.columns:
            extra_columns.append('project')
        if 'pu' in display_data.columns:
            extra_columns.append('pu')
        if 'tester' in display_data.columns:
            extra_columns.append('tester')
        
        # 添加Manual Run相关字段
        if 'id' in display_data.columns:
            extra_columns.append('id')  # manual run的id
        if 'mr_id' in display_data.columns:
            extra_columns.append('mr_id')
        if 'execution_id' in display_data.columns:
            extra_columns.append('execution_id')
        if 'test_execution_id' in display_data.columns:
            extra_columns.append('test_execution_id')
        if 'run_id' in display_data.columns:
            extra_columns.append('run_id')
        
        # 先进行分组计数
        detail_data = display_data.groupby(groupby_columns).size().reset_index(name='count')
        
        # 添加额外信息（优化版本 - 使用groupby避免O(n²)复杂度）
        if extra_columns:
            # 为每个额外列创建聚合数据
            for col in extra_columns:
                if col in display_data.columns:
                    if col in ['id', 'mr_id', 'execution_id', 'test_execution_id', 'run_id']:
                        # 对于ID类字段，聚合所有唯一值
                        agg_data = display_data.groupby(['test_week', 'test_id', 'mapped_status'])[col].apply(
                            lambda x: ', '.join(sorted(set(str(val) for val in x.dropna() 
                                                      if str(val) not in ['nan', '', 'None'])))
                        ).reset_index()
                        agg_data.rename(columns={col: f'{col}_agg'}, inplace=True)
                        detail_data = detail_data.merge(agg_data, on=['test_week', 'test_id', 'mapped_status'], how='left')
                        detail_data[col] = detail_data[f'{col}_agg'].fillna('')
                        detail_data.drop(f'{col}_agg', axis=1, inplace=True)
                    else:
                        # 对于其他字段，取第一个值
                        agg_data = display_data.groupby(['test_week', 'test_id', 'mapped_status'])[col].first().reset_index()
                        detail_data = detail_data.merge(agg_data, on=['test_week', 'test_id', 'mapped_status'], how='left')
                        detail_data[col] = detail_data[col].fillna('')
        
        if detail_data.empty:
            return create_empty_figure("测试用例详细分析 (分组后无数据)", height=600)
        
        # 过滤有效的测试周
        extract_pattern = r'(\d{2})-CW(\d{2})'
        valid_week_mask = detail_data['test_week'].astype(str).str.match(extract_pattern)
        detail_data = detail_data[valid_week_mask.fillna(False)]
        
        if detail_data.empty:
            return create_empty_figure("测试用例详细分析 (无有效周数据)", height=600)
        
        # 排序
        detail_data['test_week_str'] = detail_data['test_week'].astype(str)
        extracted_sort_keys = detail_data['test_week_str'].str.extract(extract_pattern)
        detail_data['sort_year'] = pd.to_numeric(extracted_sort_keys[0], errors='coerce').fillna(99).astype(int)
        detail_data['sort_week'] = pd.to_numeric(extracted_sort_keys[1], errors='coerce').fillna(99).astype(int)
        
        try:
            detail_data['test_id_numeric'] = pd.to_numeric(detail_data['test_id'])
            detail_data = detail_data.sort_values(["sort_year", "sort_week", "test_id_numeric"])
        except (ValueError, TypeError):
            detail_data = detail_data.sort_values(["sort_year", "sort_week", "test_id"])
        
        # 创建Y轴标签（测试ID + 名称，截断过长的名称）
        max_name_len = 30
        detail_data['y_axis_label'] = detail_data.apply(
            lambda row: f"{row['test_id']} - {str(row['test_name'])[:max_name_len]}{'...' if len(str(row['test_name'])) > max_name_len else ''}", 
            axis=1
        )
        
        # 创建完整的hover名称
        detail_data['hover_name_full'] = detail_data['test_id'].astype(str) + " - " + detail_data['test_name'].astype(str)
        
        # 限制Y轴标签数量
        unique_labels = detail_data['y_axis_label'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        if len(unique_labels) > 100:  # 进一步限制
            unique_labels = unique_labels[:100]
            detail_data = detail_data[detail_data['y_axis_label'].isin(unique_labels)]
        
        sorted_weeks = detail_data['test_week'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        sorted_y_labels = detail_data['y_axis_label'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()
        
        # 创建标题（包含数据限制信息）
        chart_title = "按测试用例和测试周分类的状态 (气泡图)"
        if data_limitation_note:
            chart_title += f"<br><sub>{data_limitation_note}</sub>"
        
        # 创建气泡图，包含custom_data以支持点击交互
        fig = px.scatter(
            detail_data, 
            x='test_week', 
            y='y_axis_label',
            size='count',
            color='mapped_status',
            title=chart_title,
            labels={'test_week': '测试周', 'y_axis_label': '测试用例 (ID - 名称)', 'count': '执行次数', 'mapped_status': '状态'},
            color_discrete_map=color_map,
            category_orders={
                'test_week': list(sorted_weeks), 
                'y_axis_label': list(sorted_y_labels), 
                'mapped_status': list(color_map.keys())
            },
            custom_data=["top_aida", "mapped_status"] + [col for col in extra_columns if col in detail_data.columns],  # 重要：为hover提供更多数据
            hover_name='hover_name_full',
            size_max=15,
            opacity=0.7
        )
        
        # 优化布局
        chart_height = min(1200, max(600, len(sorted_y_labels) * 20 + 200))
        
        fig.update_layout(
            height=chart_height,
            margin=dict(l=350, r=60, t=120, b=80),
            xaxis={'tickangle': -45}, 
            yaxis={
                'type': 'category', 
                'categoryorder':'array', 
                'categoryarray': list(sorted_y_labels), 
                'tickmode': 'linear',
                'tickfont': {'size': 8},
                'tickangle': 0,
                'automargin': True
            }, 
            xaxis_title="测试周", 
            yaxis_title="测试用例 (ID - 名称)",
            legend_title_text="运行状态",
            xaxis_showgrid=True, 
            yaxis_showgrid=True, 
            plot_bgcolor='rgba(248, 248, 250, 0.5)'
        )
        
        # 动态构建hover模板
        hover_template = ('<b>%{hovertext}</b><br>' +
                         '测试周: %{x}<br>' +
                         '<b>状态: %{customdata[1]}</b><br>' +
                         '执行次数: %{marker.size}<br>' +
                         'Top AIDA: %{customdata[0]}<br>')
        
        # 添加额外字段到hover模板
        if extra_columns:
            for i, col in enumerate(extra_columns):
                if col in detail_data.columns:
                    col_display_name = {
                        'project': '项目',
                        'pu': 'PU',
                        'tester': '测试员',
                        'id': 'Manual Run ID',
                        'mr_id': 'MR ID',
                        'execution_id': '执行ID',
                        'test_execution_id': '测试执行ID',
                        'run_id': '运行ID'
                    }.get(col, col)
                    hover_template += f'{col_display_name}: %{{customdata[{i+2}]}}<br>'
        
        hover_template += '<extra></extra>'
        
        # 更新hover模板和marker样式
        fig.update_traces(
            hovertemplate=hover_template,
            marker=dict(
                sizemode='area',
                sizemin=2,
                line_width=0.5,
                line_color='black'
            )
        )
        
        fig = apply_chart_style(fig, title="按测试用例和测试周分类的状态", height=chart_height)
        
        return fig
        
    except Exception as e:
        print(f"创建测试用例详细图表失败: {e}")
        import traceback
        traceback.print_exc()
        return create_empty_figure("测试用例详细分析 (创建失败)", height=600)

# === Phase 1 新增图表函数 ===

def create_pass_rate_trend_chart(filtered_data):
    """创建测试通过率趋势图 - 按周统计通过率"""
    if filtered_data.empty:
        return create_empty_figure("测试通过率趋势 (无数据)", height=400)
    
    try:
        # 检查必要的列
        required_cols = ['test_week', 'run_status']
        if not all(col in filtered_data.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in filtered_data.columns]
            return create_empty_figure(f"错误: 缺少列 {', '.join(missing_cols)}", height=400)
        
        # 过滤有效的测试周
        extract_pattern = r'(\d{2})-CW(\d{2})'
        valid_week_mask = filtered_data['test_week'].astype(str).str.match(extract_pattern)
        data_for_trend = filtered_data[valid_week_mask.fillna(False)]
        
        if data_for_trend.empty:
            return create_empty_figure("测试通过率趋势 (无有效周数据)", height=400)
        
        # 按测试周和状态分组统计
        status_by_week = data_for_trend.groupby(['test_week', 'run_status']).size().unstack(fill_value=0)
        
        # 计算通过率
        status_by_week['total'] = status_by_week.sum(axis=1)
        status_by_week['pass_rate'] = (status_by_week.get('Passed', 0) / status_by_week['total'] * 100).round(2)
        status_by_week['fail_rate'] = (status_by_week.get('Failed', 0) / status_by_week['total'] * 100).round(2)
        status_by_week['other_rate'] = (100 - status_by_week['pass_rate'] - status_by_week['fail_rate']).round(2)
        
        # 排序测试周
        trend_data = status_by_week.reset_index()
        trend_data['test_week_str'] = trend_data['test_week'].astype(str)
        extracted_sort_keys = trend_data['test_week_str'].str.extract(extract_pattern)
        trend_data['sort_year'] = pd.to_numeric(extracted_sort_keys[0], errors='coerce').fillna(99).astype(int)
        trend_data['sort_week'] = pd.to_numeric(extracted_sort_keys[1], errors='coerce').fillna(99).astype(int)
        trend_data = trend_data.sort_values(["sort_year", "sort_week"])
        
        # 创建多线条趋势图
        fig = go.Figure()
        
        # 添加通过率线
        fig.add_trace(go.Scatter(
            x=trend_data['test_week'],
            y=trend_data['pass_rate'],
            mode='lines+markers',
            name='通过率',
            line=dict(color='green', width=3),
            marker=dict(size=8),
            text=[f'通过率: {rate}%<br>总数: {total}' for rate, total in zip(trend_data['pass_rate'], trend_data['total'])],
            hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>'
        ))
        
        # 添加失败率线
        fig.add_trace(go.Scatter(
            x=trend_data['test_week'],
            y=trend_data['fail_rate'],
            mode='lines+markers',
            name='失败率',
            line=dict(color='red', width=3),
            marker=dict(size=8),
            text=[f'失败率: {rate}%<br>总数: {total}' for rate, total in zip(trend_data['fail_rate'], trend_data['total'])],
            hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>'
        ))
        
        # 添加其他状态率线
        if trend_data['other_rate'].sum() > 0:
            fig.add_trace(go.Scatter(
                x=trend_data['test_week'],
                y=trend_data['other_rate'],
                mode='lines+markers',
                name='其他状态',
                line=dict(color='orange', width=2),
                marker=dict(size=6),
                text=[f'其他: {rate}%<br>总数: {total}' for rate, total in zip(trend_data['other_rate'], trend_data['total'])],
                hovertemplate='<b>%{x}</b><br>%{text}<extra></extra>'
            ))
        
        # 添加90%辅助虚线
        fig.add_hline(
            y=90,
            line_dash="dash",
            line_color="gray",
            line_width=2,
            annotation_text="目标线 90%",
            annotation_position="bottom right",
            annotation_font_size=12,
            annotation_font_color="gray"
        )
        
        fig.update_layout(
            title="测试通过率趋势分析",
            xaxis_title="测试周",
            yaxis_title="比例 (%)",
            height=400,
            xaxis={'tickangle': -45},
            yaxis={'range': [0, 100]},
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode='x unified'
        )
        
        fig = apply_chart_style(fig, title="测试通过率趋势分析", height=400)
        return fig
        
    except Exception as e:
        print(f"创建测试通过率趋势图失败: {e}")
        return create_empty_figure("测试通过率趋势 (创建失败)", height=400)


def create_test_aida_wordcloud(filtered_data):
    """创建测试热点AIDA词云图"""
    if not WORDCLOUD_AVAILABLE:
        # 如果wordcloud不可用，返回空图表
        fig = go.Figure()
        fig.update_layout(
            title="测试热点AIDA词云图 (词云库不可用)",
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
    
    if filtered_data.empty:
        return create_empty_figure("测试热点AIDA词云图 (无数据)", height=500)
    
    try:
        # 检查必要的列
        if 'top_aida' not in filtered_data.columns:
            return create_empty_figure("错误: 缺少 top_aida 列", height=500)
        
        # 过滤掉空字符串、None、NaN 和 'Unknown'
        text_series = filtered_data['top_aida'].dropna().astype(str)
        text_series = text_series[text_series.str.strip() != '']
        text_series = text_series[text_series.str.lower() != 'unknown']
        
        if text_series.empty:
            fig = go.Figure()
            fig.update_layout(
                title="测试热点AIDA词云图 (无有效数据)",
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
        text = ' '.join(text_series.str.lower().tolist())
        
        # 准备停用词集合
        stopwords = set(STOPWORDS)
        additional_common_words = {'tsp', 'cn', 'iuk', 'dips', 'bmw', 'sys', 'mini', 'evo',
                                   'manage', 'aisa', 'provide', 'test', 'via', 'connected',
                                   'international', 'service', 'control', 'asia',
                                   'remote', 'display', 'china', 'chinese'}
        stopwords.update(additional_common_words)
        
        # 创建词云对象 - 增大尺寸和清晰度
        wordcloud = WordCloud(
            width=1200, height=600,
            background_color=None,  # 透明背景
            mode='RGBA',
            stopwords=stopwords,
            collocations=False,
            max_words=150,
            relative_scaling=0.6,
            colormap='viridis',
            prefer_horizontal=0.7,
            min_font_size=12,
            max_font_size=100
        ).generate(text)
        
        # 生成词云图片 - 更大尺寸和更高DPI
        plt.figure(figsize=(12, 6), facecolor='none')
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis('off')
        plt.tight_layout(pad=0)
        
        # 将图片转换为base64 - 提高DPI获得更清晰效果
        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150, 
                   transparent=True, facecolor='none', edgecolor='none')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close()  # 关闭图片以释放内存
        
        # 创建Plotly图表
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
        
        # 设置图表布局
        fig.update_layout(
            height=500,
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, visible=False),
            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, visible=False),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=40, b=0)
        )
        
        fig = apply_chart_style(fig, title="测试热点AIDA词云图", height=500)
        return fig
        
    except Exception as e:
        print(f"创建测试AIDA词云图失败: {e}")
        return create_empty_figure("测试热点AIDA词云图 (创建失败)", height=500)


def create_enhanced_status_distribution_pie(filtered_data):
    """创建优化的测试执行状态分布饼图"""
    if filtered_data.empty:
        return create_empty_figure("测试状态分布 (无数据)", height=400)
    
    try:
        # 优先使用native_status列，如果不存在则使用run_status列
        status_column = None
        if 'native_status' in filtered_data.columns:
            status_column = 'native_status'
        elif 'run_status' in filtered_data.columns:
            status_column = 'run_status'
        else:
            return create_empty_figure("错误: 缺少状态列 ('native_status' 或 'run_status')", height=400)
        
        # 处理状态数据，提取字典中的name字段或直接使用字符串值
        def extract_status_name(status):
            if isinstance(status, dict) and 'name' in status:
                return status['name']
            return str(status) if status is not None else 'Unknown'
        
        # 应用状态提取和映射
        status_series = filtered_data[status_column].apply(extract_status_name)
        
        # 状态映射（与test status analysis保持一致）
        status_mapping = {
            'passed': 'Passed',
            'failed': 'Failed', 
            'blocked': 'Blocked',
            'planned': 'Planned',
            'not_completed': 'In Progress',
            'skipped': 'Skipped',
            'in_progress': 'In Progress',
            'requires attention': 'Blocked'  # 将Requires Attention映射为Blocked
        }
        
        # 应用状态映射
        mapped_status = status_series.map(lambda x: status_mapping.get(x.lower() if isinstance(x, str) else str(x).lower(), x))
        
        # 统计各状态数量
        status_counts = mapped_status.value_counts()
        
        if status_counts.empty:
            return create_empty_figure("测试状态分布 (无状态数据)", height=400)
        
        # 计算百分比
        total_count = status_counts.sum()
        status_percentages = (status_counts / total_count * 100).round(1)
        
        # 定义颜色映射（与现有color_map保持一致）
        color_mapping = {
            "Passed": "#28a745",      # 绿色
            "Failed": "#dc3545",      # 红色
            "Requires Attention": "#ffc107",  # 黄色
            "Planned": "#6c757d",     # 灰色
            "In Progress": "#17a2b8", # 蓝色
            "Blocked": "#fd7e14",     # 橙色
            "Skipped": "#e83e8c"      # 粉色
        }
        
        # 为饼图准备颜色
        colors = [color_mapping.get(status, "#6c757d") for status in status_counts.index]
        
        # 创建饼图
        fig = go.Figure(data=[go.Pie(
            labels=status_counts.index,
            values=status_counts.values,
            hole=0.4,  # 创建环形图
            marker_colors=colors,
            textinfo='label+percent+value',
            texttemplate='%{label}<br>%{percent}<br>(%{value}个)',
            hovertemplate='<b>%{label}</b><br>数量: %{value}<br>占比: %{percent}<extra></extra>',
            textfont_size=12,
            pull=[0.1 if status == status_counts.index[0] else 0 for status in status_counts.index]  # 突出显示最大的扇形
        )])
        
        # 添加中心文本
        fig.add_annotation(
            text=f"总计<br>{total_count}",
            x=0.5, y=0.5,
            font_size=16,
            showarrow=False
        )
        
        fig.update_layout(
            title="测试执行状态分布",
            height=400,
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.05
            ),
            margin=dict(l=60, r=120, t=80, b=60)
        )
        
        fig = apply_chart_style(fig, title="测试执行状态分布", height=400)
        return fig
        
    except Exception as e:
        print(f"创建状态分布饼图失败: {e}")
        return create_empty_figure("测试状态分布 (创建失败)", height=400)
