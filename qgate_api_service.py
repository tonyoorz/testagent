from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from contextlib import contextmanager
import os
from typing import Any, Iterable

import qgate

from report.generate_qgate_kpi_dashboard import (
    build_dashboard_payload,
    filter_dashboard_payload,
)


DEFAULT_DEFECT_DIR = "qgate/defect"
DEFAULT_HISTORY_DIR = "qgate/history"
DEFAULT_CACHE_DIR = "qgate_cache"
DEFAULT_QGATE_DB_PATH = os.path.join("qgate", "qgate_data.db")
DEFAULT_TEAMS = tuple(getattr(qgate, "DEFAULT_TEAMS", ["DTSV_China"]))


def _current_qgate_db_path() -> str:
    return os.environ.get("QGATE_DB_PATH") or DEFAULT_QGATE_DB_PATH


@dataclass(frozen=True)
class QGateDashboardQuery:
    defect_dir: str = DEFAULT_DEFECT_DIR
    history_dir: str = DEFAULT_HISTORY_DIR
    teams: tuple[str, ...] = DEFAULT_TEAMS
    years: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    changed_by: tuple[str, ...] = ()
    fif: tuple[str, ...] = ()
    timespan_min: float = 0.0
    timespan_max: float | None = None
    min_transition_count: int = 200
    analysis_workers: int = 0
    cache_dir: str | None = DEFAULT_CACHE_DIR
    use_cache: bool = True


@contextmanager
def _temporary_qgate_source(db_path: str):
    original_source = os.environ.get("OCTANE_DATA_SOURCE")
    original_db_path = os.environ.get("OCTANE_DB_PATH")
    original_qgate_db_path = os.environ.get("QGATE_DB_PATH")

    os.environ["OCTANE_DATA_SOURCE"] = "db_only"
    os.environ["OCTANE_DB_PATH"] = db_path
    os.environ["QGATE_DB_PATH"] = db_path
    try:
        yield
    finally:
        if original_source is None:
            os.environ.pop("OCTANE_DATA_SOURCE", None)
        else:
            os.environ["OCTANE_DATA_SOURCE"] = original_source

        if original_db_path is None:
            os.environ.pop("OCTANE_DB_PATH", None)
        else:
            os.environ["OCTANE_DB_PATH"] = original_db_path

        if original_qgate_db_path is None:
            os.environ.pop("QGATE_DB_PATH", None)
        else:
            os.environ["QGATE_DB_PATH"] = original_qgate_db_path


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


def _coerce_int(raw_value: Any, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _coerce_float(raw_value: Any, default: float, *, minimum: float | None = None) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _coerce_optional_float(raw_value: Any, *, minimum: float | None = None) -> float | None:
    if raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if minimum is not None:
        value = max(minimum, value)
    return value


def _coerce_bool(raw_value: Any, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    value = str(raw_value).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_query(**kwargs: Any) -> QGateDashboardQuery:
    teams = _normalize_multi_value(kwargs.get("teams")) or DEFAULT_TEAMS
    timespan_min = _coerce_float(kwargs.get("timespan_min"), 0.0, minimum=0.0)
    timespan_max = _coerce_optional_float(kwargs.get("timespan_max"), minimum=0.0)
    if timespan_max is not None and timespan_max < timespan_min:
        timespan_max = timespan_min

    use_cache = _coerce_bool(kwargs.get("use_cache"), True)
    cache_dir = kwargs.get("cache_dir", DEFAULT_CACHE_DIR)
    if cache_dir == "":
        cache_dir = None
    if not use_cache:
        cache_dir = None

    return QGateDashboardQuery(
        defect_dir=str(kwargs.get("defect_dir") or DEFAULT_DEFECT_DIR),
        history_dir=str(kwargs.get("history_dir") or DEFAULT_HISTORY_DIR),
        teams=teams,
        years=_normalize_multi_value(kwargs.get("years")),
        groups=_normalize_multi_value(kwargs.get("groups")),
        changed_by=_normalize_multi_value(kwargs.get("changed_by")),
        fif=_normalize_multi_value(kwargs.get("fif")),
        timespan_min=timespan_min,
        timespan_max=timespan_max,
        min_transition_count=_coerce_int(kwargs.get("min_transition_count"), 200, minimum=1),
        analysis_workers=_coerce_int(kwargs.get("analysis_workers"), 0, minimum=0),
        cache_dir=None if cache_dir is None else str(cache_dir),
        use_cache=use_cache,
    )


@lru_cache(maxsize=16)
def _build_dashboard_payload_cached(
    defect_dir: str,
    history_dir: str,
    teams: tuple[str, ...],
    min_transition_count: int,
    analysis_workers: int,
    cache_dir: str | None,
    use_cache: bool,
) -> dict:
    return build_dashboard_payload(
        defect_dir=defect_dir,
        history_dir=history_dir,
        teams=list(teams),
        min_transition_count=min_transition_count,
        analysis_workers=analysis_workers,
        cache_dir=cache_dir,
        use_cache=use_cache,
        show_progress=False,
    )


def get_qgate_dashboard_payload(**kwargs: Any) -> dict:
    query = normalize_query(**kwargs)
    with _temporary_qgate_source(_current_qgate_db_path()):
        if query.use_cache:
            payload = _build_dashboard_payload_cached(
                query.defect_dir,
                query.history_dir,
                query.teams,
                query.min_transition_count,
                query.analysis_workers,
                query.cache_dir,
                query.use_cache,
            )
        else:
            payload = build_dashboard_payload(
                defect_dir=query.defect_dir,
                history_dir=query.history_dir,
                teams=list(query.teams),
                min_transition_count=query.min_transition_count,
                analysis_workers=query.analysis_workers,
                cache_dir=query.cache_dir,
                use_cache=False,
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
        min_transition_count=query.min_transition_count,
    )


def _sum_column(dataset: dict, column_name: str) -> int:
    columns = dataset.get("columns") or []
    rows = dataset.get("rows") or []
    if column_name not in columns:
        return 0

    column_index = columns.index(column_name)
    total = 0
    for row in rows:
        try:
            total += int(row[column_index] or 0)
        except (IndexError, TypeError, ValueError):
            continue
    return total


def get_qgate_meta_payload(**kwargs: Any) -> dict:
    payload = get_qgate_dashboard_payload(**kwargs)
    meta_dataset = payload.get("meta", {})
    total_defects = _sum_column(meta_dataset, "Defects")
    history_ok = _sum_column(meta_dataset, "History_OK")
    history_missing = _sum_column(meta_dataset, "History_Missing_or_Error")

    if total_defects <= 0:
        status = "empty"
    elif history_missing > 0:
        status = "partial"
    else:
        status = "healthy"

    generated_from = payload.get("generated_from", {})
    options = payload.get("options", {})
    return {
        "defect_dir": generated_from.get("defect_dir", DEFAULT_DEFECT_DIR),
        "history_dir": generated_from.get("history_dir", DEFAULT_HISTORY_DIR),
        "availableTeams": options.get("teams", []),
        "availableYears": options.get("years", []),
        "status": status,
        "teamCount": len(options.get("teams", [])),
        "totalDefects": total_defects,
        "historyOk": history_ok,
        "historyMissingOrError": history_missing,
    }