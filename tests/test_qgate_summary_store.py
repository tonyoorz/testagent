import json
import sqlite3

import qgate_summary_store

from qgate_summary_store import ensure_qgate_summary_tables, refresh_qgate_summary_tables


def test_ensure_qgate_summary_tables_creates_required_tables(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        ensure_qgate_summary_tables(conn)
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'qgate_kpi_%'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert table_names == {
        "qgate_kpi_issue_transitions",
        "qgate_kpi_ticket_scope",
    }


def test_refresh_qgate_summary_tables_builds_scope_and_transition_rows(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                2026,
                "Plant-Dadong FIT",
                "Plant-Dadong FIT",
                json.dumps(
                    {
                        "id": "1001",
                        "name": "Ticket 1001",
                        "creation_time": "2026-03-01T08:00:00Z",
                        "owner_work_item": {"name": "Alice"},
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                "Plant-Dadong FIT",
                2,
                json.dumps(
                    {
                        "data": [
                            {
                                "timestamp": "2026-03-01T08:00:00Z",
                                "user": {"name": "Setup"},
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "<missing>",
                                        "value_text": "02-QGate",
                                    }
                                ],
                            },
                            {
                                "timestamp": "2026-03-02T08:00:00Z",
                                "user": {"name": "Alice"},
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "02-QGate",
                                        "value_text": "03-Analysis",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path), teams=["Plant-Dadong FIT"])

        scope_rows = conn.execute(
            "SELECT team, ticket_id, year, has_history, history_parse_ok FROM qgate_kpi_ticket_scope"
        ).fetchall()
        transition_rows = conn.execute(
            "SELECT team, ticket_id, phase_transition, changed_by FROM qgate_kpi_issue_transitions"
        ).fetchall()
    finally:
        conn.close()

    assert scope_rows == [("Plant-Dadong FIT", "1001", "2026", 1, 1)]
    assert transition_rows == [("Plant-Dadong FIT", "1001", "02-QGate -> 03-Analysis", "Alice")]


def test_refresh_qgate_summary_tables_preserves_existing_team_rows_when_filtered_source_has_no_valid_rows(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        ensure_qgate_summary_tables(conn)
        conn.execute(
            """
            INSERT INTO qgate_kpi_ticket_scope(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                has_history, history_parse_ok, source_history_hash, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
                "existing-ticket",
                "2026",
                "Existing Ticket",
                "Alice",
                None,
                1,
                1,
                "existing-hash",
                "2026-03-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO qgate_kpi_issue_transitions(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                phase_transition, group_name, changed_by, fif,
                duration_hours, duration_days, ticket_timespan_days,
                start_time, end_time, source_history_hash, source_team, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
                "existing-ticket",
                "2026",
                "Existing Ticket",
                "Alice",
                None,
                "02-QGate -> 03-Analysis",
                None,
                "Alice",
                None,
                0.0,
                0.0,
                None,
                "2026-03-02T08:00:00Z",
                "2026-03-02T08:00:00Z",
                "existing-hash",
                "Plant-Dadong FIT",
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            ("1001", 2026, "Plant-Dadong FIT", "Plant-Dadong FIT", "{bad json"),
        )
        conn.commit()

        result = refresh_qgate_summary_tables(db_path=str(db_path), teams=["Plant-Dadong FIT"])

        scope_rows = conn.execute(
            "SELECT team, ticket_id, source_history_hash FROM qgate_kpi_ticket_scope"
        ).fetchall()
        transition_rows = conn.execute(
            "SELECT team, ticket_id, phase_transition, source_history_hash FROM qgate_kpi_issue_transitions"
        ).fetchall()
    finally:
        conn.close()

    assert result == {"ticket_scope_rows": 0, "transition_rows": 0}
    assert scope_rows == [("Plant-Dadong FIT", "existing-ticket", "existing-hash")]
    assert transition_rows == [
        ("Plant-Dadong FIT", "existing-ticket", "02-QGate -> 03-Analysis", "existing-hash")
    ]


def test_refresh_qgate_summary_tables_removes_stale_team_rows_when_valid_scope_changes(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        ensure_qgate_summary_tables(conn)
        conn.execute(
            """
            INSERT INTO qgate_kpi_ticket_scope(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                has_history, history_parse_ok, source_history_hash, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
                "stale-ticket",
                "2026",
                "Stale Ticket",
                "Alice",
                None,
                1,
                1,
                "stale-hash",
                "2026-03-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO qgate_kpi_issue_transitions(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                phase_transition, group_name, changed_by, fif,
                duration_hours, duration_days, ticket_timespan_days,
                start_time, end_time, source_history_hash, source_team, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
                "stale-ticket",
                "2026",
                "Stale Ticket",
                "Alice",
                None,
                "02-QGate -> 03-Analysis",
                None,
                "Alice",
                None,
                0.0,
                0.0,
                None,
                "2026-03-02T08:00:00Z",
                "2026-03-02T08:00:00Z",
                "stale-hash",
                "Plant-Dadong FIT",
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "2002",
                2026,
                "Plant-Dadong FIT",
                "Plant-Dadong FIT",
                json.dumps(
                    {
                        "id": "2002",
                        "name": "Replacement Ticket",
                        "creation_time": "2026-03-03T08:00:00Z",
                        "owner_work_item": {"name": "Bob"},
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (
                "2002",
                "Plant-Dadong FIT",
                2,
                json.dumps(
                    {
                        "data": [
                            {
                                "timestamp": "2026-03-03T08:00:00Z",
                                "user": {"name": "Setup"},
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "<missing>",
                                        "value_text": "02-QGate",
                                    }
                                ],
                            },
                            {
                                "timestamp": "2026-03-04T08:00:00Z",
                                "user": {"name": "Bob"},
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "02-QGate",
                                        "value_text": "03-Analysis",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                "2026-03-04T08:00:00Z",
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path), teams=["Plant-Dadong FIT"])

        scope_rows = conn.execute(
            "SELECT team, ticket_id FROM qgate_kpi_ticket_scope ORDER BY ticket_id"
        ).fetchall()
        transition_rows = conn.execute(
            "SELECT team, ticket_id, phase_transition FROM qgate_kpi_issue_transitions ORDER BY ticket_id"
        ).fetchall()
    finally:
        conn.close()

    assert scope_rows == [("Plant-Dadong FIT", "2002")]
    assert transition_rows == [("Plant-Dadong FIT", "2002", "02-QGate -> 03-Analysis")]


def test_refresh_qgate_summary_tables_removes_stale_team_rows_when_filtered_source_has_no_rows(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        ensure_qgate_summary_tables(conn)
        conn.execute(
            """
            INSERT INTO qgate_kpi_ticket_scope(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                has_history, history_parse_ok, source_history_hash, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
                "stale-ticket",
                "2026",
                "Stale Ticket",
                "Alice",
                None,
                1,
                1,
                "stale-hash",
                "2026-03-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO qgate_kpi_issue_transitions(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                phase_transition, group_name, changed_by, fif,
                duration_hours, duration_days, ticket_timespan_days,
                start_time, end_time, source_history_hash, source_team, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
                "stale-ticket",
                "2026",
                "Stale Ticket",
                "Alice",
                None,
                "02-QGate -> 03-Analysis",
                None,
                "Alice",
                None,
                0.0,
                0.0,
                None,
                "2026-03-02T08:00:00Z",
                "2026-03-02T08:00:00Z",
                "stale-hash",
                "Plant-Dadong FIT",
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.commit()

        result = refresh_qgate_summary_tables(db_path=str(db_path), teams=["Plant-Dadong FIT"])

        scope_rows = conn.execute("SELECT team, ticket_id FROM qgate_kpi_ticket_scope").fetchall()
        transition_rows = conn.execute(
            "SELECT team, ticket_id FROM qgate_kpi_issue_transitions"
        ).fetchall()
    finally:
        conn.close()

    assert result == {"ticket_scope_rows": 0, "transition_rows": 0}
    assert scope_rows == []
    assert transition_rows == []




def test_qgate_summary_store_main_refreshes_selected_teams(monkeypatch, capsys):
    captured = {}

    def fake_refresh_qgate_summary_tables(*, db_path, teams=None):
        captured["db_path"] = db_path
        captured["teams"] = teams
        return {"ticket_scope_rows": 1, "transition_rows": 2}

    monkeypatch.setattr(qgate_summary_store, "refresh_qgate_summary_tables", fake_refresh_qgate_summary_tables)

    exit_code = qgate_summary_store.main(["--db-path", "custom.db", "--teams", "Plant-Dadong FIT,Plant-Tiexi FIT"])

    assert exit_code == 0
    assert captured == {
        "db_path": "custom.db",
        "teams": ["Plant-Dadong FIT", "Plant-Tiexi FIT"],
    }
    assert capsys.readouterr().out.strip() == '{"ticket_scope_rows": 1, "transition_rows": 2}'
def test_refresh_qgate_summary_tables_skips_transition_when_history_has_only_single_phase_event(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                2026,
                "Plant-Dadong FIT",
                "Plant-Dadong FIT",
                json.dumps(
                    {
                        "id": "1001",
                        "name": "Ticket 1001",
                        "creation_time": "2026-03-01T08:00:00Z",
                        "owner_work_item": {"name": "Alice"},
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                "Plant-Dadong FIT",
                1,
                json.dumps(
                    {
                        "data": [
                            {
                                "timestamp": "2026-03-02T08:00:00Z",
                                "user": {"name": "Alice"},
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "value_text": "03-Analysis",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path), teams=["Plant-Dadong FIT"])

        transition_rows = conn.execute(
            "SELECT team, ticket_id, phase_transition, changed_by FROM qgate_kpi_issue_transitions"
        ).fetchall()
    finally:
        conn.close()

    assert transition_rows == []


def test_refresh_qgate_summary_tables_filters_source_queries_by_requested_team(tmp_path, monkeypatch):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    statements: list[str] = []

    real_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        traced_conn = real_connect(*args, **kwargs)
        if args and str(args[0]) == str(db_path):
            traced_conn.set_trace_callback(statements.append)
        return traced_conn

    monkeypatch.setattr(qgate_summary_store.sqlite3, "connect", traced_connect)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                2026,
                "Plant-Dadong FIT",
                "Plant-Dadong FIT",
                json.dumps(
                    {
                        "id": "1001",
                        "name": "Ticket 1001",
                        "creation_time": "2026-03-01T08:00:00Z",
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "2002",
                2026,
                "Other Team",
                "Other Team",
                json.dumps(
                    {
                        "id": "2002",
                        "name": "Ticket 2002",
                        "creation_time": "2026-03-01T08:00:00Z",
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                "Plant-Dadong FIT",
                0,
                json.dumps({"data": []}),
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (
                "2002",
                "Other Team",
                0,
                json.dumps({"data": []}),
                "2026-03-02T08:00:00Z",
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path), teams=["Plant-Dadong FIT"])
    finally:
        conn.close()

    defect_selects = [statement for statement in statements if "FROM octane_defects" in statement]
    history_selects = [statement for statement in statements if "FROM octane_defect_histories" in statement]

    assert defect_selects
    assert history_selects
    assert any("WHERE" in statement and "Plant-Dadong FIT" in statement for statement in defect_selects)
    assert any("WHERE" in statement and "Plant-Dadong FIT" in statement for statement in history_selects)


def test_refresh_qgate_summary_tables_prefers_problem_finder_team_for_unfiltered_refresh(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                2026,
                "EA-233",
                "Plant-Dadong FIT",
                json.dumps(
                    {
                        "id": "1001",
                        "name": "Ticket 1001",
                        "creation_time": "2026-03-01T08:00:00Z",
                    }
                ),
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path))

        scope_rows = conn.execute("SELECT team, ticket_id FROM qgate_kpi_ticket_scope").fetchall()
    finally:
        conn.close()

    assert scope_rows == [("Plant-Dadong FIT", "1001")]


def test_refresh_qgate_summary_tables_skips_rows_without_problem_finder_team_on_unfiltered_refresh(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                2026,
                "EA-233",
                "Plant-Dadong FIT",
                json.dumps({"id": "1001", "creation_time": "2026-03-01T08:00:00Z"}),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1002",
                2026,
                "EA-999",
                None,
                json.dumps({"id": "1002", "creation_time": "2026-03-01T08:00:00Z"}),
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path))

        scope_rows = conn.execute("SELECT team, ticket_id FROM qgate_kpi_ticket_scope ORDER BY ticket_id").fetchall()
    finally:
        conn.close()

    assert scope_rows == [("Plant-Dadong FIT", "1001")]


def test_refresh_qgate_summary_tables_populates_transition_metadata_from_history(tmp_path):
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE octane_defects (
                defect_id TEXT PRIMARY KEY,
                year INTEGER,
                team TEXT,
                problem_finder_team TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE octane_defect_histories (
                defect_id TEXT PRIMARY KEY,
                team TEXT NOT NULL,
                total_count INTEGER,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                2026,
                "EA-233",
                "Plant-Dadong FIT",
                json.dumps(
                    {
                        "id": "1001",
                        "name": "Ticket 1001",
                        "creation_time": "2026-03-01T08:00:00Z",
                        "detected_by": {"full_name": "Alice"},
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            (
                "1001",
                "Plant-Dadong FIT",
                4,
                json.dumps(
                    {
                        "data": [
                            {
                                "timestamp": "2026-03-01T08:00:00Z",
                                "user_name": "Alice",
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "<missing>",
                                        "value_text": "01-New",
                                    }
                                ],
                            },
                            {
                                "timestamp": "2026-03-02T08:00:00Z",
                                "user_name": "Bob",
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "01-New",
                                        "value_text": "02-In Pre-Analysis",
                                    },
                                    {
                                        "field_name": "product_areas",
                                        "field_label": "Found in Function",
                                        "value_text": "Connected Music China [01.04.01.06.04]",
                                    },
                                ],
                            },
                            {
                                "timestamp": "2026-03-04T08:00:00Z",
                                "user_name": "Carol",
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "02-In Pre-Analysis",
                                        "value_text": "03-In Analysis",
                                    }
                                ],
                            },
                            {
                                "timestamp": "2026-03-07T08:00:00Z",
                                "user_name": "Dora",
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "03-In Analysis",
                                        "value_text": "09-Concluded without action",
                                    }
                                ],
                            },
                        ]
                    }
                ),
                "2026-03-07T08:00:00Z",
            ),
        )
        conn.commit()

        refresh_qgate_summary_tables(db_path=str(db_path))

        scope_rows = conn.execute(
            "SELECT team, ticket_id, ticket_url, tester FROM qgate_kpi_ticket_scope"
        ).fetchall()
        transition_rows = conn.execute(
            """
            SELECT team, ticket_id, phase_transition, group_name, changed_by, fif,
                   duration_hours, duration_days, ticket_timespan_days, start_time, end_time
            FROM qgate_kpi_issue_transitions
            ORDER BY start_time, end_time
            """
        ).fetchall()
    finally:
        conn.close()

    assert scope_rows == [
        (
            "Plant-Dadong FIT",
            "1001",
            "https://octane-prod.bmwgroup.net/ui/entity-navigation?p=1002/2001&entityType=work_item&id=1001",
            "Alice",
        )
    ]
    assert transition_rows == [
        (
            "Plant-Dadong FIT",
            "1001",
            "01-New -> 02-In Pre-Analysis",
            "Integration",
            "Bob",
            "China Specific",
            24.0,
            1.0,
            6.0,
            "2026-03-01T08:00:00Z",
            "2026-03-02T08:00:00Z",
        ),
        (
            "Plant-Dadong FIT",
            "1001",
            "02-In Pre-Analysis -> 03-In Analysis",
            "Q-Gate",
            "Carol",
            "China Specific",
            48.0,
            2.0,
            6.0,
            "2026-03-02T08:00:00Z",
            "2026-03-04T08:00:00Z",
        ),
        (
            "Plant-Dadong FIT",
            "1001",
            "03-In Analysis -> 09-Concluded without action",
            "CoC",
            "Dora",
            "China Specific",
            72.0,
            3.0,
            6.0,
            "2026-03-04T08:00:00Z",
            "2026-03-07T08:00:00Z",
        ),
    ]