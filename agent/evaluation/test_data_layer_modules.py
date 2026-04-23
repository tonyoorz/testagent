"""Tests for the new data-layer modules added in the harness improvement phase.

Covers:
- column_stats_cache
- few_shot_sql_library
- query_result_validator
- context_compaction
- query_memory (persistence extension)
- validate_and_annotate integration
"""

import os
import sqlite3
import tempfile
import unittest

# ─────────────────────────────────────────────────────────────
# column_stats_cache
# ─────────────────────────────────────────────────────────────

from agent.core.column_stats_cache import ColumnStatsCache, get_column_stats_cache


class ColumnStatsCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._db_path = cls._tmp.name
        cls._tmp.close()
        conn = sqlite3.connect(cls._db_path)
        conn.execute("""
            CREATE TABLE octane_defects (
                defect_id TEXT, project TEXT, severity TEXT,
                ecu TEXT, risk_score REAL
            )
        """)
        rows = [
            ("D001", "IDC", "Critical", "CDE-01", 8.5),
            ("D002", "IDC", "High", "CDE-01", 6.0),
            ("D003", "IDCEVO", "Medium", None, 3.0),
            ("D004", "IDCEVO", "Medium", "WAVE-01", None),
            ("D005", "MGU", "Low", "", 1.0),
        ]
        conn.executemany(
            "INSERT INTO octane_defects VALUES (?, ?, ?, ?, ?)", rows
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls._db_path)

    def test_build_populates_stats(self):
        cache = ColumnStatsCache(self._db_path)
        cache.build()
        stats = cache.get_all_stats()
        self.assertIn("project", stats)
        self.assertIn("severity", stats)
        self.assertEqual(stats["project"]["type"], "categorical")
        self.assertEqual(stats["project"]["distinct_count"], 3)

    def test_numeric_column_stats(self):
        cache = ColumnStatsCache(self._db_path)
        cache.build()
        risk = cache.get_stats("risk_score")
        self.assertIsNotNone(risk)
        self.assertEqual(risk["type"], "numeric")
        self.assertEqual(risk["min"], 1.0)
        self.assertEqual(risk["max"], 8.5)

    def test_build_prompt_context_returns_text(self):
        cache = ColumnStatsCache(self._db_path)
        cache.build()
        ctx = cache.build_prompt_context()
        self.assertIn("project", ctx)
        self.assertIn("5 rows", ctx)

    def test_lookup_value_exact_match(self):
        cache = ColumnStatsCache(self._db_path)
        cache.build()
        val = cache.lookup_value("MGU", "project")
        self.assertEqual(val, "MGU")

    def test_lookup_value_fuzzy(self):
        cache = ColumnStatsCache(self._db_path)
        cache.build()
        val = cache.lookup_value("CDE", "ecu")
        self.assertEqual(val, "CDE-01")

    def test_value_mapping_context(self):
        cache = ColumnStatsCache(self._db_path)
        cache.build()
        hints = cache.build_value_mapping_context("IDC项目的缺陷")
        self.assertIn("IDC", hints)

    def test_is_stale_initially(self):
        cache = ColumnStatsCache(self._db_path)
        self.assertTrue(cache.is_stale)


# ─────────────────────────────────────────────────────────────
# few_shot_sql_library
# ─────────────────────────────────────────────────────────────

from agent.core.few_shot_sql_library import (
    retrieve_few_shot_examples,
    build_few_shot_prompt,
    DEFECT_EXAMPLES,
)


class FewShotSqlLibraryTests(unittest.TestCase):
    def test_examples_list_not_empty(self):
        self.assertGreater(len(DEFECT_EXAMPLES), 20)

    def test_retrieve_returns_relevant_examples(self):
        examples = retrieve_few_shot_examples("各项目缺陷数量排名")
        self.assertGreater(len(examples), 0)
        # Should contain project-related example
        questions = [e["question"] for e in examples]
        self.assertTrue(
            any("项目" in q or "project" in q.lower() for q in questions)
        )

    def test_retrieve_returns_at_most_top_k(self):
        examples = retrieve_few_shot_examples("Critical", top_k=2)
        self.assertLessEqual(len(examples), 2)

    def test_build_prompt_returns_formatted_text(self):
        prompt = build_few_shot_prompt("severity distribution count")
        self.assertIn("Similar query examples", prompt)
        self.assertIn("SQL:", prompt)

    def test_empty_question_returns_defaults(self):
        examples = retrieve_few_shot_examples("")
        self.assertEqual(len(examples), 3)


# ─────────────────────────────────────────────────────────────
# query_result_validator
# ─────────────────────────────────────────────────────────────

from agent.core.query_result_validator import (
    validate_sql_result,
    format_validation_summary,
    has_blocking_issues,
    ValidationIssue,
    LEVEL_WARNING,
    LEVEL_ERROR,
)


class QueryResultValidatorTests(unittest.TestCase):
    def test_zero_rows_produces_warning(self):
        issues = validate_sql_result(sql="SELECT * FROM t", rows=[], table_name="t")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "ZERO_ROWS")

    def test_no_issues_for_healthy_result(self):
        rows = [{"project": "IDC", "cnt": 100}, {"project": "IDCEVO", "cnt": 80}]
        issues = validate_sql_result(
            sql="SELECT project, COUNT(*) AS cnt FROM t GROUP BY project",
            rows=rows,
            table_name="t",
        )
        self.assertEqual(len(issues), 0)

    def test_high_null_rate_detected(self):
        rows = [{"ecu": None, "cnt": i} for i in range(10)]
        issues = validate_sql_result(
            sql="SELECT ecu, COUNT(*) AS cnt FROM t GROUP BY ecu",
            rows=rows,
            table_name="t",
        )
        codes = [i.code for i in issues]
        self.assertIn("HIGH_NULL_RATE", codes)

    def test_single_group_detected(self):
        rows = [{"project": "IDC", "cnt": 500}]
        issues = validate_sql_result(
            sql="SELECT project, COUNT(*) AS cnt FROM t GROUP BY project",
            rows=rows,
            table_name="t",
        )
        codes = [i.code for i in issues]
        self.assertIn("SINGLE_GROUP", codes)

    def test_format_summary_includes_message(self):
        issues = [ValidationIssue(LEVEL_WARNING, "TEST", "test message", "fix it")]
        summary = format_validation_summary(issues)
        self.assertIn("test message", summary)
        self.assertIn("fix it", summary)

    def test_has_blocking_issues(self):
        self.assertFalse(
            has_blocking_issues([ValidationIssue(LEVEL_WARNING, "W", "warn")])
        )
        self.assertTrue(
            has_blocking_issues([ValidationIssue(LEVEL_ERROR, "E", "err")])
        )

    def test_missing_limit_for_large_result(self):
        rows = [{"id": i} for i in range(200)]
        issues = validate_sql_result(
            sql="SELECT * FROM octane_defects", rows=rows, table_name="octane_defects"
        )
        codes = [i.code for i in issues]
        self.assertIn("MISSING_LIMIT", codes)


# ─────────────────────────────────────────────────────────────
# context_compaction
# ─────────────────────────────────────────────────────────────

from agent.core.context_compaction import (
    compact_conversation,
    build_conversation_summary,
    estimate_token_count,
)


class ContextCompactionTests(unittest.TestCase):
    def test_short_conversation_unchanged(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = compact_conversation(msgs, keep_recent=4)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["content"], "sys")

    def test_long_tool_output_truncated(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "content": "x" * 2000},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "q3"},
            {"role": "assistant", "content": "a3"},
            {"role": "user", "content": "q4"},
        ]
        result = compact_conversation(msgs, keep_recent=4)
        # Tool output in early messages should be truncated
        tool_msg = next(m for m in result if m["role"] == "tool")
        self.assertLess(len(tool_msg["content"]), 2000)
        self.assertIn("truncated", tool_msg["content"])

    def test_recent_messages_preserved(self):
        msgs = [{"role": "system", "content": "sys"}]
        for i in range(10):
            msgs.append({"role": "user", "content": f"q{i}"})
        result = compact_conversation(msgs, keep_recent=3)
        # Last 3 should be the recent user messages
        self.assertEqual(result[-1]["content"], "q9")
        self.assertEqual(result[-2]["content"], "q8")
        self.assertEqual(result[-3]["content"], "q7")

    def test_build_summary_extracts_questions(self):
        msgs = [
            {"role": "user", "content": "各项目缺陷数量是多少？"},
            {"role": "assistant", "content": "总结: IDC 有 8835 个缺陷"},
        ]
        summary = build_conversation_summary(msgs)
        self.assertIn("各项目缺陷数量", summary)

    def test_estimate_token_count(self):
        msgs = [{"role": "user", "content": "hello world"}]
        tokens = estimate_token_count(msgs)
        self.assertGreater(tokens, 0)


# ─────────────────────────────────────────────────────────────
# query_memory (persistence extension)
# ─────────────────────────────────────────────────────────────

from agent.core.query_memory import QueryMemory


class QueryMemoryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()

    def tearDown(self):
        try:
            os.unlink(self._db_path)
        except Exception:
            pass

    def test_persistence_across_instances(self):
        qm1 = QueryMemory(db_path=self._db_path)
        qm1.add_query(
            "各项目缺陷数", answer="IDC: 8835",
            sql_used="SELECT project, COUNT(*) FROM octane_defects GROUP BY project",
            row_count=7,
            columns_accessed=["project"],
        )
        # Create new instance from same DB
        qm2 = QueryMemory(db_path=self._db_path)
        entries = qm2.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["question"], "各项目缺陷数")
        self.assertEqual(entries[0]["sql_used"], "SELECT project, COUNT(*) FROM octane_defects GROUP BY project")
        self.assertEqual(entries[0]["row_count"], 7)

    def test_find_similar_query(self):
        qm = QueryMemory(db_path=self._db_path)
        qm.add_query("show project defect ranking", answer="IDC最多",
                      sql_used="SELECT project, COUNT(*) AS cnt FROM octane_defects GROUP BY project ORDER BY cnt DESC")
        result = qm.find_similar_query("project defect ranking details")
        self.assertIsNotNone(result)
        self.assertIn("SELECT project", result["sql_used"])

    def test_find_similar_no_match(self):
        qm = QueryMemory(db_path=self._db_path)
        qm.add_query("各项目缺陷数", answer="a")
        result = qm.find_similar_query("天气怎么样")
        self.assertIsNone(result)

    def test_backward_compat_no_db_path(self):
        qm = QueryMemory()
        qm.add_query("test", answer="ans")
        self.assertEqual(len(qm.list_entries()), 1)
        self.assertIsNone(qm._db_path)

    def test_new_fields_in_prompt_context(self):
        qm = QueryMemory()
        qm.add_query("test q", answer="ans", sql_used="SELECT 1")
        ctx = qm.build_prompt_context()
        self.assertIn("SQL:", ctx)


# ─────────────────────────────────────────────────────────────
# validate_and_annotate integration
# ─────────────────────────────────────────────────────────────

from agent.core.sql_runtime_service import validate_and_annotate


class ValidateAndAnnotateTests(unittest.TestCase):
    def test_annotates_zero_row_result(self):
        result = {"success": True, "rows": [], "sql": "SELECT * FROM t"}
        # success=True but rows=[] => won't annotate (early return on empty rows)
        out = validate_and_annotate(result, table_name="t")
        self.assertNotIn("validation_issues", out)

    def test_annotates_healthy_result(self):
        result = {
            "success": True,
            "rows": [{"project": "IDC", "cnt": 100}, {"project": "IDCEVO", "cnt": 80}],
            "sql": "SELECT project, COUNT(*) AS cnt FROM t GROUP BY project",
        }
        out = validate_and_annotate(result, table_name="t")
        # Multi-group healthy result should have no issues
        self.assertNotIn("validation_issues", out)

    def test_passes_through_failed_result(self):
        result = {"success": False, "rows": [], "sql": "SELECT 1"}
        out = validate_and_annotate(result, table_name="t")
        self.assertEqual(out["success"], False)

    def test_annotates_high_null_rate(self):
        rows = [{"ecu": None, "cnt": i} for i in range(10)]
        result = {
            "success": True,
            "rows": rows,
            "sql": "SELECT ecu, cnt FROM t",
        }
        out = validate_and_annotate(result, table_name="t")
        self.assertIn("validation_issues", out)
        codes = [i["code"] for i in out["validation_issues"]]
        self.assertIn("HIGH_NULL_RATE", codes)


if __name__ == "__main__":
    unittest.main()
