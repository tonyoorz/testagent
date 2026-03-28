#!/usr/bin/env python3
"""
Text-to-SQL Agent 单元测试

测试 Text-to-SQL Agent 的核心功能：
- SQL 生成和执行
- 缓存机制
- 错误处理
- 业务规则集成
- Few-shot 学习

运行测试：
python chatdb/test_text_to_sql_agent.py

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import os
import sys
import sqlite3
import unittest
import tempfile
from pathlib import Path
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chatdb.text_to_sql_agent import (
    TextToSQLAgent,
    TextToSQLAgentConfig,
    create_text_to_sql_agent,
    QueryCache,
    SQLValidator,
    SQLExecutor,
    SchemaDescriptionLoader,
    FewshotExamplesLoader
)


# ============================================================================
# 创建测试数据库
# =============================================================================

def create_test_db():
    """创建测试数据库"""
    db_path = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建 defects 表
    cursor.execute("""
        CREATE TABLE defects (
            id INTEGER PRIMARY KEY,
            name TEXT,
            project TEXT,
            ecu TEXT,
            status_phase TEXT,
            matrix TEXT,
            is_topissue INTEGER,
            topissue_risk_score REAL,
            ecu_no_of_changes INTEGER,
            domain_pingpong_count INTEGER,
            processing_cycle_days INTEGER,
            creation_time TEXT,
            parent_child TEXT,
            child_count INTEGER
        )
    """)
    
    # 创建 test_executions 表
    cursor.execute("""
        CREATE TABLE test_executions (
            id INTEGER PRIMARY KEY,
            test_id TEXT,
            test_name TEXT,
            project TEXT,
            run_status TEXT,
            test_week TEXT
        )
    """)
    
    # 插入测试数据
    test_defects = [
        (1, '导航无法启动', 'App', 'IuK_HU', '04-In Progress', 'Matrix-1A', 1, 145.5, 5, 2, 45, '2025-03-28 10:30:00', 'Parent', 3),
        (2, '蓝牙连接失败', 'App', 'DIPS_HU', '03-In Analysis', 'Matrix-1B', 1, 132.0, 3, 1, 38, '2025-03-27 14:20:00', 'Child', 0),
        (3, '音频播放问题', 'IDC', 'IuK_HU', '02-In Pre-Analysis', 'Matrix-2A', 0, 45.0, 1, 0, 15, '2025-03-26 09:15:00', 'Parent', 1),
        (4, '地图显示异常', 'MGU', 'DIPS_HU', '01-New', 'Matrix-3A', 0, 30.0, 0, 0, 2, '2025-03-28 15:00:00', None, 0),
        (5, 'RSU 更新失败', 'RSU', 'IuK_HU', '04-In Progress', 'Matrix-1C', 1, 110.0, 4, 3, 42, '2025-03-25 11:45:00', 'Parent', 5)
    ]
    
    cursor.executemany("""
        INSERT INTO defects VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, test_defects)
    
    # 插入测试执行数据
    test_executions = [
        (1, 'TC-001', 'Navigation start test', 'App', 'Passed', '2025-CW42'),
        (2, 'TC-002', 'Bluetooth connection test', 'App', 'Failed', '2025-CW42'),
        (3, 'TC-003', 'Audio playback test', 'IDC', 'Passed', '2025-CW42')
    ]
    
    cursor.executemany("""
        INSERT INTO test_executions VALUES (?, ?, ?, ?, ?, ?)
    """, test_executions)
    
    conn.commit()
    conn.close()
    
    return db_path


# ============================================================================
# 测试用例
# =============================================================================

class TestQueryCache(unittest.TestCase):
    """测试查询缓存"""
    
    def setUp(self):
        """设置测试"""
        self.cache = QueryCache(ttl_seconds=60)
        self.test_df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['A', 'B', 'C']
        })
    
    def test_cache_set_get(self):
        """测试缓存设置和获取"""
        query = "SELECT * FROM defects"
        sql = "SELECT id, name FROM defects"
        
        # 设置缓存
        entry = self.cache.set(query, sql, self.test_df)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.query, query)
        self.assertEqual(entry.sql, sql)
    
    def test_cache_hit(self):
        """测试缓存命中"""
        query = "SELECT * FROM defects"
        sql = "SELECT id, name FROM defects"
        
        self.cache.set(query, sql, self.test_df)
        cached = self.cache.get(query)
        
        self.assertIsNotNone(cached)
        self.assertEqual(cached.query, query)
        self.assertTrue(len(cached.result) == len(self.test_df))
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        cached = self.cache.get("SELECT * FROM defects WHERE id = 999")
        self.assertIsNone(cached)
    
    def test_cache_clear(self):
        """测试缓存清空"""
        query = "SELECT * FROM defects"
        sql = "SELECT id, name FROM defects"
        
        self.cache.set(query, sql, self.test_df)
        self.cache.clear()
        
        cached = self.cache.get(query)
        self.assertIsNone(cached)
    
    def test_cache_expiry(self):
        """测试缓存过期"""
        query = "SELECT * FROM defects"
        sql = "SELECT id, name FROM defects"
        
        # 创建已过期的缓存（TTL = 0）
        cache = QueryCache(ttl_seconds=0)
        cache.set(query, sql, self.test_df)
        
        cached = cache.get(query)
        self.assertIsNone(cached)


class TestSQLValidator(unittest.TestCase):
    """测试 SQL 验证器"""
    
    def setUp(self):
        """设置测试"""
        self.dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER"]
        self.validator = SQLValidator(self.dangerous_keywords, allow_write_operations=False)
    
    def test_valid_select(self):
        """测试有效的 SELECT 查询"""
        sql = "SELECT * FROM defects WHERE is_topissue = 1"
        is_valid, error = self.validator.validate(sql)
        
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_dangerous_drop(self):
        """测试危险的 DROP 操作"""
        sql = "DROP TABLE defects"
        is_valid, error = self.validator.validate(sql)
        
        self.assertFalse(is_valid)
        self.assertIn("DROP", error)
    
    def test_dangerous_delete(self):
        """测试危险的 DELETE 操作"""
        sql = "DELETE FROM defects WHERE id = 1"
        is_valid, error = self.validator.validate(sql)
        
        self.assertFalse(is_valid)
        self.assertIn("DELETE", error)
    
    def test_missing_from(self):
        """测试缺少 FROM 子句"""
        sql = "SELECT 1"
        is_valid, error = self.validator.validate(sql)
        
        self.assertFalse(is_valid)
        self.assertIn("FROM", error)
    
    def test_unmatched_parentheses(self):
        """测试括号不匹配"""
        sql = "SELECT * FROM defects WHERE (is_topissue = 1"
        is_valid, error = self.validator.validate(sql)
        
        self.assertFalse(is_valid)
        self.assertIn("括号", error)
    
    def test_allow_write_operations(self):
        """测试允许写操作"""
        validator = SQLValidator(self.dangerous_keywords, allow_write_operations=True)
        sql = "UPDATE defects SET name = 'test' WHERE id = 1"
        
        is_valid, error = validator.validate(sql)
        self.assertTrue(is_valid)


class TestSQLExecutor(unittest.TestCase):
    """测试 SQL 执行器"""
    
    def setUp(self):
        """设置测试"""
        self.db_path = create_test_db()
        self.executor = SQLExecutor(self.db_path)
    
    def tearDown(self):
        """清理测试"""
        import os
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_execute_valid_query(self):
        """测试执行有效查询"""
        sql = "SELECT * FROM defects"
        success, df, error = self.executor.execute(sql)
        
        self.assertTrue(success)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 5)
        self.assertIsNone(error)
    
    def test_execute_with_where(self):
        """测试执行带 WHERE 的查询"""
        sql = "SELECT * FROM defects WHERE is_topissue = 1"
        success, df, error = self.executor.execute(sql)
        
        self.assertTrue(success)
        self.assertEqual(len(df), 3)  # 3 个 TopIssue
    
    def test_execute_invalid_query(self):
        """测试执行无效查询"""
        sql = "SELECT * FROM non_existent_table"
        success, df, error = self.executor.execute(sql)
        
        self.assertFalse(success)
        self.assertIsNone(df)
        self.assertIsNotNone(error)
    
    def test_execute_aggregation(self):
        """测试执行聚合查询"""
        sql = "SELECT COUNT(*) as total FROM defects"
        success, df, error = self.executor.execute(sql)
        
        self.assertTrue(success)
        self.assertEqual(df.iloc[0]['total'], 5)
    
    def test_execute_join(self):
        """测试执行 JOIN 查询"""
        sql = """
            SELECT d.id, d.name, t.test_name
            FROM defects d
            LEFT JOIN test_executions t ON d.project = t.project
            WHERE d.id = 1
        """
        success, df, error = self.executor.execute(sql)
        
        self.assertTrue(success)
        self.assertEqual(len(df), 1)


class TestSchemaDescriptionLoader(unittest.TestCase):
    """测试 Schema 描述加载器"""
    
    def setUp(self):
        """设置测试"""
        self.schema_path = "chatdb/schema_description.md"
        self.loader = SchemaDescriptionLoader(self.schema_path)
    
    def test_load_schema(self):
        """测试加载 Schema 描述"""
        schema = self.loader.load()
        
        self.assertIsNotNone(schema)
        self.assertIn("defects", schema)
        self.assertIn("test_executions", schema)
    
    def test_load_business_terms(self):
        """测试加载业务术语"""
        terms = self.loader.load_business_terms()
        
        self.assertIsNotNone(terms)
        self.assertIn("TopIssue", terms)


class TestFewshotExamplesLoader(unittest.TestCase):
    """测试 Few-shot 示例加载器"""
    
    def setUp(self):
        """设置测试"""
        self.fewshot_path = "chatdb/fewshot_examples.md"
        self.loader = FewshotExamplesLoader(self.fewshot_path, max_examples=5)
    
    def test_load_examples(self):
        """测试加载示例"""
        examples = self.loader.load()
        
        self.assertIsNotNone(examples)
        self.assertGreater(len(examples), 0)
    
    def test_example_structure(self):
        """测试示例结构"""
        examples = self.loader.load()
        
        if examples:
            example = examples[0]
            self.assertIn('question', example)
            self.assertIn('sql', example)
            self.assertIn('description', example)
    
    def test_get_similar_examples(self):
        """测试获取相似示例"""
        question = "查询所有 TopIssue 缺陷"
        similar = self.loader.get_similar_examples(question, top_k=3)
        
        self.assertIsNotNone(similar)
        self.assertLessEqual(len(similar), 3)


class TestTextToSQLAgent(unittest.TestCase):
    """测试 Text-to-SQL Agent"""
    
    def setUp(self):
        """设置测试"""
        self.db_path = create_test_db()
        self.config = TextToSQLAgentConfig(
            db_path=self.db_path,
            schema_path="chatdb/schema_description.md",
            business_rules_path="chatdb/business_rules.py",
            fewshot_path="chatdb/fewshot_examples.md",
            max_retries=3,
            enable_cache=True,
            verbose=False
        )
        self.agent = TextToSQLAgent(self.config)
    
    def tearDown(self):
        """清理测试"""
        import os
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_query_top_issues(self):
        """测试查询 TopIssue"""
        question = "查询所有 TopIssue 缺陷，按风险评分降序排列"
        result = self.agent.query(question)
        
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["sql"])
        self.assertIsNotNone(result["data"])
        self.assertEqual(len(result["data"]), 3)
    
    def test_query_with_project_filter(self):
        """测试带项目过滤的查询"""
        question = "查询 App 项目的缺陷"
        result = self.agent.query(question)
        
        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]), 0)
    
    def test_query_cache(self):
        """测试缓存机制"""
        question = "查询所有 TopIssue 缺陷"
        
        # 第一次查询
        result1 = self.agent.query(question)
        self.assertFalse(result1["from_cache"])
        
        # 第二次查询（应该命中缓存）
        result2 = self.agent.query(question)
        self.assertTrue(result2["from_cache"])
    
    def test_clear_cache(self):
        """测试清空缓存"""
        question = "查询所有 TopIssue 缺陷"
        
        # 第一次查询
        self.agent.query(question)
        
        # 清空缓存
        self.agent.clear_cache()
        
        # 再次查询（不应命中缓存）
        result = self.agent.query(question)
        self.assertFalse(result["from_cache"])
    
    def test_invalid_sql(self):
        """测试无效 SQL 查询"""
        question = "删除所有数据"
        result = self.agent.query(question)
        
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])
    
    def test_query_high_runners(self):
        """测试查询 High Runner"""
        question = "查询所有 High Runner 缺陷（ECU转移≥3次）"
        result = self.agent.query(question)
        
        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]), 0)
    
    def test_query_long_runners(self):
        """测试查询 Long Runner"""
        question = "查询所有 Long Runner 缺陷（处理周期≥30天）"
        result = self.agent.query(question)
        
        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]), 0)
    
    def test_query_statistics(self):
        """测试统计查询"""
        question = "按项目统计缺陷总数"
        result = self.agent.query(question)
        
        self.assertTrue(result["success"])
        self.assertGreater(len(result["data"]), 0)
    
    def test_factory_function(self):
        """测试工厂函数"""
        agent = create_text_to_sql_agent(
            db_path=self.db_path,
            schema_path="chatdb/schema_description.md"
        )
        
        self.assertIsNotNone(agent)
        
        result = agent.query("查询所有 TopIssue 缺陷")
        self.assertTrue(result["success"])


# ============================================================================
# 运行测试
# =============================================================================

def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试用例
    suite.addTests(loader.loadTestsFromTestCase(TestQueryCache))
    suite.addTests(loader.loadTestsFromTestCase(TestSQLValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestSQLExecutor))
    suite.addTests(loader.loadTestsFromTestCase(TestSchemaDescriptionLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestFewshotExamplesLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestTextToSQLAgent))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("Text-to-SQL Agent 单元测试")
    print("=" * 60)
    print()
    
    # 运行测试
    result = run_tests()
    
    # 输出结果
    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败！")
        print(f"失败: {len(result.failures)}")
        print(f"错误: {len(result.errors)}")
    print("=" * 60)
    
    # 返回退出码
    sys.exit(0 if result.wasSuccessful() else 1)
