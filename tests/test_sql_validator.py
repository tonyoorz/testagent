#!/usr/bin/env python3
"""
单元测试 - SQL 验证器测试

测试 SQLValidator 类的功能
"""

import unittest
from sql_query_engine import SQLValidator, SQLQueryConfig


class TestSQLValidator(unittest.TestCase):
    """SQL 验证器测试"""

    def setUp(self):
        """测试前准备"""
        self.config = SQLQueryConfig()
        self.validator = SQLValidator(self.config.dangerous_keywords)

    def test_validate_safe_select(self):
        """测试安全的 SELECT 查询"""
        sql = "SELECT * FROM defects WHERE id = 1"
        is_valid, error = self.validator.validate(sql)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_dangerous_drop(self):
        """测试危险的 DROP 操作"""
        sql = "DROP TABLE defects"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("DROP", error)

    def test_validate_dangerous_delete(self):
        """测试危险的 DELETE 操作"""
        sql = "DELETE FROM defects WHERE id = 1"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("DELETE", error)

    def test_validate_dangerous_update(self):
        """测试危险的 UPDATE 操作"""
        sql = "UPDATE defects SET status = 'Closed' WHERE id = 1"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("UPDATE", error)

    def test_validate_dangerous_create(self):
        """测试危险的 CREATE 操作"""
        sql = "CREATE TABLE new_table (id INT)"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("CREATE", error)

    def test_validate_dangerous_alter(self):
        """测试危险的 ALTER 操作"""
        sql = "ALTER TABLE defects ADD COLUMN new_col INT"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("ALTER", error)

    def test_validate_dangerous_truncate(self):
        """测试危险的 TRUNCATE 操作"""
        sql = "TRUNCATE TABLE defects"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("TRUNCATE", error)

    def test_validate_non_select(self):
        """测试非 SELECT 语句"""
        sql = "SHOW TABLES"
        is_valid, error = self.validator.validate(sql)

        self.assertFalse(is_valid)
        self.assertIn("只允许 SELECT", error)

    def test_sanitize_sql(self):
        """测试 SQL 清理"""
        sql = "SELECT * FROM defects -- 这是一个注释\nWHERE id = 1"
        sanitized = self.validator.sanitize_sql(sql)

        # 注释应该被移除
        self.assertNotIn("--", sanitized)
        self.assertIn("SELECT * FROM defects WHERE id = 1", sanitized)

    def test_sanitize_sql_compression(self):
        """测试 SQL 空格压缩"""
        sql = "SELECT   *   FROM   defects   WHERE   id   =   1"
        sanitized = self.validator.sanitize_sql(sql)

        # 多余空格应该被压缩
        self.assertEqual(sanitized, "SELECT * FROM defects WHERE id = 1")

    def test_sanitize_block_comment(self):
        """测试块注释清理"""
        sql = "SELECT /* 多行注释\n第二行 */ * FROM defects WHERE id = 1"
        sanitized = self.validator.sanitize_sql(sql)

        # 块注释应该被移除
        self.assertNotIn("/*", sanitized)
        self.assertNotIn("*/", sanitized)

    def test_validate_complex_select(self):
        """测试复杂的 SELECT 查询"""
        sql = """
        SELECT d.id, d.severity, COUNT(*) as count
        FROM defects d
        JOIN test_runs tr ON d.build_number = tr.build_number
        WHERE d.creation_time >= date('now', '-7 days')
        GROUP BY d.id, d.severity
        ORDER BY count DESC
        LIMIT 10
        """
        is_valid, error = self.validator.validate(sql)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_case_insensitive_keywords(self):
        """测试关键词不区分大小写"""
        # 各种大小写组合
        dangerous_sqls = [
            "drop table defects",
            "DELETE FROM defects",
            "Update defects SET status = 'Closed'",
            "create TABLE new_table (id INT)"
        ]

        for sql in dangerous_sqls:
            is_valid, error = self.validator.validate(sql)
            self.assertFalse(is_valid, f"应该阻止: {sql}")
            self.assertIsNotNone(error)


if __name__ == '__main__':
    unittest.main()
