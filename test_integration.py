#!/usr/bin/env python3
"""
集成测试 - 端到端流程测试

测试增强的 AI Chat with SQL 的完整流程

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sys
from pathlib import Path
import pandas as pd
import json

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from ai_chat_with_sql_optimized import (
    AIChatWithSQLOptimized,
    create_ai_chat_with_sql_optimized
)


# Mock LLM 生成函数
def mock_llm_generate(prompt: str) -> str:
    """Mock LLM 生成函数"""
    import re

    # 从 prompt 中提取用户问题
    question_match = re.search(r'## 用户问题\n(.+?)\n', prompt, re.DOTALL)
    if question_match:
        question = question_match.group(1).strip()

        # 根据问题返回对应的 SQL（简化版）
        if "缺陷数量" in question and "统计" in question:
            if "模块" in question:
                return "SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module ORDER BY defect_count DESC LIMIT 10"
            else:
                return "SELECT COUNT(*) as total_defects FROM defects"
        elif "通过率" in question:
            return "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs LIMIT 10"
        elif "最近7天" in question and "通过率" in question:
            return "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs WHERE start_time >= date('now', '-7 days') LIMIT 10"
        elif "本周" in question and "新增" in question:
            return "SELECT COUNT(*) as new_defects_this_week FROM defects WHERE creation_time >= date('now', 'weekday 0', '-7 days', 'start of day')"
        elif "最近30天" in question and "Critical" in question:
            return "SELECT * FROM defects WHERE severity = 'Critical' AND creation_time >= date('now', '-30 days') ORDER BY creation_time DESC LIMIT 10"
        elif "每个缺陷" in question and "对应的测试执行" in question:
            return "SELECT d.id, d.severity, d.status as defect_status, tr.test_name, tr.result as test_result FROM defects d LEFT JOIN test_runs tr ON d.build_number = tr.build_number WHERE d.id IS NOT NULL LIMIT 20"
        elif "超过平均值" in question and "模块" in question:
            return "SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module HAVING COUNT(*) > (SELECT AVG(defect_count) FROM (SELECT module, COUNT(*) as defect_count FROM defects GROUP BY subq.module) as subq) ORDER BY defect_count DESC LIMIT 10"
        elif "排序并编号" in question and "缺陷" in question:
            return "SELECT id, severity, status, creation_time, ROW_NUMBER() OVER (ORDER BY creation_time DESC) as row_num FROM defects LIMIT 20"
        else:
            # 默认查询
            return "SELECT * FROM defects LIMIT 10"

    # 知识问答
    if "严重度" in prompt:
        return "缺陷严重度级别包括：Critical（致命）、Major（严重）、Medium（中等）、Minor（轻微）。"
    elif "重开率" in prompt:
        return "降低缺陷重开率的方法：1. 深入分析根本原因；2. 改进测试覆盖率；3. 加强代码审查；4. 使用自动化回归测试。"
    elif "pingpong" in prompt:
        return "pingpong 表示缺陷被重新打开的次数，反映了问题的复杂性和解决的难度。"

    return "这是一个很好的问题，让我来回答..."


def test_basic_queries():
    """测试基础查询"""
    print("=" * 70)
    print("测试 1: 基础查询")
    print("=" * 70 + "\n")

    # 创建实例（使用 Mock LLM）
    chat = AIChatWithSQLOptimized(
        db_path="database/local_data.db",
        llm_generate_func=mock_llm_generate
    )

    # 测试查询
    test_queries = [
        "统计所有缺陷的数量",
        "各模块的缺陷数量统计",
        "测试通过率是多少"
    ]

    for i, question in enumerate(test_queries, 1):
        print(f"测试 {i}/{len(test_queries)}: {question}")
        print("-" * 70)

        result = chat.ask(question)

        if result["success"]:
            print(f"✅ 成功")
            print(f"  来源: {result['source']}")
            print(f"  SQL: {result.get('sql', 'N/A')[:100]}..." if result.get('sql') else "")
            print(f"  数据行数: {len(result.get('data', pd.DataFrame()))}")
            print(f"  答案: {result['answer'][:200]}...")
        else:
            print(f"❌ 失败: {result.get('error')}")

        print()


def test_time_range_queries():
    """测试时间范围查询"""
    print("=" * 70)
    print("测试 2: 时间范围查询")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(
        db_path="database/local_data.db",
        llm_generate_func=mock_llm_generate
    )

    test_queries = [
        "最近7天的测试通过率",
        "本周新增的缺陷数量",
        "最近30天创建的 Critical 缺陷"
    ]

    for i, question in enumerate(test_queries, 1):
        print(f"测试 {i}/{len(test_queries)}: {question}")
        print("-" * 70)

        result = chat.ask(question)

        if result["success"]:
            print(f"✅ 成功 (来源: {result['source']})")
            print(f"  数据行数: {len(result.get('data', pd.DataFrame()))}")
        else:
            print(f"❌ 失败: {result.get('error')}")

        print()


def test_complex_queries():
    """测试复杂查询"""
    print("=" * 70)
    print("测试 3: 复杂查询")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(llm_generate_func=mock_llm_generate)

    test_queries = [
        "每个缺陷对应的测试执行情况",
        "缺陷数量超过平均值的模块",
        "按创建时间排序并给每个缺陷编号"
    ]

    for i, question in enumerate(test_queries, 1):
        print(f"测试 {i}/{len(test_queries)}: {question}")
        print("-" * 70)

        result = chat.ask(question)

        if result["success"]:
            print(f"✅ 成功 (来源: {result['source']})")
            print(f"  数据行数: {len(result.get('data', pd.DataFrame()))}")
        else:
            print(f"❌ 失败: {result.get('error')}")

        print()


def test_knowledge_questions():
    """测试知识问答"""
    print("=" * 70)
    print("测试 4: 知识问答（应使用 LLM）")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(llm_generate_func=mock_llm_generate)

    test_queries = [
        "什么是缺陷的严重度级别？",
        "如何降低缺陷重开率？",
        "请解释一下什么是 pingpong"
    ]

    for i, question in enumerate(test_queries, 1):
        print(f"测试 {i}/{len(test_queries)}: {question}")
        print("-" * 70)

        result = chat.ask(question, enable_sql=True)

        if result["success"]:
            print(f"✅ 成功")
            print(f"  来源: {result['source']}")
            print(f"  答案: {result['answer'][:200]}...")
        else:
            print(f"❌ 失败: {result.get('error')}")

        print()


def test_data_context():
    """测试数据上下文"""
    print("=" * 70)
    print("测试 5: 数据上下文")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(llm_generate_func=mock_llm_generate)

    # 创建模拟数据上下文
    mock_data = pd.DataFrame({
        'project': ['AIDA', 'AIDA', 'AIDA'],
        'module': ['Module1', 'Module1', 'Module2'],
        'severity': ['Critical', 'Major', 'Medium'],
        'status': ['Open', 'Closed', 'Open']
    })

    print("模拟数据上下文：")
    print(mock_data.to_string(index=False))
    print()

    test_queries = [
        "测试通过率",
        "缺陷数量"
    ]

    for i, question in enumerate(test_queries, 1):
        print(f"测试 {i}/{len(test_queries)}: {question}（基于当前筛选数据）")
        print("-" * 70)

        result = chat.ask(question, data_context=mock_data)

        if result["success"]:
            print(f"✅ 成功 (来源: {result['source']})")
        else:
            print(f"❌ 失败: {result.get('error')}")

        print()


def test_cache():
    """测试缓存功能"""
    print("=" * 70)
    print("测试 6: 缓存功能")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(llm_generate_func=mock_llm_generate)

    question = "统计所有缺陷的数量"

    print("第一次查询（应该使用 SQL）：")
    result1 = chat.ask(question, use_cache=False)
    print(f"  来源: {result1['source']}")
    print(f"  缓存命中: {result1.get('from_cache', False)}")
    print()

    print("第二次查询（应该使用缓存）：")
    result2 = chat.ask(question, use_cache=True)
    print(f"  来源: {result2['source']}")
    print(f"  缓存命中: {result2.get('from_cache', False)}")

    if result2.get('from_cache'):
        print("\n✅ 缓存功能正常")
    else:
        print("\n❌ 缓存功能异常")

    print()


def test_query_stats():
    """测试查询统计"""
    print("=" * 70)
    print("测试 7: 查询统计")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(llm_generate_func=mock_llm_generate)

    # 运行一些查询
    queries = [
        "统计所有缺陷的数量",
        "各模块的缺陷数量统计",
        "什么是缺陷的严重度级别？",
        "测试通过率是多少"
    ]

    for question in queries:
        chat.ask(question)

    # 获取统计
    stats = chat.get_stats()

    print("查询统计：")
    print(f"  总查询数: {stats['total_queries']}")
    print(f"  SQL 查询数: {stats['sql_queries']}")
    print(f"  LLM 查询数: {stats['llm_queries']}")
    print(f"  SQL 成功率: {stats['sql_success_rate']}")
    print(f"  平均耗时: {stats['avg_time_ms']}")
    print(f"  缓存命中率: {stats['cache_hit_rate']}")

    print()


def test_engine_stats():
    """测试引擎统计"""
    print("=" * 70)
    print("测试 8: 引擎统计")
    print("=" * 70 + "\n")

    chat = AIChatWithSQLOptimized(llm_generate_func=mock_llm_generate)

    # 获取引擎统计
    engine_stats = chat.get_engine_stats()

    print("引擎统计：")
    print(json.dumps(engine_stats, indent=2, ensure_ascii=False))

    print()


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("增强的 AI Chat with SQL - 集成测试")
    print("=" * 70 + "\n")

    # 运行所有测试
    test_basic_queries()
    test_time_range_queries()
    test_complex_queries()
    test_knowledge_questions()
    test_data_context()
    test_cache()
    test_query_stats()
    test_engine_stats()

    print("=" * 70)
    print("所有集成测试完成！✅")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
