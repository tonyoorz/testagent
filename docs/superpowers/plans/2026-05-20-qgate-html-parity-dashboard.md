# QGate HTML-Parity Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the experimental QGate Next.js page so it visually aligns with the existing static HTML dashboard, supports live frontend filters, removes ticket drilldown, and preserves the fast non-blocking bootstrap.

**Architecture:** Keep the current route bootstrap and typed payload adapter intact, then add a ready-state-only local filtering layer inside the QGate feature. Split the page into smaller React components for hero, filters, coverage, transition analysis, and summary so the UI can converge on the HTML dashboard without reintroducing backend round-trips for every interaction.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Testing Library, CSS variables in `app/globals.css`

---

## File Map

- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filtering.ts`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filtering.test.ts`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filters.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-sections.tsx`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Modify: `apps/qgate-kpi/app/globals.css`
- Modify: `README.md`

### Task 1: Add local filtering primitives

**Files:**
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filtering.ts`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filtering.test.ts`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filtering.test.ts`

- [ ] **Step 1: Write the failing filter derivation test**

```ts
import { describe, expect, it } from "vitest";

import type { QGateDashboardFilters, QGateDashboardViewModel } from "../../lib/types";

import { applyDashboardFilters, createDashboardFilterOptionsSummary } from "./dashboard-filtering";

const sampleData: QGateDashboardViewModel = {
  generatedFrom: {
    defectDir: "qgate/defect",
    historyDir: "qgate/history",
    teams: ["DTSV_China", "DTSV_CE"],
    minTransitionCount: 200,
  },
  overview: {
    teamCount: 2,
    totalDefects: 6,
    historyOk: 4,
    historyBad: 2,
    historySuccessRate: 66.7,
    transitionSamples: 3,
    uniqueTransitions: 2,
    uniqueTickets: 2,
    changedByCount: 2,
    timespanMax: 5,
  },
  insights: ["Seed insight"],
  options: {
    teams: ["DTSV_China", "DTSV_CE"],
    years: ["2025", "2026"],
    groups: ["Q-Gate", "CoC"],
    changedBy: ["Alice", "Bob"],
    fif: ["Global", "Local"],
    timespanMax: 5,
  },
  metaRows: [
    { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
  ],
  coverageRows: [
    { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    { team: "DTSV_CE", year: "2025", defects: 2, historyOk: 1, historyMissingOrError: 1 },
  ],
  ticketRows: [],
  issueRows: [
    {
      year: "2026",
      team: "DTSV_China",
      ticketId: "1001",
      phaseTransition: "02-QGate -> 03-Analysis",
      group: "Q-Gate",
      durationHours: 24,
      changedBy: "Alice",
      fif: "Global",
      ticketTimespanDays: 2,
    },
    {
      year: "2025",
      team: "DTSV_CE",
      ticketId: "1002",
      phaseTransition: "03-Analysis -> 04-Fix",
      group: "CoC",
      durationHours: 12,
      changedBy: "Bob",
      fif: "Local",
      ticketTimespanDays: 1,
    },
  ],
};

function buildFilters(overrides: Partial<QGateDashboardFilters>): QGateDashboardFilters {
  return {
    defectDir: "qgate/defect",
    historyDir: "qgate/history",
    teams: [],
    years: [],
    groups: [],
    changedBy: [],
    fif: [],
    timespanMin: 0,
    timespanMax: null,
    minTransitionCount: 200,
    analysisWorkers: 0,
    cacheDir: "qgate_cache",
    useCache: true,
    ...overrides,
  };
}

describe("applyDashboardFilters", () => {
  it("filters issue and coverage rows by the active chips and numeric inputs", () => {
    const result = applyDashboardFilters(
      sampleData,
      buildFilters({
        teams: ["DTSV_China"],
        years: ["2026"],
        groups: ["Q-Gate"],
        changedBy: ["Alice"],
        fif: ["Global"],
        timespanMin: 1,
        timespanMax: 3,
      }),
    );

    expect(result.issueRows).toHaveLength(1);
    expect(result.issueRows[0]?.ticketId).toBe("1001");
    expect(result.coverageRows).toEqual([
      { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    ]);
    expect(result.metaRows).toEqual([
      { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    ]);
  });

  it("builds a compact active-filter summary for the UI", () => {
    const summary = createDashboardFilterOptionsSummary(
      buildFilters({ teams: ["DTSV_China"], groups: ["Q-Gate"], changedBy: ["Alice"] }),
    );

    expect(summary).toEqual(["1 team", "1 group", "Alice", "Timespan >= 0d", "Min transitions 200"]);
  });
});
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `Push-Location apps/qgate-kpi ; npm run test -- src/features/qgate-dashboard/dashboard-filtering.test.ts`

Expected: FAIL with `Cannot find module './dashboard-filtering'` or missing export errors.

- [ ] **Step 3: Write the minimal filter derivation implementation**

```ts
import type {
  QGateCoverageRow,
  QGateDashboardFilters,
  QGateDashboardViewModel,
  QGateIssueRow,
  QGateMetaRow,
} from "../../lib/types";

type FilteredDashboardData = Pick<QGateDashboardViewModel, "metaRows" | "coverageRows" | "issueRows">;

function matchesListFilter(activeValues: string[], candidate: string) {
  return activeValues.length === 0 || activeValues.includes(candidate);
}

function matchesTimespan(issue: QGateIssueRow, filters: QGateDashboardFilters) {
  const value = issue.ticketTimespanDays;

  if (value === null) {
    return filters.timespanMax === null;
  }

  if (value < filters.timespanMin) {
    return false;
  }

  return filters.timespanMax === null || value <= filters.timespanMax;
}

function buildMetaRows(coverageRows: QGateCoverageRow[]): QGateMetaRow[] {
  return Array.from(
    coverageRows.reduce((accumulator, row) => {
      const current = accumulator.get(row.team) ?? {
        team: row.team,
        defects: 0,
        historyOk: 0,
        historyMissingOrError: 0,
      };

      current.defects += row.defects;
      current.historyOk += row.historyOk;
      current.historyMissingOrError += row.historyMissingOrError;
      accumulator.set(row.team, current);
      return accumulator;
    }, new Map<string, QGateMetaRow>()),
  ).map(([, row]) => row);
}

export function applyDashboardFilters(
  viewModel: QGateDashboardViewModel,
  filters: QGateDashboardFilters,
): FilteredDashboardData {
  const issueRows = viewModel.issueRows.filter(
    (row) =>
      matchesListFilter(filters.teams, row.team) &&
      matchesListFilter(filters.years, row.year) &&
      matchesListFilter(filters.groups, row.group) &&
      matchesListFilter(filters.changedBy, row.changedBy) &&
      matchesListFilter(filters.fif, row.fif) &&
      matchesTimespan(row, filters),
  );

  const coverageRows = viewModel.coverageRows.filter(
    (row) => matchesListFilter(filters.teams, row.team) && matchesListFilter(filters.years, row.year),
  );

  return {
    issueRows,
    coverageRows,
    metaRows: buildMetaRows(coverageRows),
  };
}

export function createDashboardFilterOptionsSummary(filters: QGateDashboardFilters) {
  const summary: string[] = [];

  if (filters.teams.length > 0) {
    summary.push(`${filters.teams.length} team` + (filters.teams.length > 1 ? "s" : ""));
  }

  if (filters.groups.length > 0) {
    summary.push(`${filters.groups.length} group` + (filters.groups.length > 1 ? "s" : ""));
  }

  if (filters.changedBy.length === 1) {
    summary.push(filters.changedBy[0]);
  }

  summary.push(`Timespan >= ${filters.timespanMin}d`);
  summary.push(`Min transitions ${filters.minTransitionCount}`);

  return summary;
}
```

- [ ] **Step 4: Run the filter test to verify it passes**

Run: `Push-Location apps/qgate-kpi ; npm run test -- src/features/qgate-dashboard/dashboard-filtering.test.ts`

Expected: PASS with 2 tests passed.

### Task 2: Add parity-focused page tests before the UI rewrite

**Files:**
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

- [ ] **Step 1: Add failing tests for filters, reset behavior, and ticket removal**

```ts
it("renders the HTML-parity filter section in ready state", () => {
  render(<QGateDashboardPage state="ready" initialData={sampleDashboardData} />);

  expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "All years" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "All teams" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reset filters" })).toBeInTheDocument();
});

it("updates the visible dashboard sections when filters change and reset", async () => {
  const user = userEvent.setup();

  render(
    <QGateDashboardPage
      state="ready"
      initialData={{
        ...sampleDashboardData,
        coverageRows: [
          { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
          { team: "DTSV_CE", year: "2025", defects: 2, historyOk: 1, historyMissingOrError: 1 },
        ],
        metaRows: [
          { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
          { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
        ],
        issueRows: [
          ...sampleDashboardData.issueRows,
          {
            year: "2025",
            team: "DTSV_CE",
            ticketId: "1002",
            phaseTransition: "03-Analysis -> 04-Fix",
            group: "CoC",
            durationHours: 12,
            changedBy: "Bob",
            fif: "Global",
            ticketTimespanDays: 1,
          },
        ],
      }}
    />,
  );

  await user.click(screen.getByRole("button", { name: "DTSV_CE" }));

  expect(screen.getByText("03-Analysis -> 04-Fix")).toBeInTheDocument();
  expect(screen.queryByText("02-QGate -> 03-Analysis")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Reset filters" }));

  expect(screen.getByText("02-QGate -> 03-Analysis")).toBeInTheDocument();
  expect(screen.getByText("03-Analysis -> 04-Fix")).toBeInTheDocument();
});

it("does not render the old ticket watch section in ready state", () => {
  render(<QGateDashboardPage state="ready" initialData={sampleDashboardData} />);

  expect(screen.queryByText("Most active tickets")).not.toBeInTheDocument();
  expect(screen.queryByText("Ticket watch")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the page test to verify it fails**

Run: `Push-Location apps/qgate-kpi ; npm run test -- src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: FAIL because the current page has no filter section and still renders the ticket panel.

- [ ] **Step 3: Adjust test imports for user interaction support**

```ts
import userEvent from "@testing-library/user-event";

import { render, screen } from "@testing-library/react";
```

- [ ] **Step 4: Re-run the page test and keep it failing only on missing implementation**

Run: `Push-Location apps/qgate-kpi ; npm run test -- src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: FAIL on the new assertions, with no import or setup errors.

### Task 3: Implement the new ready-state dashboard composition

**Files:**
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-filters.tsx`
- Create: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-sections.tsx`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

- [ ] **Step 1: Add the filter bar component**

```tsx
import type { QGateDashboardFilters, QGateDashboardOptions } from "../../lib/types";

type DashboardFiltersProps = {
  filters: QGateDashboardFilters;
  options: QGateDashboardOptions;
  summary: string[];
  onToggleValue: (field: "years" | "teams" | "groups", value: string) => void;
  onSelectValue: (field: "changedBy" | "fif", value: string) => void;
  onNumberChange: (field: "timespanMin" | "timespanMax" | "minTransitionCount", value: number | null) => void;
  onReset: () => void;
};

function FilterChip({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button className={active ? "filter-chip is-active" : "filter-chip"} onClick={onClick} type="button">
      {children}
    </button>
  );
}

export function QGateDashboardFilters({ filters, options, summary, onToggleValue, onSelectValue, onNumberChange, onReset }: DashboardFiltersProps) {
  return (
    <section className="filter-panel" aria-label="Dashboard filters">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Scope</p>
          <h2>Filters</h2>
        </div>
        <button className="filter-reset" onClick={onReset} type="button">
          Reset filters
        </button>
      </div>

      <div className="filter-group">
        <p className="filter-label">Years</p>
        <div className="chip-row">
          <FilterChip active={filters.years.length === 0} onClick={() => onToggleValue("years", "__all__")}>All years</FilterChip>
          {options.years.map((year) => (
            <FilterChip key={year} active={filters.years.includes(year)} onClick={() => onToggleValue("years", year)}>
              {year}
            </FilterChip>
          ))}
        </div>
      </div>

      <div className="filter-summary" aria-label="Active filters">
        {summary.map((item) => (
          <span className="filter-summary-chip" key={item}>{item}</span>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Add section components without ticket drilldown**

```tsx
type CoverageSectionProps = {
  coverageRows: Array<{ team: string; year: string; defects: number; historyOk: number; historyMissingOrError: number }>;
  metaRows: Array<{ team: string; defects: number; historyOk: number; historyMissingOrError: number }>;
};

type TransitionSectionProps = {
  issueRows: Array<{ phaseTransition: string; durationHours: number; team: string }>;
};

export function QGateCoverageSection({ coverageRows, metaRows }: CoverageSectionProps) {
  return (
    <article className="workbench-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">A</p>
          <h2>Team Coverage</h2>
        </div>
      </div>
      <div className="coverage-table" role="table" aria-label="Team coverage">
        {metaRows.map((row) => (
          <div className="coverage-table-row" key={row.team} role="row">
            <span role="cell">{row.team}</span>
            <span role="cell">{row.historyOk}/{row.defects}</span>
            <span role="cell">{row.historyMissingOrError}</span>
            <span role="cell">{coverageRows.filter((item) => item.team === row.team).length} years</span>
          </div>
        ))}
      </div>
    </article>
  );
}

export function QGateTransitionSection({ issueRows }: TransitionSectionProps) {
  const groups = Array.from(
    issueRows.reduce((accumulator, row) => {
      const current = accumulator.get(row.phaseTransition) ?? { phaseTransition: row.phaseTransition, count: 0, durationHours: 0 };
      current.count += 1;
      current.durationHours += row.durationHours;
      accumulator.set(row.phaseTransition, current);
      return accumulator;
    }, new Map<string, { phaseTransition: string; count: number; durationHours: number }>()),
  ).map(([, row]) => row);

  return (
    <article className="workbench-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">B</p>
          <h2>Transition Analysis</h2>
        </div>
      </div>
      <div className="stack-list" aria-label="Transition analysis">
        {groups.map((row) => (
          <article className="stack-item" key={row.phaseTransition}>
            <p className="stack-title">{row.phaseTransition}</p>
            <div className="stack-meta">
              <span>{row.count} samples</span>
              <span>{(row.durationHours / row.count).toFixed(1)}h avg</span>
            </div>
          </article>
        ))}
      </div>
    </article>
  );
}
```

- [ ] **Step 3: Rewrite the page ready state around local filters**

```tsx
const [filters, setFilters] = useState(() => getDefaultQGateDashboardFilters());

const filteredData = useMemo(() => {
  if (state !== "ready") {
    return null;
  }

  return applyDashboardFilters(initialData, filters);
}, [filters, initialData, state]);

function toggleMultiValue(field: "years" | "teams" | "groups", value: string) {
  setFilters((current) => {
    if (value === "__all__") {
      return { ...current, [field]: [] };
    }

    const nextValues = current[field].includes(value)
      ? current[field].filter((item) => item !== value)
      : [...current[field], value];

    return { ...current, [field]: nextValues };
  });
}

function resetFilters() {
  setFilters(getDefaultQGateDashboardFilters());
}

{state === "ready" ? (
  <>
    <QGateDashboardFilters
      filters={filters}
      options={initialData.options}
      summary={createDashboardFilterOptionsSummary(filters)}
      onToggleValue={toggleMultiValue}
      onSelectValue={(field, value) => setFilters((current) => ({ ...current, [field]: value ? [value] : [] }))}
      onNumberChange={(field, value) => setFilters((current) => ({ ...current, [field]: value }))}
      onReset={resetFilters}
    />

    <section className="dashboard-grid" aria-label="QGate workbench">
      <QGateCoverageSection coverageRows={filteredData?.coverageRows ?? []} metaRows={filteredData?.metaRows ?? []} />
      <QGateTransitionSection issueRows={filteredData?.issueRows ?? []} />
      <QGateSummarySection coverageRows={filteredData?.coverageRows ?? []} issueRows={filteredData?.issueRows ?? []} />
    </section>
  </>
) : null}
```

- [ ] **Step 4: Run the page test to verify it passes**

Run: `Push-Location apps/qgate-kpi ; npm run test -- src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: PASS with the new filter and no-ticket assertions.

### Task 4: Apply the HTML-parity visual system and source copy

**Files:**
- Modify: `apps/qgate-kpi/app/globals.css`
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Modify: `README.md`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

- [ ] **Step 1: Add the filter and section styling in `globals.css`**

```css
:root {
  --color-canvas: #eef3f8;
  --color-card-surface: #ffffff;
  --color-hero-start: #0d376d;
  --color-hero-end: #071f45;
  --color-chip-border: #b9cbe1;
  --color-chip-active: #0f5fb8;
  --color-chip-active-text: #ffffff;
}

.filter-panel {
  margin-top: 1rem;
  border: 1px solid #d5dfeb;
  border-radius: 1.5rem;
  background: var(--color-card-surface);
  color: #14324f;
  padding: 1.25rem;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.filter-chip {
  border: 1px solid var(--color-chip-border);
  border-radius: 999px;
  background: #f7fafd;
  color: #1d466f;
  padding: 0.55rem 0.9rem;
}

.filter-chip.is-active {
  border-color: var(--color-chip-active);
  background: var(--color-chip-active);
  color: var(--color-chip-active-text);
}

.filter-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1rem;
}
```

- [ ] **Step 2: Update source wording and remove read-only copy**

```tsx
<p className="hero-copy">
  A single-screen QGate workbench aligned with the existing KPI HTML dashboard. Defect scope is loaded from qgate defect files,
  while transition history follows the current database-first analysis path with file fallback when configured.
</p>

<div className="context-section">
  <p className="context-label">Data source</p>
  <p className="context-copy">Defect scope: {initialData.generatedFrom.defectDir}</p>
  <p className="context-copy">History path: database-first with file fallback, using {initialData.generatedFrom.historyDir} as the configured history directory.</p>
</div>
```

- [ ] **Step 3: Document the experimental frontend behavior in `README.md`**

```md
## QGate experimental frontend

The React-based QGate dashboard lives in `apps/qgate-kpi` and is intentionally separate from the Dash pages.

Start the backend API:

```powershell
Push-Location .
.\.venv\Scripts\python.exe -m uvicorn qgate_api:app --host 127.0.0.1 --port 8002 --reload
```

Start the frontend:

```powershell
Push-Location apps/qgate-kpi
$env:NEXT_PUBLIC_QGATE_API_BASE = "http://127.0.0.1:8002"
npm run dev
```

Current data source behavior is hybrid: defect scope comes from `qgate/defect`, while history analysis uses the existing database-first path with file fallback.
```

- [ ] **Step 4: Run the focused validation suite**

Run: `Push-Location apps/qgate-kpi ; npm run test -- src/features/qgate-dashboard/dashboard-filtering.test.ts src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`

Expected: PASS with filter derivation and dashboard page coverage both green.

- [ ] **Step 5: Run the final project validation**

Run: `Push-Location apps/qgate-kpi ; npm run lint ; npm run typecheck ; npm run build`

Expected: PASS for lint, TypeScript, and production build.

## Self-Review

### Spec coverage

- HTML-parity visual direction is covered by Task 4.
- Live frontend filters are covered by Task 1 and Task 3.
- Ticket drilldown removal is covered by Task 2 and Task 3.
- Hybrid data-source wording is covered by Task 4.
- Non-blocking bootstrap preservation is maintained because no task replaces `app/page.tsx` or `dashboard-bootstrap.tsx`.

### Placeholder scan

- No `TODO`, `TBD`, or `implement later` placeholders remain.
- Each task includes concrete files, concrete code, and explicit commands.

### Type consistency

- Filter state uses the existing `QGateDashboardFilters` type from `src/lib/types.ts`.
- New filtering helpers only derive `metaRows`, `coverageRows`, and `issueRows`, which matches the UI sections retained in scope.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-20-qgate-html-parity-dashboard.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?