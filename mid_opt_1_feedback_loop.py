#!/usr/bin/env python3
"""
中期优化项目 1：实现反馈循环

目标：收集用户反馈，持续优化 SQL 生成
预期效果：准确率 +5-8%
时间：1周

实施步骤：
1. 在 AI Chat 中添加反馈按钮（正确/错误）
2. 记录所有反馈到数据库
3. 分析失败模式
4. 自动生成新的示例
5. 更新 Few-shot 示例库

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import sqlite3
import re

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from sql_query_engine import FewShotExamples


# ============================================================================
# 反馈数据结构
# ============================================================================

@dataclass
class FeedbackRecord:
    """反馈记录"""
    id: Optional[int] = None
    question: str = ""
    generated_sql: str = ""
    is_correct: bool = False
    corrected_sql: Optional[str] = None
    error_type: Optional[str] = None
    feedback_type: str = "user"  # user | automatic
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "sql_chat"  # sql_chat | api | batch


# ============================================================================
# 反馈管理器
# ============================================================================

class FeedbackManager:
    """反馈管理器"""

    def __init__(self, db_path: str = "database/feedback.db"):
        """
        初始化反馈管理器

        Args:
            db_path: 反馈数据库路径
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """初始化反馈数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 创建反馈表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                generated_sql TEXT NOT NULL,
                is_correct BOOLEAN NOT NULL,
                corrected_sql TEXT,
                error_type TEXT,
                feedback_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL
            )
        """)

        # 创建分析表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_date TEXT NOT NULL,
                total_feedback INTEGER NOT NULL,
                correct_feedback INTEGER NOT NULL,
                incorrect_feedback INTEGER NOT NULL,
                accuracy REAL NOT NULL,
                common_error_types TEXT,
                new_examples_generated INTEGER
            )
        """)

        conn.commit()
        conn.close()

    def record_feedback(self, feedback: FeedbackRecord) -> int:
        """
        记录反馈

        Args:
            feedback: 反馈记录

        Returns:
            记录 ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO feedback (
                question, generated_sql, is_correct, corrected_sql,
                error_type, feedback_type, timestamp, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            feedback.question,
            feedback.generated_sql,
            feedback.is_correct,
            feedback.corrected_sql,
            feedback.error_type,
            feedback.feedback_type,
            feedback.timestamp,
            feedback.source
        ))

        feedback_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return feedback_id

    def analyze_feedback(self, days: int = 7) -> Dict[str, Any]:
        """
        分析反馈数据

        Args:
            days: 分析最近 N 天的反馈

        Returns:
            分析结果
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 统计总数
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as incorrect
            FROM feedback
            WHERE date(timestamp) >= date('now', ?)
        """, (f"-{days} days",))

        stats = cursor.fetchone()
        total, correct, incorrect = stats

        # 计算准确率
        accuracy = (correct / total * 100) if total > 0 else 0

        # 统计错误类型
        cursor.execute("""
            SELECT error_type, COUNT(*) as count
            FROM feedback
            WHERE is_correct = 0 AND date(timestamp) >= date('now', ?)
            GROUP BY error_type
            ORDER BY count DESC
        """, (f"-{days} days",))

        error_types = cursor.fetchall()

        # 获取常见错误模式
        common_errors = []
        for error_type, count in error_types:
            common_errors.append({
                "error_type": error_type,
                "count": count,
                "percentage": (count / incorrect * 100) if incorrect > 0 else 0
            })

        conn.close()

        return {
            "total_feedback": total,
            "correct_feedback": correct,
            "incorrect_feedback": incorrect,
            "accuracy": accuracy,
            "common_error_types": common_errors
        }

    def generate_new_examples(self, limit: int = 5) -> List[Dict[str, str]]:
        """
        从失败案例生成新的示例

        Args:
            limit: 生成示例的数量限制

        Returns:
            新生成的示例列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 获取最近的错误反馈
        cursor.execute("""
            SELECT question, generated_sql, corrected_sql, error_type
            FROM feedback
            WHERE is_correct = 0 AND corrected_sql IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit * 2,))  # 获取 2 倍，然后筛选

        feedbacks = cursor.fetchall()
        conn.close()

        new_examples = []
        seen_questions = set()

        # 生成示例（简化版）
        for question, generated_sql, corrected_sql, error_type in feedbacks:
            # 检查是否已存在相似问题
            if question in seen_questions:
                continue

            seen_questions.add(question)

            # 创建新示例
            new_examples.append({
                "question": question,
                "sql": corrected_sql,
                "note": f"用户反馈修正 - 错误类型: {error_type}",
                "source": "user_feedback"
            })

            if len(new_examples) >= limit:
                break

        return new_examples

    def update_examples_from_feedback(self, limit: int = 10) -> int:
        """
        从反馈更新 Few-shot 示例库

        Args:
            limit: 添加示例的最大数量

        Returns:
            实际添加的示例数量
        """
        new_examples = self.generate_new_examples(limit)
        added_count = 0

        for example in new_examples:
            # 检查是否已存在
            exists = False
            for ex in FewShotExamples.EXAMPLES:
                if ex["question"] == example["question"]:
                    exists = True
                    break

            if not exists:
                FewShotExamples.EXAMPLES.append({
                    "question": example["question"],
                    "sql": example["sql"],
                    "note": example.get("note", "")
                })
                added_count += 1

        return added_count

    def save_analysis(self, analysis: Dict[str, Any], new_examples_count: int):
        """
        保存分析结果

        Args:
            analysis: 分析结果
            new_examples_count: 新增示例数量
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 序列化常见错误类型
        common_errors_json = json.dumps(
            analysis["common_error_types"],
            ensure_ascii=False
        )

        cursor.execute("""
            INSERT INTO feedback_analysis (
                analysis_date, total_feedback, correct_feedback,
                incorrect_feedback, accuracy, common_error_types,
                new_examples_generated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            analysis["total_feedback"],
            analysis["correct_feedback"],
            analysis["incorrect_feedback"],
            analysis["accuracy"],
            common_errors_json,
            new_examples_count
        ))

        conn.commit()
        conn.close()

    def get_feedback_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取反馈历史记录

        Args:
            limit: 返回记录的数量限制

        Returns:
            反馈历史记录列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, question, generated_sql, is_correct, corrected_sql,
                   error_type, feedback_type, timestamp, source
            FROM feedback
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        history = []
        for row in rows:
            history.append({
                "id": row[0],
                "question": row[1],
                "generated_sql": row[2],
                "is_correct": row[3],
                "corrected_sql": row[4],
                "error_type": row[5],
                "feedback_type": row[6],
                "timestamp": row[7],
                "source": row[8]
            })

        return history


# ============================================================================
# 自动错误分类器
# ============================================================================

class ErrorClassifier:
    """自动错误分类器"""

    ERROR_PATTERNS = [
        {
            "type": "语法错误",
            "keywords": ["syntax error", "near", "at line", "SQLITE_ERROR"],
            "regex": r"syntax error"
        },
        {
            "type": "字段不存在",
            "keywords": ["no such column", "ambiguous column"],
            "regex": r"no such column"
        },
        {
            "type": "表不存在",
            "keywords": ["no such table"],
            "regex": r"no such table"
        },
        {
            "type": "除零错误",
            "keywords": ["division by zero", "divide by zero"],
            "regex": r"division by zero"
        },
        {
            "type": "类型错误",
            "keywords": ["type mismatch", "no such function", "invalid type"],
            "regex": r"type mismatch"
        },
        {
            "type": "约束错误",
            "keywords": ["constraint", "unique constraint", "foreign key"],
            "regex": r"constraint"
        }
    ]

    @classmethod
    def classify_error(cls, error_message: str) -> str:
        """
        分类错误类型

        Args:
            error_message: 错误消息

        Returns:
            错误类型
        """
        error_lower = error_message.lower()

        # 使用正则匹配
        for pattern in cls.ERROR_PATTERNS:
            if pattern.get("regex"):
                if re.search(pattern["regex"], error_lower, re.IGNORECASE):
                    return pattern["type"]

        # 使用关键词匹配
        for pattern in cls.ERROR_PATTERNS:
            if pattern.get("keywords"):
                for keyword in pattern["keywords"]:
                    if keyword in error_lower:
                        return pattern["type"]

        # 默认类型
        return "其他错误"


# ============================================================================
# 演示和测试
# ============================================================================

def demo_feedback_loop():
    """演示反馈循环"""
    print("=" * 70)
    print("中期优化项目 1: 实现反馈循环")
    print("=" * 70 + "\n")

    # 创建反馈管理器
    feedback_manager = FeedbackManager()

    # 模拟一些反馈数据
    sample_feedbacks = [
        FeedbackRecord(
            question="统计每个模块的缺陷数量",
            generated_sql="SELECT module, COUNT(*) FROM defects GROUP BY module",
            is_correct=True,
            source="demo"
        ),
        FeedbackRecord(
            question="统计每个模块的缺陷数量和测试数量",
            generated_sql="SELECT module, COUNT(*) as defect_count, COUNT(*) as test_count FROM defects d JOIN test_runs tr ON d.build_number = tr.build_number GROUP BY module",
            is_correct=False,
            corrected_sql="SELECT d.module, COUNT(DISTINCT d.id) as defect_count, COUNT(DISTINCT tr.id) as test_count FROM defects d LEFT JOIN test_runs tr ON d.build_number = tr.build_number GROUP BY d.module",
            error_type="业务逻辑错误",
            source="demo"
        ),
        FeedbackRecord(
            question="测试通过率",
            generated_sql="SELECT COUNT(*) / SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) FROM test_runs",
            is_correct=False,
            corrected_sql="SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs",
            error_type="除零错误",
            source="demo"
        )
    ]

    # 记录反馈
    print("记录反馈数据...\n")
    for feedback in sample_feedbacks:
        feedback_id = feedback_manager.record_feedback(feedback)
        print(f"  记录 {feedback_id}: {feedback.question[:50]}...")
        print(f"    正确: {feedback.is_correct}")
        if feedback.error_type:
            print(f"    错误类型: {feedback.error_type}")
        print()

    # 分析反馈
    print("分析反馈数据...\n")
    analysis = feedback_manager.analyze_feedback(days=1)

    print(f"总反馈数: {analysis['total_feedback']}")
    print(f"正确反馈: {analysis['correct_feedback']}")
    print(f"错误反馈: {analysis['incorrect_feedback']}")
    print(f"准确率: {analysis['accuracy']:.1f}%")

    if analysis['common_error_types']:
        print(f"\n常见错误类型:")
        for error_type_info in analysis['common_error_types'][:3]:
            print(f"  - {error_type_info['error_type']}: {error_type_info['count']} 次 ({error_type_info['percentage']:.1f}%)")

    # 生成新示例
    print(f"\n生成新示例...\n")
    new_examples = feedback_manager.generate_new_examples(limit=2)

    print(f"生成了 {len(new_examples)} 个新示例:")
    for i, example in enumerate(new_examples, 1):
        print(f"  示例 {i}:")
        print(f"    问题: {example['question']}")
        print(f"    SQL: {example['sql'][:80]}...")
        print(f"    备注: {example.get('note', '')}")
        print()

    # 更新示例库
    print("更新示例库...\n")
    added_count = feedback_manager.update_examples_from_feedback(limit=2)

    print(f"添加了 {added_count} 个新示例到 Few-shot 示例库")
    print(f"当前示例总数: {len(FewShotExamples.EXAMPLES)}")

    # 保存分析结果
    print(f"\n保存分析结果...")
    feedback_manager.save_analysis(analysis, added_count)
    print("✅ 分析结果已保存")

    # 获取反馈历史
    print(f"\n获取反馈历史...\n")
    history = feedback_manager.get_feedback_history(limit=5)

    print("最近的反馈记录:")
    for record in history[:3]:
        print(f"  - {record['question'][:50]}...")
        print(f"    正确: {record['is_correct']}")
        if record.get('error_type'):
            print(f"    错误类型: {record['error_type']}")
        print()


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("中期优化项目 1: 实现反馈循环")
    print("=" * 70 + "\n")

    # 演示反馈循环
    demo_feedback_loop()

    # 总结
    print("=" * 70)
    print("中期优化项目 1 完成总结")
    print("=" * 70 + "\n")

    print("✅ 完成的工作:")
    print("  1. 实现了反馈管理器（FeedbackManager）")
    print("  2. 实现了自动错误分类器（ErrorClassifier）")
    print("  3. 实现了反馈数据库存储")
    print("  4. 实现了反馈分析和统计")
    print("  5. 实现了从反馈生成新示例")
    print("  6. 实现了自动更新示例库")

    print(f"\n📊 核心功能:")
    print("  1. 记录用户反馈（正确/错误）")
    print("  2. 自动分类错误类型")
    print("  3. 分析反馈数据统计")
    print("  4. 从失败案例生成新示例")
    print("  5. 自动更新 Few-shot 示例库")
    print("  6. 保存分析历史")

    print(f"\n🎯 预期效果:")
    print(f"  准确率提升: +5-8%")
    print(f"  工作时间: 1周")

    print(f"\n📋 数据库表:")
    print("  1. feedback - 存储反馈记录")
    print("  2. feedback_analysis - 存储分析结果")

    print(f"\n🚀 下一步:")
    print("  1. 在 AI Chat UI 中添加反馈按钮")
    print("  2. 收集真实的用户反馈")
    print("  3. 持续分析和优化")
    print("  4. 定期更新示例库")

    print("\n" + "=" * 70)
    print("✅ 中期优化项目 1 框架完成！")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
