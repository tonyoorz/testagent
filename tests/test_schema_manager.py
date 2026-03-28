#!/usr/bin/env python3
"""
单元测试 - Schema 管理器测试

测试 SchemaManager 类的功能
"""

import unittest
import tempfile
import sqlite3
import os
from pathlib import Path
from sql_query_engine import SchemaManager


class TestSchemaManager(unittest.TestCase):
    """Schema 管理器测试"""

    def setUp(self):
        """测试前准备"""
        # 创建临时数据库
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # 创建测试表
        self._create_test_tables()

        # 初始化 Schema 管理器
        self.schema_manager = SchemaManager(self.db_path)

    def tearDown(self):
        """测试后清理"""
        # 删除临时数据库
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _create_test_tables(self):
        """创建测试表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 创建 defects 表
        cursor.execute("""
            CREATE TABLE defects (
                id INTEGER PRIMARY KEY,
                severity TEXT,
                status TEXT,
                project TEXT,
                module TEXT,
                creation_time TEXT
            )
        """)

        # 创建 test_runs 表
        cursor.execute("""
            CREATE TABLE test_runs (
                id INTEGER PRIMARY KEY,
                test_name TEXT,
                status TEXT,
                project TEXT,
                module TEXT,
                start_time TEXT
            )
        """)

        # 插入测试数据
        cursor.execute("""
            INSERT INTO defects (severity, status, project, module, creation_time)
            VALUES
                ('Critical', 'Open', 'ProjectA', 'Module1', '2025-03-28'),
                ('Major', 'Closed', 'ProjectA', 'Module1', '2025-03-27'),
                ('Medium', 'Open', 'ProjectB', 'Module2', '2025-03-26')
        """)

        cursor.execute("""
            INSERT INTO test_runs (test_name, status, project, module, start_time)
            VALUES
                ('Test1', 'Passed', 'ProjectA', 'Module1', '2025-03-28'),
                ('Test2', 'Failed', 'ProjectA', 'Module1', '2025-03-28'),
                ('Test3', 'Passed', 'ProjectB', 'Module2', '2025-03-27')
        """)

        conn.commit()
        conn.close()

    def test_get_schema_basic(self):
        """测试获取基础 Schema"""
        schema = self.schema_manager.get_schema()

        # 检查是否包含表名
        self.assertIn("defects", schema)
        self.assertIn("test_runs", schema)

        # 检查是否包含字段信息
        self.assertIn("id", schema)
        self.assertIn("severity", schema)
        self.assertIn("status", schema)

    def test_get_schema_cache(self):
        """测试 Schema 缓存"""
        # 第一次获取
        schema1 = self.schema_manager.get_schema()

        # 第二次获取（应该使用缓存）
        schema2 = self.schema_manager.get_schema()

        # 应该返回相同的结果
        self.assertEqual(schema1, schema2)

    def test_get_schema_force_refresh(self):
        """测试强制刷新 Schema"""
        # 第一次获取
        schema1 = self.schema_manager.get_schema()

        # 强制刷新
        schema2 = self.schema_manager.get_schema(force_refresh=True)

        # 内容应该相同（因为没有实际修改数据库）
        self.assertEqual(schema1, schema2)

    def test_get_table_sample(self):
        """测试获取表样本数据"""
        sample = self.schema_manager.get_table_sample("defects", limit=2)

        # 检查是否包含表名
        self.assertIn("defects", sample)

        # 检查是否包含字段信息
        self.assertIn("severity", sample)
        self.assertIn("status", sample)

        # 检查是否包含数据
        self.assertIn("Critical", sample)

    def test_get_table_sample_invalid_table(self):
        """测试获取不存在的表样本"""
        sample = self.schema_manager.get_table_sample("nonexistent_table")

        # 应该返回空字符串或错误信息
        self.assertEqual("", sample)

    def test_schema_format(self):
        """测试 Schema 格式"""
        schema = self.schema_manager.get_schema()

        # 检查格式是否正确
        self.assertIn("数据库 Schema", schema)
        self.assertIn("表:", schema)
        self.assertIn("字段:", schema)

    def test_multiple_tables(self):
        """测试多表 Schema"""
        schema = self.schema_manager.get_schema()

        # 检查是否包含所有表
        self.assertIn("defects", schema)
        self.assertIn("test_runs", schema)

        # 检查表的数量
        table_count = schema.count("### 表:")
        self.assertEqual(table_count, 2)

    def test_primary_key_marking(self):
        """测试主键标记"""
        schema = self.schema_manager.get_schema()

        # 检查主键标记
        self.assertIn("(PK)", schema)

    def test_data_types(self):
        """测试数据类型显示"""
        schema = self.schema_manager.get_schema()

        # 检查是否显示数据类型
        self.assertIn("INTEGER", schema)
        self.assertIn("TEXT", schema)


if __name__ == '__main__':
    unittest.main()
