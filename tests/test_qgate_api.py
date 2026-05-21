from fastapi.testclient import TestClient
import os
import sqlite3
import pytest

import qgate_api
import qgate_api_service
from report.generate_qgate_kpi_dashboard import QGateDashboardDataError


def _create_summary_db(db_path):
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
            """
            INSERT INTO qgate_kpi_ticket_scope(
                team, ticket_id, year, ticket_name, tester, ticket_url,
                has_history, history_parse_ok, source_history_hash, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Plant-Dadong FIT",
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
                "Plant-Dadong FIT",
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
                "Plant-Dadong FIT",
                "2026-05-21T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_qgate_kpi_dashboard_endpoint_returns_payload_families(monkeypatch):
    captured = {}

    def fake_get_qgate_dashboard_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "generated_from": {
                "defect_dir": "qgate/defect",
                "history_dir": "qgate/history",
                "teams": ["DTSV_China"],
                "min_transition_count": 1,
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
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2026"],
                "groups": ["Q-Gate"],
                "changedBy": ["Alice"],
                "fif": ["Global"],
                "timespanMax": 2,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 4, 3, 1]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2026", 4, 3, 1]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
            },
            "issues": {
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
                "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
            },
        }

    monkeypatch.setattr(
        qgate_api,
        "get_qgate_dashboard_payload",
        fake_get_qgate_dashboard_payload,
    )
    client = TestClient(qgate_api.app)

    response = client.get(
        "/api/qgate/kpi-dashboard",
        params={"teams": ["DTSV_China"], "min_transition_count": 1},
    )

    assert response.status_code == 200
    assert captured["kwargs"]["teams"] == ["DTSV_China"]
    assert captured["kwargs"]["groups"] == []
    assert captured["kwargs"]["min_transition_count"] == 1
    assert set(response.json().keys()) == {
        "generated_from",
        "overview",
        "insights",
        "options",
        "meta",
        "coverage",
        "tickets",
        "issues",
    }


def test_qgate_kpi_dashboard_endpoint_forwards_full_filter_surface(monkeypatch):
    captured = {}

    def fake_get_qgate_dashboard_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "generated_from": {},
            "overview": {},
            "insights": [],
            "options": {"teams": [], "years": [], "groups": [], "changedBy": [], "fif": [], "timespanMax": 0},
            "meta": {"columns": [], "rows": []},
            "coverage": {"columns": [], "rows": []},
            "tickets": {"columns": [], "rows": []},
            "issues": {"columns": [], "rows": []},
        }

    monkeypatch.setattr(
        qgate_api,
        "get_qgate_dashboard_payload",
        fake_get_qgate_dashboard_payload,
    )
    client = TestClient(qgate_api.app)

    response = client.get(
        "/api/qgate/kpi-dashboard",
        params={
            "teams": ["DTSV_China"],
            "years": ["2026"],
            "groups": ["Q-Gate"],
            "changed_by": ["Alice"],
            "fif": ["Global"],
            "timespan_min": 1.5,
            "timespan_max": 2.9,
            "min_transition_count": 2,
            "analysis_workers": 3,
            "cache_dir": "custom-cache",
            "use_cache": "false",
        },
    )

    assert response.status_code == 200
    assert set(response.json().keys()) == {
        "generated_from",
        "overview",
        "insights",
        "options",
        "meta",
        "coverage",
        "tickets",
        "issues",
    }
    assert captured["kwargs"] == {
        "defect_dir": "qgate/defect",
        "history_dir": "qgate/history",
        "teams": ["DTSV_China"],
        "years": ["2026"],
        "groups": ["Q-Gate"],
        "changed_by": ["Alice"],
        "fif": ["Global"],
        "timespan_min": 1.5,
        "timespan_max": 2.9,
        "min_transition_count": 2,
        "analysis_workers": 3,
        "cache_dir": "custom-cache",
        "use_cache": False,
    }


def test_qgate_meta_endpoint_returns_health_summary(monkeypatch):
    captured = {}

    def fake_get_qgate_meta_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "defect_dir": "qgate/defect",
            "history_dir": "qgate/history",
            "availableTeams": ["DTSV_China"],
            "availableYears": ["2026"],
            "status": "healthy",
        }

    monkeypatch.setattr(
        qgate_api,
        "get_qgate_meta_payload",
        fake_get_qgate_meta_payload,
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/meta", params={"teams": ["DTSV_China"]})

    assert response.status_code == 200
    assert captured["kwargs"]["teams"] == ["DTSV_China"]
    assert response.json()["status"] == "healthy"


def test_qgate_dashboard_service_applies_filters(monkeypatch):
    monkeypatch.setattr(
        qgate_api_service,
        "_build_dashboard_payload_cached",
        lambda *args: {
            "generated_from": {
                "defect_dir": "qgate/defect",
                "history_dir": "qgate/history",
                "teams": ["DTSV_China"],
                "min_transition_count": 1,
            },
            "overview": {
                "team_count": 1,
                "total_defects": 2,
                "history_ok": 2,
                "history_bad": 0,
                "history_success_rate": 100.0,
                "transition_samples": 2,
                "unique_transitions": 2,
                "unique_tickets": 2,
                "changed_by_count": 2,
                "timespan_max": 5,
            },
            "insights": ["sample"],
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2025", "2026"],
                "groups": ["Q-Gate", "Integration"],
                "changedBy": ["Alice", "Bob"],
                "fif": ["Global", "China Specific"],
                "timespanMax": 5,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 2, 2, 0]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2025", 1, 1, 0], ["DTSV_China", "2026", 1, 1, 0]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"], ["1002", "https://octane/1002", "Ticket 1002", "Bob"]],
            },
            "issues": {
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
                "rows": [
                    ["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2],
                    ["2025", "DTSV_China", "1002", "09-Integration -> 01-Open", "Integration", 72, "Bob", "China Specific", 5],
                ],
            },
        },
    )

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["DTSV_China"],
        years=["2026"],
        groups=["Q-Gate"],
        changed_by=["Alice"],
        fif=["Global"],
        timespan_min=1,
        timespan_max=3,
        min_transition_count=1,
    )

    assert payload["issues"]["rows"] == [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]]
    assert payload["tickets"]["rows"] == [["1001", "https://octane/1001", "Ticket 1001", "Alice"]]
    assert payload["coverage"]["rows"] == [["DTSV_China", "2026", 1, 1, 0]]
    assert payload["overview"]["unique_tickets"] == 1
    assert payload["options"]["years"] == ["2025", "2026"]
    assert payload["options"]["groups"] == ["Q-Gate", "Integration"]


def test_qgate_dashboard_service_raises_clear_error_when_summary_missing(monkeypatch):
    qgate_api_service._build_dashboard_payload_cached.cache_clear()

    def raise_summary_missing(*args, **kwargs):
        raise QGateDashboardDataError("QGate summary data has not been built")

    monkeypatch.setattr(qgate_api_service, "_build_dashboard_payload_cached", raise_summary_missing)

    with pytest.raises(QGateDashboardDataError, match="QGate summary data has not been built"):
        qgate_api_service.get_qgate_dashboard_payload(teams=["Plant-Dadong FIT"])


def test_qgate_dashboard_endpoint_returns_422_when_summary_missing(monkeypatch):
    def raise_summary_missing(**kwargs):
        raise QGateDashboardDataError("QGate summary data has not been built")

    monkeypatch.setattr(qgate_api, "get_qgate_dashboard_payload", raise_summary_missing)
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/kpi-dashboard", params={"teams": ["Plant-Dadong FIT"]})

    assert response.status_code == 422
    assert response.json()["detail"] == "QGate summary data has not been built"


def test_qgate_dashboard_service_uses_env_db_path_for_summary_reads(tmp_path, monkeypatch):
    db_path = tmp_path / "summary.db"
    _create_summary_db(db_path)
    qgate_api_service._build_dashboard_payload_cached.cache_clear()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["Plant-Dadong FIT"],
        min_transition_count=1,
        use_cache=False,
    )

    assert payload["overview"]["total_defects"] == 1
    assert payload["issues"]["rows"] == [
        ["2026", "Plant-Dadong FIT", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24.0, "Alice", "Global", 2.0]
    ]


def test_qgate_dashboard_service_returns_empty_scoped_coverage_when_issue_filters_match_nothing(monkeypatch):
    monkeypatch.setattr(
        qgate_api_service,
        "_build_dashboard_payload_cached",
        lambda *args: {
            "generated_from": {
                "defect_dir": "qgate/defect",
                "history_dir": "qgate/history",
                "teams": ["DTSV_China"],
                "min_transition_count": 1,
            },
            "overview": {
                "team_count": 1,
                "total_defects": 1,
                "history_ok": 1,
                "history_bad": 0,
                "history_success_rate": 100.0,
                "transition_samples": 1,
                "unique_transitions": 1,
                "unique_tickets": 1,
                "changed_by_count": 1,
                "timespan_max": 2,
            },
            "insights": ["sample"],
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2026"],
                "groups": ["Q-Gate"],
                "changedBy": ["Alice"],
                "fif": ["Global"],
                "timespanMax": 2,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 1, 1, 0]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2026", 1, 1, 0]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
            },
            "issues": {
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
                "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
            },
        },
    )

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["DTSV_China"],
        changed_by=["Nobody"],
        min_transition_count=1,
    )

    assert payload["issues"]["rows"] == []
    assert payload["coverage"]["rows"] == [["DTSV_China", "2026", 1, 1, 0]]
    assert payload["meta"]["rows"] == [["DTSV_China", 1, 1, 0]]
    assert payload["overview"]["total_defects"] == 1


def test_qgate_dashboard_service_preserves_history_completeness_from_base_coverage(monkeypatch):
    monkeypatch.setattr(
        qgate_api_service,
        "_build_dashboard_payload_cached",
        lambda *args: {
            "generated_from": {
                "defect_dir": "qgate/defect",
                "history_dir": "qgate/history",
                "teams": ["DTSV_China"],
                "min_transition_count": 1,
            },
            "overview": {
                "team_count": 1,
                "total_defects": 2,
                "history_ok": 1,
                "history_bad": 1,
                "history_success_rate": 50.0,
                "transition_samples": 1,
                "unique_transitions": 1,
                "unique_tickets": 1,
                "changed_by_count": 1,
                "timespan_max": 2,
            },
            "insights": ["sample"],
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2026"],
                "groups": ["Q-Gate"],
                "changedBy": ["Alice"],
                "fif": ["Global"],
                "timespanMax": 2,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 2, 1, 1]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2026", 2, 1, 1]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
            },
            "issues": {
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
                "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
            },
        },
    )

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["DTSV_China"],
        changed_by=["Alice"],
        min_transition_count=1,
    )

    assert payload["coverage"]["rows"] == [["DTSV_China", "2026", 2, 1, 1]]
    assert payload["meta"]["rows"] == [["DTSV_China", 2, 1, 1]]
    assert payload["overview"]["total_defects"] == 2
    assert payload["overview"]["history_bad"] == 1


def test_qgate_dashboard_service_uses_fractional_timespan_bounds(monkeypatch):
    monkeypatch.setattr(
        qgate_api_service,
        "_build_dashboard_payload_cached",
        lambda *args: {
            "generated_from": {
                "defect_dir": "qgate/defect",
                "history_dir": "qgate/history",
                "teams": ["DTSV_China"],
                "min_transition_count": 1,
            },
            "overview": {
                "team_count": 1,
                "total_defects": 1,
                "history_ok": 1,
                "history_bad": 0,
                "history_success_rate": 100.0,
                "transition_samples": 1,
                "unique_transitions": 1,
                "unique_tickets": 1,
                "changed_by_count": 1,
                "timespan_max": 3,
            },
            "insights": ["sample"],
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2026"],
                "groups": ["Q-Gate"],
                "changedBy": ["Alice"],
                "fif": ["Global"],
                "timespanMax": 3,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 1, 1, 0]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2026", 1, 1, 0]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
            },
            "issues": {
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
                "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2.9]],
            },
        },
    )

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["DTSV_China"],
        timespan_min=1.5,
        timespan_max=2.8,
        min_transition_count=1,
    )

    assert payload["issues"]["rows"] == []


def test_qgate_dashboard_service_excludes_invalid_timespan_values_when_bounds_are_active(monkeypatch):
    monkeypatch.setattr(
        qgate_api_service,
        "_build_dashboard_payload_cached",
        lambda *args: {
            "generated_from": {
                "defect_dir": "qgate/defect",
                "history_dir": "qgate/history",
                "teams": ["DTSV_China"],
                "min_transition_count": 1,
            },
            "overview": {
                "team_count": 1,
                "total_defects": 2,
                "history_ok": 2,
                "history_bad": 0,
                "history_success_rate": 100.0,
                "transition_samples": 2,
                "unique_transitions": 2,
                "unique_tickets": 2,
                "changed_by_count": 2,
                "timespan_max": 2,
            },
            "insights": ["sample"],
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2026"],
                "groups": ["Q-Gate"],
                "changedBy": ["Alice", "Bob"],
                "fif": ["Global"],
                "timespanMax": 2,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 2, 2, 0]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2026", 2, 2, 0]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"], ["1002", "https://octane/1002", "Ticket 1002", "Bob"]],
            },
            "issues": {
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
                "rows": [
                    ["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", ""],
                    ["2026", "DTSV_China", "1002", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Bob", "Global", "abc"],
                ],
            },
        },
    )

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["DTSV_China"],
        timespan_max=2.0,
        min_transition_count=1,
    )

    assert payload["issues"]["rows"] == []
    assert payload["coverage"]["rows"] == [["DTSV_China", "2026", 2, 2, 0]]
    assert payload["meta"]["rows"] == [["DTSV_China", 2, 2, 0]]


def test_qgate_dashboard_service_returns_defensive_copies(monkeypatch):
    base_payload = {
        "generated_from": {
            "defect_dir": "qgate/defect",
            "history_dir": "qgate/history",
            "teams": ["DTSV_China"],
            "min_transition_count": 1,
        },
        "overview": {
            "team_count": 1,
            "total_defects": 1,
            "history_ok": 1,
            "history_bad": 0,
            "history_success_rate": 100.0,
            "transition_samples": 1,
            "unique_transitions": 1,
            "unique_tickets": 1,
            "changed_by_count": 1,
            "timespan_max": 2,
        },
        "insights": ["sample"],
        "options": {
            "teams": ["DTSV_China"],
            "years": ["2026"],
            "groups": ["Q-Gate"],
            "changedBy": ["Alice"],
            "fif": ["Global"],
            "timespanMax": 2,
        },
        "meta": {
            "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
            "rows": [["DTSV_China", 1, 1, 0]],
        },
        "coverage": {
            "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
            "rows": [["DTSV_China", "2026", 1, 1, 0]],
        },
        "tickets": {
            "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
            "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
        },
        "issues": {
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
            "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
        },
    }
    monkeypatch.setattr(qgate_api_service, "_build_dashboard_payload_cached", lambda *args: base_payload)

    first = qgate_api_service.get_qgate_dashboard_payload(teams=["DTSV_China"], min_transition_count=1)
    first["issues"]["rows"][0][0] = "2099"
    second = qgate_api_service.get_qgate_dashboard_payload(teams=["DTSV_China"], min_transition_count=1)

    assert second["issues"]["rows"][0][0] == "2026"


def test_qgate_dashboard_service_bypasses_memory_cache_when_use_cache_is_false(monkeypatch):
    calls = {"count": 0}

    def fail_cached(*args):
        raise AssertionError("cached builder should not run when use_cache is false")

    def fake_build_dashboard_payload(**kwargs):
        calls["count"] += 1
        return {
            "generated_from": {
                "defect_dir": kwargs["defect_dir"],
                "history_dir": kwargs["history_dir"],
                "teams": kwargs["teams"],
                "min_transition_count": kwargs["min_transition_count"],
            },
            "overview": {
                "team_count": 1,
                "total_defects": 1,
                "history_ok": 1,
                "history_bad": 0,
                "history_success_rate": 100.0,
                "transition_samples": 1,
                "unique_transitions": 1,
                "unique_tickets": 1,
                "changed_by_count": 1,
                "timespan_max": 2,
            },
            "insights": ["sample"],
            "options": {
                "teams": ["DTSV_China"],
                "years": ["2026"],
                "groups": ["Q-Gate"],
                "changedBy": ["Alice"],
                "fif": ["Global"],
                "timespanMax": 2,
            },
            "meta": {
                "columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", 1, 1, 0]],
            },
            "coverage": {
                "columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
                "rows": [["DTSV_China", "2026", 1, 1, 0]],
            },
            "tickets": {
                "columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
                "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
            },
            "issues": {
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
                "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
            },
        }

    monkeypatch.setattr(qgate_api_service, "_build_dashboard_payload_cached", fail_cached)
    monkeypatch.setattr(qgate_api_service, "build_dashboard_payload", fake_build_dashboard_payload)

    first = qgate_api_service.get_qgate_dashboard_payload(teams=["DTSV_China"], min_transition_count=1, use_cache=False)
    second = qgate_api_service.get_qgate_dashboard_payload(teams=["DTSV_China"], min_transition_count=1, use_cache=False)

    assert first["overview"]["total_defects"] == 1
    assert second["overview"]["total_defects"] == 1
    assert calls["count"] == 2


def test_qgate_dashboard_service_prefers_qgate_db_with_file_fallback(monkeypatch):
    captured_env = {}

    def fake_build_dashboard_payload(**kwargs):
        captured_env["OCTANE_DATA_SOURCE"] = os.environ.get("OCTANE_DATA_SOURCE")
        captured_env["OCTANE_DB_PATH"] = os.environ.get("OCTANE_DB_PATH")
        captured_env["QGATE_DB_PATH"] = os.environ.get("QGATE_DB_PATH")
        return {
            "generated_from": {
                "defect_dir": kwargs["defect_dir"],
                "history_dir": kwargs["history_dir"],
                "teams": kwargs["teams"],
                "min_transition_count": kwargs["min_transition_count"],
            },
            "overview": {
                "team_count": 1,
                "total_defects": 1,
                "history_ok": 1,
                "history_bad": 0,
                "history_success_rate": 100.0,
                "transition_samples": 1,
                "unique_transitions": 1,
                "unique_tickets": 1,
                "changed_by_count": 1,
                "timespan_max": 2,
            },
            "insights": [],
            "options": {"teams": ["DTSV_China"], "years": [], "groups": [], "changedBy": [], "fif": [], "timespanMax": 2},
            "meta": {"columns": [], "rows": []},
            "coverage": {"columns": [], "rows": []},
            "tickets": {"columns": [], "rows": []},
            "issues": {"columns": [], "rows": []},
        }

    monkeypatch.setattr(qgate_api_service, "build_dashboard_payload", fake_build_dashboard_payload)
    monkeypatch.setattr(qgate_api_service, "_build_dashboard_payload_cached", lambda *args: (_ for _ in ()).throw(AssertionError("cached builder should not run")))
    monkeypatch.delenv("OCTANE_DATA_SOURCE", raising=False)
    monkeypatch.delenv("OCTANE_DB_PATH", raising=False)
    monkeypatch.delenv("QGATE_DB_PATH", raising=False)

    qgate_api_service.get_qgate_dashboard_payload(teams=["DTSV_China"], min_transition_count=1, use_cache=False)

    assert captured_env == {
        "OCTANE_DATA_SOURCE": "db_only",
        "OCTANE_DB_PATH": os.path.join("qgate", "qgate_data.db"),
        "QGATE_DB_PATH": os.path.join("qgate", "qgate_data.db"),
    }
    assert os.environ.get("OCTANE_DATA_SOURCE") is None
    assert os.environ.get("OCTANE_DB_PATH") is None
    assert os.environ.get("QGATE_DB_PATH") is None


def test_qgate_dashboard_endpoint_maps_data_errors_to_422(monkeypatch):
    monkeypatch.setattr(
        qgate_api,
        "get_qgate_dashboard_payload",
        lambda **kwargs: (_ for _ in ()).throw(qgate_api.QGateDashboardDataError("No QGate issue rows were produced.")),
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/kpi-dashboard")

    assert response.status_code == 422
    assert response.json()["detail"] == "No QGate issue rows were produced."


def test_qgate_meta_endpoint_maps_data_errors_to_422(monkeypatch):
    monkeypatch.setattr(
        qgate_api,
        "get_qgate_meta_payload",
        lambda **kwargs: (_ for _ in ()).throw(qgate_api.QGateDashboardDataError("No meta payload available.")),
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/meta")

    assert response.status_code == 422
    assert response.json()["detail"] == "No meta payload available."