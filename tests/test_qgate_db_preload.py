import json
import sqlite3

import pandas as pd

import data_processor
import qgate


def test_history_cache_preload_histories_reads_from_db_only(tmp_path, monkeypatch):
    db_path = tmp_path / "qgate_data.db"
    conn = sqlite3.connect(db_path)
    try:
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
        payload = {
            "data": [
                {
                    "timestamp": "2026-03-01T08:00:00Z",
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
        conn.execute(
            "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
            ("1001", "Plant-Dadong FIT", 1, json.dumps(payload), "2026-03-01T08:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("OCTANE_DATA_SOURCE", "db_only")
    monkeypatch.setenv("OCTANE_DB_PATH", str(db_path))
    data_processor.history_cache.clear()

    data_processor.history_cache.preload_histories(["1001"], history_dir=str(tmp_path / "missing"), max_workers=1)

    cached = data_processor.history_cache.get("1001")
    assert cached == payload


def test_build_team_statistics_preloads_history_cache(monkeypatch):
    preload_calls = {}

    monkeypatch.setattr(qgate.os, "cpu_count", lambda: 4)

    monkeypatch.setattr(
        qgate,
        "load_defect_info_for_team",
        lambda defect_dir, team: {"1001": {"name": "Ticket 1001", "tester": "Alice"}},
    )

    def fake_preload_histories(defect_ids, history_dir="history", max_workers=10):
        preload_calls["defect_ids"] = list(defect_ids)
        preload_calls["history_dir"] = history_dir
        preload_calls["max_workers"] = max_workers

    monkeypatch.setattr(data_processor.history_cache, "preload_histories", fake_preload_histories)

    monkeypatch.setattr(
        qgate.lra,
        "bulk_analyze_phases",
        lambda *args, **kwargs: {
            "phase_duration_records": {},
            "ticket_meta": {},
            "successful_count": 0,
            "failed_count": 0,
        },
    )

    df, issues_df, ok, bad = qgate.build_team_statistics(
        "Plant-Dadong FIT",
        {"1001", "1002"},
        "__missing_history__",
        show_progress=False,
        analysis_workers=0,
        cache_dir=None,
        use_cache=True,
        defect_info={"1001": {"name": "Ticket 1001", "tester": "Alice"}},
    )

    assert preload_calls == {
        "defect_ids": ["1001", "1002"],
        "history_dir": "__missing_history__",
        "max_workers": 8,
    }
    assert isinstance(df, pd.DataFrame)
    assert isinstance(issues_df, pd.DataFrame)
    assert ok == 0
    assert bad == 0