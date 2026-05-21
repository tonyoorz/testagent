# QGate Next.js KPI Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Next.js 16 QGate KPI dashboard backed by a lightweight Python API that reuses the current `qgate.py` and `report/generate_qgate_kpi_dashboard.py` calculation path while matching the current HTML dashboard's data scope.

**Architecture:** Split the work into two isolated slices: a Python compatibility layer that exposes a typed JSON contract over the existing file-first QGate analytics, and a new `apps/qgate-kpi` Next.js application that renders a premium, responsive workbench on top of that contract. Keep the backend logic close to the current report generator so parity bugs are easy to detect, then use typed adapters on the frontend so later Top Issue and Test Coverage pages can share the same app shell, tokens, and query model.

**Tech Stack:** Python, FastAPI, pytest, Next.js 16, React 19, TypeScript, TanStack Query, TanStack Table, ECharts, Vitest, Testing Library.

---

Git commit steps are intentionally omitted from this plan because the workspace policy requires explicit user approval before any commit.

## Planned File Map

- Modify: `report/generate_qgate_kpi_dashboard.py`
  Purpose: remove the hidden `args` dependency from payload building and expose a reusable backend entry point for both the HTML generator and the API.
- Modify: `requirements.txt`
  Purpose: add FastAPI and Uvicorn for the Python gateway.
- Create: `qgate_api_service.py`
  Purpose: normalize query parameters, call the reused payload builder, derive meta/status information, and cache default responses.
- Create: `qgate_api.py`
  Purpose: expose `/api/qgate/kpi-dashboard` and `/api/qgate/meta`.
- Create: `tests/test_qgate_kpi_payload.py`
  Purpose: verify the reusable payload builder returns the expected contract without relying on CLI globals.
- Create: `tests/test_qgate_api.py`
  Purpose: verify API status codes and payload families.
- Create: `apps/qgate-kpi/package.json`
  Purpose: define the standalone Next.js application and frontend dependencies.
- Create: `apps/qgate-kpi/tsconfig.json`
  Purpose: TypeScript configuration.
- Create: `apps/qgate-kpi/next.config.ts`
  Purpose: Next.js configuration.
- Create: `apps/qgate-kpi/vitest.config.ts`
  Purpose: frontend test runner configuration.
- Create: `apps/qgate-kpi/src/test/setup.ts`
  Purpose: Testing Library setup.
- Create: `apps/qgate-kpi/.env.local.example`
  Purpose: document the API base URL expected by the frontend.
- Create: `apps/qgate-kpi/app/layout.tsx`
  Purpose: root layout, fonts, and query provider bootstrap.
- Create: `apps/qgate-kpi/app/page.tsx`
  Purpose: server-side initial payload fetch with TanStack Query hydration.
- Create: `apps/qgate-kpi/app/globals.css`
  Purpose: shared tokens, layout primitives, and responsive styling.
- Create: `apps/qgate-kpi/src/lib/types.ts`
  Purpose: Zod schemas and TypeScript types for the API contract.
- Create: `apps/qgate-kpi/src/lib/api.ts`
  Purpose: browser/server fetch helpers.
- Create: `apps/qgate-kpi/src/lib/query-options.ts`
  Purpose: central query keys and prefetch options.
- Create: `apps/qgate-kpi/src/lib/payload-adapter.ts`
  Purpose: convert row/column payload datasets into typed records for charts and tables.
- Create: `apps/qgate-kpi/src/lib/default-filters.ts`
  Purpose: initial filter state.
- Create: `apps/qgate-kpi/src/components/providers.tsx`
  Purpose: QueryClientProvider.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
  Purpose: top-level page composition and linked state.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/state-banner.tsx`
  Purpose: loading, error, stale, and partial-data banners.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/hero-kpis.tsx`
  Purpose: hero KPI cards.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/insights-strip.tsx`
  Purpose: key insight cards.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/filter-bar.tsx`
  Purpose: global filter surface.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/coverage-panel.tsx`
  Purpose: team coverage chart.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/summary-panel.tsx`
  Purpose: team x group efficiency summary.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/transition-panel.tsx`
  Purpose: transition analysis chart/table.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/ticket-drilldown.tsx`
  Purpose: active drilldown table.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/payload-adapter.test.ts`
  Purpose: verify payload conversion and derived metrics.
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
  Purpose: verify first-screen rendering, linked selection, and explicit states.
- Create: `docs/qgate-next-dashboard-dev.md`
  Purpose: startup and validation instructions for the Python API and the Next.js app.

### Task 1: Extract A Reusable QGate Payload Builder

**Files:**
- Modify: `report/generate_qgate_kpi_dashboard.py`
- Create: `tests/test_qgate_kpi_payload.py`
- Test: `tests/test_qgate_kpi_payload.py`

- [ ] **Step 1: Write a failing backend payload test that proves the generator can run without CLI globals**

```python
from types import SimpleNamespace

import pandas as pd

import report.generate_qgate_kpi_dashboard as report_mod


def test_build_dashboard_payload_uses_explicit_generated_from(monkeypatch):
    meta_df = pd.DataFrame([
        {"Team": "DTSV_China", "Defects": 4, "History_OK": 3, "History_Missing_or_Error": 1}
    ])
    issues_df = pd.DataFrame([
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
    ])

    monkeypatch.setattr(
        report_mod.qgate,
        "compute_all_teams_data",
        lambda **kwargs: (meta_df, pd.DataFrame(), issues_df),
    )

    payload = report_mod.build_dashboard_payload(
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
```

- [ ] **Step 2: Run the payload test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_qgate_kpi_payload.py -q`

Expected: FAIL because `build_dashboard_payload()` does not exist yet and `build_payload()` still depends on the module-level `args` object.

- [ ] **Step 3: Make the generator reusable by removing the hidden `args` dependency and introducing an explicit builder**

```python
def build_payload(
    meta_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    issues_df: pd.DataFrame,
    overview: dict,
    insights: list[str],
    min_transition_count: int,
    generated_from: dict,
) -> dict:
    groups = sorted({str(x) for x in issues_df.get("Group", pd.Series(dtype="object")).dropna().tolist()})
    changed_by = sorted({str(x) for x in issues_df.get("Changed_By", pd.Series(dtype="object")).dropna().tolist() if str(x).strip()})
    fif_values = sorted({str(x) for x in issues_df.get("FiF", pd.Series(dtype="object")).dropna().tolist() if str(x).strip() and str(x) != "(All)"})
    years = sorted({str(x) for x in coverage_df.get("Year", pd.Series(dtype="object")).dropna().tolist()})
  ticket_columns = ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"]
  tickets_df = pd.DataFrame(columns=ticket_columns)
  if not issues_df.empty:
    tickets_df = (
      issues_df[ticket_columns]
      .drop_duplicates(["Ticket_ID"])
      .sort_values(["Ticket_ID"])
      .reset_index(drop=True)
    )

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
        "meta": sanitize_dataset(meta_df, ["Team", "Defects", "History_OK", "History_Missing_or_Error"]),
        "coverage": sanitize_dataset(coverage_df, ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"]),
        "tickets": sanitize_dataset(tickets_df, ticket_columns),
        "issues": sanitize_dataset(issues_df, [
            "Year",
            "Team",
            "Ticket_ID",
            "Phase_Transition",
            "Group",
            "Duration_Hours",
            "Changed_By",
            "FiF",
            "Ticket_Timespan_Days",
        ]),
    }
    return payload


def build_dashboard_payload(
    *,
    defect_dir: str,
    history_dir: str,
    teams: list[str],
    min_transition_count: int,
    analysis_workers: int,
    cache_dir: str | None,
    use_cache: bool,
    show_progress: bool,
) -> dict:
    meta_df, _stats_df, issues_df = qgate.compute_all_teams_data(
        defect_dir=defect_dir,
        history_dir=history_dir,
        teams=teams,
        show_progress=show_progress,
        analysis_workers=analysis_workers,
        cache_dir=cache_dir,
        use_cache=use_cache,
    )
    if issues_df.empty:
        raise SystemExit("No QGate issue rows were produced. Check defect/history inputs.")

    year_lookup, coverage_df = build_year_lookup_and_coverage(defect_dir, teams, issues_df)
    issues_df = issues_df.copy()
    issues_df["Year"] = [
        year_lookup.get((str(team), str(ticket_id)), "")
        for team, ticket_id in zip(issues_df["Team"].tolist(), issues_df["Ticket_ID"].tolist())
    ]
    detail_df = build_detail_from_issues(issues_df)
    _, summary_df = qgate.build_summary_frames(detail_df.copy(), min_transition_count)
    filtered_detail_df = detail_df[detail_df["Count"] >= int(min_transition_count)].copy() if not detail_df.empty else detail_df
    transition_df = qgate.aggregate_transition_summary(filtered_detail_df)
    overview = build_overview(coverage_df, issues_df, summary_df, transition_df)
    insights = build_insights(meta_df, issues_df, transition_df)
    return build_payload(
        meta_df=meta_df,
        coverage_df=coverage_df,
        issues_df=issues_df,
        overview=overview,
        insights=insights,
        min_transition_count=min_transition_count,
        generated_from={
            "defect_dir": defect_dir,
            "history_dir": history_dir,
            "teams": teams,
            "min_transition_count": min_transition_count,
        },
    )
```

- [ ] **Step 4: Update `main()` to call the reusable builder rather than duplicating the flow inline**

```python
def main() -> None:
    teams = [team.strip() for team in args.teams.split(",") if team.strip()]
    use_cache = not args.no_cache
    cache_dir = None if args.no_cache else args.cache_dir

    payload = build_dashboard_payload(
        defect_dir=args.defect_dir,
        history_dir=args.history_dir,
        teams=teams,
        min_transition_count=args.min_transition_count,
        analysis_workers=args.analysis_workers,
        cache_dir=cache_dir,
        use_cache=use_cache,
        show_progress=not args.no_progress,
    )

    html = render_html(payload)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    overview = payload["overview"]
    print(f"QGate KPI dashboard generated: {output_path}")
    print(f"Teams: {overview['team_count']}, tickets: {overview['unique_tickets']}, transitions: {overview['unique_transitions']}")
```

- [ ] **Step 5: Run the payload test again and verify the generator still compiles**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_qgate_kpi_payload.py -q`

Expected: PASS with `1 passed`.

Run: `.\.venv\Scripts\python.exe -m py_compile report\generate_qgate_kpi_dashboard.py`

Expected: no output and exit code `0`.

### Task 2: Add A Python API Gateway Over The Reused Payload Builder

**Files:**
- Modify: `requirements.txt`
- Create: `qgate_api_service.py`
- Create: `qgate_api.py`
- Create: `tests/test_qgate_api.py`
- Test: `tests/test_qgate_api.py`

- [ ] **Step 1: Write failing API contract tests for the dashboard and meta endpoints**

```python
from fastapi.testclient import TestClient

import qgate_api


def test_qgate_kpi_dashboard_endpoint_returns_payload_families(monkeypatch):
    monkeypatch.setattr(
        qgate_api,
        "get_qgate_dashboard_payload",
        lambda **kwargs: {
            "generated_from": {"defect_dir": "qgate/defect", "history_dir": "qgate/history", "teams": ["DTSV_China"], "min_transition_count": 1},
            "overview": {"team_count": 1, "total_defects": 4, "history_ok": 3, "history_bad": 1, "history_success_rate": 75.0, "transition_samples": 1, "unique_transitions": 1, "unique_tickets": 1, "changed_by_count": 1, "timespan_max": 2},
            "insights": ["sample"],
            "options": {"teams": ["DTSV_China"], "years": ["2026"], "groups": ["Q-Gate"], "changedBy": ["Alice"], "fif": ["Global"], "timespanMax": 2},
            "meta": {"columns": ["Team", "Defects", "History_OK", "History_Missing_or_Error"], "rows": [["DTSV_China", 4, 3, 1]]},
            "coverage": {"columns": ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"], "rows": [["DTSV_China", "2026", 4, 3, 1]]},
            "tickets": {"columns": ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"], "rows": [["1001", "https://octane/1001", "Ticket 1001", "Alice"]]},
            "issues": {"columns": ["Year", "Team", "Ticket_ID", "Phase_Transition", "Group", "Duration_Hours", "Changed_By", "FiF", "Ticket_Timespan_Days"], "rows": [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]]},
        },
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/kpi-dashboard", params={"teams": ["DTSV_China"], "min_transition_count": 1})

    assert response.status_code == 200
    assert set(response.json().keys()) == {"generated_from", "overview", "insights", "options", "meta", "coverage", "tickets", "issues"}


def test_qgate_meta_endpoint_returns_health_summary(monkeypatch):
    monkeypatch.setattr(
        qgate_api,
        "get_qgate_meta_payload",
        lambda **kwargs: {
            "defect_dir": "qgate/defect",
            "history_dir": "qgate/history",
            "availableTeams": ["DTSV_China"],
            "availableYears": ["2026"],
            "status": "healthy",
        },
    )
    client = TestClient(qgate_api.app)

    response = client.get("/api/qgate/meta")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_qgate_api.py -q`

Expected: FAIL because `qgate_api.py` does not exist yet.

- [ ] **Step 3: Add FastAPI dependencies to `requirements.txt`**

```text
fastapi>=0.115.0
uvicorn>=0.30.0
```

- [ ] **Step 4: Implement the service and API files with a small cached default path and explicit query normalization**

```python
# qgate_api_service.py
from dataclasses import dataclass
from functools import lru_cache

from report.generate_qgate_kpi_dashboard import build_dashboard_payload


@dataclass(frozen=True)
class QGateDashboardQuery:
    defect_dir: str = "qgate/defect"
    history_dir: str = "qgate/history"
    teams: tuple[str, ...] = ()
    years: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    changed_by: tuple[str, ...] = ()
    fif: tuple[str, ...] = ()
    timespan_min: int = 0
    timespan_max: int | None = None
    min_transition_count: int = 200
    analysis_workers: int = 0
    cache_dir: str | None = "qgate_cache"
    use_cache: bool = True


def normalize_query(**kwargs) -> QGateDashboardQuery:
    teams = tuple(value for value in kwargs.get("teams") or () if value)
    return QGateDashboardQuery(
        defect_dir=kwargs.get("defect_dir") or "qgate/defect",
        history_dir=kwargs.get("history_dir") or "qgate/history",
        teams=teams,
        years=tuple(kwargs.get("years") or ()),
        groups=tuple(kwargs.get("groups") or ()),
        changed_by=tuple(kwargs.get("changed_by") or ()),
        fif=tuple(kwargs.get("fif") or ()),
        timespan_min=int(kwargs.get("timespan_min") or 0),
        timespan_max=kwargs.get("timespan_max"),
        min_transition_count=int(kwargs.get("min_transition_count") or 200),
        analysis_workers=int(kwargs.get("analysis_workers") or 0),
        cache_dir=kwargs.get("cache_dir", "qgate_cache"),
        use_cache=bool(kwargs.get("use_cache", True)),
    )


@lru_cache(maxsize=16)
def get_qgate_dashboard_payload(**kwargs) -> dict:
    query = normalize_query(**kwargs)
    teams = list(query.teams) if query.teams else None
    return build_dashboard_payload(
        defect_dir=query.defect_dir,
        history_dir=query.history_dir,
        teams=teams or ["DTSV_China"],
        min_transition_count=query.min_transition_count,
        analysis_workers=query.analysis_workers,
        cache_dir=query.cache_dir,
        use_cache=query.use_cache,
        show_progress=False,
    )


def get_qgate_meta_payload(**kwargs) -> dict:
    payload = get_qgate_dashboard_payload(**kwargs)
    history_bad = sum(int(row[3]) for row in payload["meta"]["rows"])
    status = "healthy" if history_bad == 0 else "partial"
    return {
        "defect_dir": payload["generated_from"]["defect_dir"],
        "history_dir": payload["generated_from"]["history_dir"],
        "availableTeams": payload["options"]["teams"],
        "availableYears": payload["options"]["years"],
        "status": status,
    }
```

```python
# qgate_api.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from qgate_api_service import get_qgate_dashboard_payload, get_qgate_meta_payload


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
    teams: list[str] = Query(default=[]),
    years: list[str] = Query(default=[]),
    groups: list[str] = Query(default=[]),
    changed_by: list[str] = Query(default=[]),
    fif: list[str] = Query(default=[]),
    timespan_min: int = 0,
    timespan_max: int | None = None,
    min_transition_count: int = 200,
):
    return get_qgate_dashboard_payload(
        teams=teams,
        years=years,
        groups=groups,
        changed_by=changed_by,
        fif=fif,
        timespan_min=timespan_min,
        timespan_max=timespan_max,
        min_transition_count=min_transition_count,
    )


@app.get("/api/qgate/meta")
def read_qgate_meta(teams: list[str] = Query(default=[])):
    return get_qgate_meta_payload(teams=teams)
```

- [ ] **Step 5: Run backend verification for the new API slice**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_qgate_kpi_payload.py tests/test_qgate_api.py -q`

Expected: PASS with all tests green.

Run: `.\.venv\Scripts\python.exe -m py_compile qgate_api.py qgate_api_service.py report\generate_qgate_kpi_dashboard.py`

Expected: no output and exit code `0`.

### Task 3: Scaffold The Standalone Next.js App

**Files:**
- Create: `apps/qgate-kpi/package.json`
- Create: `apps/qgate-kpi/tsconfig.json`
- Create: `apps/qgate-kpi/next.config.ts`
- Create: `apps/qgate-kpi/vitest.config.ts`
- Create: `apps/qgate-kpi/src/test/setup.ts`
- Create: `apps/qgate-kpi/.env.local.example`
- Create: `apps/qgate-kpi/app/layout.tsx`
- Create: `apps/qgate-kpi/app/globals.css`
- Create: `apps/qgate-kpi/src/components/providers.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

- [ ] **Step 1: Write a failing frontend smoke test for the dashboard shell**

```tsx
import { render, screen } from "@testing-library/react";

import { QGateDashboardPage } from "../dashboard-page";


describe("QGateDashboardPage", () => {
  it("renders the hero title and loading skeleton", () => {
    render(<QGateDashboardPage initialData={null} />);

    expect(screen.getByText("QGate KPI Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Loading dashboard data...")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Create the app manifest and install dependencies**

```json
{
  "name": "qgate-kpi",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev --port 3001",
    "build": "next build",
    "start": "next start --port 3001",
    "test": "vitest --run",
    "lint": "next lint"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "@tanstack/react-table": "^8.20.5",
    "echarts": "^5.5.1",
    "echarts-for-react": "^3.0.2",
    "next": "16.1.1",
    "react": "19.2.0",
    "react-dom": "19.2.0",
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.0.1",
    "@types/node": "^22.8.1",
    "@types/react": "^19.0.2",
    "@types/react-dom": "^19.0.2",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.3",
    "vitest": "^2.1.5"
  }
}
```

Run: `Set-Location .\apps\qgate-kpi; npm install`

Expected: `package-lock.json` is created and install exits with code `0`.

- [ ] **Step 3: Run the smoke test to verify it fails before the shell exists**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: FAIL because `dashboard-page.tsx` and supporting files do not exist yet.

- [ ] **Step 4: Implement the app shell, provider, fonts, and base tokens**

```json
// apps/qgate-kpi/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

```ts
// apps/qgate-kpi/next.config.ts
import type { NextConfig } from "next";


const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    reactCompiler: true,
  },
};


export default nextConfig;
```

```ts
// apps/qgate-kpi/vitest.config.ts
import { defineConfig } from "vitest/config";


export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

```ts
// apps/qgate-kpi/src/test/setup.ts
import "@testing-library/jest-dom/vitest";
```

```dotenv
// apps/qgate-kpi/.env.local.example
NEXT_PUBLIC_QGATE_API_BASE=http://127.0.0.1:8001
```

```tsx
// apps/qgate-kpi/app/layout.tsx
import { IBM_Plex_Sans, Space_Grotesk } from "next/font/google";

import "./globals.css";
import { Providers } from "../src/components/providers";


const displayFont = Space_Grotesk({ subsets: ["latin"], variable: "--font-display" });
const bodyFont = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-body" });


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${displayFont.variable} ${bodyFont.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

```tsx
// apps/qgate-kpi/src/components/providers.tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";


export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx
export function QGateDashboardPage({ initialData }: { initialData: unknown | null }) {
  return (
    <main className="page-shell">
      <section className="hero-panel">
        <p className="eyebrow">PreAnalysis experimental frontend</p>
        <h1>QGate KPI Dashboard</h1>
        {initialData ? <p>Dashboard ready.</p> : <p>Loading dashboard data...</p>}
      </section>
    </main>
  );
}
```

```css
/* apps/qgate-kpi/app/globals.css */
:root {
  --bg: #08111f;
  --panel: rgba(11, 23, 38, 0.86);
  --panel-border: rgba(123, 173, 226, 0.18);
  --text: #e8f0f7;
  --muted: #8fa8bf;
  --accent: #18c29c;
  --accent-2: #53a6ff;
  --warn: #f6b73c;
  --danger: #ef7d7d;
  --radius-lg: 24px;
}

* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: radial-gradient(circle at top, #11345a 0%, #08111f 48%, #050a12 100%); color: var(--text); font-family: var(--font-body); }
.page-shell { max-width: 1440px; margin: 0 auto; padding: 32px 20px 80px; }
.hero-panel { background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius-lg); padding: 32px; box-shadow: 0 30px 60px rgba(0, 0, 0, 0.28); }
.eyebrow { margin: 0 0 12px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent); font-size: 12px; }
h1 { margin: 0; font-family: var(--font-display); font-size: clamp(2.2rem, 4vw, 4.25rem); }
```

- [ ] **Step 5: Run the smoke test again**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: PASS with `1 passed`.

### Task 4: Add The Typed Data Layer And Server-Side Initial Fetch

**Files:**
- Create: `apps/qgate-kpi/src/lib/types.ts`
- Create: `apps/qgate-kpi/src/lib/api.ts`
- Create: `apps/qgate-kpi/src/lib/query-options.ts`
- Create: `apps/qgate-kpi/src/lib/payload-adapter.ts`
- Create: `apps/qgate-kpi/src/lib/default-filters.ts`
- Create: `apps/qgate-kpi/app/page.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/payload-adapter.test.ts`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/payload-adapter.test.ts`

- [ ] **Step 1: Write a failing adapter test for the column/row payload format**

```ts
import { adaptDashboardPayload } from "../../lib/payload-adapter";


it("maps coverage, tickets, and issues rows into typed records", () => {
  const adapted = adaptDashboardPayload({
    generated_from: { defect_dir: "qgate/defect", history_dir: "qgate/history", teams: ["DTSV_China"], min_transition_count: 1 },
    overview: { team_count: 1, total_defects: 4, history_ok: 3, history_bad: 1, history_success_rate: 75, transition_samples: 2, unique_transitions: 1, unique_tickets: 1, changed_by_count: 1, timespan_max: 3 },
    insights: ["Coverage risk is concentrated in DTSV_China."],
    options: { teams: ["DTSV_China"], years: ["2026"], groups: ["Q-Gate"], changedBy: ["Alice"], fif: ["Global"], timespanMax: 3 },
    meta: { columns: ["Team", "Defects", "History_OK", "History_Missing_or_Error"], rows: [["DTSV_China", 4, 3, 1]] },
    coverage: { columns: ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"], rows: [["DTSV_China", "2026", 4, 3, 1]] },
    tickets: { columns: ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"], rows: [["1001", "https://octane/1001", "Ticket 1001", "Alice"]] },
    issues: { columns: ["Year", "Team", "Ticket_ID", "Phase_Transition", "Group", "Duration_Hours", "Changed_By", "FiF", "Ticket_Timespan_Days"], rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 3]] },
  });

  expect(adapted.coverage[0].historyOk).toBe(3);
  expect(adapted.tickets[0].ticketId).toBe("1001");
  expect(adapted.issues[0].phaseTransition).toBe("02-QGate -> 03-Analysis");
});
```

- [ ] **Step 2: Run the adapter test to verify it fails**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/payload-adapter.test.ts`

Expected: FAIL because the adapter and schema files do not exist yet.

- [ ] **Step 3: Implement the schemas, fetchers, query options, and server-side initial fetch**

```ts
// apps/qgate-kpi/src/lib/types.ts
import { z } from "zod";


export const datasetSchema = z.object({
  columns: z.array(z.string()),
  rows: z.array(z.array(z.any())),
});

export const qgateDashboardPayloadSchema = z.object({
  generated_from: z.object({
    defect_dir: z.string(),
    history_dir: z.string(),
    teams: z.array(z.string()),
    min_transition_count: z.number(),
  }),
  overview: z.object({
    team_count: z.number(),
    total_defects: z.number(),
    history_ok: z.number(),
    history_bad: z.number(),
    history_success_rate: z.number(),
    transition_samples: z.number(),
    unique_transitions: z.number(),
    unique_tickets: z.number(),
    changed_by_count: z.number(),
    timespan_max: z.number(),
  }),
  insights: z.array(z.string()),
  options: z.object({
    teams: z.array(z.string()),
    years: z.array(z.string()),
    groups: z.array(z.string()),
    changedBy: z.array(z.string()),
    fif: z.array(z.string()),
    timespanMax: z.number(),
  }),
  meta: datasetSchema,
  coverage: datasetSchema,
  tickets: datasetSchema,
  issues: datasetSchema,
});

export type QGateDashboardPayload = z.infer<typeof qgateDashboardPayloadSchema>;
```

```ts
// apps/qgate-kpi/src/lib/api.ts
import { qgateDashboardPayloadSchema } from "./types";


const API_BASE = process.env.NEXT_PUBLIC_QGATE_API_BASE ?? "http://127.0.0.1:8001";


export async function fetchQGateDashboard(params: URLSearchParams = new URLSearchParams()) {
  const response = await fetch(`${API_BASE}/api/qgate/kpi-dashboard?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`QGate dashboard request failed with ${response.status}`);
  }
  return qgateDashboardPayloadSchema.parse(await response.json());
}
```

```ts
// apps/qgate-kpi/src/lib/default-filters.ts
export const defaultFilters = {
  teams: [] as string[],
  years: [] as string[],
  groups: [] as string[],
  changedBy: "",
  fif: "",
  timespanMin: 0,
  timespanMax: 0,
  minTransitionCount: 200,
};
```

```ts
// apps/qgate-kpi/src/lib/query-options.ts
import { fetchQGateDashboard } from "./api";


export function qgateDashboardQueryOptions(params: URLSearchParams = new URLSearchParams()) {
  const serialized = params.toString();
  return {
    queryKey: ["qgate-dashboard", serialized || "default"],
    queryFn: () => fetchQGateDashboard(params),
  };
}
```

```ts
// apps/qgate-kpi/src/lib/payload-adapter.ts
import type { QGateDashboardPayload } from "./types";


function rowsToObjects<T extends Record<string, unknown>>(columns: string[], rows: unknown[][]): T[] {
  return rows.map((row) => Object.fromEntries(columns.map((column, index) => [column, row[index]])) as T);
}


export function adaptDashboardPayload(payload: QGateDashboardPayload) {
  return {
    overview: payload.overview,
    insights: payload.insights,
    options: payload.options,
    meta: rowsToObjects<{ Team: string; Defects: number; History_OK: number; History_Missing_or_Error: number }>(payload.meta.columns, payload.meta.rows),
    coverage: rowsToObjects<{ Team: string; Year: string; Defects: number; History_OK: number; History_Missing_or_Error: number }>(payload.coverage.columns, payload.coverage.rows).map((row) => ({
      team: String(row.Team),
      year: String(row.Year),
      defects: Number(row.Defects),
      historyOk: Number(row.History_OK),
      historyBad: Number(row.History_Missing_or_Error),
    })),
    tickets: rowsToObjects<{ Ticket_ID: string; Ticket_URL: string; Ticket_Name: string; Tester: string }>(payload.tickets.columns, payload.tickets.rows).map((row) => ({
      ticketId: String(row.Ticket_ID),
      ticketUrl: String(row.Ticket_URL),
      ticketName: String(row.Ticket_Name),
      tester: String(row.Tester),
    })),
    issues: rowsToObjects<{ Year: string; Team: string; Ticket_ID: string; Phase_Transition: string; Group: string; Duration_Hours: number; Changed_By: string; FiF: string; Ticket_Timespan_Days: number }>(payload.issues.columns, payload.issues.rows).map((row) => ({
      year: String(row.Year),
      team: String(row.Team),
      ticketId: String(row.Ticket_ID),
      phaseTransition: String(row.Phase_Transition),
      group: String(row.Group),
      durationHours: Number(row.Duration_Hours),
      changedBy: String(row.Changed_By),
      fif: String(row.FiF),
      ticketTimespanDays: Number(row.Ticket_Timespan_Days),
    })),
  };
}
```

```tsx
// apps/qgate-kpi/app/page.tsx
import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query";

import { fetchQGateDashboard } from "../src/lib/api";
import { QGateDashboardPage } from "../src/features/qgate-dashboard/dashboard-page";


export default async function Page() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: ["qgate-dashboard", "default"],
    queryFn: () => fetchQGateDashboard(),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <QGateDashboardPage initialData={queryClient.getQueryData(["qgate-dashboard", "default"]) ?? null} />
    </HydrationBoundary>
  );
}
```

- [ ] **Step 4: Run the adapter test again**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/payload-adapter.test.ts`

Expected: PASS.

### Task 5: Implement The First Screen Workbench

**Files:**
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/state-banner.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/hero-kpis.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/insights-strip.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/filter-bar.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/coverage-panel.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/summary-panel.tsx`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Modify: `apps/qgate-kpi/app/globals.css`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

- [ ] **Step 1: Extend the frontend test so the first screen must render KPIs, insights, and filters from typed data**

```tsx
import { render, screen } from "@testing-library/react";

import { QGateDashboardPage } from "../dashboard-page";


const samplePayload = {
  generated_from: { defect_dir: "qgate/defect", history_dir: "qgate/history", teams: ["DTSV_China"], min_transition_count: 1 },
  overview: { team_count: 1, total_defects: 4, history_ok: 3, history_bad: 1, history_success_rate: 75, transition_samples: 2, unique_transitions: 1, unique_tickets: 1, changed_by_count: 1, timespan_max: 3 },
  insights: ["Coverage risk is concentrated in DTSV_China."],
  options: { teams: ["DTSV_China"], years: ["2026"], groups: ["Q-Gate"], changedBy: ["Alice"], fif: ["Global"], timespanMax: 3 },
  meta: { columns: ["Team", "Defects", "History_OK", "History_Missing_or_Error"], rows: [["DTSV_China", 4, 3, 1]] },
  coverage: { columns: ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"], rows: [["DTSV_China", "2026", 4, 3, 1]] },
  tickets: { columns: ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"], rows: [["1001", "https://octane/1001", "Ticket 1001", "Alice"]] },
  issues: { columns: ["Year", "Team", "Ticket_ID", "Phase_Transition", "Group", "Duration_Hours", "Changed_By", "FiF", "Ticket_Timespan_Days"], rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 3]] },
};


it("renders hero metrics, insight cards, and the global filter bar", () => {
  render(<QGateDashboardPage initialData={samplePayload} />);

  expect(screen.getByText("Total defects")).toBeInTheDocument();
  expect(screen.getByText("4")).toBeInTheDocument();
  expect(screen.getByText("Coverage risk is concentrated in DTSV_China.")).toBeInTheDocument();
  expect(screen.getByLabelText("Teams")).toBeInTheDocument();
  expect(screen.getByText("Team coverage")).toBeInTheDocument();
  expect(screen.getByText("Team x Group efficiency")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the dashboard render test to verify it fails**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: FAIL because the page still renders only the basic shell.

- [ ] **Step 3: Implement the first screen sections and client-side linked selection state**

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/hero-kpis.tsx
export function HeroKpis({ overview }: { overview: { total_defects: number; history_success_rate: number; transition_samples: number; unique_tickets: number } }) {
  const cards = [
    { label: "Total defects", value: overview.total_defects },
    { label: "History success", value: `${overview.history_success_rate}%` },
    { label: "Transition samples", value: overview.transition_samples },
    { label: "Unique tickets", value: overview.unique_tickets },
  ];
  return (
    <section className="kpi-grid">
      {cards.map((card) => (
        <article key={card.label} className="metric-card">
          <p>{card.label}</p>
          <strong>{card.value}</strong>
        </article>
      ))}
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/insights-strip.tsx
export function InsightsStrip({ insights }: { insights: string[] }) {
  return (
    <section className="insight-grid">
      {insights.map((insight) => (
        <article key={insight} className="panel insight-card">
          <p>{insight}</p>
        </article>
      ))}
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/filter-bar.tsx
type FilterState = {
  teams: string[];
  years: string[];
  groups: string[];
  changedBy: string;
  fif: string;
  timespanMin: number;
  timespanMax: number;
  minTransitionCount: number;
};


export function FilterBar({ options, filters, onChange, onReset }: { options: { teams: string[]; years: string[]; groups: string[]; changedBy: string[]; fif: string[]; timespanMax: number }; filters: FilterState; onChange: (next: FilterState) => void; onReset: () => void }) {
  return (
    <section className="panel stack-gap">
      <div className="section-head">
        <h2>Global filters</h2>
        <button type="button" onClick={onReset}>Reset</button>
      </div>
      <div className="filter-grid">
        <label>
          <span>Teams</span>
          <select aria-label="Teams" multiple value={filters.teams} onChange={(event) => onChange({ ...filters, teams: Array.from(event.target.selectedOptions).map((option) => option.value) })}>
            {options.teams.map((team) => <option key={team} value={team}>{team}</option>)}
          </select>
        </label>
        <label>
          <span>Changed By</span>
          <select aria-label="Changed By" value={filters.changedBy} onChange={(event) => onChange({ ...filters, changedBy: event.target.value })}>
            <option value="">All</option>
            {options.changedBy.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/coverage-panel.tsx
export function CoveragePanel({ coverage, selectedTeam, onSelectTeam }: { coverage: Array<{ team: string; year: string; defects: number; historyOk: number; historyBad: number }>; selectedTeam: string | null; onSelectTeam: (team: string) => void }) {
  return (
    <section className="panel stack-gap">
      <div className="section-head">
        <h2>Team coverage</h2>
      </div>
      {coverage.map((row) => (
        <button key={`${row.team}-${row.year}`} type="button" className={row.team === selectedTeam ? "coverage-row is-active" : "coverage-row"} onClick={() => onSelectTeam(row.team)}>
          <span>{row.team}</span>
          <span>{row.historyOk}/{row.defects}</span>
        </button>
      ))}
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/summary-panel.tsx
export function SummaryPanel({ issues, selectedTeam }: { issues: Array<{ team: string; group: string; durationHours: number }>; selectedTeam: string | null }) {
  const scoped = issues.filter((issue) => !selectedTeam || issue.team === selectedTeam);
  const totals = Object.entries(
    scoped.reduce<Record<string, number>>((accumulator, issue) => {
      accumulator[issue.group] = (accumulator[issue.group] ?? 0) + issue.durationHours;
      return accumulator;
    }, {}),
  );

  return (
    <section className="panel stack-gap">
      <div className="section-head">
        <h2>Team x Group efficiency</h2>
      </div>
      <ul className="summary-list">
        {totals.map(([group, total]) => (
          <li key={group}><span>{group}</span><strong>{Math.round(total)}h</strong></li>
        ))}
      </ul>
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx
"use client";

import { useState } from "react";

import { adaptDashboardPayload } from "../../lib/payload-adapter";
import { CoveragePanel } from "./components/coverage-panel";
import { FilterBar } from "./components/filter-bar";
import { HeroKpis } from "./components/hero-kpis";
import { InsightsStrip } from "./components/insights-strip";
import { SummaryPanel } from "./components/summary-panel";


export function QGateDashboardPage({ initialData }: { initialData: any }) {
  if (!initialData) {
    return (
      <main className="page-shell">
        <section className="hero-panel">
          <p className="eyebrow">PreAnalysis experimental frontend</p>
          <h1>QGate KPI Dashboard</h1>
          <p>Loading dashboard data...</p>
        </section>
      </main>
    );
  }

  const adapted = adaptDashboardPayload(initialData);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(adapted.coverage[0]?.team ?? null);
  const [filters, setFilters] = useState({
    teams: adapted.options.teams,
    years: adapted.options.years,
    groups: adapted.options.groups,
    changedBy: "",
    fif: "",
    timespanMin: 0,
    timespanMax: adapted.options.timespanMax,
    minTransitionCount: initialData.generated_from.min_transition_count,
  });

  return (
    <main className="page-shell dashboard-stack">
      <section className="hero-panel stack-gap">
        <p className="eyebrow">PreAnalysis experimental frontend</p>
        <h1>QGate KPI Dashboard</h1>
        <HeroKpis overview={adapted.overview} />
      </section>
      <InsightsStrip insights={adapted.insights} />
      <FilterBar options={adapted.options} filters={filters} onChange={setFilters} onReset={() => setFilters({ ...filters, teams: adapted.options.teams, years: adapted.options.years, groups: adapted.options.groups, changedBy: "", fif: "", timespanMin: 0, timespanMax: adapted.options.timespanMax })} />
      <div className="dashboard-grid">
        <CoveragePanel coverage={adapted.coverage} selectedTeam={selectedTeam} onSelectTeam={setSelectedTeam} />
        <SummaryPanel issues={adapted.issues} selectedTeam={selectedTeam} />
      </div>
    </main>
  );
}
```

- [ ] **Step 4: Run the dashboard render test again**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: PASS.

### Task 6: Implement The Second Screen, Explicit States, And Startup Docs

**Files:**
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/transition-panel.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/components/ticket-drilldown.tsx`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/components/state-banner.tsx`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Modify: `apps/qgate-kpi/app/globals.css`
- Create: `docs/qgate-next-dashboard-dev.md`
- Modify: `README.md`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

- [ ] **Step 1: Add failing tests for the explicit error state and the drilldown section**

```tsx
it("shows the empty-state banner when the payload has no issues", () => {
  render(<QGateDashboardPage initialData={{ ...samplePayload, issues: { columns: samplePayload.issues.columns, rows: [] } }} />);

  expect(screen.getByText("No rows match the current filter scope.")).toBeInTheDocument();
});


it("renders the drilldown table for the active team selection", () => {
  render(<QGateDashboardPage initialData={samplePayload} />);

  expect(screen.getByText("Ticket drilldown")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Ticket 1001" })).toHaveAttribute("href", "https://octane/1001");
});
```

- [ ] **Step 2: Run the dashboard test suite to verify the new cases fail**

Run: `Set-Location .\apps\qgate-kpi; npm run test -- --run src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: FAIL because the second screen and state banners are not implemented yet.

- [ ] **Step 3: Implement the second-screen panels and explicit state handling**

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/state-banner.tsx
export function StateBanner({ kind, message }: { kind: "partial" | "empty" | "error"; message: string }) {
  return <div className={`state-banner state-${kind}`}>{message}</div>;
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/transition-panel.tsx
export function TransitionPanel({ issues }: { issues: Array<{ phaseTransition: string; durationHours: number }> }) {
  const rows = Object.entries(
    issues.reduce<Record<string, number>>((accumulator, issue) => {
      accumulator[issue.phaseTransition] = (accumulator[issue.phaseTransition] ?? 0) + issue.durationHours;
      return accumulator;
    }, {}),
  ).sort((left, right) => right[1] - left[1]);

  return (
    <section className="panel stack-gap">
      <div className="section-head">
        <h2>Transition analysis</h2>
      </div>
      <ul className="summary-list">
        {rows.map(([transition, totalHours]) => (
          <li key={transition}><span>{transition}</span><strong>{Math.round(totalHours)}h</strong></li>
        ))}
      </ul>
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/components/ticket-drilldown.tsx
export function TicketDrilldown({ tickets }: { tickets: Array<{ ticketId: string; ticketName: string; ticketUrl: string; tester: string }> }) {
  return (
    <section className="panel stack-gap">
      <div className="section-head">
        <h2>Ticket drilldown</h2>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Tester</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.ticketId}>
              <td><a href={ticket.ticketUrl} target="_blank" rel="noreferrer">{ticket.ticketName}</a></td>
              <td>{ticket.tester}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

```tsx
// apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx
import { StateBanner } from "./components/state-banner";
import { TicketDrilldown } from "./components/ticket-drilldown";
import { TransitionPanel } from "./components/transition-panel";


const visibleIssues = adapted.issues.filter((issue) => !selectedTeam || issue.team === selectedTeam);
const visibleTickets = adapted.tickets.filter((ticket) => visibleIssues.some((issue) => issue.ticketId === ticket.ticketId));
const historyBadTotal = adapted.meta.reduce((sum, row) => sum + Number(row.History_Missing_or_Error ?? 0), 0);

return (
  <main className="page-shell dashboard-stack">
    {historyBadTotal > 0 ? <StateBanner kind="partial" message="History coverage is partial for the current scope." /> : null}
    {visibleIssues.length === 0 ? <StateBanner kind="empty" message="No rows match the current filter scope." /> : null}
    <section className="second-screen-grid">
      <TransitionPanel issues={visibleIssues} />
      <TicketDrilldown tickets={visibleTickets} />
    </section>
  </main>
);
```

- [ ] **Step 4: Add startup documentation for both services**

```md
# QGate Next Dashboard Dev Startup

## 1. Start the Python API

Run `.\.venv\Scripts\python.exe -m uvicorn qgate_api:app --host 127.0.0.1 --port 8001`

Expected: `Uvicorn running on http://127.0.0.1:8001`

## 2. Start the Next.js app

Run `Set-Location .\apps\qgate-kpi`

Run `$env:NEXT_PUBLIC_QGATE_API_BASE = 'http://127.0.0.1:8001'`

Run `npm run dev`

Expected: Next.js serves `http://127.0.0.1:3001`

## 3. Verification

Run `.\.venv\Scripts\python.exe -m pytest tests/test_qgate_kpi_payload.py tests/test_qgate_api.py -q`

Run `Set-Location .\apps\qgate-kpi`

Run `npm run test`

Run `npm run build`
```

- [ ] **Step 5: Run full verification for the frontend and backend slices**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_qgate_kpi_payload.py tests/test_qgate_api.py -q`

Expected: PASS.

Run: `Set-Location .\apps\qgate-kpi; npm run test`

Expected: PASS.

Run: `Set-Location .\apps\qgate-kpi; npm run build`

Expected: PASS with a production build summary.

## Spec Coverage Check

- Scope: covered by Task 2 for the Python API and Tasks 3-6 for the standalone Next.js app.
- Data parity: covered by Task 1 reusing the existing report generator path and Task 2 exposing the same payload families.
- UX direction: covered by Task 3 token shell and Tasks 5-6 for the workbench layout.
- Interaction model: covered by Task 5 linked team selection and Task 6 drilldown.
- Explicit loading, empty, error, and partial states: covered by Tasks 3 and 6.
- Extensibility toward Top Issue and Test Coverage: covered by the app-shell and shared lib/component boundaries in Tasks 3-6.

## Placeholder Scan

- Confirm there are no unresolved placeholder phrases from the `No Placeholders` rule anywhere in this plan.
- Confirm every executable step includes either concrete code, an exact command, or both.
- Confirm all paths in commands match the file map above.
