#!/usr/bin/env python3
"""
单元测试 - Few-shot 示例测试

测试 FewShotExamples 类的功能
"""

import unittest
from sql_query_engine import FewShotExamples


class TestFewShotExamples(unittest.TestCase):
    """Few-shot 示例测试"""

    def test_examples_count(self):
        """测试示例数量"""
        count = len(FewShotExamples.EXAMPLES)

        # 应该有 60 个示例
        self.assertGreaterEqual(count, 50, "示例数量应该大于等于 50")
        self.assertEqual(count, 60, "示例数量应该等于 60")

    def test_examples_structure(self):
        """测试示例结构"""
        for i, ex in enumerate(FewShotExamples.EXAMPLES, 1):
            # 每个示例应该有 'question' 和 'sql' 字段
            self.assertIn('question', ex, f"示例 {i} 缺少 'question' 字段")
            self.assertIn('sql', ex, f"示例 {i} 缺少 'sql' 字段")

            # 字段值不应该为空
            self.assertIsNotNone(ex['question'], f"示例 {i} 的 'question' 为 None")
            self.assertIsNotNone(ex['sql'], f"示例 {i} 的 'sql' 为 None")

            # 字段值不应该为空字符串
            self.assertNotEqual(ex['question'], "", f"示例 {i} 的 'question' 为空字符串")
            self.assertNotEqual(ex['sql'], "", f"示例 {i} 的 'sql' 为空字符串")

    def test_sql_syntax(self):
        """测试 SQL 语法"""
        import re

        for i, ex in enumerate(FewShotExamples.EXAMPLES, 1):
            sql = ex['sql']

            # SQL 应该以 SELECT 开头
            self.assertTrue(
                re.match(r'^\s*SELECT', sql, re.IGNORECASE),
                f"示例 {i} ('{ex['question']}') 不是 SELECT 语句"
            )

            # 检查括号平衡
            self.assertEqual(
                sql.count('('),
                sql.count(')'),
                f"示例 {i} ('{ex['question']}') 括号不平衡"
            )

    def test_get_examples_with_limit(self):
        """测试获取限制数量的示例"""
        examples = FewShotExamples.get_examples(limit=5)

        # 检查格式
        self.assertIn("示例查询（学习这些模式）：", examples)

        # 检查示例数量
        self.assertIn("示例 1:", examples)
        self.assertIn("示例 2:", examples)
        self.assertIn("示例 3:", examples)
        self.assertIn("示例 4:", examples)
        self.assertIn("示例 5:", examples)
        self.assertNotIn("示例 6:", examples)

    def test_get_examples_default_limit(self):
        """测试默认限制数量"""
        examples = FewShotExamples.get_examples()

        # 默认应该是 5 个示例
        self.assertIn("示例 1:", examples)
        self.assertIn("示例 5:", examples)
        self.assertNotIn("示例 6:", examples)

    def test_find_similar_example(self):
        """测试查找相似示例"""
        # 测试各种关键词
        test_cases = [
            ("统计缺陷", "数量"),
            ("通过率", "通过率"),
            ("覆盖率", "覆盖"),
            ("趋势", "趋势"),
            ("测试", "测试"),
            ("Critical", "Critical")
        ]

        for question, keyword in test_cases:
            similar = FewShotExamples.find_similar_example(question)
            self.assertIsNotNone(similar, f"应该能找到关于 '{keyword}' 的相似示例")

            # 应该包含问题或 SQL
            self.assertIn("问题:", similar)
            self.assertIn("SQL:", similar)

    def test_find_similar_example_no_match(self):
        """测试查找不相似示例"""
        # 使用不太可能匹配的关键词
        similar = FewShotExamples.find_similar_example("这个问题不太可能匹配")

        # 应该返回 None 或空字符串
        self.assertIsNone(similar)

    def test_example_categories(self):
        """测试示例分类"""
        examples = FewShotExamples.EXAMPLES

        # 检查是否包含各种类型的示例
        categories = {
            "基础统计": ["统计", "数量"],
            "时间过滤": ["最近", "本周", "最近7天", "本月"],
            "多表 JOIN": ["对应的测试执行", "覆盖率与缺陷", "在不同严重度"],
            "子查询": ["超过平均值", "低于项目平均", "重开次数最多"],
            "窗口函数": ["排序并编号", "排名", "最新的", "密度排名"],
            "时间序列": ["趋势分析", "每周", "每日", "季度"],
            "复杂条件": ["高风险", "严重度级别", "多条件筛选", "综合分析"]
        }

        for category, keywords in categories.items():
            found = False
            for ex in examples:
                question = ex['question']
                if any(keyword in question for keyword in keywords):
                    found = True
                    break

            self.assertTrue(found, f"应该找到 {category} 类型的示例")

    def test_no_duplicate_questions(self):
        """测试没有重复的问题"""
        questions = [ex['question'] for ex in FewShotExamples.EXAMPLES]

        # 检查是否有重复
        unique_questions = set(questions)
        self.assertEqual(len(questions), len(unique_questions), "不应该有重复的问题")

    def test_sql_quality(self):
        """测试 SQL 质量"""
        for i, ex in enumerate(FewShotExamples.EXAMPLES, 1):
            sql = ex['sql']

            # 检查 SQL 是否为空
            self.assertTrue(len(sql) > 0, f"示例 {i} 的 SQL 为空")

            # 检查 SQL 是否包含常见 SQL 关键词
            sql_upper = sql.upper()
            self.assertTrue(
                any(keyword in sql_upper for keyword in ['SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY', 'ORDER BY']),
                f"示例 {i} 的 SQL 应该包含常见 SQL 关键词"
            )

    def test_example_formatting(self):
        """测试示例格式化输出"""
        examples_str = FewShotExamples.get_examples(limit=3)

        # 检查格式
        self.assertIn("\n", examples_str)
        self.assertIn("问题:", examples_str)
        self.assertIn("SQL:", examples_str)


if __name__ == '__main__':
    unittest.main()
