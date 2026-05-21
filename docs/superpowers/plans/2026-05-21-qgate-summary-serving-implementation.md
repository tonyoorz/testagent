# QGate Summary Serving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace request-time QGate KPI history analysis with a SQLite summary-serving layer that preserves the existing API payload shape and fails clearly when summary data is unavailable.

**Architecture:** Add two derived SQLite serving tables, build them offline from `octane_defects` plus `octane_defect_histories`, and switch dashboard payload generation to read the derived tables instead of parsing raw history during requests. Keep the current frontend contract unchanged and keep the old online path out of the request hot path.

**Tech Stack:** Python 3.11, SQLite, pandas, FastAPI, pytest

---

## File Structure

- Create: `qgate_summary_store.py`
  - Own schema creation for QGate summary tables.
  - Own full-refresh build flow from raw defect and history tables.
  - Own read helpers for summary-backed dashboard payload generation.
  - Own a small CLI entrypoint for manual refresh.
- Modify: `octane_db.py`
  - Add reusable schema helpers for QGate summary-serving tables and indexes.
- Modify: `report/generate_qgate_kpi_dashboard.py`
  - Add summary-backed payload builder.
  - Route `build_dashboard_payload()` to the summary-backed path.
  - Raise explicit `QGateDashboardDataError` when summary data is absent.
- Modify: `qgate_api_service.py`
  - Keep query normalization unchanged.
  - Call summary-backed payload generation and preserve filtering behavior.
- Modify: `qgate_api.py`
  - Preserve `422` mapping for `QGateDashboardDataError`.
  - Add tests for summary-missing error surface.
- Create: `tests/test_qgate_summary_store.py`
  - Cover schema creation, full refresh, and summary row correctness.
- Modify: `tests/test_qgate_kpi_payload.py`
  - Cover summary-backed payload generation, summary-missing failures, and filter compatibility.
- Modify: `tests/test_qgate_api.py`
  - Cover API behavior when summary data exists and when it is missing.

## Task 1: Add Summary Store Schema And Full Refresh Builder

**Files:**
- Create: `qgate_summary_store.py`
- Modify: `octane_db.py`
- Test: `tests/test_qgate_summary_store.py`

- [ ] **Step 1: Write the failing tests for schema creation and refresh output**

```python
import json
import sqlite3

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
```

- [ ] **Step 2: Run the new tests and verify they fail for the right reason**

Run: `pytest tests/test_qgate_summary_store.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'qgate_summary_store'` or missing symbol errors for `ensure_qgate_summary_tables` / `refresh_qgate_summary_tables`.

- [ ] **Step 3: Add schema helpers in `octane_db.py` and create `qgate_summary_store.py` with minimal full-refresh support**

```python
# octane_db.py
def ensure_qgate_summary_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS qgate_kpi_ticket_scope (
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
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS qgate_kpi_issue_transitions (
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
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qgate_scope_team_year ON qgate_kpi_ticket_scope(team, year)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qgate_scope_parse_ok ON qgate_kpi_ticket_scope(history_parse_ok)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qgate_transitions_team_year ON qgate_kpi_issue_transitions(team, year)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qgate_transitions_group ON qgate_kpi_issue_transitions(group_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qgate_transitions_changed_by ON qgate_kpi_issue_transitions(changed_by)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qgate_transitions_fif ON qgate_kpi_issue_transitions(fif)")
    conn.commit()


# qgate_summary_store.py
def refresh_qgate_summary_tables(*, db_path: str, teams: list[str] | None = None) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        ensure_qgate_summary_tables(conn)
        scoped = _load_scoped_defects(conn, teams=teams or [])
        conn.execute("DELETE FROM qgate_kpi_issue_transitions")
        conn.execute("DELETE FROM qgate_kpi_ticket_scope")
        scope_rows, transition_rows = _build_summary_rows(conn, scoped)
        conn.executemany(
            "INSERT OR REPLACE INTO qgate_kpi_ticket_scope(team, ticket_id, year, ticket_name, tester, ticket_url, has_history, history_parse_ok, source_history_hash, refreshed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            scope_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO qgate_kpi_issue_transitions(team, ticket_id, year, ticket_name, tester, ticket_url, phase_transition, group_name, changed_by, fif, duration_hours, duration_days, ticket_timespan_days, start_time, end_time, source_history_hash, source_team, refreshed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            transition_rows,
        )
        conn.commit()
        return {"ticket_scope": len(scope_rows), "issue_transitions": len(transition_rows)}
    finally:
        conn.close()
```

- [ ] **Step 4: Re-run the summary-store tests and make them pass**

Run: `pytest tests/test_qgate_summary_store.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the schema and refresh builder**

```bash
git add octane_db.py qgate_summary_store.py tests/test_qgate_summary_store.py
git commit -m "feat: add qgate summary refresh store"
```

## Task 2: Add Summary Store Read Helpers And Payload Builder Coverage

**Files:**
- Modify: `qgate_summary_store.py`
- Modify: `report/generate_qgate_kpi_dashboard.py`
- Modify: `tests/test_qgate_kpi_payload.py`

- [ ] **Step 1: Write failing payload tests for summary-backed reads and missing-summary errors**

```python
def test_build_dashboard_payload_reads_from_summary_tables(tmp_path, monkeypatch):
    module = _load_module()
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE qgate_kpi_ticket_scope (team TEXT, ticket_id TEXT, year TEXT, ticket_name TEXT, tester TEXT, ticket_url TEXT, has_history INTEGER, history_parse_ok INTEGER, source_history_hash TEXT, refreshed_at TEXT, PRIMARY KEY(team, ticket_id))"
        )
        conn.execute(
            "CREATE TABLE qgate_kpi_issue_transitions (team TEXT, ticket_id TEXT, year TEXT, ticket_name TEXT, tester TEXT, ticket_url TEXT, phase_transition TEXT, group_name TEXT, changed_by TEXT, fif TEXT, duration_hours REAL, duration_days REAL, ticket_timespan_days REAL, start_time TEXT, end_time TEXT, source_history_hash TEXT, source_team TEXT, refreshed_at TEXT, PRIMARY KEY(team, ticket_id, phase_transition, start_time, end_time))"
        )
        conn.execute(
            "INSERT INTO qgate_kpi_ticket_scope VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Plant-Dadong FIT", "1001", "2026", "Ticket 1001", "Alice", "https://octane/1001", 1, 1, "hash-1", "2026-05-21T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO qgate_kpi_issue_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Plant-Dadong FIT", "1001", "2026", "Ticket 1001", "Alice", "https://octane/1001", "02-QGate -> 03-Analysis", "Q-Gate", "Alice", "Global", 24.0, 1.0, 2.0, "2026-03-01T08:00:00Z", "2026-03-02T08:00:00Z", "hash-1", "Plant-Dadong FIT", "2026-05-21T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setenv("OCTANE_DATA_SOURCE", "db_only")

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

    assert payload["overview"]["total_defects"] == 1
    assert payload["overview"]["history_ok"] == 1
    assert payload["issues"]["rows"][0][1] == "Plant-Dadong FIT"
    assert payload["tickets"]["rows"][0][0] == "1001"


def test_build_dashboard_payload_raises_when_summary_tables_are_missing(tmp_path, monkeypatch):
    module = _load_module()
    db_path = tmp_path / "qgate.db"
    sqlite3.connect(db_path).close()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setenv("OCTANE_DATA_SOURCE", "db_only")

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
```

- [ ] **Step 2: Run the payload tests and verify the new cases fail correctly**

Run: `pytest tests/test_qgate_kpi_payload.py -k "summary_tables or summary data" -v`

Expected: FAIL with current online-computation behavior or missing helper errors.

- [ ] **Step 3: Implement summary-backed read helpers and route `build_dashboard_payload()` through them**

```python
# qgate_summary_store.py
def load_summary_data(*, db_path: str, teams: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = sqlite3.connect(db_path)
    try:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('qgate_kpi_ticket_scope', 'qgate_kpi_issue_transitions')"
            ).fetchall()
        }
        if table_names != {"qgate_kpi_ticket_scope", "qgate_kpi_issue_transitions"}:
            raise ValueError("QGate summary data has not been built")

        placeholders = ",".join(["?"] * len(teams)) if teams else ""
        scope_query = "SELECT team, ticket_id, year, ticket_name, tester, ticket_url, has_history, history_parse_ok FROM qgate_kpi_ticket_scope"
        issues_query = "SELECT team, ticket_id, year, ticket_name, tester, ticket_url, phase_transition, group_name, changed_by, fif, duration_hours, duration_days, ticket_timespan_days FROM qgate_kpi_issue_transitions"
        params: list[str] = []
        if teams:
            scope_query += f" WHERE team IN ({placeholders})"
            issues_query += f" WHERE team IN ({placeholders})"
            params = list(teams)
        scope_df = pd.read_sql_query(scope_query, conn, params=params)
        issues_df = pd.read_sql_query(issues_query, conn, params=params)
        return scope_df, issues_df
    finally:
        conn.close()


# report/generate_qgate_kpi_dashboard.py
def build_dashboard_payload(...):
    db_path = os.environ.get("QGATE_DB_PATH") or os.path.join("qgate", "qgate_data.db")
    try:
        scope_df, issues_source_df = load_summary_data(db_path=db_path, teams=teams)
    except ValueError as exc:
        raise QGateDashboardDataError(str(exc)) from exc

    if issues_source_df.empty and scope_df.empty:
        raise QGateDashboardDataError("QGate summary data has not been built for the selected teams.")

    issues_df = issues_source_df.rename(
        columns={
            "team": "Team",
            "ticket_id": "Ticket_ID",
            "year": "Year",
            "ticket_name": "Ticket_Name",
            "tester": "Tester",
            "ticket_url": "Ticket_URL",
            "phase_transition": "Phase_Transition",
            "group_name": "Group",
            "changed_by": "Changed_By",
            "fif": "FiF",
            "duration_hours": "Duration_Hours",
            "duration_days": "Duration_Days",
            "ticket_timespan_days": "Ticket_Timespan_Days",
        }
    )
```

- [ ] **Step 4: Re-run the payload tests and make them pass**

Run: `pytest tests/test_qgate_kpi_payload.py -v`

Expected: PASS with all existing payload-shape tests plus the new summary-backed cases.

- [ ] **Step 5: Commit the summary-backed payload reader**

```bash
git add qgate_summary_store.py report/generate_qgate_kpi_dashboard.py tests/test_qgate_kpi_payload.py
git commit -m "feat: read qgate dashboard payload from summary tables"
```

## Task 3: Preserve Filtering And Service Semantics On The Summary Path

**Files:**
- Modify: `qgate_api_service.py`
- Modify: `tests/test_qgate_api.py`

- [ ] **Step 1: Write failing service and API tests for summary-missing behavior and unchanged filter semantics**

```python
def test_qgate_dashboard_service_raises_clear_error_when_summary_missing(monkeypatch):
    def fake_build_dashboard_payload(**kwargs):
        raise qgate_api_service.qgate.QGateDashboardDataError("QGate summary data has not been built")

    monkeypatch.setattr(qgate_api_service, "build_dashboard_payload", fake_build_dashboard_payload)

    with pytest.raises(Exception, match="QGate summary data has not been built"):
        qgate_api_service.get_qgate_dashboard_payload(teams=["Plant-Dadong FIT"])


def test_qgate_dashboard_endpoint_returns_422_when_summary_missing(monkeypatch):
    def fake_get_qgate_dashboard_payload(**kwargs):
        raise QGateDashboardDataError("QGate summary data has not been built")

    monkeypatch.setattr(qgate_api, "get_qgate_dashboard_payload", fake_get_qgate_dashboard_payload)
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/kpi-dashboard", params={"teams": ["Plant-Dadong FIT"]})

    assert response.status_code == 422
    assert response.json()["detail"] == "QGate summary data has not been built"
```

- [ ] **Step 2: Run the service and API tests to verify the new cases fail correctly**

Run: `pytest tests/test_qgate_api.py -k "summary_missing or qgate_dashboard_service" -v`

Expected: FAIL because the new summary-missing path is not yet asserted or not surfaced cleanly.

- [ ] **Step 3: Update the service layer to keep the current filter surface while relying on summary-backed payloads**

```python
# qgate_api_service.py
def get_qgate_dashboard_payload(**kwargs: Any) -> dict:
    query = normalize_query(**kwargs)
    with _temporary_qgate_source(DEFAULT_QGATE_DB_PATH):
        payload = build_dashboard_payload(
            defect_dir=query.defect_dir,
            history_dir=query.history_dir,
            teams=list(query.teams),
            min_transition_count=query.min_transition_count,
            analysis_workers=query.analysis_workers,
            cache_dir=query.cache_dir,
            use_cache=query.use_cache,
            show_progress=False,
        )
    return filter_dashboard_payload(
        payload,
        teams=query.teams,
        years=query.years,
        groups=query.groups,
        changed_by=query.changed_by,
        fif=query.fif,
        timespan_min=query.timespan_min,
        timespan_max=query.timespan_max,
    )
```

- [ ] **Step 4: Re-run the API tests and make them pass**

Run: `pytest tests/test_qgate_api.py -v`

Expected: PASS with `422` for summary-missing and unchanged filter forwarding coverage.

- [ ] **Step 5: Commit the service-layer integration**

```bash
git add qgate_api_service.py qgate_api.py tests/test_qgate_api.py
git commit -m "feat: surface qgate summary errors through api"
```

## Task 4: Add Refresh CLI And Verify End-To-End Summary Build

**Files:**
- Modify: `qgate_summary_store.py`
- Modify: `tests/test_qgate_summary_store.py`

- [ ] **Step 1: Write a failing CLI test for full-refresh execution**

```python
def test_qgate_summary_store_main_refreshes_selected_teams(tmp_path, monkeypatch, capsys):
    from qgate_summary_store import main

    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE octane_defects (defect_id TEXT PRIMARY KEY, year INTEGER, team TEXT, problem_finder_team TEXT, raw_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE octane_defect_histories (defect_id TEXT PRIMARY KEY, team TEXT NOT NULL, total_count INTEGER, payload_json TEXT NOT NULL, fetched_at TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    main(["--db-path", str(db_path), "--teams", "Plant-Dadong FIT"])
    out = capsys.readouterr().out

    assert "ticket_scope" in out
    assert "issue_transitions" in out
```

- [ ] **Step 2: Run the CLI test and verify it fails before the entrypoint exists**

Run: `pytest tests/test_qgate_summary_store.py -k main_refreshes_selected_teams -v`

Expected: FAIL with missing `main` or CLI parsing errors.

- [ ] **Step 3: Add a minimal CLI entrypoint for full refresh and team scoping**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build QGate summary-serving tables")
    parser.add_argument("--db-path", default=os.path.join("qgate", "qgate_data.db"))
    parser.add_argument("--teams", default="")
    args = parser.parse_args(argv)

    teams = [item.strip() for item in str(args.teams).split(",") if item.strip()]
    result = refresh_qgate_summary_tables(db_path=args.db_path, teams=teams or None)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Re-run the summary-store tests and make the CLI case pass**

Run: `pytest tests/test_qgate_summary_store.py -v`

Expected: PASS with schema, refresh, and CLI cases all green.

- [ ] **Step 5: Commit the refresh CLI**

```bash
git add qgate_summary_store.py tests/test_qgate_summary_store.py
git commit -m "feat: add qgate summary refresh cli"
```

## Task 5: Validate Full Integration Against The Current Baseline

**Files:**
- Modify: `tests/test_qgate_kpi_payload.py`
- Modify: `tests/test_qgate_api.py`

- [ ] **Step 1: Add an integration-style regression test that proves summary mode preserves payload families and filtering**

```python
def test_summary_backed_payload_preserves_filter_surface(tmp_path, monkeypatch):
    module = _load_module()
    db_path = tmp_path / "qgate.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE qgate_kpi_ticket_scope (team TEXT, ticket_id TEXT, year TEXT, ticket_name TEXT, tester TEXT, ticket_url TEXT, has_history INTEGER, history_parse_ok INTEGER, source_history_hash TEXT, refreshed_at TEXT, PRIMARY KEY(team, ticket_id))"
        )
        conn.execute(
            "CREATE TABLE qgate_kpi_issue_transitions (team TEXT, ticket_id TEXT, year TEXT, ticket_name TEXT, tester TEXT, ticket_url TEXT, phase_transition TEXT, group_name TEXT, changed_by TEXT, fif TEXT, duration_hours REAL, duration_days REAL, ticket_timespan_days REAL, start_time TEXT, end_time TEXT, source_history_hash TEXT, source_team TEXT, refreshed_at TEXT, PRIMARY KEY(team, ticket_id, phase_transition, start_time, end_time))"
        )
        conn.executemany(
            "INSERT INTO qgate_kpi_ticket_scope VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("Plant-Dadong FIT", "1001", "2026", "Ticket 1001", "Alice", "https://octane/1001", 1, 1, "hash-1", "2026-05-21T00:00:00Z"),
                ("Plant-Dadong FIT", "1002", "2025", "Ticket 1002", "Bob", "https://octane/1002", 1, 1, "hash-2", "2026-05-21T00:00:00Z"),
            ],
        )
        conn.executemany(
            "INSERT INTO qgate_kpi_issue_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("Plant-Dadong FIT", "1001", "2026", "Ticket 1001", "Alice", "https://octane/1001", "02-QGate -> 03-Analysis", "Q-Gate", "Alice", "Global", 24.0, 1.0, 2.0, "2026-03-01T08:00:00Z", "2026-03-02T08:00:00Z", "hash-1", "Plant-Dadong FIT", "2026-05-21T00:00:00Z"),
                ("Plant-Dadong FIT", "1002", "2025", "Ticket 1002", "Bob", "https://octane/1002", "09-Integration -> 01-Open", "Integration", "Bob", "China Specific", 72.0, 3.0, 5.0, "2025-01-01T08:00:00Z", "2025-01-04T08:00:00Z", "hash-2", "Plant-Dadong FIT", "2026-05-21T00:00:00Z"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("QGATE_DB_PATH", str(db_path))
    monkeypatch.setenv("OCTANE_DATA_SOURCE", "db_only")

    payload = qgate_api_service.get_qgate_dashboard_payload(
        teams=["Plant-Dadong FIT"],
        years=["2026"],
        groups=["Q-Gate"],
        changed_by=["Alice"],
        fif=["Global"],
        timespan_min=0,
        timespan_max=3,
        min_transition_count=1,
        use_cache=True,
    )

    assert payload["overview"]["total_defects"] == 1
    assert payload["issues"]["rows"] == [["2026", "Plant-Dadong FIT", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24.0, "Alice", "Global", 2.0]]
```

- [ ] **Step 2: Run the focused integration tests and verify they fail before the wiring is complete**

Run: `pytest tests/test_qgate_kpi_payload.py tests/test_qgate_api.py -k "summary_backed_payload_preserves_filter_surface or summary_missing" -v`

Expected: FAIL if any payload family, filtering rule, or `422` error mapping is still inconsistent.

- [ ] **Step 3: Reconcile remaining naming or shape mismatches without changing the frontend contract**

```python
# report/generate_qgate_kpi_dashboard.py
issue_columns = [
    "Year",
    "Team",
    "Ticket_ID",
    "Phase_Transition",
    "Group",
    "Duration_Hours",
    "Changed_By",
    "FiF",
    "Ticket_Timespan_Days",
]

ticket_columns = ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"]

payload = {
    "generated_from": generated_from,
    "overview": overview,
    "insights": insights,
    "options": {
        "teams": meta_df["Team"].dropna().astype(str).tolist() if not meta_df.empty else [],
        "years": years,
        "groups": groups,
        "changedBy": changed_by,
        "fif": fif_values,
        "timespanMax": overview["timespan_max"],
    },
    "meta": sanitize_dataset(meta_df, meta_columns),
    "coverage": sanitize_dataset(coverage_df, coverage_columns),
    "tickets": sanitize_dataset(tickets_df, ticket_columns),
    "issues": sanitize_dataset(issues_df, issue_columns),
}
```

- [ ] **Step 4: Run the complete QGate test set and the real two-team timing check**

Run: `pytest tests/test_qgate_summary_store.py tests/test_qgate_kpi_payload.py tests/test_qgate_api.py -v`

Expected: PASS.

Run: `@'
import time
from qgate_api_service import get_qgate_dashboard_payload

t = time.perf_counter()
payload = get_qgate_dashboard_payload(
    teams=['Plant-Dadong FIT', 'Plant-Tiexi FIT'],
    min_transition_count=1,
    use_cache=True,
)
elapsed = time.perf_counter() - t
print({'elapsed_seconds': round(elapsed, 3), 'overview': payload['overview']})
'@ | .\.venv\Scripts\python.exe -`

Expected: PASS and materially lower elapsed time than the 144.584 second baseline.

- [ ] **Step 5: Commit the final summary-serving integration**

```bash
git add qgate_summary_store.py report/generate_qgate_kpi_dashboard.py qgate_api_service.py qgate_api.py tests/test_qgate_summary_store.py tests/test_qgate_kpi_payload.py tests/test_qgate_api.py
git commit -m "feat: switch qgate dashboard to summary serving"
```

## Self-Review

- Spec coverage check: schema, full refresh, payload generation, API error behavior, and validation are all covered by Tasks 1 through 5.
- Placeholder scan: no unfinished markers remain in the task steps.
- Type consistency check: the plan uses `qgate_kpi_ticket_scope`, `qgate_kpi_issue_transitions`, `ensure_qgate_summary_tables`, `refresh_qgate_summary_tables`, and `load_summary_data` consistently across tasks.