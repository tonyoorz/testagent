#!/usr/bin/env python3
"""
Text-to-SQL Agent 快速演示

快速演示 Text-to-SQL Agent 的核心功能。

运行演示：
python chatdb/demo.py

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chatdb.text_to_sql_agent import create_text_to_sql_agent


def main():
    """主函数"""
    print("=" * 70)
    print(" " * 15 + "Text-to-SQL Agent 演示")
    print("=" * 70)
    print()
    
    # 创建 agent
    print("🚀 初始化 Text-to-SQL Agent...")
    agent = create_text_to_sql_agent(
        db_path="database/local_data.db",
        schema_path="chatdb/schema_description.md",
        business_rules_path="chatdb/business_rules.py",
        fewshot_path="chatdb/fewshot_examples.md",
        verbose=True
    )
    print("✅ 初始化完成！")
    print()
    
    # 测试问题
    test_questions = [
        "查询所有 TopIssue 缺陷，按风险评分降序排列",
        "按项目统计缺陷总数、高严重性缺陷数、平均处理周期",
        "查询所有 High Runner 缺陷（ECU转移≥3次或Domain转移≥3次）",
        "查询所有 Long Runner 缺陷（处理周期≥30天且未解决）",
        "查询大规模主票（子票数≥5个），按子票数量降序排序",
        "查询 App 项目的 TopIssue 缺陷"
    ]
    
    # 执行查询
    for i, question in enumerate(test_questions, 1):
        print(f"\n{'='*70}")
        print(f"查询 {i}/{len(test_questions)}: {question}")
        print('='*70)
        
        # 执行查询
        result = agent.query(question)
        
        # 显示结果
        if result["success"]:
            print(f"\n✅ 查询成功！")
            print(f"⏱️ 执行时间: {result['execution_time_ms']}ms")
            print(f"🔄 重试次数: {result['retries']}")
            print(f"💾 缓存: {'命中' if result['from_cache'] else '未命中'}")
            print(f"📊 数据行数: {len(result['data'])}")
            print(f"\n🔍 生成的 SQL:")
            print("-" * 70)
            print(result['sql'])
            print("-" * 70)
            print(f"\n💬 回答:")
            print("-" * 70)
            print(result['answer'][:500])
            if len(result['answer']) > 500:
                print("...(内容太长，已截断)")
            print("-" * 70)
            
            # 显示数据预览
            if not result['data'].empty:
                print(f"\n📋 数据预览 (前 3 行):")
                print("-" * 70)
                print(result['data'].head(3).to_string())
                print("-" * 70)
        else:
            print(f"\n❌ 查询失败！")
            print(f"错误: {result['error']}")
            if result.get('sql'):
                print(f"\n生成的 SQL: {result['sql']}")
        
        # 等待用户输入
        if i < len(test_questions):
            input("\n按 Enter 继续...")
    
    # 测试缓存
    print(f"\n{'='*70}")
    print("测试缓存机制")
    print('='*70)
    
    question = "查询所有 TopIssue 缺陷，按风险评分降序排列"
    
    print(f"\n第一次查询（应该未命中缓存）:")
    result1 = agent.query(question)
    print(f"缓存: {'命中' if result1['from_cache'] else '未命中'}")
    
    print(f"\n第二次查询（应该命中缓存）:")
    result2 = agent.query(question)
    print(f"缓存: {'命中' if result2['from_cache'] else '未命中'}")
    print(f"执行时间: {result2['execution_time_ms']}ms (应该很快)")
    
    # 清空缓存
    print(f"\n清空缓存...")
    agent.clear_cache()
    
    print(f"\n第三次查询（应该未命中缓存）:")
    result3 = agent.query(question)
    print(f"缓存: {'命中' if result3['from_cache'] else '未命中'}")
    
    # 交互式查询
    print(f"\n{'='*70}")
    print("交互式查询模式")
    print('='*70)
    print("\n输入你的问题（输入 'exit' 退出）:")
    
    while True:
        print()
        question = input("问题> ").strip()
        
        if question.lower() in ['exit', 'quit', '退出']:
            print("👋 再见！")
            break
        
        if not question:
            continue
        
        print(f"\n查询中...")
        result = agent.query(question)
        
        if result["success"]:
            print(f"\n✅ 查询成功！")
            print(f"⏱️ 执行时间: {result['execution_time_ms']}ms")
            print(f"📊 数据行数: {len(result['data'])}")
            print(f"\n💬 回答:")
            print(result['answer'])
        else:
            print(f"\n❌ 查询失败: {result['error']}")
    
    print("\n" + "=" * 70)
    print("✅ 演示结束")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 演示被用户中断")
    except Exception as e:
        print(f"\n\n❌ 演示出错: {e}")
        import traceback
        traceback.print_exc()
