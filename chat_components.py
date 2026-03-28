"""
AI 聊天图表组件渲染模块
======================

让 AI Agent 能够返回图表、表格等可视化组件

使用方式：
    from chat_components import render_ai_response
    
    # AI 返回 JSON 格式的图表描述
    ai_output = '''
    以下是缺陷分析结果：
    
    {"chart": "bar", "data": {"x": ["Critical", "Major", "Minor"], "y": [5, 20, 15], "title": "按严重性分类的缺陷数量"}}
    '''
    
    components = render_ai_response(ai_output)
    # 返回: [html.Div("以下是缺陷分析结果："), dcc.Graph(figure=...)]
"""

import json
import re
from typing import List, Union, Any, Dict
import plotly.express as px
import plotly.graph_objects as go
from dash import html, dcc
import pandas as pd


def extract_chart_json(text: str) -> tuple:
    """
    从文本中提取图表 JSON 描述
    
    支持两种格式：
    1. 独立的 JSON 块 ```json ... ```
    2. 内联 JSON 对象 {"chart": ...}
    
    Returns:
        (纯文本, 图表JSON列表)
    """
    chart_jsons = []
    
    # 提取独立的 JSON 代码块
    json_block_pattern = r'```json\s*([\s\S]*?)\s*```'
    for match in re.finditer(json_block_pattern, text):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and 'chart' in data:
                chart_jsons.append(data)
                text = text.replace(match.group(0), '')
        except json.JSONDecodeError:
            pass
    
    # 提取内联 JSON 对象
    inline_pattern = r'\{"chart"\s*:\s*"[^"]+"[^}]*\}'
    for match in re.finditer(inline_pattern, text):
        try:
            data = json.loads(match.group(0))
            if 'chart' in data:
                chart_jsons.append(data)
                text = text.replace(match.group(0), '')
        except json.JSONDecodeError:
            pass
    
    return text.strip(), chart_jsons


def create_chart(chart_config: Dict) -> dcc.Graph:
    """
    根据配置创建 Plotly 图表
    
    Args:
        chart_config: 图表配置，包含：
            - chart: 图表类型 (bar, pie, line, scatter, histogram)
            - data: 数据字典 {x: [...], y: [...], name: ...}
            - title: 图表标题
            - xlabel: X轴标签
            - ylabel: Y轴标签
            - color: 颜色主题
    
    Returns:
        dcc.Graph 组件
    """
    chart_type = chart_config.get('chart', 'bar')
    data = chart_config.get('data', {})
    title = chart_config.get('title', '')
    xlabel = chart_config.get('xlabel', '')
    ylabel = chart_config.get('ylabel', '')
    color = chart_config.get('color', 'blue')
    
    x = data.get('x', [])
    y = data.get('y', [])
    
    # 根据类型创建图表
    if chart_type == 'bar':
        if len(x) > 0 and len(y) > 0:
            df = pd.DataFrame({'x': x, 'y': y})
            fig = px.bar(df, x='x', y='y', title=title)
            if xlabel: fig.update_xaxes(title=xlabel)
            if ylabel: fig.update_yaxes(title=ylabel)
        else:
            fig = go.Figure()
            
    elif chart_type == 'pie':
        if len(x) > 0 and len(y) > 0:
            fig = px.pie(names=x, values=y, title=title)
        else:
            fig = go.Figure()
            
    elif chart_type == 'line':
        if len(x) > 0 and len(y) > 0:
            df = pd.DataFrame({'x': x, 'y': y})
            fig = px.line(df, x='x', y='y', title=title)
            if xlabel: fig.update_xaxes(title=xlabel)
            if ylabel: fig.update_yaxes(title=ylabel)
        else:
            fig = go.Figure()
            
    elif chart_type == 'scatter':
        if len(x) > 0 and len(y) > 0:
            fig = px.scatter(x=x, y=y, title=title)
            if xlabel: fig.update_xaxes(title=xlabel)
            if ylabel: fig.update_yaxes(title=ylabel)
        else:
            fig = go.Figure()
            
    elif chart_type == 'histogram':
        if len(y) > 0:
            fig = px.histogram(y=y, nbins=20, title=title)
            if ylabel: fig.update_yaxes(title=ylabel)
        else:
            fig = go.Figure()
            
    else:
        # 默认柱状图
        if len(x) > 0 and len(y) > 0:
            df = pd.DataFrame({'x': x, 'y': y})
            fig = px.bar(df, x='x', y='y', title=title)
        else:
            fig = go.Figure()
    
    # 统一样式
    fig.update_layout(
        template='plotly_white',
        font=dict(family='Arial', size=12),
        margin=dict(l=40, r=40, t=60, b=40),
        height=350,
    )
    
    return dcc.Graph(figure=fig, config={'displayModeBar': True})


def create_table(data: List[Dict], columns: List[str] = None) -> html.Table:
    """
    创建 Dash 表格组件
    
    Args:
        data: 表格数据，每行是一个字典
        columns: 列名列表，如果为 None 则使用字典的 key
    
    Returns:
        html.Table 组件
    """
    if not data:
        return html.Div("无数据")
    
    # 获取列名
    if columns is None:
        columns = list(data[0].keys()) if data else []
    
    # 表头
    header = [html.Th(col) for col in columns]
    
    # 表体
    rows = []
    for row_data in data:
        cells = [html.Td(str(row_data.get(col, '-'))) for col in columns]
        rows.append(html.Tr(cells))
    
    return html.Table([
        html.Thead(html.Tr(header)),
        html.Tbody(rows)
    ], style={
        'width': '100%',
        'borderCollapse': 'collapse',
        'marginTop': '10px',
        'fontSize': '14px'
    })


def extract_table_json(text: str) -> tuple:
    """
    从文本中提取表格 JSON 描述
    
    Returns:
        (纯文本, 表格JSON列表)
    """
    table_jsons = []
    
    # 提取表格 JSON
    pattern = r'\{"table"\s*:\s*\[[\s\S]*?\]\s*\}'
    for match in re.finditer(pattern, text):
        try:
            data = json.loads(match.group(0))
            if 'table' in data:
                table_jsons.append(data['table'])
                text = text.replace(match.group(0), '')
        except json.JSONDecodeError:
            pass
    
    return text.strip(), table_jsons


def render_ai_response(ai_text: str) -> List:
    """
    渲染 AI 响应，支持文本、图表、表格
    
    Args:
        ai_text: AI 返回的文本，可能包含图表/表格 JSON
    
    Returns:
        Dash 组件列表
    """
    components = []
    
    # 1. 先提取表格
    text, table_configs = extract_table_json(ai_text)
    
    # 2. 再提取图表
    text, chart_configs = extract_chart_json(text)
    
    # 3. 添加文本部分（如果有）
    if text:
        # 按换行符分段
        paragraphs = text.split('\n\n')
        for para in paragraphs:
            if para.strip():
                components.append(html.Div(para, style={
                    'marginBottom': '10px',
                    'lineHeight': '1.6'
                }))
    
    # 4. 添加图表
    for config in chart_configs:
        try:
            chart = create_chart(config)
            components.append(chart)
        except Exception as e:
            components.append(html.Div(f"图表渲染错误: {str(e)}", 
                style={'color': 'red', 'padding': '10px'}))
    
    # 5. 添加表格
    for table_data in table_configs:
        try:
            table = create_table(table_data)
            components.append(table)
        except Exception as e:
            components.append(html.Div(f"表格渲染错误: {str(e)}", 
                style={'color': 'red', 'padding': '10px'}))
    
    return components


# ============================================================
# AI 提示词模板 - 告诉 AI 如何返回图表
# ============================================================

CHART_PROMPT = """
## 可视化输出格式

当你需要返回图表时，使用以下 JSON 格式：

### 柱状图
```json
{"chart": "bar", "data": {"x": ["类别A", "类别B", "类别C"], "y": [10, 20, 15]}, "title": "标题", "xlabel": "X轴", "ylabel": "Y轴"}
```

### 饼图
```json
{"chart": "pie", "data": {"x": ["A", "B", "C"], "y": [30, 50, 20]}, "title": "占比分布"}
```

### 折线图
```json
{"chart": "line", "data": {"x": ["周一", "周二", "周三"], "y": [100, 120, 90]}, "title": "趋势图"}
```

### 散点图
```json
{"chart": "scatter", "data": {"x": [1, 2, 3, 4], "y": [10, 15, 13, 17]}, "title": "相关性"}
```

### 表格
```json
{"table": [{"列1": "值1", "列2": "值2"}, {"列1": "值3", "列2": "值4"}]}
```

**重要提示**：
1. JSON 放在独立的代码块 ```json ... ``` 中
2. 先用文字说明分析结果，再附上图表
3. 确保数据有实际意义
"""


if __name__ == "__main__":
    # 测试
    test_output = """
    根据分析，以下是缺陷分布情况：
    
    按严重性分类：
    
    ```json
    {"chart": "bar", "data": {"x": ["Critical", "Major", "Minor", "Trivial"], "y": [5, 25, 18, 7]}, "title": "按严重性分类的缺陷数量", "ylabel": "缺陷数量"}
    ```
    
    按状态分布：
    
    ```json
    {"chart": "pie", "data": {"x": ["Open", "In Progress", "Resolved", "Closed"], "y": [15, 10, 20, 10]}, "title": "缺陷状态分布"}
    ```
    """
    
    print("=== 测试 AI 响应渲染 ===")
    components = render_ai_response(test_output)
    print(f"生成了 {len(components)} 个组件")
    for i, c in enumerate(components):
        print(f"  {i+1}. {type(c).__name__}")
