import dash
from dash import dcc, html
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from dash.dependencies import Input, Output, State
import numpy as np # Needed for np.where
from dash import callback_context # 用于识别触发回调的组件
import traceback # 用于打印详细错误
import dash_bootstrap_components as dbc # 导入 dbc

# --- 安全列访问函数 ---
def safe_get_unique_values(df, column_name, default_list=None):
    """安全地获取列的唯一值，如果列不存在则返回默认列表"""
    if default_list is None:
        default_list = []
    
    if column_name not in df.columns or df.empty:
        return default_list
    
    try:
        return sorted(df[column_name].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).unique())
    except Exception as e:
        print(f"处理列 '{column_name}' 时出错: {e}. 使用默认值.")
        return default_list

# --- Feature Region映射函数 ---
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
        'Provide Navigation 2.0 [01.04.03.01.03.06]'
    ]
    
    # 检查是否在中国特有功能列表中
    if str(top_aida).strip() in china_specific_aidas:
        return 'China Specific'
    else:
        return 'Global'

# --- 1. 加载数据 --- 
from data_processor import load_test_data # 从新文件导入函数
tdf = load_test_data() # 调用函数加载数据

# 添加Feature Region列
if 'top_aida' in tdf.columns:
    tdf['feature_region'] = tdf['top_aida'].apply(get_feature_region)
    print(f"Feature Region分布: {tdf['feature_region'].value_counts().to_dict()}")
else:
    print("警告: 'top_aida' 列不存在，无法创建 Feature Region 列")
    tdf['feature_region'] = 'Global'  # 默认值

# --- 配置 ---
px.defaults.template = "simple_white"
color_map = {
    "Passed": "lightgreen",  # 浅绿
    "Failed": "lightcoral",  # 浅红
    "Requires Attention": "khaki", # 浅黄 (替换原来的 orange)
    "Planned": "lightgrey",   # 浅灰
    # 你可以根据需要添加或修改其他状态的颜色
}

# --- 2. 初始化 Dash 应用 ---
# 使用 Bootstrap 主题
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP]) 
app.title = "测试覆盖率看板" # 设置浏览器标签页标题

# --- 3. 定义应用布局 ---

# === 修改: 在布局前准备 Top AIDA 选项 ===
# 检查 'top_aida' 列是否存在且不为空
if 'top_aida' in tdf.columns and not tdf['top_aida'].isnull().all():
    try:
        # 获取 top_aida 列的唯一、非空字符串值
        unique_top_aidas = sorted(tdf['top_aida'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().astype(str).unique())
        # 过滤掉空字符串 (如果存在)
        unique_top_aidas = [aida for aida in unique_top_aidas if aida]
        print(f"生成的 Top AIDA 选项数量: {len(unique_top_aidas)}")
    except Exception as e:
        print(f"处理 Top AIDA 列时出错: {e}. 使用空列表代替.")
        unique_top_aidas = []
else:
    print("警告: 'top_aida' 列不存在或全为空，无法生成 Top AIDA 下拉选项。")
    unique_top_aidas = []
# === 修改结束 ===

app.layout = dbc.Container([ # 使用 dbc.Container 作为最外层容器
    dbc.Row(dbc.Col(html.H1("测试覆盖率看板", className="text-center my-4"))), # 使用 dbc 类进行样式调整

    # --- Filters ---
    dbc.Card([ # 将过滤器放入 Card 中
        dbc.CardHeader("筛选器"),
        dbc.CardBody([
            dbc.Row([ # 第一行过滤器
                dbc.Col([
                    dbc.Label("Project:", html_for='project-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='project-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                                [{'label': i, 'value': i} for i in safe_get_unique_values(tdf, 'project')],
                        value=['all'], multi=True, placeholder="选择 Project..."
                    )
                ], md=4), # 中等屏幕及以上占 4 列
                dbc.Col([
                    dbc.Label("Test Week:", html_for='testweek-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='testweek-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                        [{'label': i, 'value': i} for i in sorted(
                            [wk for wk in safe_get_unique_values(tdf, 'test_week') if isinstance(wk, str)], # 确保是字符串再排序
                            key=lambda x: (int(x.split('-')[0]) if '-' in x and x.split('-')[0].isdigit() else 99,
                                         int(x.split('CW')[1]) if 'CW' in x and x.split('CW')[1].isdigit() else 99)
                        )],
                         value=['all'], multi=True, placeholder="选择 Test Week..."
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("PU:", html_for='pu-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='pu-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                                [{'label': i, 'value': i} for i in safe_get_unique_values(tdf, 'pu')],
                         value=['all'], multi=True, placeholder="选择 PU..."
                    )
                ], md=4),
            ], className="mb-3"), # 添加下边距
            dbc.Row([ # 第二行过滤器
                 dbc.Col([
                    dbc.Label("Top AIDA:", html_for='aida-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='aida-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                                [{'label': i, 'value': i} for i in unique_top_aidas],
                         value=['all'], multi=True, placeholder="选择 Top AIDA..."
                    )
                    ], md=3),
                dbc.Col([
                    dbc.Label("Feature Region:", html_for='feature-region-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='feature-region-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                                [{'label': i, 'value': i} for i in safe_get_unique_values(tdf, 'feature_region')],
                         value=['all'], multi=True, placeholder="选择 Feature Region..."
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("FVP:", html_for='fvp-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='fvp-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                                [{'label': i, 'value': i} for i in safe_get_unique_values(tdf, 'fvp')],
                         value=['all'], multi=True, placeholder="选择 FVP..."
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("FV:", html_for='fv-dropdown', style={'fontWeight': 'bold'}),
                    dcc.Dropdown(
                        id='fv-dropdown',
                        options=[{'label': '全部', 'value': 'all'}] +
                                [{'label': i, 'value': i} for i in safe_get_unique_values(tdf, 'fv')],
                         value=['all'], multi=True, placeholder="选择 FV..."
                    )
                ], md=3),
            ])
        ])
    ], className="mb-4"), # Card 与下方图表间距

    # --- Charts ---
    dbc.Row([ # 图表行
        dbc.Col([ # 图表列
            dbc.Card([ # 图表1 Card
                dbc.CardHeader("图表 1: 按周和功能分类的测试状态"),
                dbc.CardBody([
                    dcc.Loading(
                        id="loading-graph-1", type="circle",
                        children=dcc.Graph(id='coverage-bubble-chart', clear_on_unhover=True)
                    )
                ])
            ])
        ], md=12, className="mb-4") # 占满整行，添加下边距
    ]),
    dbc.Row([ # 图表行
        dbc.Col([ # 图表列
            dbc.Card([ # 图表2 Card
                dbc.CardHeader("图表 2: 按 Top AIDA 和测试周分类的状态"),
                dbc.CardBody([
                    dcc.Loading(
                        id="loading-graph-2", type="circle",
                        children=dcc.Graph(id='aida-vs-week-chart', clear_on_unhover=True)
                    )
                ])
            ])
        ], md=12, className="mb-4") # 占满整行，添加下边距
    ]),
     dbc.Row([ # 图表行
        dbc.Col([ # 图表列
            dbc.Card([ # 图表3 Card
                dbc.CardHeader("图表 3: 按测试用例和测试周分类的状态"),
                dbc.CardBody([
                    dcc.Loading(
                        id="loading-graph-3",
                        type="circle",
                        children=dcc.Graph(id='test-vs-week-chart', clear_on_unhover=True)
                    )
                ])
            ])
        ], md=12, className="mb-4") # 占满整行，添加下边距
    ])

], fluid=True) # 设置 Container 为 fluid

# --- 4. 定义回调函数 (重构以支持点击筛选) ---
@app.callback(
    [Output('coverage-bubble-chart', 'figure'),
     Output('aida-vs-week-chart', 'figure'),
     Output('test-vs-week-chart', 'figure'),
     Output('fv-dropdown', 'value'),       
     Output('aida-dropdown', 'value')],    
    [Input('project-dropdown', 'value'),
     Input('testweek-dropdown', 'value'),
     Input('pu-dropdown', 'value'),
     Input('aida-dropdown', 'value'),      
     Input('feature-region-dropdown', 'value'),
     Input('fvp-dropdown', 'value'),
     Input('fv-dropdown', 'value'),        
     Input('coverage-bubble-chart', 'clickData'), 
     Input('aida-vs-week-chart', 'clickData'),    
     Input('test-vs-week-chart', 'clickData')],   
    [State('fv-dropdown', 'value'),       
     State('aida-dropdown', 'value')]     
)
def update_graph(selected_projects, selected_testweeks, selected_pus,
                 selected_aidas_input, selected_feature_regions, selected_fvps, selected_fvs_input, 
                 click_data_fv, click_data_aida, click_data_test, 
                 fv_state, aida_state): 
    
    print("--- Callback triggered ---")
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'No trigger'
    print(f"Triggered by: {triggered_id}")

    # --- Create Figure Helpers ---
    def create_empty_figure(message="没有符合筛选条件的数据"):
        fig = go.Figure()
        fig.update_layout(
            xaxis={"visible": False}, yaxis={"visible": False},
            annotations=[{"text": message, "xref": "paper", "yref": "paper", "showarrow": False, "font": {"size": 20}}],
            plot_bgcolor='rgba(248, 248, 250, 0.5)'
        )
        return fig

    def is_filter_active(selected_values):
        # 确保 selected_values 是列表且不只包含 'all'
        return isinstance(selected_values, list) and selected_values and 'all' not in selected_values

    # --- 处理点击事件和更新筛选状态 ---
    # 优先使用 State 获取下拉菜单的当前值
    current_fvs = list(fv_state) if isinstance(fv_state, list) else []
    current_aidas = list(aida_state) if isinstance(aida_state, list) else []
    print(f"Initial state: fvs={current_fvs}, aidas={current_aidas}")

    clicked_value = None
    filter_type = None # 'fv' or 'aida'

    if triggered_id == 'coverage-bubble-chart' and click_data_fv:
        clicked_value = click_data_fv['points'][0]['y']
        filter_type = 'fv'
        print(f"Chart 1 clicked. Value: {clicked_value}")
    elif triggered_id == 'aida-vs-week-chart' and click_data_aida:
        clicked_value = click_data_aida['points'][0]['y']
        filter_type = 'aida'
        print(f"Chart 2 clicked. Value: {clicked_value}")
    elif triggered_id == 'test-vs-week-chart' and click_data_test:
        custom_data = click_data_test['points'][0].get('customdata')
        print(f"Chart 3 clicked. Customdata: {custom_data}")
        # 假设 top_aida 是 custom_data 的第一个元素 (在 hover_data 中显式指定)
        if isinstance(custom_data, list) and len(custom_data) > 0:
            clicked_value = custom_data[0] 
            if clicked_value:
                filter_type = 'aida'
                print(f"Chart 3 extracted AIDA: {clicked_value}")
        else:
             print("警告: 图表3点击事件缺少有效的 customdata[0] (top_aida)")

    # 更新筛选列表
    output_fvs = current_fvs.copy()
    output_aidas = current_aidas.copy()

    if filter_type == 'fv' and clicked_value:
        if 'all' in output_fvs:
            output_fvs = [clicked_value] # 如果是'all', 直接替换
        elif clicked_value in output_fvs:
            output_fvs.remove(clicked_value)
            if not output_fvs: # 如果移除后为空，设为'all'
                output_fvs = ['all']
        else:
            output_fvs.append(clicked_value) # 添加新值
        print(f"FV list updated: {output_fvs}")
            
    elif filter_type == 'aida' and clicked_value:
        if 'all' in output_aidas:
            output_aidas = [clicked_value] # 如果是'all', 直接替换
        elif clicked_value in output_aidas:
            output_aidas.remove(clicked_value)
            if not output_aidas: # 如果移除后为空，设为'all'
                output_aidas = ['all']
        else:
            output_aidas.append(clicked_value) # 添加新值
        print(f"AIDA list updated: {output_aidas}")
        
    # 如果没有点击事件触发，或者点击事件没有有效值，则使用下拉菜单的输入值
    # 这确保了下拉菜单本身的更改也能触发更新
    if filter_type is None: 
        output_fvs = list(selected_fvs_input) if isinstance(selected_fvs_input, list) else []
        output_aidas = list(selected_aidas_input) if isinstance(selected_aidas_input, list) else []
        # 确保列表不为空，否则设为 'all'
        if not output_fvs: output_fvs = ['all']
        if not output_aidas: output_aidas = ['all']
        print(f"No click or invalid click, using input values: fvs={output_fvs}, aidas={output_aidas}")


    # --- Filter Data (使用最终确定的筛选值) ---
    print(f"Filtering with: fvs={output_fvs}, aidas={output_aidas}, feature_regions={selected_feature_regions}")
    filtered_tdf = tdf.copy()
    if is_filter_active(selected_projects):
        filtered_tdf = filtered_tdf[filtered_tdf['project'].isin(selected_projects)]
    if is_filter_active(selected_testweeks):
        filtered_tdf = filtered_tdf[filtered_tdf['test_week'].isin(selected_testweeks)]
    if is_filter_active(selected_pus):
        filtered_tdf = filtered_tdf[filtered_tdf['pu'].isin(selected_pus)]
    if is_filter_active(output_aidas): 
        if 'top_aida' in filtered_tdf.columns:
            try:
                filtered_tdf = filtered_tdf[filtered_tdf['top_aida'].isin(output_aidas)]
            except Exception as e:
                print(f"Error applying Top AIDA filter: {e}")
                empty_fig = create_empty_figure("Top AIDA 筛选时出错")
                return empty_fig, empty_fig, empty_fig, output_fvs, output_aidas 
        else:
            print("警告: Top AIDA filter selected but 'top_aida' column missing.")
            empty_fig = create_empty_figure("错误: 'top_aida' 列不存在")
            return empty_fig, empty_fig, empty_fig, output_fvs, output_aidas 

    if is_filter_active(selected_feature_regions):
        if 'feature_region' in filtered_tdf.columns:
            try:
                filtered_tdf = filtered_tdf[filtered_tdf['feature_region'].isin(selected_feature_regions)]
            except Exception as e:
                print(f"Error applying Feature Region filter: {e}")
                empty_fig = create_empty_figure("Feature Region 筛选时出错")
                return empty_fig, empty_fig, empty_fig, output_fvs, output_aidas 
        else:
            print("警告: Feature Region filter selected but 'feature_region' column missing.")
            empty_fig = create_empty_figure("错误: 'feature_region' 列不存在")
            return empty_fig, empty_fig, empty_fig, output_fvs, output_aidas 

    if is_filter_active(selected_fvps):
        filtered_tdf = filtered_tdf[filtered_tdf['fvp'].isin(selected_fvps)]
    if is_filter_active(output_fvs):
        filtered_tdf = filtered_tdf[filtered_tdf['fv'].isin(output_fvs)]

    # --- Check if Filtered Data is Empty --- 
    if filtered_tdf.empty:
        print("Filtered data is empty.")
        empty_fig = create_empty_figure()
        return empty_fig, empty_fig, empty_fig, output_fvs, output_aidas 

    # --- Check for Count Column --- 
    count_col = None
    if 'test_case_id' in filtered_tdf.columns:
        count_col = 'test_case_id'
    elif 'id' in filtered_tdf.columns:
        count_col = 'id'
        
    if count_col is None:
        print(f"警告: 无法找到用于计数的列 ('test_case_id' 或 'id').")
        error_fig = create_empty_figure("错误：缺少用于计数的列")
        return error_fig, error_fig, error_fig, output_fvs, output_aidas 
        
    # ====================================
    # --- Chart 1: Bubble Chart (FV vs Week) ---
    # ====================================
    fig1 = create_empty_figure("图表1加载中...") 
    try:
        grouped_data1 = filtered_tdf.groupby(
            ["test_week", "fvp", "fv", "run_status"], as_index=False
        )[count_col].nunique().rename(columns={count_col: 'count'}) 
        
        extract_pattern = r'(\d{2})-CW(\d{2})' 
        valid_week_mask = grouped_data1['test_week'].astype(str).str.match(extract_pattern)
        grouped_data1 = grouped_data1[valid_week_mask.fillna(False)]
        
        if grouped_data1.empty:
             print("警告: 过滤无效周后，图表1数据为空")
             fig1 = create_empty_figure("无有效周数据显示")
        else:
            grouped_data1['test_week_str'] = grouped_data1['test_week'].astype(str)
            extracted_sort_keys1 = grouped_data1['test_week_str'].str.extract(extract_pattern)
            grouped_data1['sort_year'] = pd.to_numeric(extracted_sort_keys1[0], errors='coerce').fillna(99).astype(int)
            grouped_data1['sort_week'] = pd.to_numeric(extracted_sort_keys1[1], errors='coerce').fillna(99).astype(int)
            grouped_data1 = grouped_data1.sort_values(["sort_year", "sort_week", "fvp", "fv"])
            sorted_weeks1 = grouped_data1['test_week'].dropna().unique()
            sorted_fvs1 = grouped_data1.sort_values(['fvp', 'fv'])['fv'].dropna().unique()

            fig1 = px.scatter(
                grouped_data1, x="test_week", y="fv", color="run_status", size="count",
                size_max=40, opacity=0.8,
                hover_data={"test_week": True, "fvp": True, "fv": True, "run_status": True, "count": True, "sort_year": False, "sort_week": False},
                labels={"test_week": "测试周", "fv": "功能 (FV)", "run_status": "运行状态", "count": "测试数量", "fvp": "FVP"},
                color_discrete_map=color_map,
                category_orders={"test_week": list(sorted_weeks1), "fv": list(sorted_fvs1), "run_status": list(color_map.keys())}
            )
            fig1.update_layout(
                height=800, xaxis={'tickangle': -45}, yaxis={}, xaxis_title="测试周", yaxis_title="功能 (FV)",
                title="按周和功能分类的测试状态 (气泡图)", showlegend=True, legend_title_text="运行状态",
                xaxis_showgrid=True, yaxis_showgrid=True, plot_bgcolor='rgba(248, 248, 250, 0.5)',
                hoverlabel=dict(bgcolor="white", font_size=12, font_family="Rockwell")
            )
            fig1.update_traces(marker=dict(sizemode='area', line_width=1, line_color='black'))

    except Exception as e:
        print(f"创建图表1时出错: {e}")
        traceback.print_exc()
        fig1 = create_empty_figure(f"创建图表1时出错: {e}")

    # ========================================
    # --- Chart 2: Bubble Chart (Top AIDA vs Week) ---
    # ========================================
    fig2 = create_empty_figure("图表2加载中...") 
    try:
        if 'top_aida' not in filtered_tdf.columns:
            fig2 = create_empty_figure("错误: 缺少 'top_aida' 数据")
        else:
            grouped_data2 = filtered_tdf.groupby(
                ["test_week", "top_aida", "run_status"], as_index=False
            )[count_col].nunique().rename(columns={count_col: 'count'}) 

            # === 增强: 过滤图表2的无效周 ===
            valid_week_mask2 = grouped_data2['test_week'].astype(str).str.match(extract_pattern)
            grouped_data2 = grouped_data2[valid_week_mask2.fillna(False)]
            # === 增强结束 ===
            
            if grouped_data2.empty:
                print("警告: 过滤无效周后，图表2数据为空")
                fig2 = create_empty_figure("无有效周数据显示")
            else:
                grouped_data2['test_week_str'] = grouped_data2['test_week'].astype(str)
                extracted_sort_keys2 = grouped_data2['test_week_str'].str.extract(extract_pattern)
                grouped_data2['sort_year'] = pd.to_numeric(extracted_sort_keys2[0], errors='coerce').fillna(99).astype(int)
                grouped_data2['sort_week'] = pd.to_numeric(extracted_sort_keys2[1], errors='coerce').fillna(99).astype(int)
                grouped_data2 = grouped_data2.sort_values(["sort_year", "sort_week", "top_aida"])
                sorted_weeks2 = grouped_data2['test_week'].dropna().unique() 
                sorted_aidas2 = sorted(grouped_data2['top_aida'].apply(lambda x: str(x) if isinstance(x, dict) else x).dropna().unique()) 

                fig2 = px.scatter(
                    grouped_data2, x='test_week', y='top_aida', color='run_status', size='count',
                    size_max=40, opacity=0.8,
                    title="按 Top AIDA 和测试周分类的状态 (气泡图)",
                    labels={'count': '测试数量', 'top_aida': 'Top AIDA', 'test_week': '测试周', 'run_status': '状态'},
                    color_discrete_map=color_map,
                    category_orders={'test_week': list(sorted_weeks2), 'top_aida': list(sorted_aidas2), 'run_status': list(color_map.keys())},
                    hover_data={"test_week": True, "top_aida": True, "run_status": True, "count": True, "sort_year": False, "sort_week": False}
                )
                fig2.update_layout(
                    height=max(600, len(sorted_aidas2) * 30 + 150), xaxis={'tickangle': -45}, yaxis={},
                    xaxis_title="测试周", yaxis_title="Top AIDA", legend_title_text="运行状态",
                    xaxis_showgrid=True, yaxis_showgrid=True, plot_bgcolor='rgba(248, 248, 250, 0.5)',
                    hoverlabel=dict(bgcolor="white", font_size=12, font_family="Rockwell") 
                )
                fig2.update_traces(marker=dict(sizemode='area', line_width=1, line_color='black'))

    except Exception as e:
        print(f"创建图表2时出错: {e}")
        traceback.print_exc()
        fig2 = create_empty_figure(f"创建图表2时出错: {e}")

    # ========================================
    # --- Chart 3: Bubble Chart (Test ID vs Week) ---
    # ========================================
    fig3 = create_empty_figure("图表3加载中...")
    try:
        required_cols_3 = ['test_id', 'test_name', 'tester', 'top_aida', 'id'] # 确保原始id列存在
        if not all(col in filtered_tdf.columns for col in required_cols_3):
             missing_cols = [col for col in required_cols_3 if col not in filtered_tdf.columns]
             print(f"警告: DataFrame 缺少生成图表3所需的列: {missing_cols}")
             fig3 = create_empty_figure(f"错误: 缺少列 {', '.join(missing_cols)}")
        else:
            # === 修改: 调整分组和聚合逻辑 ===
            grouped_data3 = filtered_tdf.groupby(
                # Group by test case identifier, week, and status, keep top_aida for click
                ["test_week", "test_id", "test_name", "run_status", "top_aida"], 
                as_index=False
            ).agg(
                # Aggregate MR IDs and testers into lists
                mr_ids=('id', list), 
                testers=('tester', lambda x: list(set(x))) # Get unique testers per group
            )
            
            # 计算执行次数
            grouped_data3['count'] = grouped_data3['mr_ids'].apply(len)
            # === 修改结束 ===
            
            # 过滤无效周 (保持不变)
            valid_week_mask3 = grouped_data3['test_week'].astype(str).str.match(extract_pattern)
            grouped_data3 = grouped_data3[valid_week_mask3.fillna(False)]

            if grouped_data3.empty:
                print("警告: 过滤无效周后，图表3数据为空")
                fig3 = create_empty_figure("无有效周数据显示")
            else:
                # 排序 (保持不变)
                grouped_data3['test_week_str'] = grouped_data3['test_week'].astype(str)
                extracted_sort_keys3 = grouped_data3['test_week_str'].str.extract(extract_pattern)
                grouped_data3['sort_year'] = pd.to_numeric(extracted_sort_keys3[0], errors='coerce').fillna(99).astype(int)
                grouped_data3['sort_week'] = pd.to_numeric(extracted_sort_keys3[1], errors='coerce').fillna(99).astype(int)
                try:
                    grouped_data3['test_id_numeric'] = pd.to_numeric(grouped_data3['test_id'])
                    grouped_data3 = grouped_data3.sort_values(["sort_year", "sort_week", "test_id_numeric"])
                except (ValueError, TypeError):
                    print("Note: Sorting test_id alphabetically as it's not purely numeric.")
                    grouped_data3 = grouped_data3.sort_values(["sort_year", "sort_week", "test_id"])
                    
                # 创建 Y 轴标签 (保持不变)
                max_name_len = 30 
                grouped_data3['y_axis_label'] = grouped_data3.apply(
                    lambda row: f"{row['test_id']} - {str(row['test_name'])[:max_name_len]}{'...' if len(str(row['test_name'])) > max_name_len else ''}",
                    axis=1
                )
                
                sorted_weeks3 = grouped_data3['test_week'].dropna().unique()
                sorted_y_labels3 = grouped_data3['y_axis_label'].dropna().unique() 
                
                # === 新增: 创建自定义悬停文本 ===
                def format_hover(row):
                    mr_ids_str = ', '.join(map(str, row['mr_ids']))
                    # 显示最多5个MR ID，如果更多则加省略号
                    max_mr_ids_to_show = 5
                    if len(row['mr_ids']) > max_mr_ids_to_show:
                        mr_ids_str = ', '.join(map(str, row['mr_ids'][:max_mr_ids_to_show])) + ', ...'
                    else:
                        mr_ids_str = ', '.join(map(str, row['mr_ids']))
                        
                    testers_str = ', '.join(row['testers'])
                    return (f"状态={row['run_status']}<br>"
                            f"测试周={row['test_week']}<br>"
                            f"测试用例={row['y_axis_label']}<br>"
                            f"执行次数={row['count']}<br>"
                            f"MR IDs={mr_ids_str}<br>"
                            f"测试名称={row['test_name']}<br>"
                            f"测试员={testers_str}")

                grouped_data3['hover_text'] = grouped_data3.apply(format_hover, axis=1)
                # === 新增结束 ===

                # === 修改: 更新 px.scatter 调用 ===
                fig3 = px.scatter(
                    grouped_data3, 
                    x='test_week', 
                    y='y_axis_label', 
                    color='run_status', 
                    size='count', # 大小基于 count (即 MR ID 数量)
                    size_max=15, 
                    opacity=0.8,
                    title="按测试用例和测试周分类的状态 (气泡图)", 
                    labels={
                        'count': '执行次数', 
                        'y_axis_label': '测试用例 (ID - 名称)', 
                        'test_week': '测试周', 
                        'run_status': '状态', 
                        # 以下标签虽然存在于数据中，但已包含在自定义悬停文本里，故不再需要单独列出
                        # 'test_name': '测试名称', 
                        # 'tester': '测试员'
                    },
                    color_discrete_map=color_map,
                    category_orders={
                        'test_week': list(sorted_weeks3), 
                        'y_axis_label': list(sorted_y_labels3), 
                        'run_status': list(color_map.keys())
                    },
                    # 显式指定 custom_data
                    custom_data=["top_aida", "hover_text"], # top_aida 在前用于点击，hover_text 在后用于悬停
                    hover_name='y_axis_label' # 主要标识符，或可移除
                    # hover_data 参数被移除，因为我们使用自定义悬停模板
                )
                
                # 更新布局 (保持不变)
                fig3.update_layout(
                    height=max(1000, len(sorted_y_labels3) * 22 + 200), 
                    margin=dict(l=100, r=60, t=100, b=50), 
                    xaxis={'tickangle': -45}, 
                    yaxis={
                        'type': 'category', 
                        'categoryorder':'array', 
                        'categoryarray': list(sorted_y_labels3), 
                        'tickmode': 'linear' 
                    }, 
                    xaxis_title="测试周", 
                    yaxis_title="测试用例 (ID - 名称)",
                    legend_title_text="运行状态",
                    xaxis_showgrid=True, 
                    yaxis_showgrid=True, 
                    plot_bgcolor='rgba(248, 248, 250, 0.5)',
                    # hoverlabel=dict(bgcolor="white", font_size=12, font_family="Rockwell") # Hoverlabel可能不再需要
                )
                                
                # === 修改: 更新 hovertemplate ===
                fig3.update_traces(
                    hovertemplate='%{customdata[1]}<extra></extra>', # 显示 custom_data 的第二个元素 (hover_text)
                    marker=dict(
                        sizemode='area',
                        line_width=1,
                        line_color='black'
                    )
                )
                # === 修改结束 ===

    except Exception as e:
        print(f"创建图表3时出错: {e}")
        traceback.print_exc()
        fig3 = create_empty_figure(f"创建图表3时出错: {e}")

    print("--- Callback finished ---")
    # 返回图表和更新后的下拉菜单值
    return fig1, fig2, fig3, output_fvs, output_aidas 

# --- 5. 运行应用 ---
if __name__ == '__main__':
    # 监听所有网络接口，允许局域网访问
    app.run(debug=True, port=8055, host='0.0.0.0')