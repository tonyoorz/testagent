import json
import os
import sqlite3
import tempfile
import unittest

from agent.core.intelligent_agent import SQLiteNLQueryWithFixTool


class _LLMStub:
    def __init__(self, response_text='{"sql":"SELECT 1 AS id"}'):
        self.response_text = response_text
        self.calls = []

    def chat_completion(self, messages, temperature=0.1, max_tokens=800):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self.response_text


class _ToolStub:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def execute(self, data=None, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class SQLiteNLQueryWithFixToolTests(unittest.TestCase):
    def test_execute_includes_relative_time_semantics_in_prompt_payload(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE octane_manual_runs (creation_time TEXT, status TEXT, run_by TEXT, test_id TEXT)")
            conn.commit()
            conn.close()

            llm = _LLMStub()
            tool = SQLiteNLQueryWithFixTool(db_path=db_path, llm=llm)
            tool._schema_tool = _ToolStub(
                {
                    "success": True,
                    "result": {
                        "tables": {
                            "octane_manual_runs": [
                                {"name": "creation_time"},
                                {"name": "status"},
                                {"name": "run_by"},
                                {"name": "test_id"},
                            ]
                        }
                    },
                }
            )
            tool._profile_tool = _ToolStub({"success": True, "result": {"top_values": {}}})
            tool._query_tool = _ToolStub(
                {
                    "success": True,
                    "result": {
                        "sql": "SELECT 1 AS id",
                        "columns": ["id"],
                        "rows": [{"id": 1}],
                    },
                }
            )

            out = tool.execute(
                None,
                question="上周团队测试用例情况",
                table="octane_manual_runs",
                limit=20,
                semantic_hints={"scope_team": "DTSV_China"},
            )

            self.assertTrue(out.get("success"))
            self.assertEqual(len(llm.calls), 1)

            llm_messages = llm.calls[0]["messages"]
            self.assertEqual(len(llm_messages), 2)
            self.assertIn("relative_period", llm_messages[0]["content"])
            self.assertIn("week_number", llm_messages[0]["content"])

            payload = json.loads(llm_messages[1]["content"])
            semantic_hints = payload.get("semantic_term_hints") or {}
            self.assertEqual(semantic_hints.get("scope_team"), "DTSV_China")
            self.assertEqual(semantic_hints.get("relative_period"), "last_week")
            self.assertIn("relative_period=last_week", payload.get("normalized_question") or "")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
