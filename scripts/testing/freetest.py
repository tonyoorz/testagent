import pandas as pd
# import pygwalker as pyg # Pygwalker不再使用
import dash
from dash import dcc, html, Input, Output, State
import plotly.express as px

# 导入指定的CSV文件
raw_df = pd.read_csv('download/DTSV_CN Speech_IDCEVO_checklist_v2.csv')

# --- 数据转换为看板所需格式 ---

# 1. 识别ID变量和CW状态列
id_vars_for_status = ['Test Scope', 'Test Module', 'Customer Cases']
raw_df.columns = [col.strip() for col in raw_df.columns]
id_vars_for_status = [col for col in id_vars_for_status if col in raw_df.columns]

if 'Customer Cases' not in id_vars_for_status:
    print("Error: 'Customer Cases' column not found in CSV. Please ensure it exists.")
    if 'Test Step' in raw_df.columns:
        print("Hint: 'Test Step' column found. Modify script if you intend to use it.")
    exit()

if not all(item in raw_df.columns for item in ['Test Scope', 'Test Module']):
    print("Error: 'Test Scope' or 'Test Module' column missing from CSV.")
    exit()

cw_status_cols = [col for col in raw_df.columns if col.startswith('CW')]

if not cw_status_cols:
    print("Error: No columns starting with 'CW' (representing test weeks) found in CSV.")
    exit()

valid_id_vars = [col for col in id_vars_for_status if col in raw_df.columns]

# 2. 提取BugID数据
def clean_bug_id(value):
    s_val = str(value).strip()
    if not s_val or s_val.lower() == 'nan':
        return None
    status_words = {"pass", "fail", "blocked", "no run"}
    if s_val.lower() in status_words:
        return None
    return s_val

bug_data_records = []
columns_list = raw_df.columns.tolist()
for row_idx, row_series in raw_df.iterrows():
    base_data = {vid: row_series[vid] for vid in valid_id_vars}
    for col_idx, col_name in enumerate(columns_list):
        if col_name.startswith("CW"):
            if col_idx > 0:
                ticket_col_name = columns_list[col_idx - 1]
                if ticket_col_name not in valid_id_vars and not ticket_col_name.startswith("CW"):
                    bug_id_val = row_series[ticket_col_name]
                    cleaned_bug_id = clean_bug_id(bug_id_val)
                    if cleaned_bug_id:
                        record = base_data.copy()
                        record['TestWeek'] = col_name
                        record['BugID'] = cleaned_bug_id
                        bug_data_records.append(record)

bug_id_df = pd.DataFrame(bug_data_records)
if not bug_id_df.empty:
    bug_id_df = bug_id_df.drop_duplicates(subset=valid_id_vars + ['TestWeek'])

# 3. 提取状态数据并与BugID数据融合
melted_status_df = pd.melt(raw_df,
                           id_vars=valid_id_vars,
                           value_vars=cw_status_cols,
                           var_name='TestWeek',
                           value_name='Status_raw')

# 与BugID数据融合
if not bug_id_df.empty:
    merged_df = pd.merge(melted_status_df, bug_id_df, on=valid_id_vars + ['TestWeek'], how='left')
else:
    merged_df = melted_status_df
    merged_df['BugID'] = None

# 4. 后续处理
def clean_status_value(status_val):
    s = str(status_val).strip().lower()
    if not s or s == 'nan':
        return None
    if s.startswith('pass'): return 'Pass'
    if s.startswith('fail'): return 'Fail'
    if s == 'blocked': return 'Blocked'
    if s == 'no run': return 'No Run'
    return None

merged_df['Status'] = merged_df['Status_raw'].apply(clean_status_value)

# 计算Bug数量和对应的标记大小
def calculate_marker_size_from_bugid(bug_id_cell):
    if pd.isna(bug_id_cell):
        return 8  # 0个BugID (调整后)
    num_bugs = len(str(bug_id_cell).split())
    if num_bugs <= 1:
        return 8  # 1个BugID (调整后)
    elif num_bugs == 2:
        return 12  # 2个BugID (调整后)
    else:
        return 16  # >=3个BugID (调整后)

def count_actual_bugs(bug_id_cell):
    if pd.isna(bug_id_cell):
        return 0
    return len(str(bug_id_cell).split())

merged_df['MarkerSizeValue'] = merged_df['BugID'].apply(calculate_marker_size_from_bugid)
merged_df['BugCount'] = merged_df['BugID'].apply(count_actual_bugs)

status_dashboard_df = merged_df.dropna(subset=['Test Scope', 'Test Module', 'Status'])

if not status_dashboard_df.empty:
    status_dashboard_df.loc[:, 'TestWeek'] = pd.Categorical(status_dashboard_df['TestWeek'], categories=cw_status_cols, ordered=True)
# --- 数据转换逻辑结束 ---

# --- Dash 应用开始 ---
if status_dashboard_df.empty:
    print("No valid data to display after processing. Dash dashboard will not be generated.")
else:
    app = dash.Dash(__name__)
    plot_height = 800
    # ... (app.layout and theme setup remains the same) ...
    initial_theme = 'dark'
    initial_bg_color = '#111111' if initial_theme == 'dark' else '#f0f0f0'
    initial_text_color = 'white' if initial_theme == 'dark' else 'black'

    app.layout = html.Div(id='main-container', children=[
        html.Div([
            html.H1("Test Status Dashboard (Dash)", id='dashboard-title',
                    style={'textAlign': 'center', 'marginBottom': '10px', 'color': initial_text_color}),
            dcc.RadioItems(
                id='theme-switcher',
                options=[
                    {'label': 'Light Theme', 'value': 'light'},
                    {'label': 'Dark Theme', 'value': 'dark'}
                ],
                value=initial_theme,
                labelStyle={'display': 'inline-block', 'marginRight': '10px', 'color': initial_text_color},
                style={'textAlign': 'center', 'marginBottom':'20px'}
            )
        ]),
        dcc.Graph(id='status-scatter-plot', style={'height': f'{plot_height}px'})
    ], style={'backgroundColor': initial_bg_color, 'padding': '10px'})

    @app.callback(
        Output('status-scatter-plot', 'figure'),
        Output('dashboard-title', 'style'),
        Output('theme-switcher', 'labelStyle'),
        Output('main-container', 'style'),
        [Input('theme-switcher', 'value')]
    )
    def update_graph_and_theme(selected_theme):
        if selected_theme == 'dark':
            graph_template = 'plotly_dark'
            title_style = {'textAlign': 'center', 'marginBottom': '10px', 'color': 'white'}
            radio_label_style = {'display': 'inline-block', 'marginRight': '10px', 'color': 'white'}
            container_style = {'backgroundColor': '#111111', 'padding': '10px'}
        else: 
            graph_template = 'plotly'
            title_style = {'textAlign': 'center', 'marginBottom': '10px', 'color': 'black'}
            radio_label_style = {'display': 'inline-block', 'marginRight': '10px', 'color': 'black'}
            container_style = {'backgroundColor': '#f0f0f0', 'padding': '10px'}
        
        figure = px.scatter(
            status_dashboard_df,
            x='TestWeek',
            y='Test Module',
            color='Status',
            size='MarkerSizeValue',
            category_orders={
                "TestWeek": cw_status_cols,
                "Status": ['Pass', 'Fail', 'Blocked', 'No Run']
            },
            color_discrete_map={
                'Pass': 'green',
                'Fail': 'red',
                'Blocked': 'orange',
                'No Run': 'grey'
            },
            title="Test Execution Status (by Week, Scope, and Module)",
            labels={'TestWeek': 'Test Week', 'Test Module': 'Test Module', 'Status': 'Status', 
                    'Test Scope': 'Test Scope', 'BugID': 'Bug ID', 'Customer Cases': 'Customer Case',
                    'MarkerSizeValue': 'Marker Size'
                   },
            hover_name='Customer Cases',
            hover_data={
                'Status': True,
                'TestWeek': False,
                'Test Scope': False,
                'Test Module': False,
                'Customer Cases': False,
                'BugID': True,
                'MarkerSizeValue': False,
                'BugCount': False
            },
            size_max=18 # 调整 size_max 以进一步限制最大点的视觉尺寸
        )

        figure.update_yaxes(matches=None, showticklabels=True, title_text=None, autorange="reversed")
        figure.update_xaxes(showticklabels=True, title_text="Test Week")

        layout_updates = {
            "height": plot_height,
            "margin": dict(l=250, r=50, t=80, b=100),
            "legend_title_text": 'Status',
            "title_x": 0.5,
            "template": graph_template
        }

        if selected_theme == 'light':
            layout_updates['plot_bgcolor'] = 'white'
            layout_updates['paper_bgcolor'] = 'white'
            figure.update_xaxes(gridcolor='#e5e5e5')
            figure.update_yaxes(gridcolor='#e5e5e5', title_text='Test Module')
        else:
            figure.update_yaxes(title_text='Test Module')
            pass

        figure.update_layout(**layout_updates)
        
        return figure, title_style, radio_label_style, container_style

    if __name__ == '__main__':
        print("Dash dashboard is ready. Open http://127.0.0.1:8072/ in your browser.")
        app.run(debug=True, host='0.0.0.0', port=8072)
# --- Dash 应用结束 ---

# 原Pygwalker输出逻辑 (已注释掉)
# if not status_dashboard_df.empty:
#     final_cols_for_dashboard = valid_id_vars + ['TestWeek', 'Status']
#     final_cols_for_dashboard = [col for col in final_cols_for_dashboard if col in status_dashboard_df.columns]
#     status_dashboard_df_final = status_dashboard_df[final_cols_for_dashboard]
#     html_output = pyg.walk(status_dashboard_df_final, return_html=True)
#     output_filename = 'pygwalker_status_dashboard.html'
#     with open(output_filename, 'w', encoding='utf-8') as f:
#         f.write(html_output)
#     print(f"状态看板数据已处理完毕，并已生成 {output_filename} 文件。")
#     print("请打开该HTML文件，并在Pygwalker界面中配置散点图：")
#     print("- X轴: TestWeek")
#     print("- Y轴: Test Scope, Test Module (按顺序拖入)")
#     print("- Color: Status")
#     print("- Mark Type: Point/Circle (散点图)")
# else:
#     print("处理后没有有效数据可用于生成状态看板。")

# print("数据已成功导入，并已生成 pygwalker_output.html 文件用于数据探索。") # 旧的打印语句