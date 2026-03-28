#!/usr/bin/env python3
"""
性能对比测试 - 原版 vs 优化版

对比原版 SQL 查询引擎和优化版的性能和准确率

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sys
import time
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from sql_query_engine import SQLQueryEngine
from sql_query_engine_optimized_v2 import OptimizedSQLQueryEngine, create_optimized_sql_query_engine


# ============================================================================
# 测试配置
# ============================================================================

@dataclass
class TestQuery:
    """测试查询"""
    question: str
    category: str


# 测试查询列表（包含各种复杂度）
TEST_QUERIES = [
    # 基础查询
    TestQuery("统计所有缺陷的数量", "基础"),
    TestQuery("各模块的缺陷数量统计", "基础"),
    TestQuery("测试通过率是多少", "基础"),

    # 时间过滤
    TestQuery("最近7天的测试通过率", "时间"),
    TestQuery("本周新增的缺陷数量", "时间"),
    TestQuery("最近30天创建的 Critical 缺陷", "时间"),

    # 多表 JOIN
    TestQuery("每个缺陷对应的测试执行情况", "JOIN"),
    TestQuery("测试覆盖率与缺陷数量的关系", "JOIN"),
    TestQuery("各项目在不同严重度上的缺陷分布", "JOIN"),

    # 子查询
    TestQuery("缺陷数量超过平均值的模块", "子查询"),
    TestQuery("测试通过率低于项目平均水平的模块", "子查询"),
    TestQuery("重开次数最多的前 5 个缺陷", "子查询"),

    # 窗口函数
    TestQuery("按创建时间排序并给每个缺陷编号", "窗口函数"),
    TestQuery("每个模块内缺陷数量排名", "窗口函数"),
    TestQuery("查找各模块最新的缺陷", "窗口函数"),

    # 时间序列
    TestQuery("缺陷趋势分析（按月）", "时间序列"),
    TestQuery("每周缺陷数量统计", "时间序列"),
    TestQuery("每日测试执行趋势", "时间序列"),

    # 复杂条件
    TestQuery("高风险缺陷（Critical + 重开 > 3 次）", "复杂条件"),
    TestQuery("多条件筛选：Critical 或 Major 状态为 Open", "复杂条件"),
    TestQuery("过去14天内创建的 Critical 缺陷，且未被修复", "复杂条件"),
]


# ============================================================================
# Mock LLM 生成函数
# ============================================================================

def mock_llm_generate(prompt: str) -> str:
    """
    Mock LLM 生成函数

    在实际使用中，这里应该调用真实的 LLM API
    """
    # 这是一个简单的 mock，实际应该调用 LLM API
    # 这里只是演示，返回一个固定的 SQL

    # 从 prompt 中提取用户问题
    import re
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
        elif "测试覆盖率" in question and "缺陷数量" in question:
            return "SELECT tc.module, tc.component, tc.coverage_percent, COUNT(d.id) as defect_count FROM test_coverage tc LEFT JOIN defects d ON tc.module = d.module AND tc.component = d.component WHERE tc.test_week = (SELECT MAX(test_week) FROM test_coverage) GROUP BY tc.module, tc.component ORDER BY tc.coverage_percent ASC LIMIT 20"
        elif "超过平均值" in question:
            return "SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module HAVING COUNT(*) > (SELECT AVG(defect_count) FROM (SELECT module, COUNT(*) as defect_count FROM defects GROUP BY subq.module) as subq) ORDER BY defect_count DESC LIMIT 10"
        elif "低于项目平均" in question and "通过率" in question:
            return "SELECT module, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs GROUP BY module HAVING pass_rate < (SELECT ROUND(AVG(pass_rate), 2) FROM (SELECT module, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs GROUP BY module) as avg_rates) ORDER BY pass_rate ASC LIMIT 10"
        elif "重开次数最多" in question:
            return "SELECT * FROM defects WHERE pingpong = (SELECT MAX(pingpong) FROM defects) UNION SELECT * FROM defects WHERE pingpong = (SELECT MAX(pingpong) FROM defects WHERE pingpong < (SELECT MAX(pingpong) FROM defects)) ORDER BY pingpong DESC LIMIT 5"
        elif "排序并编号" in question:
            return "SELECT id, severity, status, creation_time, ROW_NUMBER() OVER (ORDER BY creation_time DESC) as row_num FROM defects LIMIT 20"
        elif "排名" in question and "模块内" in question:
            return "SELECT module, id, severity, creation_time, ROW_NUMBER() OVER (PARTITION BY module ORDER BY creation_time DESC) as rank_in_module FROM defects WHERE module IS NOT NULL LIMIT 20"
        elif "最新" in question and "各模块" in question:
            return "SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY module ORDER BY creation_time DESC) as rn FROM defects) ranked WHERE rn = 1 ORDER BY creation_time DESC LIMIT 20"
        elif "趋势分析" in question and "按月" in question:
            return "SELECT strftime('%Y-%m', creation_time) as month, COUNT(*) as total_defects, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical_count FROM defects WHERE creation_time IS NOT NULL GROUP BY strftime('%Y-%m', creation_time) ORDER BY month DESC LIMIT 12"
        elif "每周" in question and "缺陷数量" in question:
            return "SELECT strftime('%Y-W%W', creation_time) as week, COUNT(*) as defect_count, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical_count, SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major_count FROM defects WHERE creation_time >= date('now', '-90 days') GROUP BY week ORDER BY week DESC LIMIT 12"
        elif "每日" in question and "测试执行" in question:
            return "SELECT DATE(start_time) as date, COUNT(*) as test_count, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs WHERE start_time >= date('now', '-30 days') GROUP BY date ORDER BY date DESC LIMIT 30"
        elif "高风险" in question and "Critical" in question and "重开" in question:
            return "SELECT * FROM defects WHERE severity = 'Critical' AND pingpong > 3 LIMIT 10"
        elif "Critical" in question or "Major" in question and "Open" in question:
            return "SELECT * FROM defects WHERE severity IN ('Critical', 'Major') AND status = 'Open' ORDER BY severity DESC, creation_time DESC LIMIT 20"
        elif "过去14天" in question and "Critical" in question and "未被修复" in question:
            return "SELECT * FROM defects WHERE severity = 'Critical' AND creation_time >= date('now', '-14 days') AND status NOT IN ('Fixed', 'Closed') ORDER BY creation_time DESC LIMIT 10"
        else:
            # 默认查询
            return "SELECT * FROM defects LIMIT 10"

    return "SELECT * FROM defects LIMIT 10"


# ============================================================================
# 性能测试
# ============================================================================

def run_performance_test(
    engine_name: str,
    engine,
    queries: List[TestQuery],
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    运行性能测试

    Args:
        engine_name: 引擎名称
        engine: SQL 查询引擎实例
        queries: 测试查询列表
        use_cache: 是否使用缓存

    Returns:
        性能测试结果
    """
    print(f"\n{'=' * 70}")
    print(f"测试引擎: {engine_name}")
    print(f"{'=' * 70}\n")

    results = {
        "engine_name": engine_name,
        "total_queries": len(queries),
        "successful": 0,
        "failed": 0,
        "total_time_ms": 0,
        "avg_time_ms": 0,
        "min_time_ms": float('inf'),
        "max_time_ms": 0,
        "retries": 0,
        "cache_hits": 0,
        "category_stats": {}
    }

    # 清空缓存
    engine.clear_cache()

    # 运行每个查询
    for i, test_query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] 测试: {test_query.question[:50]}...")

        try:
            start_time = time.time()

            # 执行查询
            result = engine.query(
                test_query.question,
                mock_llm_generate,
                use_cache=use_cache
            )

            elapsed_time = (time.time() - start_time) * 1000

            # 记录结果
            if result["success"]:
                results["successful"] += 1
                print(f"  ✅ 成功 ({elapsed_time:.1f}ms)")
                if result.get("from_cache"):
                    results["cache_hits"] += 1
                    print(f"     ⚡ 缓存命中")
            else:
                results["failed"] += 1
                print(f"  ❌ 失败: {result.get('error', 'Unknown error')}")

            # 统计时间
            results["total_time_ms"] += elapsed_time
            results["min_time_ms"] = min(results["min_time_ms"], elapsed_time)
            results["max_time_ms"] = max(results["max_time_ms"], elapsed_time)

            # 统计重试次数
            results["retries"] += result.get("retries", 0)

            # 分类统计
            category = test_query.category
            if category not in results["category_stats"]:
                results["category_stats"][category] = {
                    "total": 0,
                    "successful": 0,
                    "failed": 0
                }
            results["category_stats"][category]["total"] += 1
            if result["success"]:
                results["category_stats"][category]["successful"] += 1
            else:
                results["category_stats"][category]["failed"] += 1

        except Exception as e:
            results["failed"] += 1
            print(f"  💥 异常: {e}")

    # 计算平均值
    if results["total_queries"] > 0:
        results["avg_time_ms"] = results["total_time_ms"] / results["total_queries"]

    return results


def print_comparison_results(original: Dict[str, Any], optimized: Dict[str, Any]):
    """打印对比结果"""
    print(f"\n{'=' * 70}")
    print("性能对比结果")
    print(f"{'=' * 70}\n")

    # 基本统计
    print("📊 基本统计")
    print("-" * 70)
    print(f"{'指标':<30} {'原版':<15} {'优化版':<15} {'改进':<15}")
    print("-" * 70)

    metrics = [
        ("成功率", lambda r: f"{r['successful']}/{r['total_queries']} ({r['successful']*100//r['total_queries']}%)"),
        ("失败数", lambda r: str(r['failed'])),
        ("总耗时", lambda r: f"{r['total_time_ms']:.1f}ms"),
        ("平均耗时", lambda r: f"{r['avg_time_ms']:.1f}ms"),
        ("最小耗时", lambda r: f"{r['min_time_ms']:.1f}ms"),
        ("最大耗时", lambda r: f"{r['max_time_ms']:.1f}ms"),
        ("总重试次数", lambda r: str(r['retries'])),
        ("缓存命中", lambda r: str(r['cache_hits'])),
    ]

    for name, getter in metrics:
        orig_val = getter(original)
        opt_val = getter(optimized)

        # 计算改进
        improvement = ""
        if "耗时" in name and "平均" in name:
            if original['avg_time_ms'] > 0:
                improvement = f"{((orig_val - opt_val) / orig_val * 100):.1f}%"
        elif "成功率" in name:
            if original['successful'] < original['total_queries']:
                orig_rate = original['successful'] / original['total_queries']
                opt_rate = optimized['successful'] / optimized['total_queries']
                if orig_rate < opt_rate:
                    improvement = f"+{((opt_rate - orig_rate) / orig_rate * 100):.1f}%"

        print(f"{name:<30} {orig_val:<15} {opt_val:<15} {improvement:<15}")

    # 分类统计
    print(f"\n📋 分类统计")
    print("-" * 70)

    categories = sorted(set(
        list(original["category_stats"].keys()) +
        list(optimized["category_stats"].keys())
    ))

    for category in categories:
        orig_stats = original["category_stats"].get(category, {"total": 0, "successful": 0, "failed": 0})
        opt_stats = optimized["category_stats"].get(category, {"total": 0, "successful": 0, "failed": 0})

        orig_rate = f"{orig_stats['successful']}/{orig_stats['total']}"
        opt_rate = f"{opt_stats['successful']}/{opt_stats['total']}"

        print(f"{category:<20} 原版: {orig_rate:<10} 优化版: {opt_rate}")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("SQL 查询引擎性能对比测试")
    print("原版 vs 优化版")
    print("=" * 70 + "\n")

    # 创建引擎
    print("初始化引擎...")
    original_engine = SQLQueryEngine()
    optimized_engine = create_optimized_sql_query_engine(use_enhanced_prompt=True)

    # 显示引擎配置
    print(f"\n优化版引擎统计: {optimized_engine.get_stats()}")

    # 运行测试
    print("\n开始性能测试...")

    # 第一轮：不带缓存
    original_results = run_performance_test(
        "原版 SQL 查询引擎（无缓存）",
        original_engine,
        TEST_QUERIES,
        use_cache=False
    )

    optimized_results = run_performance_test(
        "优化版 SQL 查询引擎（无缓存）",
        optimized_engine,
        TEST_QUERIES,
        use_cache=False
    )

    # 第二轮：带缓存
    print(f"\n{'=' * 70}")
    print("第二轮：测试缓存性能")
    print(f"{'=' * 70}\n")

    original_cache_results = run_performance_test(
        "原版 SQL 查询引擎（有缓存）",
        original_engine,
        TEST_QUERIES,
        use_cache=True
    )

    optimized_cache_results = run_performance_test(
        "优化版 SQL 查询引擎（有缓存）",
        optimized_engine,
        TEST_QUERIES,
        use_cache=True
    )

    # 打印对比结果
    print_comparison_results(original_results, optimized_results)

    print(f"\n{'=' * 70}")
    print("缓存性能对比")
    print(f"{'=' * 70}\n")

    print(f"{'指标':<30} {'原版':<15} {'优化版':<15}")
    print("-" * 70)
    print(f"{'缓存命中数':<30} {original_cache_results['cache_hits']:<15} {optimized_cache_results['cache_hits']:<15}")
    print(f"{'缓存总耗时':<30} {original_cache_results['total_time_ms']:.1f}ms     {optimized_cache_results['total_time_ms']:.1f}ms")
    print(f"{'缓存平均耗时':<30} {original_cache_results['avg_time_ms']:.1f}ms     {optimized_cache_results['avg_time_ms']:.1f}ms")

    # 总结
    print(f"\n{'=' * 70}")
    print("测试总结")
    print(f"{'=' * 70}\n")

    print(f"✅ 测试查询总数: {len(TEST_QUERIES)}")
    print(f"📈 优化版成功: {optimized_results['successful']}/{optimized_results['total_queries']}")
    print(f"📊 优化版平均耗时: {optimized_results['avg_time_ms']:.1f}ms")

    if original_results['total_queries'] > 0:
        improvement = (optimized_results['successful'] - original_results['successful']) / original_results['total_queries'] * 100
        print(f"🚀 成功率提升: {improvement:.1f}%")

    print(f"\n{'=' * 70}\n")


if __name__ == "__main__":
    main()
