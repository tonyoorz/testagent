#!/usr/bin/env python3
"""
简化的 Prompt 测试 - 验证增强的 Prompt 构建

测试增强的 Prompt 构建器是否能正常工作

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from sql_query_engine import SQLQueryEngine, SchemaManager


def test_prompt_builders():
    """测试 Prompt 构建器"""
    print("=" * 70)
    print("测试增强的 Prompt 构建")
    print("=" * 70 + "\n")

    # 初始化基础组件
    print("初始化 Schema 管理器...")
    schema_manager = SchemaManager("database/local_data.db")

    # 测试问题
    test_questions = [
        "统计所有缺陷的数量",
        "各模块的缺陷数量统计",
        "测试通过率是多少",
        "最近7天的测试通过率",
        "缺陷数量超过平均值的模块",
    ]

    for i, question in enumerate(test_questions, 1):
        print(f"\n{'=' * 70}")
        print(f"测试 {i}/{len(test_questions)}: {question}")
        print(f"{'=' * 70}\n")

        # 测试基础 Prompt
        print("【基础 Prompt】")
        from sql_query_engine import FewShotExamples, BusinessKnowledge

        basic_prompt_parts = [
            "# SQL 查询助手\n",
            "你是一个专业的 SQL 查询助手，专门查询汽车测试数据库。\n",
            "## 数据库 Schema\n",
            schema_manager.get_schema()[:200] + "...",  # 只显示前200个字符
            "\n## 业务知识\n",
            BusinessKnowledge.get_knowledge()[:200] + "...",
            "\n## 查询示例\n",
            FewShotExamples.get_examples(limit=2),
            "\n## 用户问题\n",
            f"{question}\n",
            "请生成 SQL 查询语句。只输出 SQL，不要任何解释或多余文字。"
        ]

        basic_prompt = "\n".join(basic_prompt_parts)
        print(f"长度: {len(basic_prompt)} 字符")
        print(f"包含 Few-shot 示例: {'✓' if '示例' in basic_prompt else '✗'}")
        print(f"包含 Schema: {'✓' if 'Schema' in basic_prompt else '✗'}")
        print(f"包含业务知识: {'✓' if '业务知识' in basic_prompt else '✗'}")

        # 测试增强的 Prompt
        print("\n【增强的 Prompt】")
        try:
            from enhanced_prompt_builder import create_enhanced_prompt_builder

            prompt_builder = create_enhanced_prompt_builder(schema_manager)
            enhanced_prompt = prompt_builder.build_prompt(question)

            print(f"长度: {len(enhanced_prompt)} 字符")
            print(f"包含思考过程: {'✓' if '思考过程' in enhanced_prompt else '✗'}")
            print(f"包含质量检查: {'✓' if '质量检查' in enhanced_prompt else '✗'}")
            print(f"包含最佳实践: {'✓' if '最佳实践' in enhanced_prompt else '✗'}")
            print(f"包含常见错误: {'✓' if '常见错误' in enhanced_prompt else '✗'}")

            # 比较 Prompt 长度
            print(f"\n【长度对比】")
            print(f"基础 Prompt: {len(basic_prompt)} 字符")
            print(f"增强 Prompt: {len(enhanced_prompt)} 字符")
            print(f"增加: {len(enhanced_prompt) - len(basic_prompt)} 字符 ({(len(enhanced_prompt) - len(basic_prompt)) / len(basic_prompt) * 100:.1f}%)")

        except Exception as e:
            print(f"❌ 增强的 Prompt 构建失败: {e}")

    print(f"\n{'=' * 70}")
    print("Prompt 构建测试完成")
    print(f"{'=' * 70}\n")


def test_optimization_config():
    """测试优化配置"""
    print("=" * 70)
    print("测试优化配置")
    print("=" * 70 + "\n")

    from enhanced_prompt_builder import PromptOptimizationConfig

    config = PromptOptimizationConfig()

    print("优化配置:")
    print(f"  - 包含思考过程: {config.include_thinking_process}")
    print(f"  - 包含质量检查: {config.include_quality_checks}")
    print(f"  - 包含常见错误: {config.include_common_errors}")
    print(f"  - 包含最佳实践: {config.include_best_practices}")
    print(f"  - Few-shot 示例数量: {config.few_shot_examples_count}")
    print(f"  - 使用结构化示例: {config.use_structured_examples}")

    print(f"\n{'=' * 70}\n")


def test_business_rules():
    """测试增强的业务规则"""
    print("=" * 70)
    print("测试增强的业务规则")
    print("=" * 70 + "\n")

    from enhanced_prompt_builder import EnhancedBusinessRules

    rules = EnhancedBusinessRules.get_rules()

    print(f"业务规则长度: {len(rules)} 字符")
    print(f"包含最佳实践: {'✓' if '最佳实践' in rules else '✗'}")
    print(f"包含数据选择: {'✓' if '数据选择' in rules else '✗'}")
    print(f"包含时间过滤: {'✓' if '时间过滤' in rules else '✗'}")
    print(f"包含聚合函数: {'✓' if '聚合函数' in rules else '✗'}")
    print(f"包含 JOIN 使用: {'✓' if 'JOIN' in rules else '✗'}")
    print(f"包含子查询: {'✓' if '子查询' in rules else '✗'}")
    print(f"包含窗口函数: {'✓' if '窗口函数' in rules else '✗'}")
    print(f"包含性能优化: {'✓' if '性能优化' in rules else '✗'}")

    print(f"\n规则片段（前500字符）:\n{rules[:500]}...")

    print(f"\n{'=' * 70}\n")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("增强的 Prompt 构建器测试")
    print("=" * 70 + "\n")

    # 运行测试
    test_optimization_config()
    test_business_rules()
    test_prompt_builders()

    print("\n" + "=" * 70)
    print("所有测试完成！✅")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
