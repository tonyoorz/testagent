import sqlite3

from fastapi.testclient import TestClient
import pytest

import full_picture_api_service
import qgate_api


def _create_sqlite_db(db_path, ddl_statements):
    conn = sqlite3.connect(db_path)
    try:
        for statement in ddl_statements:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def test_full_picture_service_default_db_candidates_are_repo_anchored():
    repo_root = full_picture_api_service.REPOSITORY_ROOT

    assert full_picture_api_service.DEFAULT_DEFECT_DB_CANDIDATES == (
        repo_root / "qgate" / "qgate_data.db",
        repo_root / "database" / "local_data_rebuilt.db",
    )
    assert full_picture_api_service.DEFAULT_HISTORY_DB_CANDIDATES == (
        repo_root / "qgate" / "qgate_data.db",
    )


def test_resolve_db_path_requires_requested_columns(tmp_path):
    incomplete_db = tmp_path / "incomplete_generic.db"
    complete_db = tmp_path / "complete_generic.db"
    _create_sqlite_db(
        incomplete_db,
        [
            "CREATE TABLE sample_table (id TEXT, label TEXT)",
        ],
    )
    _create_sqlite_db(
        complete_db,
        [
            "CREATE TABLE sample_table (id TEXT, label TEXT, status TEXT)",
        ],
    )

    resolved = full_picture_api_service._resolve_db_path(
        (incomplete_db, complete_db),
        "sample_table",
        ("id", "label", "status"),
    )

    assert resolved == complete_db


def test_resolve_defect_db_path_skips_candidate_missing_required_columns(monkeypatch, tmp_path):
    incomplete_db = tmp_path / "incomplete_defects.db"
    complete_db = tmp_path / "complete_defects.db"
    _create_sqlite_db(
        incomplete_db,
        [
            """
            CREATE TABLE octane_defects (
                defect_id TEXT,
                name TEXT,
                status_phase TEXT,
                problem_finder_team TEXT,
                year TEXT
            )
            """,
        ],
    )
    _create_sqlite_db(
        complete_db,
        [
            """
            CREATE TABLE octane_defects (
                defect_id TEXT,
                name TEXT,
                status_phase TEXT,
                problem_finder_team TEXT,
                year TEXT,
                project TEXT,
                assigned_ecu TEXT,
                top_aida TEXT,
                aida_english TEXT,
                aida_businesskey TEXT,
                phase TEXT,
                solution_cluster TEXT,
                pu TEXT,
                market TEXT,
                lead_model TEXT
            )
            """,
        ],
    )

    full_picture_api_service._resolve_defect_db_path.cache_clear()
    try:
        monkeypatch.setattr(
            full_picture_api_service,
            "DEFAULT_DEFECT_DB_CANDIDATES",
            (incomplete_db, complete_db),
        )

        assert full_picture_api_service._resolve_defect_db_path() == complete_db
    finally:
        full_picture_api_service._resolve_defect_db_path.cache_clear()


def test_full_picture_service_accepts_qgate_style_defect_schema_with_missing_optional_dimensions(monkeypatch, tmp_path):
    qgate_like_db = tmp_path / "qgate_like_defects.db"
    _create_sqlite_db(
        qgate_like_db,
        [
            """
            CREATE TABLE octane_defects (
                defect_id TEXT,
                name TEXT,
                status_phase TEXT,
                problem_finder_team TEXT,
                year INTEGER,
                assigned_ecu TEXT,
                top_aida TEXT,
                aida_english TEXT,
                aida_businesskey TEXT,
                phase TEXT,
                solution_cluster TEXT,
                lead_model TEXT
            )
            """,
            """
            INSERT INTO octane_defects(
                defect_id,
                name,
                status_phase,
                problem_finder_team,
                year,
                assigned_ecu,
                top_aida,
                aida_english,
                aida_businesskey,
                phase,
                solution_cluster,
                lead_model
            ) VALUES (
                '1001',
                'QGate sourced defect',
                '08-Ready for Review',
                'DTSV_China',
                2026,
                'ECU-1',
                'Top AIDA',
                'AIDA English',
                'BK-1',
                '08-Ready for Review',
                'Cluster A',
                'NA5'
            )
            """,
        ],
    )

    full_picture_api_service._resolve_defect_db_path.cache_clear()
    try:
        monkeypatch.setattr(
            full_picture_api_service,
            "DEFAULT_DEFECT_DB_CANDIDATES",
            (qgate_like_db,),
        )
        monkeypatch.setattr(full_picture_api_service, "_load_history_events", lambda defect_ids: [])
        monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)

        payload = full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"])

        assert payload["generated_from"]["defect_db_path"] == str(qgate_like_db)
        assert payload["overview"]["ticket_count"] == 1
        assert payload["filters"] == {
            "years": ["2026"],
            "projects": [],
            "assigned_ecus": ["ECU-1"],
            "problem_finder_teams": ["DTSV_China"],
            "aidas": ["Top AIDA"],
            "phases": ["08-Ready for Review"],
            "solution_clusters": ["Cluster A"],
            "pus": [],
            "markets": [],
            "lead_models": ["NA5"],
            "groups": ["Integration"],
        }
        assert payload["ticket_rows"] == [
            {
                "ticket_id": "1001",
                "ticket_name": "QGate sourced defect",
                "status": "08-Ready for Review",
                "problem_finder_team": "DTSV_China",
                "group": "Integration",
                "phase": "08-Ready for Review",
                "is_resolved_forward": False,
                "is_rejected_directly": False,
                "year": "2026",
                "project": "",
                "assigned_ecu": "ECU-1",
                "aida": "Top AIDA",
                "solution_cluster": "Cluster A",
                "pu": "",
                "market": "",
                "lead_model": "NA5",
            }
        ]
    finally:
        full_picture_api_service._resolve_defect_db_path.cache_clear()


def test_resolve_history_db_path_skips_candidate_missing_required_columns(monkeypatch, tmp_path):
    incomplete_db = tmp_path / "incomplete_history.db"
    complete_db = tmp_path / "complete_history.db"
    _create_sqlite_db(
        incomplete_db,
        [
            """
            CREATE TABLE octane_defect_history_events (
                defect_id TEXT,
                field_name TEXT,
                event_timestamp TEXT
            )
            """,
        ],
    )
    _create_sqlite_db(
        complete_db,
        [
            """
            CREATE TABLE octane_defect_history_events (
                defect_id TEXT,
                field_name TEXT,
                event_timestamp TEXT,
                entry_index INTEGER,
                change_index INTEGER,
                old_value TEXT,
                new_value TEXT,
                old_value_text TEXT,
                new_value_text TEXT
            )
            """,
        ],
    )

    full_picture_api_service._resolve_history_db_path.cache_clear()
    try:
        monkeypatch.setattr(
            full_picture_api_service,
            "DEFAULT_HISTORY_DB_CANDIDATES",
            (incomplete_db, complete_db),
        )

        assert full_picture_api_service._resolve_history_db_path() == complete_db
    finally:
        full_picture_api_service._resolve_history_db_path.cache_clear()


def test_full_picture_dashboard_endpoint_returns_payload_families(monkeypatch):
    def fake_get_full_picture_dashboard_payload(**kwargs):
        return {
            "generated_from": {"years": ["2026"]},
            "filters": {
                "years": ["2026"],
                "projects": [],
                "assigned_ecus": [],
                "problem_finder_teams": [],
                "aidas": [],
                "phases": [],
                "solution_clusters": [],
                "pus": [],
                "markets": [],
                "lead_models": [],
                "groups": [],
            },
            "overview": {"total_tickets": 1},
            "outcome_summary": [],
            "team_outcome_rows": [],
            "ticket_rows": [],
        }

    monkeypatch.setattr(
        qgate_api,
        "get_full_picture_dashboard_payload",
        fake_get_full_picture_dashboard_payload,
        raising=False,
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/full-picture/dashboard")

    assert response.status_code == 200
    assert set(response.json().keys()) == {
        "generated_from",
        "filters",
        "overview",
        "outcome_summary",
        "team_outcome_rows",
        "ticket_rows",
    }


def test_full_picture_dashboard_endpoint_forwards_filter_surface(monkeypatch):
    captured = {}

    def fake_get_full_picture_dashboard_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "generated_from": {"years": ["2026"]},
            "filters": {
                "years": ["2026"],
                "projects": [],
                "assigned_ecus": [],
                "problem_finder_teams": [],
                "aidas": [],
                "phases": [],
                "solution_clusters": [],
                "pus": [],
                "markets": [],
                "lead_models": [],
                "groups": [],
            },
            "overview": {"total_tickets": 0},
            "outcome_summary": [],
            "team_outcome_rows": [],
            "ticket_rows": [],
        }

    monkeypatch.setattr(
        qgate_api,
        "get_full_picture_dashboard_payload",
        fake_get_full_picture_dashboard_payload,
        raising=False,
    )
    client = TestClient(qgate_api.app)

    response = client.get(
        "/api/full-picture/dashboard",
        params={
            "years": ["2025", "2026"],
            "projects": ["Project A"],
            "assigned_ecus": ["ECU-1"],
            "problem_finder_teams": ["DTSV_China"],
            "aidas": ["AIDA-1"],
            "phases": ["08-Ready for Review"],
            "solution_clusters": ["Cluster A"],
            "pus": ["PU-1"],
            "markets": ["CN"],
            "lead_models": ["NA5"],
            "groups": ["Integration"],
        },
    )

    assert response.status_code == 200
    assert captured["kwargs"] == {
        "years": ["2025", "2026"],
        "projects": ["Project A"],
        "assigned_ecus": ["ECU-1"],
        "problem_finder_teams": ["DTSV_China"],
        "aidas": ["AIDA-1"],
        "phases": ["08-Ready for Review"],
        "solution_clusters": ["Cluster A"],
        "pus": ["PU-1"],
        "markets": ["CN"],
        "lead_models": ["NA5"],
        "groups": ["Integration"],
    }


def test_full_picture_dashboard_endpoint_translates_sqlite_errors_to_422(monkeypatch):
    def fake_get_full_picture_dashboard_payload(**kwargs):
        raise sqlite3.DatabaseError("unable to open database file")

    monkeypatch.setattr(
        qgate_api,
        "get_full_picture_dashboard_payload",
        fake_get_full_picture_dashboard_payload,
        raising=False,
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/full-picture/dashboard")

    assert response.status_code == 422
    assert response.json() == {"detail": "unable to open database file"}


def test_full_picture_dashboard_endpoint_defaults_to_2026_scope(monkeypatch):
    captured = {}

    defect_rows = [
        {
            "ticket_id": "1001",
            "ticket_name": "Forward fixed",
            "status": "In Progress",
            "problem_finder_team": "DTSV_China",
            "year": "2026",
            "project": "Project A",
            "assigned_ecu": "ECU-1",
            "aida": "AIDA-1",
            "phase": "08-Ready for Review",
            "solution_cluster": "Cluster A",
            "pu": "PU-1",
            "market": "CN",
            "lead_model": "NA5",
        },
        {
            "ticket_id": "1002",
            "ticket_name": "Older ticket",
            "status": "Open",
            "problem_finder_team": "DTSV_China",
            "year": "2025",
            "project": "Project B",
            "assigned_ecu": "ECU-2",
            "aida": "AIDA-2",
            "phase": "03-In Analysis",
            "solution_cluster": "Cluster B",
            "pu": "PU-2",
            "market": "EU",
            "lead_model": "G60",
        },
    ]

    def fake_load_defect_rows(query):
        captured["years"] = query.years
        return [row for row in defect_rows if row["year"] in set(query.years)]

    monkeypatch.setattr(full_picture_api_service, "_load_defect_rows", fake_load_defect_rows)
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_history_events",
        lambda defect_ids: [
            {
                "ticket_id": "1001",
                "old_value": "",
                "new_value": "",
                "old_value_text": "08-Ready for Review",
                "new_value_text": "06-Resolved",
                "event_timestamp": "2026-03-01T10:00:00Z",
                "entry_index": 1,
                "change_index": 1,
            }
        ],
    )
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)
    monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)
    client = TestClient(qgate_api.app)

    response = client.get("/api/full-picture/dashboard")

    assert response.status_code == 200
    assert captured["years"] == ("2026",)
    payload = response.json()
    assert payload["generated_from"]["years"] == ["2026"]
    assert [row["ticket_id"] for row in payload["ticket_rows"]] == ["1001"]


def test_full_picture_service_aggregates_outcomes_and_filter_options(monkeypatch):
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_defect_rows",
        lambda query: [
            {
                "ticket_id": "1001",
                "ticket_name": "Forward fixed",
                "status": "In Progress",
                "problem_finder_team": "Team A",
                "year": "2026",
                "project": "Project A",
                "assigned_ecu": "ECU-1",
                "aida": "AIDA-1",
                "phase": "08-Ready for Review",
                "solution_cluster": "Cluster A",
                "pu": "PU-1",
                "market": "CN",
                "lead_model": "NA5",
            },
            {
                "ticket_id": "1002",
                "ticket_name": "Rejected directly",
                "status": "Open",
                "problem_finder_team": "Team A",
                "year": "2026",
                "project": "Project A",
                "assigned_ecu": "ECU-2",
                "aida": "AIDA-2",
                "phase": "01-Open",
                "solution_cluster": "Cluster B",
                "pu": "PU-2",
                "market": "CN",
                "lead_model": "NA5",
            },
            {
                "ticket_id": "1003",
                "ticket_name": "Still in analysis",
                "status": "In Analysis",
                "problem_finder_team": "Team B",
                "year": "2026",
                "project": "Project B",
                "assigned_ecu": "ECU-3",
                "aida": "AIDA-3",
                "phase": "03-In Analysis",
                "solution_cluster": "Cluster C",
                "pu": "PU-3",
                "market": "EU",
                "lead_model": "G60",
            },
            {
                "ticket_id": "1004",
                "ticket_name": "Q-Gate waiting",
                "status": "QGate",
                "problem_finder_team": "Team C",
                "year": "2026",
                "project": "Project C",
                "assigned_ecu": "ECU-4",
                "aida": "AIDA-4",
                "phase": "02-QGate",
                "solution_cluster": "Cluster D",
                "pu": "PU-4",
                "market": "US",
                "lead_model": "U11",
            },
        ],
    )
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_history_events",
        lambda defect_ids: [
            {
                "ticket_id": "1001",
                "old_value": "",
                "new_value": "",
                "old_value_text": "08-Ready for Review",
                "new_value_text": "06-Resolved",
                "event_timestamp": "2026-03-01T10:00:00Z",
                "entry_index": 1,
                "change_index": 1,
            },
            {
                "ticket_id": "1002",
                "old_value": "phase_01",
                "new_value": "phase_09",
                "old_value_text": "",
                "new_value_text": "",
                "event_timestamp": "2026-03-02T10:00:00Z",
                "entry_index": 1,
                "change_index": 1,
            },
        ],
    )
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)
    monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)

    payload = full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"])

    assert payload["overview"] == {
        "ticket_count": 4,
        "resolved_forward_count": 1,
        "rejected_directly_count": 1,
        "resolved_forward_percent": 25.0,
        "rejected_directly_percent": 25.0,
    }
    assert payload["filters"] == {
        "years": ["2026"],
        "projects": ["Project A", "Project B", "Project C"],
        "assigned_ecus": ["ECU-1", "ECU-2", "ECU-3", "ECU-4"],
        "problem_finder_teams": ["Team A", "Team B", "Team C"],
        "aidas": ["AIDA-1", "AIDA-2", "AIDA-3", "AIDA-4"],
        "phases": ["01-Open", "02-QGate", "03-In Analysis", "08-Ready for Review"],
        "solution_clusters": ["Cluster A", "Cluster B", "Cluster C", "Cluster D"],
        "pus": ["PU-1", "PU-2", "PU-3", "PU-4"],
        "markets": ["CN", "EU", "US"],
        "lead_models": ["G60", "NA5", "U11"],
        "groups": ["Q-Gate", "Integration", "CoC"],
    }
    assert payload["outcome_summary"] == [
        {
            "key": "resolved_forward",
            "label": "Resolved Forward (08 -> 06)",
            "count": 1,
            "percent": 25.0,
            "denominator": 4,
        },
        {
            "key": "rejected_directly",
            "label": "Rejected Directly (01 -> 09)",
            "count": 1,
            "percent": 25.0,
            "denominator": 4,
        },
    ]
    assert payload["team_outcome_rows"] == [
        {
            "problem_finder_team": "Team A",
            "total_tickets": 2,
            "resolved_forward_count": 1,
            "rejected_directly_count": 1,
            "resolved_forward_team_percent": 50.0,
            "rejected_directly_team_percent": 50.0,
            "team_denominator": 2,
        },
        {
            "problem_finder_team": "Team B",
            "total_tickets": 1,
            "resolved_forward_count": 0,
            "rejected_directly_count": 0,
            "resolved_forward_team_percent": 0.0,
            "rejected_directly_team_percent": 0.0,
            "team_denominator": 1,
        },
        {
            "problem_finder_team": "Team C",
            "total_tickets": 1,
            "resolved_forward_count": 0,
            "rejected_directly_count": 0,
            "resolved_forward_team_percent": 0.0,
            "rejected_directly_team_percent": 0.0,
            "team_denominator": 1,
        },
    ]
    assert payload["ticket_rows"][0]["ticket_id"] == "1001"
    assert payload["ticket_rows"][0]["is_resolved_forward"] is True
    assert payload["ticket_rows"][1]["is_rejected_directly"] is True
    assert "outcome" not in payload["ticket_rows"][0]
    assert "outcome" not in payload["ticket_rows"][1]
    assert payload["ticket_rows"][2]["group"] == "CoC"
    assert payload["ticket_rows"][3]["group"] == "Q-Gate"


def test_full_picture_service_returns_empty_state_when_group_filter_matches_nothing(monkeypatch):
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_defect_rows",
        lambda query: [
            {
                "ticket_id": "1001",
                "ticket_name": "Only integration ticket",
                "status": "Open",
                "problem_finder_team": "Team A",
                "year": "2026",
                "project": "Project A",
                "assigned_ecu": "ECU-1",
                "aida": "AIDA-1",
                "phase": "01-Open",
                "solution_cluster": "Cluster A",
                "pu": "PU-1",
                "market": "CN",
                "lead_model": "NA5",
            }
        ],
    )
    monkeypatch.setattr(full_picture_api_service, "_load_history_events", lambda defect_ids: [])
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)
    monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)

    payload = full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"], groups=["Q-Gate"])

    assert payload["overview"]["ticket_count"] == 0
    assert payload["filters"] == {
        "years": [],
        "projects": [],
        "assigned_ecus": [],
        "problem_finder_teams": [],
        "aidas": [],
        "phases": [],
        "solution_clusters": [],
        "pus": [],
        "markets": [],
        "lead_models": [],
        "groups": [],
    }
    assert payload["team_outcome_rows"] == []
    assert payload["ticket_rows"] == []


def test_full_picture_service_counts_both_path_flags_without_collapsing_outcome(monkeypatch):
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_defect_rows",
        lambda query: [
            {
                "ticket_id": "2001",
                "ticket_name": "Seen in both paths",
                "status": "Open",
                "problem_finder_team": "Team Both",
                "year": "2026",
                "project": "Project Both",
                "assigned_ecu": "ECU-BOTH",
                "aida": "AIDA-BOTH",
                "phase": "08-Ready for Review",
                "solution_cluster": "Cluster Both",
                "pu": "PU-BOTH",
                "market": "CN",
                "lead_model": "NA5",
            },
            {
                "ticket_id": "2002",
                "ticket_name": "Scope-only ticket",
                "status": "Open",
                "problem_finder_team": "Team Solo",
                "year": "2026",
                "project": "Project Solo",
                "assigned_ecu": "ECU-SOLO",
                "aida": "AIDA-SOLO",
                "phase": "03-In Analysis",
                "solution_cluster": "Cluster Solo",
                "pu": "PU-SOLO",
                "market": "EU",
                "lead_model": "G60",
            },
        ],
    )
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_history_events",
        lambda defect_ids: [
            {
                "ticket_id": "2001",
                "old_value": "phase_08",
                "new_value": "phase_06",
                "old_value_text": "",
                "new_value_text": "",
                "event_timestamp": "2026-03-01T10:00:00Z",
                "entry_index": 1,
                "change_index": 1,
            },
            {
                "ticket_id": "2001",
                "old_value": "phase_01",
                "new_value": "phase_09",
                "old_value_text": "",
                "new_value_text": "",
                "event_timestamp": "2026-03-02T10:00:00Z",
                "entry_index": 1,
                "change_index": 1,
            },
        ],
    )
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)
    monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)

    payload = full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"])

    assert payload["overview"] == {
        "ticket_count": 2,
        "resolved_forward_count": 1,
        "rejected_directly_count": 1,
        "resolved_forward_percent": 50.0,
        "rejected_directly_percent": 50.0,
    }
    assert payload["outcome_summary"] == [
        {
            "key": "resolved_forward",
            "label": "Resolved Forward (08 -> 06)",
            "count": 1,
            "percent": 50.0,
            "denominator": 2,
        },
        {
            "key": "rejected_directly",
            "label": "Rejected Directly (01 -> 09)",
            "count": 1,
            "percent": 50.0,
            "denominator": 2,
        },
    ]
    assert payload["team_outcome_rows"] == [
        {
            "problem_finder_team": "Team Both",
            "total_tickets": 1,
            "resolved_forward_count": 1,
            "rejected_directly_count": 1,
            "resolved_forward_team_percent": 100.0,
            "rejected_directly_team_percent": 100.0,
            "team_denominator": 1,
        },
        {
            "problem_finder_team": "Team Solo",
            "total_tickets": 1,
            "resolved_forward_count": 0,
            "rejected_directly_count": 0,
            "resolved_forward_team_percent": 0.0,
            "rejected_directly_team_percent": 0.0,
            "team_denominator": 1,
        },
    ]
    both_path_row = next(row for row in payload["ticket_rows"] if row["ticket_id"] == "2001")
    assert both_path_row["is_resolved_forward"] is True
    assert both_path_row["is_rejected_directly"] is True
    assert "outcome" not in both_path_row


def test_full_picture_group_mapping_reuses_qgate_vocabulary():
    assert full_picture_api_service.classify_phase_transition_group("02-QGate -> 03-In Analysis") == "Q-Gate"
    assert full_picture_api_service.classify_phase_transition_group("09-Integration -> 01-Open") == "Integration"
    assert full_picture_api_service.classify_phase_transition_group("03-In Analysis -> 04-In Progress") == "CoC"
    assert full_picture_api_service.classify_phase_transition_group("unknown") == "Other"


def test_full_picture_service_keeps_current_06_and_09_phases_in_integration(monkeypatch):
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_defect_rows",
        lambda query: [
            {
                "ticket_id": "3001",
                "ticket_name": "Resolved ticket",
                "status": "Resolved",
                "problem_finder_team": "Team Integration",
                "year": "2026",
                "project": "Project I",
                "assigned_ecu": "ECU-I1",
                "aida": "AIDA-I1",
                "phase": "06-Resolved",
                "solution_cluster": "Cluster I",
                "pu": "PU-I",
                "market": "CN",
                "lead_model": "NA5",
            },
            {
                "ticket_id": "3002",
                "ticket_name": "Integration ticket",
                "status": "Integration",
                "problem_finder_team": "Team Integration",
                "year": "2026",
                "project": "Project I",
                "assigned_ecu": "ECU-I2",
                "aida": "AIDA-I2",
                "phase": "09-Integration",
                "solution_cluster": "Cluster I",
                "pu": "PU-I",
                "market": "CN",
                "lead_model": "NA5",
            },
        ],
    )
    monkeypatch.setattr(full_picture_api_service, "_load_history_events", lambda defect_ids: [])
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)
    monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)

    payload = full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"])

    assert [row["group"] for row in payload["ticket_rows"]] == ["Integration", "Integration"]


def test_full_picture_service_raises_when_defect_db_source_is_missing(monkeypatch):
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)

    with pytest.raises(full_picture_api_service.FullPictureDashboardDataError, match="defect database"):
        full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"])


def test_full_picture_service_raises_when_history_db_source_is_missing(monkeypatch):
    monkeypatch.setattr(
        full_picture_api_service,
        "_load_defect_rows",
        lambda query: [
            {
                "ticket_id": "4001",
                "ticket_name": "Needs history",
                "status": "Open",
                "problem_finder_team": "Team History",
                "year": "2026",
                "project": "Project H",
                "assigned_ecu": "ECU-H1",
                "aida": "AIDA-H1",
                "phase": "01-Open",
                "solution_cluster": "Cluster H",
                "pu": "PU-H",
                "market": "CN",
                "lead_model": "NA5",
            }
        ],
    )
    monkeypatch.setattr(full_picture_api_service, "_resolve_defect_db_path", lambda: None)
    monkeypatch.setattr(full_picture_api_service, "_resolve_history_db_path", lambda: None)

    with pytest.raises(full_picture_api_service.FullPictureDashboardDataError, match="history database"):
        full_picture_api_service.get_full_picture_dashboard_payload(years=["2026"])


def test_full_picture_dashboard_endpoint_translates_service_data_errors_to_422(monkeypatch):
    def fake_get_full_picture_dashboard_payload(**kwargs):
        raise full_picture_api_service.FullPictureDashboardDataError("Full Picture defect database is not available")

    monkeypatch.setattr(
        qgate_api,
        "get_full_picture_dashboard_payload",
        fake_get_full_picture_dashboard_payload,
        raising=False,
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/full-picture/dashboard")

    assert response.status_code == 422
    assert response.json() == {"detail": "Full Picture defect database is not available"}