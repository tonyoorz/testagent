#!/usr/bin/env python3
"""
SQL Chat 快速使用示例

展示如何集成 Text-to-SQL 功能到现有项目

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import os
import sys

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_chat_with_sql import AIChatWithSQL, create_chat_interface_with_sql
import dash
from dash import html, dcc


# ============================================================================
# 示例 1: 基础使用
# ============================================================================

def example_basic():
    """基础使用示例"""
    print("=" * 60)
    print("示例 1: 基础使用")
    print("=" * 60)
    
    # 创建 AI Chat 实例
    chat = AIChatWithSQL()
    
    # 测试问题列表
    questions = [
        "统计所有缺陷的数量",
        "测试通过率是多少",
        "各模块的缺陷数量统计",
        "最近7天的测试通过率",
        "各项目的测试数量统计"
    ]
    
    for i, question in enumerate(questions, 1):
        print(f"\n问题 {i}: {question}")
        print("-" * 60)
        
        result = chat.ask(question)
        
        print(f"回答: {result['answer']}")
        
        if result.get("sql"):
            print(f"\nSQL: {result['sql']}")
        
        if result.get("data") is not None and not result["data"].empty:
            print(f"\n数据预览:")
            print(result["data"].to_string(index=False))
        
        print()


# ============================================================================
# 示例 2: Dash 集成
# ============================================================================

def example_dash_integration():
    """Dash 集成示例"""
    print("=" * 60)
    print("示例 2: Dash 集成")
    print("=" * 60)
    
    app = dash.Dash(__name__)
    
    app.layout = html.Div([
        html.H1("🚗 汽车测试数据分析平台", style={"textAlign": "center", "margin-bottom": "30px"}),
        
        # 创建聊天界面
        create_chat_interface_with_sql(app, "test-chat"),
        
        # 其他内容
        html.Div([
            html.H2("📊 数据概览"),
            html.P("这里可以添加其他 Dashboard 组件...")
        ], style={"margin": "20px"})
    ])
    
    print("\n启动 Dash 应用...")
    print("访问: http://localhost:8050")
    print("按 Ctrl+C 停止")
    
    app.run_server(debug=True, port=8050)


# ============================================================================
# 示例 3: 集成到现有模块
# ============================================================================

def example_integrate_to_existing_module():
    """集成到现有模块的示例"""
    print("=" * 60)
    print("示例 3: 集成到现有模块")
    print("=" * 60)
    
    # 在你的 defect_explore.py 中，可以这样集成：
    
    code_example = """
# 在 defect_explore.py 顶部添加导入
from ai_chat_with_sql import create_chat_interface_with_sql

# 在 create_defect_explore_page() 函数中添加聊天界面
def create_defect_explore_page(self):
    return html.Div([
        # 原有内容
        self.create_filter_section(),
        self.create_main_dashboard(),
        
        # 添加 AI 聊天界面
        create_chat_interface_with_sql(app, "defect-chat")
    ])

# 注册回调（在 register_callbacks 函数中）
def register_callbacks(self, app):
    # 原有回调
    app.callback(...)
    
    # AI 聊天回调会自动注册
    pass
"""
    
    print("\n代码示例:")
    print("-" * 60)
    print(code_example)
    print()


# ============================================================================
# 示例 4: 高级用法 - 自定义配置
# ============================================================================

def example_advanced():
    """高级用法示例"""
    print("=" * 60)
    print("示例 4: 高级用法 - 自定义配置")
    print("=" * 60)
    
    from sql_query_engine import SQLQueryConfig, BusinessKnowledge
    
    # 自定义配置
    config = SQLQueryConfig(
        db_path="database/local_data.db",
        max_retries=5,  # 增加重试次数
        enable_cache=True,
        cache_ttl_seconds=7200,  # 缓存 2 小时
        verbose=True
    )
    
    # 创建聊天实例
    chat = AIChatWithSQL(config=config)
    
    # 添加自定义业务知识
    print("\n自定义业务知识:")
    print(BusinessKnowledge.get_knowledge())
    
    # 测试
    question = "高风险缺陷有哪些？"
    result = chat.ask(question)
    
    print(f"\n问题: {question}")
    print(f"回答: {result['answer']}")
    
    if result.get("sql"):
        print(f"SQL: {result['sql']}")


# ============================================================================
# 示例 5: 交互式测试
# ============================================================================

def example_interactive():
    """交互式测试"""
    print("=" * 60)
    print("示例 5: 交互式测试")
    print("=" * 60)
    print("\n输入问题，输入 'quit' 退出")
    print("提示问题:")
    print("  - 统计所有缺陷的数量")
    print("  - 测试通过率是多少")
    print("  - 各模块的缺陷数量统计")
    print("  - 最近7天的测试通过率")
    print("  - 各项目的测试数量统计")
    print("-" * 60)
    
    chat = AIChatWithSQL()
    
    while True:
        try:
            question = input("\n你: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("\n再见！")
                break
            
            if not question:
                continue
            
            result = chat.ask(question)
            
            print(f"\nAI: {result['answer']}")
            
            if result.get("sql"):
                print(f"\n[SQL] {result['sql']}")
            
            if result.get("data") is not None and not result["data"].empty:
                print(f"\n[数据]")
                print(result["data"].to_string(index=False))
        
        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except Exception as e:
            print(f"\n错误: {e}")


# ============================================================================
# 主程序
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SQL Chat 示例")
    parser.add_argument(
        "--example", "-e",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="选择示例编号"
    )
    
    args = parser.parse_args()
    
    examples = {
        1: example_basic,
        2: example_dash_integration,
        3: example_integrate_to_existing_module,
        4: example_advanced,
        5: example_interactive
    }
    
    if args.example:
        examples[args.example]()
    else:
        # 默认运行基础示例
        print("未指定示例，运行基础示例...")
        print("使用 --help 查看所有示例\n")
        example_basic()
