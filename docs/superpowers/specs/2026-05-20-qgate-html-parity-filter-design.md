# QGate HTML-Parity Filter Design

## Goal

Bring the experimental Next.js QGate dashboard much closer to the existing static HTML dashboard in both look and interaction quality, while keeping the recently added non-blocking bootstrap behavior.

This phase should prove four things:

- the React frontend can visually align with [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html) instead of feeling like a different product
- the core filters can work in the browser immediately after the initial payload loads
- the page can drop ticket drilldown without losing the main management value of the dashboard
- the user-facing documentation and page copy can describe the real data source path accurately

## Scope

In scope for this phase:

- align the overall visual tone with [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html)
- restore a real Filters section in the Next.js page
- make the following filters effective in the frontend:
  - years
  - teams
  - groups
  - changed by
  - FiF
  - timespan min / max
  - min transition count
- update summary and chart/table sections when those filters change
- remove ticket drilldown from the React page
- remove or replace ticket-centric panels that only exist to support drilldown
- keep the non-blocking first render so the page still opens while the backend is slow
- explain the actual data-source behavior in page copy and/or docs

Out of scope for this phase:

- making every filter trigger a server refetch on each interaction
- rebuilding the backend aggregation model
- making the dashboard database-only end to end
- rebuilding the static HTML generator itself
- adding new routes or splitting the page into multiple screens

## Current State

The current static dashboard in [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html) contains:

- a strong blue header and KPI hero
- a dedicated Filters section with chips, selects, numeric inputs, and reset behavior
- team coverage bars
- transition analysis
- team × group efficiency summary
- summary table
- ticket drilldown

The current Next.js implementation in [apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx](apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx) is intentionally lighter:

- it uses a different visual hierarchy and tone
- it does not yet have working live filters
- it still includes ticket-oriented detail panels
- it already has better startup resilience because [apps/qgate-kpi/app/page.tsx](apps/qgate-kpi/app/page.tsx) no longer blocks forever on the slow API

## Product Intent

The refreshed page should answer this sequence:

1. What is the QGate health under the selected scope?
2. Which teams or groups are weak on history coverage?
3. Which transitions are creating the most pressure?
4. How does that picture change when the user narrows the current scope?

This is still a single-screen management workbench, not an analyst drilldown console.

## Chosen UX Direction

Use a high-parity React workbench derived from the static HTML layout, but trimmed for the current product goal.

Chosen characteristics:

- preserve the HTML dashboard's blue header, white panel canvas, chips, and stacked-summary visual language
- keep the page as one route and one screen
- keep interactive filters near the top of the page
- preserve coverage, transition analysis, and team × group summary
- remove ticket drilldown entirely

Rejected alternative:

- keep the current minimal React workbench and only tweak colors
  - rejected because it would leave the user with the same structural mismatch and missing interaction model

## Information Architecture

### Section 1: Hero header

Keep a bold top header aligned with the HTML dashboard:

- title
- generated/source summary
- hero KPI cards
- lead insight strip

The visual direction should closely follow the HTML dashboard's dark blue gradient and glass-card KPI treatment.

### Section 2: Filters

Add a proper filter area directly below the hero.

Required filter controls:

- years as chip toggles with `All`
- teams as chip toggles with `All` and `None`
- groups as chip toggles with `All`
- changed by as a select
- FiF as a select
- timespan min as numeric input
- timespan max as numeric input
- min transition count as numeric input
- reset button

Also include a compact selection summary row that mirrors the HTML dashboard's active-scope feedback.

### Section 3: A. Team Coverage

Retain a dedicated coverage section with stacked/segmented bars and clearer history completeness messaging.

This section should be filtered live in the browser.

### Section 4: B. Transition Analysis

Retain the transition analysis area and visually move it closer to the HTML version.

This section should emphasize:

- grouped transition patterns
- count and average duration
- clear ranking and hover/focus affordances

### Section 5: C. Phase Efficiency Summary

Retain the team × group summary with:

- legend
- grouped stacked summary bars
- summary table

This section should remain interactive only to the extent needed for filtering/highlighting within the summary itself. It should not open a ticket drilldown panel.

### Removed section

Do not include ticket drilldown.

The React page should also stop centering ticket-specific panels as a primary section if they exist only because of drilldown. Ticket data can remain in the payload contract for now, but it should not dominate the page structure.

## Interaction Model

### Filtering strategy

This phase uses frontend-first filtering on top of the initial payload.

The page should:

1. load the initial payload once
2. keep a local filter state object in the browser
3. derive filtered datasets from the initial typed view model
4. rerender the visible sections immediately when filter state changes

This is the correct choice for this phase because the backend endpoint is still slow and should not be on the critical path for every chip click.

### State behavior

Required route-level states remain:

- `ready`
- `loading`
- `placeholder`

Within `ready`, filters are live and local.

Within `loading` or `placeholder`, filter UI may be hidden or disabled, but the page should stay visually coherent.

## Data Flow

The current data flow remains mostly intact:

1. [apps/qgate-kpi/app/page.tsx](apps/qgate-kpi/app/page.tsx) performs the non-blocking server bootstrap
2. [apps/qgate-kpi/src/features/qgate-dashboard/dashboard-bootstrap.tsx](apps/qgate-kpi/src/features/qgate-dashboard/dashboard-bootstrap.tsx) completes client-side hydration when needed
3. [apps/qgate-kpi/src/lib/api.ts](apps/qgate-kpi/src/lib/api.ts) fetches the typed payload
4. [apps/qgate-kpi/src/lib/payload-adapter.ts](apps/qgate-kpi/src/lib/payload-adapter.ts) adapts the payload
5. the dashboard feature derives filtered views locally from that adapted model

No new endpoint is required for this phase.

## Data Source Clarification

The user-facing explanation must be precise.

Current QGate dashboard data is not purely database-backed and not purely file-backed.

The current effective source path is:

- defect scope and defect metadata come from files under `qgate/defect`
- QGate history analysis is invoked through the existing history-based analysis path
- history loading beneath that path is database-first by default, with file fallback depending on source-mode configuration

In short:

> the current page uses a hybrid source path: defect files for scope input, and database-first history loading for transition analysis

This wording should replace any misleading copy that implies the page is already fully database-only.

## Component Structure

Preferred feature-level structure:

- `QGateDashboardBootstrap`
- `QGateDashboardPage`
- `QGateDashboardFilters`
- `QGateCoverageSection`
- `QGateTransitionSection`
- `QGateSummarySection`
- small shared chip/select/input helpers only if they reduce repetition cleanly

The implementation should reduce the size of [apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx](apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx) rather than make it denser.

## Styling Direction

The refreshed page should visually converge on the static HTML dashboard in these areas:

- dark blue hero gradient
- lighter white/gray panel field
- rounded bordered filter cards
- chip toggle treatments
- compact analytic table and summary styling
- a stronger legend/segment palette for Q-Gate, Integration, CoC, and Other

This should still remain a React-native implementation, not a literal copy-paste of the static HTML stylesheet.

## Error Handling

Preserve the current startup behavior:

- the page must still render quickly even if the backend payload is slow
- local filtering only activates once `ready` data exists
- malformed payloads still fall back to explicit schema messages
- unreachable API still falls back to shell messaging

The new visual parity work must not undo the recent fix for the slow backend bootstrap.

## Testing

Required coverage for this phase:

1. component tests for the filter controls and reset behavior
2. component tests proving filtered results update coverage, transitions, and summary output
3. regression tests proving ticket drilldown content is not rendered
4. regression tests proving loading/placeholder shells still render
5. lint, typecheck, and focused test validation

Browser automation is optional and not required for this phase.

## Acceptance Criteria

This phase is complete when:

- the React page looks recognizably aligned with [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html)
- top-level visual tone, spacing, and panel language are clearly closer to the HTML dashboard than the current prototype
- filter controls exist and are effective in the browser
- coverage, transition analysis, and summary sections all respond to filters
- ticket drilldown is removed from the React page
- data source wording reflects the real hybrid path
- the non-blocking page bootstrap remains intact
- tests, lint, and typecheck pass

## Follow-on Work

Later phases can decide whether to:

- add server-side refetch for advanced filters
- move more of the contract to true DB-backed query paths
- reintroduce drill-through in a different form that is lighter than the old ticket drilldown table
- migrate Top Issue and Test Coverage onto the same frontend pattern