import os
import sqlite3
import tempfile
import unittest

from agent.core.sql_runtime_service import (
    build_evidence_bundle,
    compute_total_count,
    execute_query_with_fix,
    execute_sql_rows,
)


class _ToolExecutorStub:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def execute_tool(self, tool_name, data, **kwargs):
        self.calls.append((tool_name, kwargs))
        return self._result


class _ToolExecutorRaiseStub:
    def execute_tool(self, tool_name, data, **kwargs):
        raise RuntimeError("tool boom")


class SqlRuntimeServiceTests(unittest.TestCase):
    def test_build_evidence_bundle_contains_minimum_contract_fields(self):
        bundle = build_evidence_bundle(
            sql_used='SELECT id, severity_group FROM "octane_defects" LIMIT 2',
            rows=[{"id": 101, "severity_group": "Major"}, {"id": 102, "severity_group": "Critical"}],
            total_count=24,
            rule_ids=["rule_a", "rule_b"],
            evidence_gap=["结果缺少功能字段"],
        )

        self.assertEqual(bundle.get("sql_used"), 'SELECT id, severity_group FROM "octane_defects" LIMIT 2')
        self.assertEqual(bundle.get("sample_count"), 2)
        self.assertEqual(bundle.get("total_count"), 24)
        self.assertEqual(bundle.get("key_fields"), ["id", "severity_group"])
        self.assertEqual(bundle.get("rule_ids"), ["rule_a", "rule_b"])
        self.assertEqual(bundle.get("evidence_gap"), ["结果缺少功能字段"])

    def test_execute_query_with_fix_normalizes_payload(self):
        executor = _ToolExecutorStub(
            {
                "success": True,
                "result": {
                    "generated_sql": 'SELECT id, name FROM "items" LIMIT 2',
                    "rows": [{"id": 1, "name": "alpha"}, "invalid"],
                    "business_explanation": {"highlights": ["命中 1 条记录"]},
                },
            }
        )

        result = execute_query_with_fix(
            question="show items",
            table_name="items",
            row_limit=10,
            tool_executor=executor,
        )

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("source"), "query_sqlite_with_fix")
        self.assertEqual(result.get("sql"), 'SELECT id, name FROM "items" LIMIT 2')
        self.assertEqual(len(result.get("rows") or []), 1)
        self.assertEqual((result.get("rows") or [])[0].get("name"), "alpha")
        self.assertEqual(result.get("business_explanation"), {"highlights": ["命中 1 条记录"]})
        self.assertEqual(len(executor.calls), 1)

    def test_execute_query_with_fix_forwards_scope_team_semantic_hint(self):
        executor = _ToolExecutorStub(
            {
                "success": True,
                "result": {
                    "generated_sql": 'SELECT id, name FROM "items" LIMIT 1',
                    "rows": [{"id": 1, "name": "alpha"}],
                },
            }
        )

        execute_query_with_fix(
            question="show items",
            table_name="items",
            row_limit=10,
            tool_executor=executor,
            semantic_hints={"scope_team": "DTSV_China"},
        )

        self.assertEqual(len(executor.calls), 1)
        _, kwargs = executor.calls[0]
        forwarded = kwargs.get("semantic_hints") or {}
        self.assertEqual(forwarded.get("scope_team"), "DTSV_China")

    def test_execute_query_with_fix_reports_tool_error(self):
        executor = _ToolExecutorStub({"success": False, "error": "bad request"})

        result = execute_query_with_fix(
            question="show items",
            table_name="items",
            row_limit=10,
            tool_executor=executor,
        )

        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("source"), "query_sqlite_with_fix")
        self.assertIn("bad request", str(result.get("error") or ""))

    def test_execute_query_with_fix_handles_tool_exception(self):
        result = execute_query_with_fix(
            question="show items",
            table_name="items",
            row_limit=10,
            tool_executor=_ToolExecutorRaiseStub(),
        )

        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("source"), "query_sqlite_with_fix")
        self.assertIn("tool boom", str(result.get("error") or ""))

    def test_execute_sql_rows_prefers_tool_executor(self):
        executor = _ToolExecutorStub(
            {
                "success": True,
                "result": {
                    "sql": 'SELECT id, name FROM "items" LIMIT 1',
                    "rows": [{"id": 1, "name": "alpha"}],
                },
            }
        )

        result = execute_sql_rows(
            sql_text='SELECT id, name FROM "items"',
            db_path='C:/not-used.db',
            table_name='items',
            row_limit=50,
            tool_executor=executor,
        )

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("source"), "tool")
        self.assertEqual(len(result.get("rows") or []), 1)
        self.assertEqual((result.get("rows") or [])[0].get("name"), "alpha")
        self.assertEqual((result.get("sql") or "").strip(), 'SELECT id, name FROM "items" LIMIT 1')
        self.assertEqual(len(executor.calls), 1)

    def test_execute_sql_rows_falls_back_to_local_when_tool_fails(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE items (id INTEGER, name TEXT)')
            cur.execute('INSERT INTO items (id, name) VALUES (1, "alpha")')
            cur.execute('INSERT INTO items (id, name) VALUES (2, "beta")')
            conn.commit()
            conn.close()

            executor = _ToolExecutorStub({"success": False, "error": "tool failed"})
            result = execute_sql_rows(
                sql_text='SELECT id, name FROM "items" ORDER BY id',
                db_path=db_path,
                table_name='items',
                row_limit=20,
                tool_executor=executor,
            )

            self.assertTrue(result.get("success"))
            self.assertEqual(result.get("source"), "local")
            rows = result.get("rows") or []
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].get("id"), 1)
            self.assertEqual(rows[1].get("name"), "beta")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_compute_total_count_unwraps_wrapped_sql(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE items (id INTEGER, name TEXT)')
            cur.execute('INSERT INTO items (id, name) VALUES (1, "alpha")')
            cur.execute('INSERT INTO items (id, name) VALUES (2, "beta")')
            cur.execute('INSERT INTO items (id, name) VALUES (3, "gamma")')
            conn.commit()
            conn.close()

            total = compute_total_count(
                db_path=db_path,
                table_name='items',
                sql_text='SELECT * FROM (SELECT id, name FROM "items") AS _q LIMIT 2',
                tool_executor=None,
            )

            self.assertEqual(total, 3)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_execute_sql_rows_with_non_positive_row_limit_returns_all_local_rows(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE items (id INTEGER, name TEXT)')
            cur.execute('INSERT INTO items (id, name) VALUES (1, "alpha")')
            cur.execute('INSERT INTO items (id, name) VALUES (2, "beta")')
            cur.execute('INSERT INTO items (id, name) VALUES (3, "gamma")')
            conn.commit()
            conn.close()

            result = execute_sql_rows(
                sql_text='SELECT id, name FROM "items" ORDER BY id',
                db_path=db_path,
                table_name='items',
                row_limit=0,
                tool_executor=_ToolExecutorStub({"success": True, "result": {"rows": []}}),
            )

            self.assertTrue(result.get("success"))
            self.assertEqual(result.get("source"), "local")
            rows = result.get("rows") or []
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0].get("id"), 1)
            self.assertEqual(rows[-1].get("name"), "gamma")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
