from __future__ import annotations

import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from full_picture_api_service import FullPictureDashboardDataError, get_full_picture_dashboard_payload
from qgate_api_service import get_qgate_dashboard_payload, get_qgate_meta_payload
from report.generate_qgate_kpi_dashboard import QGateDashboardDataError


app = FastAPI(title="QGate KPI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3001", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/qgate/kpi-dashboard")
def read_qgate_dashboard(
    defect_dir: str = "qgate/defect",
    history_dir: str = "qgate/history",
    teams: list[str] | None = Query(default=None),
    years: list[str] | None = Query(default=None),
    groups: list[str] | None = Query(default=None),
    changed_by: list[str] | None = Query(default=None),
    fif: list[str] | None = Query(default=None),
    timespan_min: float = 0,
    timespan_max: float | None = None,
    min_transition_count: int = 200,
    analysis_workers: int = 0,
    cache_dir: str | None = "qgate_cache",
    use_cache: bool = True,
):
    try:
        return get_qgate_dashboard_payload(
            defect_dir=defect_dir,
            history_dir=history_dir,
            teams=teams or [],
            years=years or [],
            groups=groups or [],
            changed_by=changed_by or [],
            fif=fif or [],
            timespan_min=timespan_min,
            timespan_max=timespan_max,
            min_transition_count=min_transition_count,
            analysis_workers=analysis_workers,
            cache_dir=cache_dir,
            use_cache=use_cache,
        )
    except QGateDashboardDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/qgate/meta")
def read_qgate_meta(
    defect_dir: str = "qgate/defect",
    history_dir: str = "qgate/history",
    teams: list[str] | None = Query(default=None),
):
    try:
        return get_qgate_meta_payload(
            defect_dir=defect_dir,
            history_dir=history_dir,
            teams=teams or [],
        )
    except QGateDashboardDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/full-picture/dashboard")
def read_full_picture_dashboard(
    years: list[str] | None = Query(default=None),
    projects: list[str] | None = Query(default=None),
    assigned_ecus: list[str] | None = Query(default=None),
    problem_finder_teams: list[str] | None = Query(default=None),
    aidas: list[str] | None = Query(default=None),
    phases: list[str] | None = Query(default=None),
    solution_clusters: list[str] | None = Query(default=None),
    pus: list[str] | None = Query(default=None),
    markets: list[str] | None = Query(default=None),
    lead_models: list[str] | None = Query(default=None),
    groups: list[str] | None = Query(default=None),
):
    try:
        return get_full_picture_dashboard_payload(
            years=years or [],
            projects=projects or [],
            assigned_ecus=assigned_ecus or [],
            problem_finder_teams=problem_finder_teams or [],
            aidas=aidas or [],
            phases=phases or [],
            solution_clusters=solution_clusters or [],
            pus=pus or [],
            markets=markets or [],
            lead_models=lead_models or [],
            groups=groups or [],
        )
    except (FullPictureDashboardDataError, sqlite3.DatabaseError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc