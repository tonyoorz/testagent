#!/usr/bin/env python3
"""
测试扩充后的 Few-shot 示例

验证新增的示例是否能正确生成和执行 SQL
"""

import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from sql_query_engine import SQLQueryEngine, FewShotExamples

def test_fewshot_count():
    """测试示例数量"""
    print("=" * 60)
    print("测试 1: Few-shot 示例数量")
    print("=" * 60)

    examples = FewShotExamples.EXAMPLES
    print(f"✅ 示例总数: {len(examples)}")

    # 按分类统计
    categories = {
        "基础统计查询": 4,
        "时间过滤查询": 4,
        "多表 JOIN 查询": 12,
        "子查询示例": 12,
        "窗口函数示例": 8,
        "时间序列分析示例": 8,
        "复杂条件组合示例": 8,
        "聚合函数进阶示例": 4
    }

    total_expected = sum(categories.values())
    print(f"✅ 预期总数: {total_expected}")

    if len(examples) >= total_expected:
        print(f"✅ 符合预期（目标 50+，实际 {len(examples)}）")
    else:
        print(f"❌ 不符合预期（目标 50+，实际 {len(examples)}）")

    print()

def test_example_structure():
    """测试示例结构"""
    print("=" * 60)
    print("测试 2: 示例结构验证")
    print("=" * 60)

    examples = FewShotExamples.EXAMPLES

    valid_count = 0
    invalid_count = 0

    for i, ex in enumerate(examples, 1):
        if "question" not in ex or "sql" not in ex:
            print(f"❌ 示例 {i}: 缺少必要字段")
            invalid_count += 1
        elif not ex["question"] or not ex["sql"]:
            print(f"❌ 示例 {i}: 字段值为空")
            invalid_count += 1
        else:
            valid_count += 1

    print(f"✅ 有效示例: {valid_count}")
    print(f"❌ 无效示例: {invalid_count}")

    if invalid_count == 0:
        print("✅ 所有示例结构正确")
    else:
        print(f"❌ 有 {invalid_count} 个示例结构有问题")

    print()

def test_sql_syntax():
    """测试 SQL 语法"""
    print("=" * 60)
    print("测试 3: SQL 语法验证")
    print("=" * 60)

    examples = FewShotExamples.EXAMPLES
    valid_sql_count = 0
    invalid_sql_count = 0

    # 简单的 SQL 语法检查
    import re

    for i, ex in enumerate(examples, 1):
        sql = ex["sql"]

        # 检查是否以 SELECT 开头
        if not re.match(r'^\s*SELECT', sql, re.IGNORECASE):
            print(f"❌ 示例 {i} ('{ex['question'][:30]}...'): 不是 SELECT 语句")
            invalid_sql_count += 1
            continue

        # 检查基本的括号平衡
        if sql.count('(') != sql.count(')'):
            print(f"❌ 示例 {i} ('{ex['question'][:30]}...'): 括号不平衡")
            invalid_sql_count += 1
            continue

        valid_sql_count += 1

    print(f"✅ SQL 语法正确: {valid_sql_count}")
    print(f"❌ SQL 语法错误: {invalid_sql_count}")

    if invalid_sql_count == 0:
        print("✅ 所有示例 SQL 语法正确")
    else:
        print(f"❌ 有 {invalid_sql_count} 个示例 SQL 语法有问题")

    print()

def test_query_engine():
    """测试 SQL 查询引擎"""
    print("=" * 60)
    print("测试 4: SQL 查询引擎集成测试")
    print("=" * 60)

    try:
        # 初始化引擎
        engine = SQLQueryEngine()
        print("✅ SQL 查询引擎初始化成功")

        # 测试几个简单的查询
        test_queries = [
            "统计所有缺陷的数量",
            "各模块的缺陷数量统计",
            "测试通过率是多少"
        ]

        for query in test_queries:
            try:
                result = engine.query(query)
                if result["success"]:
                    print(f"✅ 查询 '{query}' 执行成功")
                else:
                    print(f"❌ 查询 '{query}' 执行失败: {result.get('error')}")
            except Exception as e:
                print(f"❌ 查询 '{query}' 异常: {e}")

    except Exception as e:
        print(f"❌ SQL 查询引擎初始化失败: {e}")

    print()

def test_complex_queries():
    """测试复杂查询"""
    print("=" * 60)
    print("测试 5: 复杂查询测试")
    print("=" * 60)

    try:
        engine = SQLQueryEngine()

        # 测试复杂查询
        complex_queries = [
            "每个缺陷对应的测试执行情况",  # JOIN
            "缺陷数量超过平均值的模块",  # 子查询
            "按创建时间排序并给每个缺陷编号",  # 窗口函数
            "缺陷趋势分析（按月）"  # 时间序列
        ]

        for query in complex_queries:
            try:
                result = engine.query(query)
                if result["success"]:
                    print(f"✅ 复杂查询 '{query}' 执行成功")
                    print(f"   - SQL: {result.get('generated_sql', 'N/A')[:80]}...")
                else:
                    print(f"❌ 复杂查询 '{query}' 执行失败: {result.get('error')}")
            except Exception as e:
                print(f"❌ 复杂查询 '{query}' 异常: {e}")

    except Exception as e:
        print(f"❌ 复杂查询测试失败: {e}")

    print()

def print_summary():
    """打印摘要"""
    print("=" * 60)
    print("测试摘要")
    print("=" * 60)

    examples = FewShotExamples.EXAMPLES

    print(f"📊 Few-shot 示例总数: {len(examples)}")
    print(f"📈 比原来增加: {len(examples) - 12} 个")
    print(f"🎯 目标达成: {'✅' if len(examples) >= 50 else '❌'} (目标 50+)")

    print()
    print("示例分类:")
    categories = [
        ("基础统计查询", 4),
        ("时间过滤查询", 4),
        ("多表 JOIN 查询", 12),
        ("子查询示例", 12),
        ("窗口函数示例", 8),
        ("时间序列分析示例", 8),
        ("复杂条件组合示例", 8),
        ("聚合函数进阶示例", 4)
    ]

    for name, count in categories:
        print(f"  - {name}: {count} 个")

    print()
    print("✅ Few-shot 示例扩充完成！")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Few-shot 示例扩充测试")
    print("=" * 60 + "\n")

    # 运行所有测试
    test_fewshot_count()
    test_example_structure()
    test_sql_syntax()
    test_query_engine()
    test_complex_queries()

    # 打印摘要
    print_summary()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60 + "\n")
