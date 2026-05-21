# Full Picture Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new Full Picture dashboard route that loads a dedicated backend payload, defaults to 2026 defect scope, shows positive/negative outcome charts plus a ticket detail drilldown table, and keeps filter state and chart selection in sync.

**Architecture:** Keep the existing QGate KPI route untouched and add a parallel Full Picture slice. On the backend, add a new FastAPI endpoint plus a dedicated service module that normalizes multi-select filters, reads local defect/history-backed records, computes ticket-level outcome flags, and returns a payload already rich enough for client-side chart drilldown. On the frontend, add a new `/full-picture` page with its own typed API client, payload adapter, bootstrap, filtering helpers, and page component so the current QGate KPI code path remains isolated.

**Tech Stack:** FastAPI, Python dataclasses, repository-local Octane/QGate data helpers, Next.js 16, React 19, Vitest, Testing Library, pytest

---

## File Structure

### Backend

- Create: `full_picture_api_service.py`
  Owns query normalization, filter option extraction, outcome aggregation, ticket-row shaping, and payload assembly for the new endpoint.
- Modify: `qgate_api.py`
  Adds `GET /api/full-picture/dashboard` and forwards validated query args into the new service.
- Create: `tests/test_full_picture_api.py`
  Covers payload contract, query forwarding, outcome math, default 2026 year scope, and API error behavior.

### Frontend shared lib

- Create: `apps/qgate-kpi/src/lib/full-picture-types.ts`
  Defines the API payload, filter, and adapted view-model types for the new page.
- Create: `apps/qgate-kpi/src/lib/full-picture-default-filters.ts`
  Centralizes the `2026` initial year filter plus empty multi-select defaults for all other filter groups.
- Create: `apps/qgate-kpi/src/lib/full-picture-query-options.ts`
  Builds the request URL for the new endpoint with repeated multi-select query params.
- Create: `apps/qgate-kpi/src/lib/full-picture-payload-adapter.ts`
  Validates the payload shape and maps snake_case API fields into the client view model.
- Create: `apps/qgate-kpi/src/lib/full-picture-api.ts`
  Performs fetch, timeout/error handling, and schema validation for the new endpoint.
- Create: `apps/qgate-kpi/src/lib/__tests__/full-picture-api.test.ts`
  Covers healthy fetch, backend detail propagation, invalid JSON, and schema drift.

### Frontend feature

- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-bootstrap.tsx`
  Mirrors the non-blocking bootstrap behavior already used by the QGate KPI page.
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/bootstrap-state.ts`
  Resolves loading/placeholder shell states for the new page.
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.ts`
  Applies filter state and chart selection to already-loaded rows.
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-page.tsx`
  Renders the hero, filter controls, outcome chart panels, and ticket detail table.
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.test.ts`
  Verifies denominator math, team expansion rows, and chart-to-table drilldown.
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/__tests__/full-picture-page.test.tsx`
  Verifies loading/empty/ready states, required columns, and filter/chart interactions.

### Next.js route

- Create: `apps/qgate-kpi/app/full-picture/page.tsx`
  Server component for SSR bootstrap of the new dashboard route.

## Task 1: Add the backend payload contract and service skeleton

**Files:**
- Create: `tests/test_full_picture_api.py`
- Create: `full_picture_api_service.py`

- [ ] **Step 1: Write the failing backend payload-contract test**

```python
from fastapi.testclient import TestClient

import qgate_api


def test_full_picture_dashboard_endpoint_returns_payload_families(monkeypatch):
    captured = {}

    def fake_get_full_picture_dashboard_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "generated_from": {"default_years": ["2026"]},
            "filters": {
                "years": ["2026"],
                "projects": ["PHEV"],
                "assignedEcus": [],
                "problemFinderTeams": ["DTSV_China"],
                "aidas": ["Energy Management"],
                "phases": ["08-Fixed"],
                "solutionClusters": [],
                "pus": ["PU48"],
                "markets": ["CN"],
                "leadModels": ["G60"],
                "groups": ["Q-Gate"],
            },
            "overview": {"ticket_count": 3, "resolved_forward_count": 1, "rejected_directly_count": 1},
            "outcome_summary": {
                "denominator": 3,
                "rows": [
                    {"key": "resolved_forward", "label": "Resolved Forward (08 -> 06)", "count": 1, "percentage": 33.3},
                    {"key": "rejected_directly", "label": "Rejected Directly (01 -> 09)", "count": 1, "percentage": 33.3},
                ],
            },
            "team_outcome_rows": [
                {"team": "DTSV_China", "resolved_forward_count": 1, "rejected_directly_count": 1, "denominator": 2}
            ],
            "ticket_rows": [
                {
                    "ticket_id": "1001",
                    "ticket_name": "Energy issue",
                    "status": "08-Fixed",
                    "group": "Q-Gate",
                    "problem_finder_team": "DTSV_China",
                    "is_resolved_forward": True,
                    "is_rejected_directly": False,
                }
            ],
        }

    monkeypatch.setattr(qgate_api, "get_full_picture_dashboard_payload", fake_get_full_picture_dashboard_payload)
    client = TestClient(qgate_api.app)

    response = client.get("/api/full-picture/dashboard")

    assert response.status_code == 200
    assert captured["kwargs"]["years"] == ["2026"]
    assert set(response.json().keys()) == {
        "generated_from",
        "filters",
        "overview",
        "outcome_summary",
        "team_outcome_rows",
        "ticket_rows",
    }
```

- [ ] **Step 2: Run the backend test to verify it fails because the endpoint does not exist yet**

Run: `pytest tests/test_full_picture_api.py::test_full_picture_dashboard_endpoint_returns_payload_families -v`

Expected: FAIL with a 404 response or import error because `get_full_picture_dashboard_payload` is not wired into `qgate_api.py`.

- [ ] **Step 3: Create the backend query model and payload skeleton**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FullPictureDashboardQuery:
    years: tuple[str, ...] = ("2026",)
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
    if raw_value in (None, ""):
        return ()
    if isinstance(raw_value, str):
        raw_items = raw_value.split(",")
    else:
        raw_items = raw_value
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return tuple(values)


def normalize_full_picture_query(**kwargs: Any) -> FullPictureDashboardQuery:
    years = _normalize_multi_value(kwargs.get("years")) or ("2026",)
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


def get_full_picture_dashboard_payload(**kwargs: Any) -> dict:
    query = normalize_full_picture_query(**kwargs)
    return {
        "generated_from": {"default_years": list(query.years)},
        "filters": {
            "years": list(query.years),
            "projects": [],
            "assignedEcus": [],
            "problemFinderTeams": [],
            "aidas": [],
            "phases": [],
            "solutionClusters": [],
            "pus": [],
            "markets": [],
            "leadModels": [],
            "groups": [],
        },
        "overview": {"ticket_count": 0, "resolved_forward_count": 0, "rejected_directly_count": 0},
        "outcome_summary": {"denominator": 0, "rows": []},
        "team_outcome_rows": [],
        "ticket_rows": [],
    }
```

- [ ] **Step 4: Run a narrow service smoke check so the new module is importable before route wiring**

Run: `pytest tests/test_full_picture_api.py::test_full_picture_dashboard_endpoint_returns_payload_families -v --maxfail=1`

Expected: the test still fails at the missing route layer, but no longer fails because `full_picture_api_service.py` is missing or contains import-time errors. Proceed to Task 3 to make the endpoint test pass.

## Task 2: Implement outcome aggregation and filterable ticket rows in the backend service

**Files:**
- Modify: `tests/test_full_picture_api.py`
- Modify: `full_picture_api_service.py`

- [ ] **Step 1: Add a failing service-level test for denominator math, team rows, and outcome flags**

```python
import pytest

import full_picture_api_service as service


def test_full_picture_payload_computes_scope_denominator_and_team_rows(monkeypatch):
    source_rows = [
        {
            "year": "2026",
            "project": "PHEV",
            "assigned_ecu": "EDU",
            "problem_finder_team": "DTSV_China",
            "aida": "Energy Management",
            "phase": "08-Fixed",
            "solution_cluster": "Thermal",
            "pu": "PU48",
            "market": "CN",
            "lead_model": "G60",
            "group": "Q-Gate",
            "ticket_id": "1001",
            "ticket_name": "Resolved ticket",
            "status": "08-Fixed",
            "is_resolved_forward": True,
            "is_rejected_directly": False,
        },
        {
            "year": "2026",
            "project": "PHEV",
            "assigned_ecu": "EDU",
            "problem_finder_team": "DTSV_China",
            "aida": "Energy Management",
            "phase": "01-New",
            "solution_cluster": "Thermal",
            "pu": "PU48",
            "market": "CN",
            "lead_model": "G60",
            "group": "Q-Gate",
            "ticket_id": "1002",
            "ticket_name": "Rejected ticket",
            "status": "09-Closed",
            "is_resolved_forward": False,
            "is_rejected_directly": True,
        },
        {
            "year": "2026",
            "project": "PHEV",
            "assigned_ecu": "EDU",
            "problem_finder_team": "FIT_LAENDER_CHINA",
            "aida": "Energy Management",
            "phase": "03-Analysis",
            "solution_cluster": "Thermal",
            "pu": "PU48",
            "market": "CN",
            "lead_model": "G60",
            "group": "Integration",
            "ticket_id": "1003",
            "ticket_name": "Neutral ticket",
            "status": "03-Analysis",
            "is_resolved_forward": False,
            "is_rejected_directly": False,
        },
    ]

    monkeypatch.setattr(service, "load_full_picture_source_rows", lambda query: source_rows)

    payload = service.get_full_picture_dashboard_payload(years=["2026"])

    assert payload["overview"] == {
        "ticket_count": 3,
        "resolved_forward_count": 1,
        "rejected_directly_count": 1,
    }
    assert payload["outcome_summary"]["denominator"] == 3
    assert payload["outcome_summary"]["rows"][0]["percentage"] == pytest.approx(33.3, rel=0.01)
    assert payload["team_outcome_rows"] == [
        {"team": "DTSV_China", "resolved_forward_count": 1, "rejected_directly_count": 1, "denominator": 2},
        {"team": "FIT_LAENDER_CHINA", "resolved_forward_count": 0, "rejected_directly_count": 0, "denominator": 1},
    ]
    assert payload["ticket_rows"][0]["is_resolved_forward"] is True
```

- [ ] **Step 2: Run the service-level test and confirm it fails against the empty skeleton**

Run: `pytest tests/test_full_picture_api.py::test_full_picture_payload_computes_scope_denominator_and_team_rows -v`

Expected: FAIL because `load_full_picture_source_rows` is missing and the payload still returns zeros.

- [ ] **Step 3: Implement row loading, filter matching, option extraction, and aggregation in `full_picture_api_service.py`**

```python
def load_full_picture_source_rows(query: FullPictureDashboardQuery) -> list[dict[str, Any]]:
    rows = _load_rows_from_local_octane_sources()
    return [row for row in rows if _matches_query(row, query)]


def _matches_query(row: dict[str, Any], query: FullPictureDashboardQuery) -> bool:
    return (
        _matches_multi(row.get("year"), query.years)
        and _matches_multi(row.get("project"), query.projects)
        and _matches_multi(row.get("assigned_ecu"), query.assigned_ecus)
        and _matches_multi(row.get("problem_finder_team"), query.problem_finder_teams)
        and _matches_multi(row.get("aida"), query.aidas)
        and _matches_multi(row.get("phase"), query.phases)
        and _matches_multi(row.get("solution_cluster"), query.solution_clusters)
        and _matches_multi(row.get("pu"), query.pus)
        and _matches_multi(row.get("market"), query.markets)
        and _matches_multi(row.get("lead_model"), query.lead_models)
        and _matches_multi(row.get("group"), query.groups)
    )


def _build_outcome_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    resolved = sum(1 for row in rows if row.get("is_resolved_forward"))
    rejected = sum(1 for row in rows if row.get("is_rejected_directly"))
    return {
        "denominator": denominator,
        "rows": [
            {
                "key": "resolved_forward",
                "label": "Resolved Forward (08 -> 06)",
                "count": resolved,
                "percentage": 0.0 if denominator == 0 else round((resolved / denominator) * 100, 1),
            },
            {
                "key": "rejected_directly",
                "label": "Rejected Directly (01 -> 09)",
                "count": rejected,
                "percentage": 0.0 if denominator == 0 else round((rejected / denominator) * 100, 1),
            },
        ],
    }


def _build_team_outcome_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("problem_finder_team") or "Unknown"), []).append(row)
    output = []
    for team, team_rows in grouped.items():
        output.append(
            {
                "team": team,
                "resolved_forward_count": sum(1 for row in team_rows if row.get("is_resolved_forward")),
                "rejected_directly_count": sum(1 for row in team_rows if row.get("is_rejected_directly")),
                "denominator": len(team_rows),
            }
        )
    return sorted(output, key=lambda row: (-row["denominator"], row["team"]))
```

- [ ] **Step 4: Re-run the backend tests to verify the core service contract now passes**

Run: `pytest tests/test_full_picture_api.py -k "full_picture_payload or returns_payload_families" -v`

Expected: PASS for the new payload-contract and aggregation tests.

## Task 3: Expose the FastAPI route with the full filter surface

**Files:**
- Modify: `qgate_api.py`
- Modify: `tests/test_full_picture_api.py`

- [ ] **Step 1: Add a failing endpoint-forwarding test for all required filters**

```python
def test_full_picture_dashboard_endpoint_forwards_full_filter_surface(monkeypatch):
    captured = {}

    def fake_get_full_picture_dashboard_payload(**kwargs):
        captured["kwargs"] = kwargs
        return {
            "generated_from": {"default_years": ["2026"]},
            "filters": {key: [] for key in ["years", "projects", "assignedEcus", "problemFinderTeams", "aidas", "phases", "solutionClusters", "pus", "markets", "leadModels", "groups"]},
            "overview": {"ticket_count": 0, "resolved_forward_count": 0, "rejected_directly_count": 0},
            "outcome_summary": {"denominator": 0, "rows": []},
            "team_outcome_rows": [],
            "ticket_rows": [],
        }

    monkeypatch.setattr(qgate_api, "get_full_picture_dashboard_payload", fake_get_full_picture_dashboard_payload)
    client = TestClient(qgate_api.app)

    response = client.get(
        "/api/full-picture/dashboard",
        params={
            "years": ["2026"],
            "projects": ["PHEV"],
            "assigned_ecus": ["EDU"],
            "problem_finder_teams": ["DTSV_China"],
            "aidas": ["Energy Management"],
            "phases": ["08-Fixed"],
            "solution_clusters": ["Thermal"],
            "pus": ["PU48"],
            "markets": ["CN"],
            "lead_models": ["G60"],
            "groups": ["Q-Gate"],
        },
    )

    assert response.status_code == 200
    assert captured["kwargs"] == {
        "years": ["2026"],
        "projects": ["PHEV"],
        "assigned_ecus": ["EDU"],
        "problem_finder_teams": ["DTSV_China"],
        "aidas": ["Energy Management"],
        "phases": ["08-Fixed"],
        "solution_clusters": ["Thermal"],
        "pus": ["PU48"],
        "markets": ["CN"],
        "lead_models": ["G60"],
        "groups": ["Q-Gate"],
    }
```

- [ ] **Step 2: Run the forwarding test and confirm it fails before the new route exists**

Run: `pytest tests/test_full_picture_api.py::test_full_picture_dashboard_endpoint_forwards_full_filter_surface -v`

Expected: FAIL with 404 or missing route wiring.

- [ ] **Step 3: Add the FastAPI route to `qgate_api.py`**

```python
from qgate_api_service import get_qgate_dashboard_payload, get_qgate_meta_payload
from full_picture_api_service import get_full_picture_dashboard_payload


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
            years=years or ["2026"],
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
    except QGateDashboardDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

- [ ] **Step 4: Re-run the route tests to verify filter forwarding and payload families pass**

Run: `pytest tests/test_full_picture_api.py -k "endpoint" -v`

Expected: PASS for both endpoint tests.

## Task 4: Add the frontend data contract and API client

**Files:**
- Create: `apps/qgate-kpi/src/lib/full-picture-types.ts`
- Create: `apps/qgate-kpi/src/lib/full-picture-default-filters.ts`
- Create: `apps/qgate-kpi/src/lib/full-picture-query-options.ts`
- Create: `apps/qgate-kpi/src/lib/full-picture-payload-adapter.ts`
- Create: `apps/qgate-kpi/src/lib/full-picture-api.ts`
- Create: `apps/qgate-kpi/src/lib/__tests__/full-picture-api.test.ts`

- [ ] **Step 1: Write a failing API-client test for a healthy response and backend error detail**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchFullPictureDashboardPayload, FullPictureApiRequestError } from "../full-picture-api";
import { getDefaultFullPictureFilters } from "../full-picture-default-filters";

afterEach(() => {
  vi.restoreAllMocks();
});

const samplePayload = {
  generated_from: { default_years: ["2026"] },
  filters: {
    years: ["2026"],
    projects: ["PHEV"],
    assignedEcus: ["EDU"],
    problemFinderTeams: ["DTSV_China"],
    aidas: ["Energy Management"],
    phases: ["08-Fixed"],
    solutionClusters: ["Thermal"],
    pus: ["PU48"],
    markets: ["CN"],
    leadModels: ["G60"],
    groups: ["Q-Gate"],
  },
  overview: { ticket_count: 3, resolved_forward_count: 1, rejected_directly_count: 1 },
  outcome_summary: {
    denominator: 3,
    rows: [
      { key: "resolved_forward", label: "Resolved Forward (08 -> 06)", count: 1, percentage: 33.3 },
      { key: "rejected_directly", label: "Rejected Directly (01 -> 09)", count: 1, percentage: 33.3 },
    ],
  },
  team_outcome_rows: [],
  ticket_rows: [],
};

describe("fetchFullPictureDashboardPayload", () => {
  it("returns a validated payload for a healthy API response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(samplePayload), { status: 200 }));

    const payload = await fetchFullPictureDashboardPayload(getDefaultFullPictureFilters());

    expect(payload.generated_from.default_years).toEqual(["2026"]);
  });

  it("propagates backend detail for non-ok responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "No Full Picture data found." }), { status: 422 }),
    );

    await expect(fetchFullPictureDashboardPayload(getDefaultFullPictureFilters())).rejects.toThrow(FullPictureApiRequestError);
    await expect(fetchFullPictureDashboardPayload(getDefaultFullPictureFilters())).rejects.toThrow("No Full Picture data found.");
  });
});
```

- [ ] **Step 2: Run the frontend API-client test to verify the new modules do not exist yet**

Run: `npm run test -- src/lib/__tests__/full-picture-api.test.ts`

Expected: FAIL with module resolution errors for the new Full Picture lib files.

- [ ] **Step 3: Create the types, defaults, URL builder, payload validator, and fetch wrapper**

```ts
export type FullPictureFilters = {
  years: string[];
  projects: string[];
  assignedEcus: string[];
  problemFinderTeams: string[];
  aidas: string[];
  phases: string[];
  solutionClusters: string[];
  pus: string[];
  markets: string[];
  leadModels: string[];
  groups: string[];
};

export function getDefaultFullPictureFilters(): FullPictureFilters {
  return {
    years: ["2026"],
    projects: [],
    assignedEcus: [],
    problemFinderTeams: [],
    aidas: [],
    phases: [],
    solutionClusters: [],
    pus: [],
    markets: [],
    leadModels: [],
    groups: [],
  };
}

export function buildFullPictureDashboardUrl(apiBase: string, filters: FullPictureFilters) {
  const url = new URL("/api/full-picture/dashboard", apiBase);
  for (const year of filters.years) url.searchParams.append("years", year);
  for (const project of filters.projects) url.searchParams.append("projects", project);
  for (const assignedEcu of filters.assignedEcus) url.searchParams.append("assigned_ecus", assignedEcu);
  for (const team of filters.problemFinderTeams) url.searchParams.append("problem_finder_teams", team);
  for (const aida of filters.aidas) url.searchParams.append("aidas", aida);
  for (const phase of filters.phases) url.searchParams.append("phases", phase);
  for (const cluster of filters.solutionClusters) url.searchParams.append("solution_clusters", cluster);
  for (const pu of filters.pus) url.searchParams.append("pus", pu);
  for (const market of filters.markets) url.searchParams.append("markets", market);
  for (const leadModel of filters.leadModels) url.searchParams.append("lead_models", leadModel);
  for (const group of filters.groups) url.searchParams.append("groups", group);
  return url.toString();
}
```

- [ ] **Step 4: Re-run the API-client tests to verify the new fetch path is stable**

Run: `npm run test -- src/lib/__tests__/full-picture-api.test.ts`

Expected: PASS.

## Task 5: Implement client-side filtering and chart-selection drilldown logic

**Files:**
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.ts`
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.test.ts`

- [ ] **Step 1: Write the failing filtering tests for denominator math and chart-to-table narrowing**

```ts
import { describe, expect, it } from "vitest";

import { applyFullPictureFilters, applyTicketSelection } from "./full-picture-filtering";

const sampleViewModel = {
  availableFilters: {
    years: ["2026"],
    projects: ["PHEV"],
    assignedEcus: ["EDU"],
    problemFinderTeams: ["DTSV_China", "FIT_LAENDER_CHINA"],
    aidas: ["Energy Management"],
    phases: ["08-Fixed", "01-New"],
    solutionClusters: ["Thermal"],
    pus: ["PU48"],
    markets: ["CN"],
    leadModels: ["G60"],
    groups: ["Q-Gate", "Integration"],
  },
  ticketRows: [
    {
      ticketId: "1001",
      ticketName: "Resolved ticket",
      status: "08-Fixed",
      group: "Q-Gate",
      problemFinderTeam: "DTSV_China",
      year: "2026",
      project: "PHEV",
      assignedEcu: "EDU",
      aida: "Energy Management",
      phase: "08-Fixed",
      solutionCluster: "Thermal",
      pu: "PU48",
      market: "CN",
      leadModel: "G60",
      isResolvedForward: true,
      isRejectedDirectly: false,
    },
    {
      ticketId: "1002",
      ticketName: "Rejected ticket",
      status: "09-Closed",
      group: "Q-Gate",
      problemFinderTeam: "DTSV_China",
      year: "2026",
      project: "PHEV",
      assignedEcu: "EDU",
      aida: "Energy Management",
      phase: "01-New",
      solutionCluster: "Thermal",
      pu: "PU48",
      market: "CN",
      leadModel: "G60",
      isResolvedForward: false,
      isRejectedDirectly: true,
    },
  ],
};

describe("applyFullPictureFilters", () => {
  it("recomputes outcome summary from the currently filtered ticket scope", () => {
    const result = applyFullPictureFilters(sampleViewModel, {
      years: ["2026"],
      projects: [],
      assignedEcus: [],
      problemFinderTeams: [],
      aidas: [],
      phases: [],
      solutionClusters: [],
      pus: [],
      markets: [],
      leadModels: [],
      groups: [],
    });

    expect(result.outcomeSummary.denominator).toBe(2);
    expect(result.outcomeSummary.rows).toEqual([
      { key: "resolved_forward", label: "Resolved Forward (08 -> 06)", count: 1, percentage: 50 },
      { key: "rejected_directly", label: "Rejected Directly (01 -> 09)", count: 1, percentage: 50 },
    ]);
  });

  it("narrows the table to the selected outcome and team without re-fetching", () => {
    const filtered = applyFullPictureFilters(sampleViewModel, {
      years: ["2026"],
      projects: [],
      assignedEcus: [],
      problemFinderTeams: [],
      aidas: [],
      phases: [],
      solutionClusters: [],
      pus: [],
      markets: [],
      leadModels: [],
      groups: [],
    });

    const selected = applyTicketSelection(filtered.ticketRows, {
      outcomeKey: "rejected_directly",
      team: "DTSV_China",
    });

    expect(selected.map((row) => row.ticketId)).toEqual(["1002"]);
  });
});
```

- [ ] **Step 2: Run the filtering tests and confirm they fail before the helpers exist**

Run: `npm run test -- src/features/full-picture-dashboard/full-picture-filtering.test.ts`

Expected: FAIL with missing-module errors.

- [ ] **Step 3: Implement the filtering helpers with derived summary and team rows**

```ts
function matchesMulti(value: string, selectedValues: string[]) {
  return selectedValues.length === 0 || selectedValues.includes(value);
}

export function applyFullPictureFilters(viewModel: FullPictureDashboardViewModel, filters: FullPictureFilters) {
  const ticketRows = viewModel.ticketRows.filter((row) => {
    return (
      matchesMulti(row.year, filters.years) &&
      matchesMulti(row.project, filters.projects) &&
      matchesMulti(row.assignedEcu, filters.assignedEcus) &&
      matchesMulti(row.problemFinderTeam, filters.problemFinderTeams) &&
      matchesMulti(row.aida, filters.aidas) &&
      matchesMulti(row.phase, filters.phases) &&
      matchesMulti(row.solutionCluster, filters.solutionClusters) &&
      matchesMulti(row.pu, filters.pus) &&
      matchesMulti(row.market, filters.markets) &&
      matchesMulti(row.leadModel, filters.leadModels) &&
      matchesMulti(row.group, filters.groups)
    );
  });

  const denominator = ticketRows.length;
  const resolvedForwardCount = ticketRows.filter((row) => row.isResolvedForward).length;
  const rejectedDirectlyCount = ticketRows.filter((row) => row.isRejectedDirectly).length;

  return {
    ticketRows,
    outcomeSummary: {
      denominator,
      rows: [
        {
          key: "resolved_forward",
          label: "Resolved Forward (08 -> 06)",
          count: resolvedForwardCount,
          percentage: denominator === 0 ? 0 : Number(((resolvedForwardCount / denominator) * 100).toFixed(1)),
        },
        {
          key: "rejected_directly",
          label: "Rejected Directly (01 -> 09)",
          count: rejectedDirectlyCount,
          percentage: denominator === 0 ? 0 : Number(((rejectedDirectlyCount / denominator) * 100).toFixed(1)),
        },
      ],
    },
    teamOutcomeRows: buildTeamOutcomeRows(ticketRows),
  };
}

export function applyTicketSelection(ticketRows: FullPictureTicketRow[], selection: FullPictureChartSelection | null) {
  if (!selection) {
    return ticketRows;
  }
  return ticketRows.filter((row) => {
    const matchesTeam = !selection.team || row.problemFinderTeam === selection.team;
    const matchesOutcome =
      !selection.outcomeKey ||
      (selection.outcomeKey === "resolved_forward" && row.isResolvedForward) ||
      (selection.outcomeKey === "rejected_directly" && row.isRejectedDirectly);
    return matchesTeam && matchesOutcome;
  });
}
```

- [ ] **Step 4: Re-run the filtering tests to confirm derived chart and table behavior is correct**

Run: `npm run test -- src/features/full-picture-dashboard/full-picture-filtering.test.ts`

Expected: PASS.

## Task 6: Build the page component, bootstrap, and `/full-picture` route

**Files:**
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/bootstrap-state.ts`
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-bootstrap.tsx`
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-page.tsx`
- Create: `apps/qgate-kpi/src/features/full-picture-dashboard/__tests__/full-picture-page.test.tsx`
- Create: `apps/qgate-kpi/app/full-picture/page.tsx`

- [ ] **Step 1: Write the failing page test for loading, ready state, required columns, and chart-click drilldown**

```tsx
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { FullPicturePage } from "../full-picture-page";

const sampleData = {
  generatedFrom: { defaultYears: ["2026"] },
  availableFilters: {
    years: ["2026"],
    projects: ["PHEV"],
    assignedEcus: ["EDU"],
    problemFinderTeams: ["DTSV_China"],
    aidas: ["Energy Management"],
    phases: ["08-Fixed", "01-New"],
    solutionClusters: ["Thermal"],
    pus: ["PU48"],
    markets: ["CN"],
    leadModels: ["G60"],
    groups: ["Q-Gate"],
  },
  ticketRows: [
    {
      ticketId: "1001",
      ticketName: "Resolved ticket",
      status: "08-Fixed",
      group: "Q-Gate",
      problemFinderTeam: "DTSV_China",
      year: "2026",
      project: "PHEV",
      assignedEcu: "EDU",
      aida: "Energy Management",
      phase: "08-Fixed",
      solutionCluster: "Thermal",
      pu: "PU48",
      market: "CN",
      leadModel: "G60",
      isResolvedForward: true,
      isRejectedDirectly: false,
    },
  ],
};

describe("FullPicturePage", () => {
  it("renders the loading shell", () => {
    render(<FullPicturePage state="loading" />);
    expect(screen.getByText("Full Picture Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Loading dashboard data...")).toBeInTheDocument();
  });

  it("renders ready state with required table columns", () => {
    render(<FullPicturePage state="ready" initialData={sampleData} />);
    expect(screen.getByRole("heading", { name: "Full Picture Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Octane Ticket ID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Group" })).toBeInTheDocument();
  });

  it("narrows ticket detail after clicking the rejected outcome chip", () => {
    render(
      <FullPicturePage
        state="ready"
        initialData={{
          ...sampleData,
          ticketRows: [
            sampleData.ticketRows[0],
            {
              ...sampleData.ticketRows[0],
              ticketId: "1002",
              ticketName: "Rejected ticket",
              status: "09-Closed",
              isResolvedForward: false,
              isRejectedDirectly: true,
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Rejected Directly/ }));

    expect(screen.queryByText("Resolved ticket")).not.toBeInTheDocument();
    expect(screen.getByText("Rejected ticket")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the page test to verify the new route and component modules are still missing**

Run: `npm run test -- src/features/full-picture-dashboard/__tests__/full-picture-page.test.tsx`

Expected: FAIL with missing-module errors.

- [ ] **Step 3: Implement the bootstrap state, page component, and route**

```tsx
export default async function FullPictureRoute() {
  let pageProps: FullPicturePageProps;

  try {
    const payload = await fetchFullPictureDashboardPayload(getDefaultFullPictureFilters(), {
      signal: AbortSignal.timeout(INITIAL_FULL_PICTURE_BOOTSTRAP_TIMEOUT_MS),
    });
    const initialData = adaptFullPicturePayload(payload);
    pageProps = { state: "ready", initialData };
  } catch (error) {
    pageProps = resolveFullPictureShellState(error);
  }

  return <FullPictureBootstrap {...pageProps} />;
}
```

```tsx
export function FullPicturePage({ initialData, state, statusMessage }: FullPicturePageProps) {
  const [filters, setFilters] = useState<FullPictureFilters>(() => getDefaultFullPictureFilters());
  const [selection, setSelection] = useState<FullPictureChartSelection | null>(null);

  const filtered = state === "ready" ? applyFullPictureFilters(initialData, filters) : null;
  const visibleTicketRows = filtered ? applyTicketSelection(filtered.ticketRows, selection) : [];

  return (
    <main className="dashboard-shell full-picture-shell">
      <section className="hero-panel">
        <h1>Full Picture Dashboard</h1>
        <p>Track whether the current defect scope closes tickets forward or closes them directly without solution.</p>
        <p>{statusMessage ?? (state === "ready" ? "Dashboard ready." : "Loading dashboard data...")}</p>
      </section>

      <section aria-label="Filters">
        <FilterCard title="Year" values={initialData?.availableFilters.years ?? []} selectedValues={filters.years} onToggle={(value) => setFilters((current) => ({ ...current, years: toggleMulti(current.years, value) }))} />
        <FilterCard title="Project" values={initialData?.availableFilters.projects ?? []} selectedValues={filters.projects} onToggle={(value) => setFilters((current) => ({ ...current, projects: toggleMulti(current.projects, value) }))} />
      </section>

      <section className="chart-grid">
        <OutcomeSummaryPanel rows={filtered?.outcomeSummary.rows ?? []} onSelect={(outcomeKey) => setSelection(outcomeKey ? { outcomeKey } : null)} />
        <TeamOutcomePanel rows={filtered?.teamOutcomeRows ?? []} onSelect={(team, outcomeKey) => setSelection(team && outcomeKey ? { team, outcomeKey } : null)} />
      </section>

      <section>
        <table aria-label="Ticket detail">
          <thead>
            <tr>
              <th>Octane Ticket ID</th>
              <th>Name</th>
              <th>Status</th>
              <th>Group</th>
            </tr>
          </thead>
          <tbody>
            {visibleTicketRows.map((row) => (
              <tr key={row.ticketId}>
                <td>{row.ticketId}</td>
                <td>{row.ticketName}</td>
                <td>{row.status}</td>
                <td>{row.group}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Run the page tests and the existing focused frontend suite to verify the new page is stable and isolated**

Run: `npm run test -- src/features/full-picture-dashboard/__tests__/full-picture-page.test.tsx src/features/full-picture-dashboard/full-picture-filtering.test.ts src/lib/__tests__/full-picture-api.test.ts`

Expected: PASS.

## Task 7: Final integration verification

**Files:**
- Modify: `qgate_api.py`
- Modify: `full_picture_api_service.py`
- Modify: `apps/qgate-kpi/app/full-picture/page.tsx`
- Modify: `apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-page.tsx`

- [ ] **Step 1: Run the backend verification slice**

Run: `pytest tests/test_full_picture_api.py -v`

Expected: PASS.

- [ ] **Step 2: Run the frontend verification slice**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; npm run test -- src/features/full-picture-dashboard/full-picture-filtering.test.ts src/features/full-picture-dashboard/__tests__/full-picture-page.test.tsx src/lib/__tests__/full-picture-api.test.ts ; $exit=$LASTEXITCODE ; Pop-Location ; exit $exit`

Expected: PASS.

- [ ] **Step 3: Run lint and typecheck for the Next.js app**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; npm run lint ; $lintExit=$LASTEXITCODE ; npm run typecheck ; $typeExit=$LASTEXITCODE ; Pop-Location ; if (($lintExit -ne 0) -or ($typeExit -ne 0)) { exit 1 }`

Expected: PASS.

- [ ] **Step 4: Smoke-test the route manually with the local API**

Run backend: `python -m uvicorn qgate_api:app --host 127.0.0.1 --port 8001 --reload`

Run frontend: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; npm run dev`

Manual check:
- Open `http://127.0.0.1:3001/full-picture`
- Confirm the initial scope shows year `2026`
- Confirm both outcome panels render even when one count is zero
- Confirm clicking `Resolved Forward (08 -> 06)` narrows the table
- Confirm clicking a team row narrows the table to the selected team/outcome pair
- Confirm no Top Issue panel is present

Expected: page shell stays responsive, API failures show a readable placeholder state, and the ready state matches the approved spec.