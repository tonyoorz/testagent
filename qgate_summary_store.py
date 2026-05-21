import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from octane_db import ensure_qgate_summary_tables


_MISSING_PHASE_LABEL = "<missing>"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_object(payload_json: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(payload_json)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _build_octane_work_item_url(ticket_id: str | None) -> str | None:
    tid = _normalize_text(ticket_id)
    if tid is None:
        return None
    octane_base_url = os.environ.get("OCTANE_BASE_URL", "https://octane-prod.bmwgroup.net")
    octane_shared_space = os.environ.get("OCTANE_SHARED_SPACE", "1002")
    octane_workspace = os.environ.get("OCTANE_WORKSPACE", "2001")
    return f"{octane_base_url}/ui/entity-navigation?p={octane_shared_space}/{octane_workspace}&entityType=work_item&id={tid}"


def _parse_iso_timestamp(timestamp: Any) -> datetime | None:
    text = _normalize_text(timestamp)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _phase_prefix(phase_text: Any) -> str | None:
    text = _normalize_text(phase_text) or ""
    match = re.match(r"^(\d{2})-", text)
    return match.group(1) if match else None


def _classify_group(phase_transition: str) -> str:
    from_part, to_part = phase_transition, ""
    if "→" in phase_transition:
        from_part, to_part = phase_transition.split("→", 1)
    elif "->" in phase_transition:
        from_part, to_part = phase_transition.split("->", 1)

    from_prefix = _phase_prefix(from_part)
    to_prefix = _phase_prefix(to_part)

    if from_prefix == "09" and to_prefix == "01":
        return "Integration"
    if from_prefix == "06" and to_prefix == "05":
        return "Integration"
    if not from_prefix:
        return "Other"
    if from_prefix in {"02", "07"}:
        return "Q-Gate"
    if from_prefix in {"00", "01", "08"}:
        return "Integration"
    if from_prefix in {"03", "04", "05"}:
        return "CoC"
    return "Other"


def _resolve_team(team_filters: set[str] | None, team: Any, problem_finder_team: Any) -> str | None:
    problem_finder_team_text = _normalize_text(problem_finder_team)
    candidates = [problem_finder_team_text, _normalize_text(team)]
    if team_filters is None:
        return problem_finder_team_text
    for candidate in candidates:
        if candidate and candidate in team_filters:
            return candidate
    return None


def _resolve_year(year_value: Any, payload: dict[str, Any]) -> str | None:
    text = _normalize_text(year_value)
    if text:
        return text
    creation_time = _normalize_text(payload.get("creation_time"))
    if creation_time and len(creation_time) >= 4:
        return creation_time[:4]
    return None


def _resolve_tester(payload: dict[str, Any]) -> str | None:
    owner_work_item = payload.get("owner_work_item")
    if isinstance(owner_work_item, dict):
        return _normalize_text(owner_work_item.get("name") or owner_work_item.get("full_name"))
    detected_by = payload.get("detected_by")
    if isinstance(detected_by, dict):
        return _normalize_text(detected_by.get("name") or detected_by.get("full_name"))
    return None


def _extract_history_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _extract_change_set(entry: dict[str, Any]) -> list[dict[str, Any]]:
    change_set = entry.get("change_set")
    if isinstance(change_set, dict):
        return [change_set]
    if isinstance(change_set, list):
        return [item for item in change_set if isinstance(item, dict)]
    return []


def _extract_changed_by(entry: dict[str, Any]) -> str:
    user = entry.get("user")
    if isinstance(user, dict):
        changed_by = _normalize_text(user.get("name") or user.get("full_name"))
        if changed_by:
            return changed_by
    return _normalize_text(entry.get("user_name")) or "Unknown"


def _extract_phase_changes(history_payload: dict[str, Any]) -> list[dict[str, str]]:
    phase_changes: list[dict[str, str]] = []
    for entry in _extract_history_entries(history_payload):
        timestamp = _normalize_text(entry.get("timestamp"))
        changed_by = _extract_changed_by(entry)
        for change in _extract_change_set(entry):
            if _normalize_text(change.get("field_name")) != "phase":
                continue
            to_phase = _normalize_text(change.get("value_text") or change.get("valueName") or change.get("new_value"))
            if not to_phase:
                continue
            from_phase = _normalize_text(change.get("old_value_text") or change.get("old_value")) or _MISSING_PHASE_LABEL
            phase_changes.append(
                {
                    "timestamp": timestamp or "",
                    "from_phase": from_phase,
                    "to_phase": to_phase,
                    "changed_by": changed_by,
                }
            )
    phase_changes.sort(key=lambda item: item.get("timestamp") or "")
    return phase_changes


def _extract_ticket_fif(history_payload: dict[str, Any]) -> str | None:
    found_in_functions: set[str] = set()
    phase02_found_in_functions: set[str] = set()

    for entry in _extract_history_entries(history_payload):
        changes = _extract_change_set(entry)
        moved_to_phase02 = False
        for change in changes:
            if _normalize_text(change.get("field_name")) != "phase":
                continue
            to_phase = _normalize_text(change.get("value_text") or change.get("valueName") or change.get("new_value")) or ""
            if to_phase.startswith("02-"):
                moved_to_phase02 = True
                break

        for change in changes:
            if _normalize_text(change.get("field_name")) != "product_areas":
                continue
            field_label = (_normalize_text(change.get("field_label")) or "").lower()
            if field_label and ("found" not in field_label or "function" not in field_label):
                continue
            value = _normalize_text(change.get("value_text") or change.get("valueName") or change.get("new_value"))
            if value is None:
                continue
            found_in_functions.add(value)
            if moved_to_phase02:
                phase02_found_in_functions.add(value)

    items = phase02_found_in_functions or found_in_functions
    if not items:
        return None

    try:
        import qgate as qgate_module

        china_specific_fif = set(getattr(qgate_module, "CHINA_SPECIFIC_FIF", set()))
    except Exception:
        china_specific_fif = set()

    return "China Specific" if items.intersection(china_specific_fif) else "Global"


def _calculate_phase_durations(phase_changes: list[dict[str, str]]) -> list[dict[str, Any]]:
    durations: list[dict[str, Any]] = []
    for index in range(1, len(phase_changes)):
        previous_change = phase_changes[index - 1]
        current_change = phase_changes[index]
        start_dt = _parse_iso_timestamp(previous_change.get("timestamp"))
        end_dt = _parse_iso_timestamp(current_change.get("timestamp"))
        if start_dt is None or end_dt is None:
            continue
        duration_hours = round(max((end_dt - start_dt).total_seconds(), 0) / 3600, 2)
        durations.append(
            {
                "from_phase": _normalize_text(previous_change.get("to_phase")) or _MISSING_PHASE_LABEL,
                "to_phase": _normalize_text(current_change.get("to_phase")) or _MISSING_PHASE_LABEL,
                "duration_hours": duration_hours,
                "duration_days": round(duration_hours / 24, 2),
                "start_time": previous_change.get("timestamp"),
                "end_time": current_change.get("timestamp"),
                "changed_by": _normalize_text(current_change.get("changed_by")) or "Unknown",
            }
        )
    return durations


def _calculate_ticket_timespan_days(durations: list[dict[str, Any]]) -> float | None:
    start_time: datetime | None = None
    end_time: datetime | None = None

    for duration in durations:
        from_prefix = _phase_prefix(duration.get("from_phase"))
        to_prefix = _phase_prefix(duration.get("to_phase"))
        current_start = _parse_iso_timestamp(duration.get("start_time"))
        current_end = _parse_iso_timestamp(duration.get("end_time"))

        if from_prefix in {"00", "01"} and current_start is not None:
            if start_time is None or current_start < start_time:
                start_time = current_start
        if to_prefix in {"06", "09"} and current_end is not None:
            if end_time is None or current_end < end_time:
                end_time = current_end

    if start_time is None or end_time is None:
        return None
    return round((end_time - start_time).total_seconds() / 86400, 2)


def _extract_phase_transitions(
    history_payload: dict[str, Any],
    *,
    team: str,
    ticket_id: str,
    year: str | None,
    ticket_name: str | None,
    tester: str | None,
    ticket_url: str | None,
    source_history_hash: str,
    source_team: str | None,
    refreshed_at: str,
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    phase_changes = _extract_phase_changes(history_payload)
    durations = _calculate_phase_durations(phase_changes)
    ticket_timespan_days = _calculate_ticket_timespan_days(durations)
    fif = _extract_ticket_fif(history_payload)

    for duration in durations:
        transition = f"{duration['from_phase']} -> {duration['to_phase']}"
        rows.append(
            (
                team,
                ticket_id,
                year,
                ticket_name,
                tester,
                ticket_url,
                transition,
                _classify_group(transition),
                duration["changed_by"],
                fif,
                duration["duration_hours"],
                duration["duration_days"],
                ticket_timespan_days,
                duration["start_time"],
                duration["end_time"],
                source_history_hash,
                source_team,
                refreshed_at,
            )
        )
    return rows


def _build_in_clause(values: set[str]) -> tuple[str, tuple[str, ...]]:
    ordered_values = tuple(sorted(values))
    placeholders = ", ".join(["?"] * len(ordered_values))
    return placeholders, ordered_values


def load_summary_data(*, db_path: str, teams: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    team_filters = {team.strip() for team in (teams or []) if str(team).strip()} or None
    conn = sqlite3.connect(db_path)
    try:
        table_rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('qgate_kpi_ticket_scope', 'qgate_kpi_issue_transitions')
            """
        ).fetchall()
        existing_tables = {str(row[0]) for row in table_rows}
        required_tables = {"qgate_kpi_ticket_scope", "qgate_kpi_issue_transitions"}
        missing_tables = sorted(required_tables - existing_tables)
        if missing_tables:
            missing_text = ", ".join(missing_tables)
            raise ValueError(f"QGate summary data has not been built. Missing summary tables: {missing_text}.")

        scope_query = """
            SELECT
                team AS Team,
                ticket_id AS Ticket_ID,
                year AS Year,
                ticket_name AS Ticket_Name,
                tester AS Tester,
                ticket_url AS Ticket_URL,
                has_history AS Has_History,
                history_parse_ok AS History_Parse_OK,
                source_history_hash AS Source_History_Hash,
                refreshed_at AS Refreshed_At
            FROM qgate_kpi_ticket_scope
        """
        transition_query = """
            SELECT
                team AS Team,
                ticket_id AS Ticket_ID,
                year AS Year,
                ticket_name AS Ticket_Name,
                tester AS Tester,
                ticket_url AS Ticket_URL,
                phase_transition AS Phase_Transition,
                group_name AS [Group],
                changed_by AS Changed_By,
                fif AS FiF,
                duration_hours AS Duration_Hours,
                duration_days AS Duration_Days,
                ticket_timespan_days AS Ticket_Timespan_Days,
                start_time AS Start_Time,
                end_time AS End_Time,
                source_history_hash AS Source_History_Hash,
                source_team AS Source_Team,
                refreshed_at AS Refreshed_At
            FROM qgate_kpi_issue_transitions
        """
        params: tuple[str, ...] = ()
        if team_filters is not None:
            placeholders, params = _build_in_clause(team_filters)
            scope_query += f" WHERE team IN ({placeholders})"
            transition_query += f" WHERE team IN ({placeholders})"

        scope_df = pd.read_sql_query(scope_query, conn, params=params)
        transitions_df = pd.read_sql_query(transition_query, conn, params=params)
    finally:
        conn.close()

    for column in ["Has_History", "History_Parse_OK"]:
        if column in scope_df.columns:
            scope_df[column] = pd.to_numeric(scope_df[column], errors="coerce").fillna(0).astype(int)
    for column in ["Team", "Ticket_ID", "Year", "Ticket_Name", "Tester", "Ticket_URL", "Source_History_Hash", "Refreshed_At"]:
        if column in scope_df.columns:
            scope_df[column] = scope_df[column].fillna("").astype(str)
    for column in ["Duration_Hours", "Duration_Days", "Ticket_Timespan_Days"]:
        if column in transitions_df.columns:
            transitions_df[column] = pd.to_numeric(transitions_df[column], errors="coerce")
    for column in [
        "Team",
        "Ticket_ID",
        "Year",
        "Ticket_Name",
        "Tester",
        "Ticket_URL",
        "Phase_Transition",
        "Group",
        "Changed_By",
        "FiF",
        "Start_Time",
        "End_Time",
        "Source_History_Hash",
        "Source_Team",
        "Refreshed_At",
    ]:
        if column in transitions_df.columns:
            transitions_df[column] = transitions_df[column].fillna("").astype(str)

    return scope_df, transitions_df


def _iter_defect_rows(conn: sqlite3.Connection, team_filters: set[str] | None):
    if team_filters is None:
        cursor = conn.execute(
            """
            SELECT defect_id, year, team, problem_finder_team, raw_json
            FROM octane_defects
            ORDER BY defect_id
            """
        )
    else:
        placeholders, params = _build_in_clause(team_filters)
        cursor = conn.execute(
            f"""
            SELECT defect_id, year, team, problem_finder_team, raw_json
            FROM octane_defects
            WHERE team IN ({placeholders}) OR problem_finder_team IN ({placeholders})
            ORDER BY defect_id
            """,
            params + params,
        )
    yield from cursor


def _load_history_by_defect(
    conn: sqlite3.Connection, team_filters: set[str] | None
) -> dict[str, tuple[Any, ...]]:
    history_by_defect: dict[str, tuple[Any, ...]] = {}
    if team_filters is None:
        cursor = conn.execute(
            """
            SELECT defect_id, team, payload_json, fetched_at
            FROM octane_defect_histories
            """
        )
    else:
        placeholders, params = _build_in_clause(team_filters)
        cursor = conn.execute(
            f"""
            SELECT defect_id, team, payload_json, fetched_at
            FROM octane_defect_histories
            WHERE team IN ({placeholders})
               OR defect_id IN (
                    SELECT defect_id
                    FROM octane_defects
                    WHERE team IN ({placeholders}) OR problem_finder_team IN ({placeholders})
               )
            """,
            params + params + params,
        )

    for defect_id, team, payload_json, fetched_at in cursor:
        history_by_defect[str(defect_id)] = (team, payload_json, fetched_at)
    return history_by_defect


def refresh_qgate_summary_tables(*, db_path: str, teams: list[str] | None = None) -> dict[str, int]:
    team_filters = {team.strip() for team in (teams or []) if str(team).strip()} or None
    refreshed_at = _utc_now_iso()
    conn = sqlite3.connect(db_path)
    try:
        ensure_qgate_summary_tables(conn)

        history_by_defect = _load_history_by_defect(conn, team_filters)

        scope_rows: list[tuple[Any, ...]] = []
        transition_rows: list[tuple[Any, ...]] = []
        source_row_counts: dict[str, int] = {}
        valid_scope_row_counts: dict[str, int] = {}

        for defect_id, year_value, team_value, problem_finder_team, raw_json in _iter_defect_rows(conn, team_filters):
            summary_team = _resolve_team(team_filters, team_value, problem_finder_team)
            if summary_team is None:
                continue

            source_row_counts[summary_team] = source_row_counts.get(summary_team, 0) + 1

            defect_payload = _parse_json_object(raw_json or "")
            if defect_payload is None:
                continue

            ticket_id = _normalize_text(defect_payload.get("id") or defect_id)
            if ticket_id is None:
                continue

            valid_scope_row_counts[summary_team] = valid_scope_row_counts.get(summary_team, 0) + 1

            year_text = _resolve_year(year_value, defect_payload)
            ticket_name = _normalize_text(defect_payload.get("name"))
            tester = _resolve_tester(defect_payload)
            ticket_url = _build_octane_work_item_url(ticket_id)

            history_row = history_by_defect.get(str(defect_id))
            has_history = 1 if history_row else 0
            history_parse_ok = 0
            source_history_hash = None

            if history_row:
                source_team = _normalize_text(history_row[0])
                history_payload_json = history_row[1] or ""
                history_payload = _parse_json_object(history_payload_json)
                if history_payload is not None:
                    history_parse_ok = 1
                    source_history_hash = hashlib.sha1(history_payload_json.encode("utf-8")).hexdigest()
                    transition_rows.extend(
                        _extract_phase_transitions(
                            history_payload,
                            team=summary_team,
                            ticket_id=ticket_id,
                            year=year_text,
                            ticket_name=ticket_name,
                            tester=tester,
                            ticket_url=ticket_url,
                            source_history_hash=source_history_hash,
                            source_team=source_team,
                            refreshed_at=refreshed_at,
                        )
                    )

            scope_rows.append(
                (
                    summary_team,
                    ticket_id,
                    year_text,
                    ticket_name,
                    tester,
                    ticket_url,
                    has_history,
                    history_parse_ok,
                    source_history_hash,
                    refreshed_at,
                )
            )

        with conn:
            if team_filters is None:
                conn.execute("DELETE FROM qgate_kpi_issue_transitions")
                conn.execute("DELETE FROM qgate_kpi_ticket_scope")
            else:
                teams_to_replace = sorted(
                    team
                    for team in team_filters
                    if source_row_counts.get(team, 0) == 0 or valid_scope_row_counts.get(team, 0) > 0
                )
                if teams_to_replace:
                    conn.executemany(
                        "DELETE FROM qgate_kpi_issue_transitions WHERE team = ?",
                        [(team,) for team in teams_to_replace],
                    )
                    conn.executemany(
                        "DELETE FROM qgate_kpi_ticket_scope WHERE team = ?",
                        [(team,) for team in teams_to_replace],
                    )

            if scope_rows:
                conn.executemany(
                    """
                    INSERT INTO qgate_kpi_ticket_scope(
                        team, ticket_id, year, ticket_name, tester, ticket_url,
                        has_history, history_parse_ok, source_history_hash, refreshed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    scope_rows,
                )
            if transition_rows:
                conn.executemany(
                    """
                    INSERT INTO qgate_kpi_issue_transitions(
                        team, ticket_id, year, ticket_name, tester, ticket_url,
                        phase_transition, group_name, changed_by, fif,
                        duration_hours, duration_days, ticket_timespan_days,
                        start_time, end_time, source_history_hash, source_team, refreshed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    transition_rows,
                )

        return {
            "ticket_scope_rows": len(scope_rows),
            "transition_rows": len(transition_rows),
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build QGate summary-serving tables")
    parser.add_argument("--db-path", default=os.path.join("qgate", "qgate_data.db"))
    parser.add_argument("--teams", default="")
    args = parser.parse_args(argv)

    teams = [item.strip() for item in str(args.teams).split(",") if item.strip()]
    result = refresh_qgate_summary_tables(db_path=str(args.db_path), teams=teams or None)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())