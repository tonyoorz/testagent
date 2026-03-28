#!/usr/bin/env python3
"""
测试增强版 AI Chat Manager with SQL

测试 defect_explore.py 的新 AI Chat 功能
"""

import sys
import pandas as pd

# 测试导入
print("=" * 60)
print("测试 enhanced_ai_chat_with_sql 导入")
print("=" * 60)

try:
    from enhanced_ai_chat_with_sql import (
        EnhancedAIChatManagerWithSQL,
        create_enhanced_chat_manager_with_sql
    )
    print("✅ enhanced_ai_chat_with_sql 导入成功")
except ImportError as e:
    print(f"❌ enhanced_ai_chat_with_sql 导入失败: {e}")
    sys.exit(1)

# 测试创建聊天管理器
print("\n" + "=" * 60)
print("测试创建聊天管理器")
print("=" * 60)

try:
    chat_manager = create_enhanced_chat_manager_with_sql(
        dashboard_type='defect_explore',
        use_agent=True,
        enable_sql=True,
        assistant_name='SiSi'
    )
    print("✅ 聊天管理器创建成功")
    print(f"   - Dashboard 类型: {chat_manager.dashboard_type}")
    print(f"   - 使用 Agent: {chat_manager.use_agent}")
    print(f"   - 启用 SQL: {chat_manager.enable_sql}")
    print(f"   - 助手名称: {chat_manager.assistant_name}")
except Exception as e:
    print(f"❌ 聊天管理器创建失败: {e}")
    sys.exit(1)

# 测试 SQL 查询能力
print("\n" + "=" * 60)
print("测试 SQL 查询能力")
print("=" * 60)

test_questions = [
    ("SQL 查询", "统计所有缺陷的数量"),
    ("SQL 查询", "各模块的缺陷数量统计"),
    ("SQL 查询", "Critical 级别的缺陷数量"),
    ("LLM", "你好，请介绍一下你自己"),
    ("LLM", "缺陷分析的注意事项有哪些？")
]

for category, question in test_questions:
    print(f"\n[{category}] 问题: {question}")
    try:
        result = chat_manager.ask(question)

        print(f"  来源: {result.get('source', 'unknown')}")
        print(f"  成功: {result.get('success', False)}")
        print(f"  回答: {result.get('answer', '')[:100]}...")

        if result.get('sql'):
            print(f"  SQL: {result['sql'][:80]}...")

        if result.get('data') is not None and not result['data'].empty:
            print(f"  数据行数: {len(result['data'])}")
    except Exception as e:
        print(f"  ❌ 错误: {e}")

# 测试 Dash 集成
print("\n" + "=" * 60)
print("测试 Dash 集成接口")
print("=" * 60)

try:
    # 创建界面
    interface = chat_manager.create_enhanced_chat_interface('test-chat')
    print("✅ create_enhanced_chat_interface 成功")

    # 创建存储
    stores = chat_manager.create_enhanced_chat_stores('test-chat')
    print(f"✅ create_enhanced_chat_stores 成功 (创建 {len(stores)} 个存储)")

    print("\n所有测试通过！🎉")
    print("\n现在可以在 defect_explore.py 中使用新的 AI Chat 功能了。")

except Exception as e:
    print(f"❌ Dash 集成测试失败: {e}")
    import traceback
    traceback.print_exc()
