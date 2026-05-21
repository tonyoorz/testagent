from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
import re
import sqlite3
from urllib.parse import quote


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_DEFECT_DB_CANDIDATES = (
    REPOSITORY_ROOT / "qgate" / "qgate_data.db",
    REPOSITORY_ROOT / "database" / "local_data_rebuilt.db",
)
DEFAULT_HISTORY_DB_CANDIDATES = (REPOSITORY_ROOT / "qgate" / "qgate_data.db",)
REQUIRED_DEFECT_COLUMNS = frozenset(
    {
        "defect_id",
        "name",
        "status_phase",
        "problem_finder_team",
        "year",
        "assigned_ecu",
        "top_aida",
        "aida_english",
        "aida_businesskey",
        "phase",
        "solution_cluster",
        "lead_model",
    }
)
REQUIRED_HISTORY_EVENT_COLUMNS = frozenset(
    {
        "defect_id",
        "field_name",
        "event_timestamp",
        "entry_index",
        "change_index",
        "old_value",
        "new_value",
        "old_value_text",
        "new_value_text",
    }
)
DEFAULT_YEARS = ("2026",)
GROUP_ORDER = ("Q-Gate", "Integration", "CoC", "Other")
OUTCOME_SERIES = (
    ("resolved_forward", "Resolved Forward (08 -> 06)", "is_resolved_forward"),
    ("rejected_directly", "Rejected Directly (01 -> 09)", "is_rejected_directly"),
)


class FullPictureDashboardDataError(ValueError):
    pass


@dataclass(frozen=True)
class FullPictureDashboardQuery:
    years: tuple[str, ...] = DEFAULT_YEARS
    projects: tuple[str, ...] = ()
    assigned_ecus: tuple[str, ...] = ()
    problem_finder_teams: tuple[str, ...] = ()
    aidas: tuple[str, ...] = ()
    phases: tuple[str, ...] = ()
    solution_clusters: tuple[str, ...] = ()
    pus: tuple[str, ...] = ()
    markets: tuple[str, ...] = ()
    lead_models: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


def _normalize_multi_value(raw_value: Any) -> tuple[str, ...]:
    if raw_value is None:
        return ()

    if isinstance(raw_value, str):
        raw_items: Iterable[Any] = raw_value.split(",")
    else:
        raw_items = raw_value

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        parts = item.split(",") if isinstance(item, str) else [item]
        for part in parts:
            value = str(part).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
    return tuple(normalized)


def normalize_query(**kwargs: Any) -> FullPictureDashboardQuery:
    years = _normalize_multi_value(kwargs.get("years")) or DEFAULT_YEARS
    return FullPictureDashboardQuery(
        years=years,
        projects=_normalize_multi_value(kwargs.get("projects")),
        assigned_ecus=_normalize_multi_value(kwargs.get("assigned_ecus")),
        problem_finder_teams=_normalize_multi_value(kwargs.get("problem_finder_teams")),
        aidas=_normalize_multi_value(kwargs.get("aidas")),
        phases=_normalize_multi_value(kwargs.get("phases")),
        solution_clusters=_normalize_multi_value(kwargs.get("solution_clusters")),
        pus=_normalize_multi_value(kwargs.get("pus")),
        markets=_normalize_multi_value(kwargs.get("markets")),
        lead_models=_normalize_multi_value(kwargs.get("lead_models")),
        groups=_normalize_multi_value(kwargs.get("groups")),
    )


def classify_phase_transition_group(phase_transition: str) -> str:
    from_part, to_part = phase_transition, ""
    if "->" in phase_transition:
        from_part, to_part = phase_transition.split("->", 1)
    elif "→" in phase_transition:
        from_part, to_part = phase_transition.split("→", 1)

    return classify_phase_group(from_part)


def classify_phase_group(phase_value: Any) -> str:
    phase_code = _extract_phase_code(phase_value)
    if not phase_code:
        return "Other"
    if phase_code in {"02", "07"}:
        return "Q-Gate"
    if phase_code in {"00", "01", "06", "08", "09"}:
        return "Integration"
    if phase_code in {"03", "04", "05"}:
        return "CoC"
    return "Other"


def _extract_phase_code(raw_value: Any) -> str | None:
    text = str(raw_value or "").strip()
    if not text:
        return None

    patterns = (
        r"^(\d{2})(?=[^0-9]|$)",
        r"\bphase[_\s-]?(\d{2})\b",
        r"(\d{2})(?=-)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    if text.isdigit() and len(text) == 2:
        return text
    return None


def _open_sqlite_readonly(db_path: Path) -> sqlite3.Connection:
    normalized_path = str(db_path.resolve()).replace("\\", "/")
    uri = f"file:{quote(normalized_path, safe='/:')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.DatabaseError:
        pass
    return conn


@lru_cache(maxsize=8)
def _resolve_defect_db_path() -> Path | None:
    return _resolve_db_path(
        DEFAULT_DEFECT_DB_CANDIDATES,
        "octane_defects",
        REQUIRED_DEFECT_COLUMNS,
    )


@lru_cache(maxsize=8)
def _resolve_history_db_path() -> Path | None:
    return _resolve_db_path(
        DEFAULT_HISTORY_DB_CANDIDATES,
        "octane_defect_history_events",
        REQUIRED_HISTORY_EVENT_COLUMNS,
    )


def _resolve_db_path(
    candidates: tuple[Path, ...],
    table_name: str,
    required_columns: Iterable[str] = (),
) -> Path | None:
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            with _open_sqlite_readonly(candidate) as conn:
                if _table_has_required_columns(conn, table_name, required_columns):
                    return candidate
        except sqlite3.DatabaseError:
            continue
    return None


def _table_has_required_columns(
    conn: sqlite3.Connection,
    table_name: str,
    required_columns: Iterable[str],
) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if not row:
        return False

    required = {str(column).strip().lower() for column in required_columns if str(column).strip()}
    if not required:
        return True

    available = {
        str(column["name"]).strip().lower()
        for column in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    }
    return required.issubset(available)


@lru_cache(maxsize=16)
def _get_table_columns(db_path: Path, table_name: str) -> tuple[str, ...]:
    try:
        with _open_sqlite_readonly(db_path) as conn:
            return tuple(
                str(column["name"]).strip()
                for column in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            )
    except sqlite3.DatabaseError as exc:
        _raise_database_error(f"inspecting {table_name} columns", db_path, exc)


def _raise_database_error(operation: str, db_path: Path, exc: sqlite3.DatabaseError) -> None:
    raise FullPictureDashboardDataError(
        f"Full Picture database error while {operation} from {db_path}: {exc}"
    ) from exc


def _require_database_path(db_path: Path | None, database_kind: str) -> Path:
    if db_path is None:
        raise FullPictureDashboardDataError(f"Full Picture {database_kind} database is not available")
    return db_path


def _load_defect_rows(query: FullPictureDashboardQuery) -> list[dict[str, Any]]:
    db_path = _require_database_path(_resolve_defect_db_path(), "defect")
    available_columns = set(_get_table_columns(db_path, "octane_defects"))

    def optional_text_expr(column_name: str, *, cast_text: bool = False) -> str:
        if column_name not in available_columns:
            return "''"
        if cast_text:
            return f"COALESCE(CAST({column_name} AS TEXT), '')"
        return f"COALESCE({column_name}, '')"

    aida_sources = [
        f"NULLIF({column_name}, '')"
        for column_name in ("top_aida", "aida_english", "aida_businesskey")
        if column_name in available_columns
    ]
    aida_expr = f"COALESCE({', '.join(aida_sources)}, '')" if aida_sources else "''"

    where_clauses = ["1=1"]
    params: list[Any] = []
    for expression, values in (
        (optional_text_expr("year", cast_text=True), query.years),
        (optional_text_expr("project"), query.projects),
        (optional_text_expr("assigned_ecu"), query.assigned_ecus),
        (optional_text_expr("problem_finder_team"), query.problem_finder_teams),
        (aida_expr, query.aidas),
        (optional_text_expr("phase"), query.phases),
        (optional_text_expr("solution_cluster"), query.solution_clusters),
        (optional_text_expr("pu"), query.pus),
        (optional_text_expr("market"), query.markets),
        (optional_text_expr("lead_model"), query.lead_models),
    ):
        if not values:
            continue
        placeholders = ", ".join("?" for _ in values)
        where_clauses.append(f"{expression} IN ({placeholders})")
        params.extend(values)

    sql = f"""
        SELECT
            CAST(defect_id AS TEXT) AS ticket_id,
            {optional_text_expr('name')} AS ticket_name,
            {optional_text_expr('status_phase')} AS status,
            {optional_text_expr('problem_finder_team')} AS problem_finder_team,
            {optional_text_expr('year', cast_text=True)} AS year,
            {optional_text_expr('project')} AS project,
            {optional_text_expr('assigned_ecu')} AS assigned_ecu,
            {aida_expr} AS aida,
            {optional_text_expr('phase')} AS phase,
            {optional_text_expr('solution_cluster')} AS solution_cluster,
            {optional_text_expr('pu')} AS pu,
            {optional_text_expr('market')} AS market,
            {optional_text_expr('lead_model')} AS lead_model
        FROM octane_defects
        WHERE {' AND '.join(where_clauses)}
        ORDER BY CAST(year AS TEXT), CAST(defect_id AS TEXT)
    """

    try:
        with _open_sqlite_readonly(db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.DatabaseError as exc:
        _raise_database_error("loading defect rows", db_path, exc)
    return [dict(row) for row in rows]


def _load_history_events(defect_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    if not defect_ids:
        return []

    db_path = _require_database_path(_resolve_history_db_path(), "history")

    rows: list[dict[str, Any]] = []
    try:
        with _open_sqlite_readonly(db_path) as conn:
            for start in range(0, len(defect_ids), 500):
                chunk = defect_ids[start : start + 500]
                placeholders = ", ".join("?" for _ in chunk)
                sql = f"""
                    SELECT
                        CAST(defect_id AS TEXT) AS ticket_id,
                        COALESCE(event_timestamp, '') AS event_timestamp,
                        COALESCE(entry_index, 0) AS entry_index,
                        COALESCE(change_index, 0) AS change_index,
                        COALESCE(old_value, '') AS old_value,
                        COALESCE(new_value, '') AS new_value,
                        COALESCE(old_value_text, '') AS old_value_text,
                        COALESCE(new_value_text, '') AS new_value_text
                    FROM octane_defect_history_events
                    WHERE CAST(defect_id AS TEXT) IN ({placeholders})
                      AND LOWER(COALESCE(field_name, '')) LIKE '%phase%'
                """
                rows.extend(dict(row) for row in conn.execute(sql, list(chunk)).fetchall())
    except sqlite3.DatabaseError as exc:
        _raise_database_error("loading defect history", db_path, exc)

    rows.sort(
        key=lambda row: (
            str(row.get("event_timestamp") or ""),
            int(row.get("entry_index") or 0),
            int(row.get("change_index") or 0),
        )
    )
    return rows


def _build_outcome_index(history_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in history_rows:
        ticket_id = str(row.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        state = indexed.setdefault(ticket_id, _empty_outcome_state())
        old_code = _extract_phase_code(row.get("old_value_text")) or _extract_phase_code(row.get("old_value"))
        new_code = _extract_phase_code(row.get("new_value_text")) or _extract_phase_code(row.get("new_value"))

        if old_code == "08" and new_code == "06":
            state["is_resolved_forward"] = True
        elif old_code == "01" and new_code == "09":
            state["is_rejected_directly"] = True
    return indexed


def _empty_outcome_state() -> dict[str, bool]:
    return {
        "is_resolved_forward": False,
        "is_rejected_directly": False,
    }


def _build_ticket_rows(
    defect_rows: list[dict[str, Any]],
    outcome_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ticket_rows: list[dict[str, Any]] = []
    for row in defect_rows:
        ticket_id = str(row.get("ticket_id") or "").strip()
        if not ticket_id:
            continue
        phase = str(row.get("phase") or "").strip()
        group = classify_phase_group(phase)
        outcome_state = outcome_index.get(ticket_id, _empty_outcome_state())
        is_resolved_forward = bool(outcome_state["is_resolved_forward"])
        is_rejected_directly = bool(outcome_state["is_rejected_directly"])
        ticket_rows.append(
            {
                "ticket_id": ticket_id,
                "ticket_name": str(row.get("ticket_name") or "").strip(),
                "status": str(row.get("status") or row.get("phase") or "").strip(),
                "problem_finder_team": str(row.get("problem_finder_team") or "").strip(),
                "group": group,
                "phase": phase,
                "is_resolved_forward": is_resolved_forward,
                "is_rejected_directly": is_rejected_directly,
                "year": str(row.get("year") or "").strip(),
                "project": str(row.get("project") or "").strip(),
                "assigned_ecu": str(row.get("assigned_ecu") or "").strip(),
                "aida": str(row.get("aida") or "").strip(),
                "solution_cluster": str(row.get("solution_cluster") or "").strip(),
                "pu": str(row.get("pu") or "").strip(),
                "market": str(row.get("market") or "").strip(),
                "lead_model": str(row.get("lead_model") or "").strip(),
            }
        )
    ticket_rows.sort(key=lambda row: (_sortable_value(row.get("problem_finder_team")), _sortable_value(row.get("ticket_id"))))
    return ticket_rows


def _apply_group_filter(ticket_rows: list[dict[str, Any]], groups: tuple[str, ...]) -> list[dict[str, Any]]:
    if not groups:
        return ticket_rows
    allowed = set(groups)
    return [row for row in ticket_rows if row.get("group") in allowed]


def _build_filters(ticket_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    filters = {
        "years": _unique_sorted(row.get("year") for row in ticket_rows),
        "projects": _unique_sorted(row.get("project") for row in ticket_rows),
        "assigned_ecus": _unique_sorted(row.get("assigned_ecu") for row in ticket_rows),
        "problem_finder_teams": _unique_sorted(row.get("problem_finder_team") for row in ticket_rows),
        "aidas": _unique_sorted(row.get("aida") for row in ticket_rows),
        "phases": _unique_sorted(row.get("phase") for row in ticket_rows),
        "solution_clusters": _unique_sorted(row.get("solution_cluster") for row in ticket_rows),
        "pus": _unique_sorted(row.get("pu") for row in ticket_rows),
        "markets": _unique_sorted(row.get("market") for row in ticket_rows),
        "lead_models": _unique_sorted(row.get("lead_model") for row in ticket_rows),
        "groups": _unique_sorted((row.get("group") for row in ticket_rows), group_values=True),
    }
    return filters


def _build_overview(ticket_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_tickets = len(ticket_rows)
    resolved_forward_count = _count_ticket_rows(ticket_rows, "is_resolved_forward")
    rejected_directly_count = _count_ticket_rows(ticket_rows, "is_rejected_directly")
    return {
        "ticket_count": total_tickets,
        "resolved_forward_count": resolved_forward_count,
        "rejected_directly_count": rejected_directly_count,
        "resolved_forward_percent": _to_percent(resolved_forward_count, total_tickets),
        "rejected_directly_percent": _to_percent(rejected_directly_count, total_tickets),
    }


def _build_outcome_summary(ticket_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_tickets = len(ticket_rows)
    return [
        {
            "key": key,
            "label": label,
            "count": _count_ticket_rows(ticket_rows, flag_name),
            "percent": _to_percent(_count_ticket_rows(ticket_rows, flag_name), total_tickets),
            "denominator": total_tickets,
        }
        for key, label, flag_name in OUTCOME_SERIES
    ]


def _build_team_outcome_rows(ticket_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, int]] = {}
    for row in ticket_rows:
        team_name = str(row.get("problem_finder_team") or "").strip()
        state = grouped.setdefault(
            team_name,
            {"total": 0, "resolved_forward": 0, "rejected_directly": 0},
        )
        state["total"] += 1
        if row.get("is_resolved_forward"):
            state["resolved_forward"] += 1
        if row.get("is_rejected_directly"):
            state["rejected_directly"] += 1

    team_rows = []
    for team_name, state in grouped.items():
        team_total = state["total"]
        team_rows.append(
            {
                "problem_finder_team": team_name,
                "total_tickets": state["total"],
                "resolved_forward_count": state["resolved_forward"],
                "rejected_directly_count": state["rejected_directly"],
                "resolved_forward_team_percent": _to_percent(state["resolved_forward"], team_total),
                "rejected_directly_team_percent": _to_percent(state["rejected_directly"], team_total),
                "team_denominator": team_total,
            }
        )
    team_rows.sort(key=lambda row: (-int(row["total_tickets"]), _sortable_value(row["problem_finder_team"])))
    return team_rows


def _count_ticket_rows(ticket_rows: list[dict[str, Any]], flag_name: str) -> int:
    return sum(1 for row in ticket_rows if row.get(flag_name))


def _unique_sorted(values: Iterable[Any], *, group_values: bool = False) -> list[str]:
    unique_values = {str(value).strip() for value in values if str(value or "").strip()}
    if group_values:
        order = {group: index for index, group in enumerate(GROUP_ORDER)}
        return sorted(unique_values, key=lambda value: (order.get(value, len(GROUP_ORDER)), _sortable_value(value)))
    return sorted(unique_values, key=_sortable_value)


def _sortable_value(value: Any) -> tuple[int, Any]:
    text = str(value or "").strip()
    if text.isdigit():
        return (0, int(text))
    return (1, text.casefold())


def _to_percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def get_full_picture_dashboard_payload(**kwargs: Any) -> dict[str, Any]:
    query = normalize_query(**kwargs)
    defect_rows = _load_defect_rows(query)
    defect_ids = tuple(str(row.get("ticket_id") or "").strip() for row in defect_rows if str(row.get("ticket_id") or "").strip())
    history_rows = _load_history_events(defect_ids)
    outcome_index = _build_outcome_index(history_rows)
    ticket_rows = _build_ticket_rows(defect_rows, outcome_index)
    ticket_rows = _apply_group_filter(ticket_rows, query.groups)

    return {
        "generated_from": {
            "defect_db_path": str(_resolve_defect_db_path() or ""),
            "history_db_path": str(_resolve_history_db_path() or ""),
            "years": list(query.years),
            "projects": list(query.projects),
            "assigned_ecus": list(query.assigned_ecus),
            "problem_finder_teams": list(query.problem_finder_teams),
            "aidas": list(query.aidas),
            "phases": list(query.phases),
            "solution_clusters": list(query.solution_clusters),
            "pus": list(query.pus),
            "markets": list(query.markets),
            "lead_models": list(query.lead_models),
            "groups": list(query.groups),
        },
        "filters": _build_filters(ticket_rows),
        "overview": _build_overview(ticket_rows),
        "outcome_summary": _build_outcome_summary(ticket_rows),
        "team_outcome_rows": _build_team_outcome_rows(ticket_rows),
        "ticket_rows": ticket_rows,
    }