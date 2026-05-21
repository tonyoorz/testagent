import importlib.util
from argparse import Namespace
import os
from pathlib import Path
import sqlite3

import pandas as pd
import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "report" / "generate_qgate_kpi_dashboard.py"
    spec = importlib.util.spec_from_file_location("qgate_kpi_dashboard_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_summary_db(db_path: Path, *, with_tables: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    try:
        if not with_tables:
            return
        conn.executescript(
            """
            CREATE TABLE qgate_kpi_ticket_scope (
                team TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                year TEXT,
                ticket_name TEXT,
                tester TEXT,
                ticket_url TEXT,
                has_history INTEGER NOT NULL,
                history_parse_ok INTEGER NOT NULL,
                source_history_hash TEXT,
                refreshed_at TEXT NOT NULL,
                PRIMARY KEY (team, ticket_id)
            );

            CREATE TABLE qgate_kpi_issue_transitions (
                team TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                year TEXT,
                ticket_name TEXT,
                tester TEXT,
                ticket_url TEXT,
                phase_transition TEXT NOT NULL,
                group_name TEXT,
                changed_by TEXT,
                fif TEXT,
                duration_hours REAL NOT NULL,
                duration_days REAL NOT NULL,
                ticket_timespan_days REAL,
                start_time TEXT,
                end_time TEXT,
                source_history_hash TEXT NOT NULL,
                source_team TEXT,
                refreshed_at TEXT NOT NULL,
                PRIMARY KEY (team, ticket_id, phase_transition, start_time, end_time)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO qgate_kpi_ticket_scope(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                has_history, history_parse_ok, source_history_hash, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DTSV_China",
                "1001",
                "2026",
                "Ticket 1001",
                "Alice",
                "https://octane/1001",
                1,
                1,
                "hash-1001",
                "2026-05-21T00:00:00Z",
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
                "DTSV_China",
                "1001",
                "2026",
                "Ticket 1001",
                "Alice",
                "https://octane/1001",
                "02-QGate -> 03-Analysis",
                "Q-Gate",
                "Alice",
                "Global",
                24.0,
                1.0,
                2.0,
                "2026-03-01T08:00:00Z",
                "2026-03-02T08:00:00Z",
                "hash-1001",
                "DTSV_China",
                "2026-05-21T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_build_dashboard_payload_uses_explicit_generated_from(monkeypatch):
    module = _load_module()

    meta_df = pd.DataFrame(
        [
            {
                "Team": "DTSV_China",
                "Defects": 4,
                "History_OK": 3,
                "History_Missing_or_Error": 1,
            }
        ]
    )
    issues_df = pd.DataFrame(
        [
            {
                "Team": "DTSV_China",
                "Ticket_ID": "1001",
                "Ticket_URL": "https://octane/1001",
                "Ticket_Name": "Ticket 1001",
                "Tester": "Alice",
                "Phase_Transition": "02-QGate -> 03-Analysis",
                "Group": "Q-Gate",
                "Duration_Hours": 24,
                "Duration_Days": 1,
                "Changed_By": "Alice",
                "FiF": "Global",
                "Ticket_Timespan_Days": 2,
            }
        ]
    )
    coverage_df = pd.DataFrame(
        [
            {
                "Team": "DTSV_China",
                "Year": "2026",
                "Defects": 4,
                "History_OK": 3,
                "History_Missing_or_Error": 1,
            }
        ]
    )

    monkeypatch.setattr(
        module.qgate,
        "compute_all_teams_data",
        lambda **kwargs: (meta_df, pd.DataFrame(), issues_df),
    )
    monkeypatch.setattr(
        module,
        "build_year_lookup_and_coverage",
        lambda defect_dir, teams, issues: ({("DTSV_China", "1001"): "2026"}, coverage_df),
    )
    monkeypatch.setattr(
        module.qgate,
        "build_summary_frames",
        lambda detail_df, min_transition_count: (detail_df, pd.DataFrame([{"Samples_Total": 1}])),
    )
    monkeypatch.setattr(
        module.qgate,
        "aggregate_transition_summary",
        lambda detail_df: pd.DataFrame([
            {"Phase_Transition": "02-QGate -> 03-Analysis", "Group": "Q-Gate", "Avg_Days": 1.0, "Count": 1}
        ]),
    )

    payload = module.build_dashboard_payload(
        defect_dir="qgate/defect",
        history_dir="qgate/history",
        teams=["DTSV_China"],
        min_transition_count=1,
        analysis_workers=0,
        cache_dir="qgate_cache",
        use_cache=True,
        show_progress=False,
    )

    assert payload["generated_from"]["defect_dir"] == "qgate/defect"
    assert payload["generated_from"]["history_dir"] == "qgate/history"
    assert payload["generated_from"]["teams"] == ["DTSV_China"]
    assert payload["generated_from"]["min_transition_count"] == 1
    assert payload["generated_from"]["analysis_workers"] == 0
    assert payload["generated_from"]["cache_dir"] == "qgate_cache"
    assert payload["generated_from"]["use_cache"] is True
    assert payload["generated_from"]["show_progress"] is False
    assert set(payload.keys()) == {
        "generated_from",
        "overview",
        "insights",
        "options",
        "meta",
        "coverage",
        "tickets",
        "issues",
    }


def test_build_dashboard_payload_raises_regular_exception_on_empty_issues(monkeypatch):
    module = _load_module()

    monkeypatch.setattr(
        module.qgate,
        "compute_all_teams_data",
        lambda **kwargs: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
    )

    with pytest.raises(module.QGateDashboardDataError, match="No QGate issue rows were produced"):
        module.build_dashboard_payload(
            defect_dir="qgate/defect",
            history_dir="qgate/history",
            teams=["DTSV_China"],
            min_transition_count=1,
            analysis_workers=0,
            cache_dir="qgate_cache",
            use_cache=True,
            show_progress=False,
        )


def test_build_dashboard_payload_reads_summary_tables_when_available(tmp_path, monkeypatch):
    db_path = tmp_path / "qgate_summary.db"
    _create_summary_db(db_path)
    module = _load_module()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setattr(
        module.qgate,
        "compute_all_teams_data",
        lambda **kwargs: pytest.fail("raw qgate compute path should not be used when summary tables exist"),
    )

    payload = module.build_dashboard_payload(
        defect_dir="qgate/defect",
        history_dir="qgate/history",
        teams=["DTSV_China"],
        min_transition_count=1,
        analysis_workers=0,
        cache_dir="qgate_cache",
        use_cache=True,
        show_progress=False,
    )

    assert payload["meta"] == {
        "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
        "rows": [["DTSV_China", 1, 1, 0]],
    }
    assert payload["coverage"] == {
        "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
        "rows": [["DTSV_China", "2026", 1, 1, 0]],
    }
    assert payload["tickets"] == {
        "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
        "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
    }
    assert payload["issues"] == {
        "columns": [
            "Year",
            "Team",
            "Ticket_ID",
            "Phase_Transition",
            "Group",
            "Duration_Hours",
            "Changed_By",
            "FiF",
            "Ticket_Timespan_Days",
        ],
        "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24.0, "Alice", "Global", 2.0]],
    }
    assert payload["overview"]["history_ok"] == 1
    assert payload["overview"]["history_bad"] == 0
    assert payload["overview"]["transition_samples"] == 1
    assert payload["options"] == {
        "teams": ["DTSV_China"],
        "years": ["2026"],
        "groups": ["Q-Gate"],
        "changedBy": ["Alice"],
        "fif": ["Global"],
        "timespanMax": 2,
    }


def test_build_dashboard_payload_raises_when_summary_tables_are_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "qgate_missing_summary.db"
    _create_summary_db(db_path, with_tables=False)
    module = _load_module()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setattr(
        module.qgate,
        "compute_all_teams_data",
        lambda **kwargs: pytest.fail("raw qgate compute path should not be used when summary tables are required"),
    )

    with pytest.raises(module.QGateDashboardDataError, match="QGate summary data has not been built"):
        module.build_dashboard_payload(
            defect_dir="qgate/defect",
            history_dir="qgate/history",
            teams=["DTSV_China"],
            min_transition_count=1,
            analysis_workers=0,
            cache_dir="qgate_cache",
            use_cache=True,
            show_progress=False,
        )


def test_build_dashboard_payload_raises_when_selected_teams_have_no_summary_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "qgate_summary.db"
    _create_summary_db(db_path)
    module = _load_module()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setattr(
        module.qgate,
        "compute_all_teams_data",
        lambda **kwargs: pytest.fail("raw qgate compute path should not be used when summary tables exist"),
    )

    with pytest.raises(module.QGateDashboardDataError, match="QGate summary data has not been built"):
        module.build_dashboard_payload(
            defect_dir="qgate/defect",
            history_dir="qgate/history",
            teams=["Plant-Dadong FIT"],
            min_transition_count=1,
            analysis_workers=0,
            cache_dir="qgate_cache",
            use_cache=True,
            show_progress=False,
        )


def test_build_dashboard_payload_normalizes_nullable_summary_string_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "qgate_summary_nulls.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE qgate_kpi_ticket_scope (
                team TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                year TEXT,
                ticket_name TEXT,
                tester TEXT,
                ticket_url TEXT,
                has_history INTEGER NOT NULL,
                history_parse_ok INTEGER NOT NULL,
                source_history_hash TEXT,
                refreshed_at TEXT NOT NULL,
                PRIMARY KEY (team, ticket_id)
            );

            CREATE TABLE qgate_kpi_issue_transitions (
                team TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                year TEXT,
                ticket_name TEXT,
                tester TEXT,
                ticket_url TEXT,
                phase_transition TEXT NOT NULL,
                group_name TEXT,
                changed_by TEXT,
                fif TEXT,
                duration_hours REAL NOT NULL,
                duration_days REAL NOT NULL,
                ticket_timespan_days REAL,
                start_time TEXT,
                end_time TEXT,
                source_history_hash TEXT NOT NULL,
                source_team TEXT,
                refreshed_at TEXT NOT NULL,
                PRIMARY KEY (team, ticket_id, phase_transition, start_time, end_time)
            );
            """
        )
        conn.execute(
            "INSERT INTO qgate_kpi_ticket_scope VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Plant-Dadong FIT", "1001", "2026", "Ticket 1001", "Alice", None, 1, 1, "hash-1", "2026-05-21T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO qgate_kpi_issue_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "Plant-Dadong FIT",
                "1001",
                "2026",
                "Ticket 1001",
                "Alice",
                None,
                "02-QGate -> 03-Analysis",
                None,
                "Alice",
                None,
                24.0,
                1.0,
                None,
                "2026-03-01T08:00:00Z",
                "2026-03-02T08:00:00Z",
                "hash-1",
                "Plant-Dadong FIT",
                "2026-05-21T00:00:00Z"
            ),
        )
        conn.commit()
    finally:
        conn.close()

    module = _load_module()
    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setattr(
        module.qgate,
        "compute_all_teams_data",
        lambda **kwargs: pytest.fail("raw qgate compute path should not be used when summary tables exist"),
    )

    payload = module.build_dashboard_payload(
        defect_dir="qgate/defect",
        history_dir="qgate/history",
        teams=["Plant-Dadong FIT"],
        min_transition_count=1,
        analysis_workers=0,
        cache_dir="qgate_cache",
        use_cache=True,
        show_progress=False,
    )

    assert payload["tickets"]["rows"] == [["1001", "", "Ticket 1001", "Alice"]]
    assert payload["issues"]["rows"] == [
        ["2026", "Plant-Dadong FIT", "1001", "02-QGate -> 03-Analysis", "", 24.0, "Alice", "", None]
    ]


def test_main_uses_reusable_builder_with_explicit_parsed_args(monkeypatch, tmp_path):
    module = _load_module()
    output_path = tmp_path / "qgate_dashboard.html"
    captured = {}

    def fake_build_dashboard_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "generated_from": {
                "defect_dir": kwargs["defect_dir"],
                "history_dir": kwargs["history_dir"],
                "teams": kwargs["teams"],
                "min_transition_count": kwargs["min_transition_count"],
            },
            "overview": {
                "team_count": 1,
                "total_defects": 4,
                "history_ok": 3,
                "history_bad": 1,
                "history_success_rate": 75.0,
                "transition_samples": 1,
                "unique_transitions": 1,
                "unique_tickets": 1,
                "changed_by_count": 1,
                "timespan_max": 2,
            },
            "insights": ["sample"],
            "options": {"teams": ["DTSV_China"], "years": ["2026"], "groups": ["Q-Gate"], "changedBy": ["Alice"], "fif": ["Global"], "timespanMax": 2},
            "meta": {"columns": [], "rows": []},
            "coverage": {"columns": [], "rows": []},
            "tickets": {"columns": [], "rows": []},
            "issues": {"columns": [], "rows": []},
        }

    monkeypatch.setattr(
        module,
        "build_dashboard_payload",
        fake_build_dashboard_payload,
    )
    monkeypatch.setattr(module, "render_html", lambda payload: "<html>ok</html>")

    module.main(
        Namespace(
            defect_dir="qgate/defect",
            history_dir="qgate/history",
            teams="DTSV_China",
            min_transition_count=1,
            analysis_workers=0,
            cache_dir="qgate_cache",
            no_cache=False,
            no_progress=True,
            output=str(output_path),
        )
    )

    assert captured["kwargs"] == {
        "defect_dir": "qgate/defect",
        "history_dir": "qgate/history",
        "teams": ["DTSV_China"],
        "min_transition_count": 1,
        "analysis_workers": 0,
        "cache_dir": "qgate_cache",
        "use_cache": True,
        "show_progress": False,
    }
    assert output_path.read_text(encoding="utf-8") == "<html>ok</html>"


def test_main_converts_data_error_to_system_exit_without_writing_file(monkeypatch, tmp_path):
    module = _load_module()
    output_path = tmp_path / "qgate_dashboard_error.html"

    def fake_build_dashboard_payload(**kwargs):
        raise module.QGateDashboardDataError("No QGate issue rows were produced. Check defect/history inputs.")

    monkeypatch.setattr(module, "build_dashboard_payload", fake_build_dashboard_payload)

    with pytest.raises(SystemExit, match="No QGate issue rows were produced"):
        module.main(
            parsed_args=Namespace(
                defect_dir="qgate/defect",
                history_dir="qgate/history",
                teams="DTSV_China",
                min_transition_count=1,
                analysis_workers=0,
                cache_dir="qgate_cache",
                no_cache=False,
                no_progress=True,
                output=str(output_path),
            )
        )

    assert not output_path.exists()


def test_build_year_lookup_and_coverage_uses_db_when_defect_dir_is_missing(tmp_path, monkeypatch):
    module = _load_module()
    db_path = tmp_path / "qgate_data.db"
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
            "INSERT INTO octane_defects(defect_id, year, team, problem_finder_team, raw_json) VALUES (?, ?, ?, ?, ?)",
            ("1001", 2026, "Plant-Dadong FIT", "Plant-Dadong FIT", '{"id":"1001","creation_time":"2026-03-01T08:00:00Z"}'),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("OCTANE_DATA_SOURCE", "db_only")
    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))

    year_lookup, coverage_df = module.build_year_lookup_and_coverage(
        defect_dir=str(tmp_path / "missing"),
        teams=["Plant-Dadong FIT"],
        issues_df=pd.DataFrame([
            {"Team": "Plant-Dadong FIT", "Ticket_ID": "1001"},
        ]),
    )

    assert year_lookup == {("Plant-Dadong FIT", "1001"): "2026"}
    assert coverage_df.to_dict("records") == [
        {
            "Team": "Plant-Dadong FIT",
            "Year": "2026",
            "Defects": 1,
            "History_OK": 1,
            "History_Missing_or_Error": 0,
        }
    ]