# QGate Next.js KPI Dashboard Design

## Goal

Build a first modern frontend prototype for QGate KPI analysis using Next.js 16 + React 19 with a lightweight Python API gateway, while keeping the displayed data aligned with the existing static dashboard output in [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html).

The prototype should prove three things:

- the user experience can be materially better than the current Dash/static HTML flow
- the displayed KPI and analysis content can remain aligned with the current QGate KPI dashboard data scope
- the frontend and API structure can be extended later for Top Issue and Test Coverage without being rewritten

## Scope

In scope for the first prototype:

- a new standalone Next.js frontend application inside this repository
- a single QGate KPI home page
- a lightweight Python API layer that reuses current QGate/report calculation logic
- the same core data scope as the current static dashboard payload
- modern visual design, responsive layout, and significantly improved interaction quality
- filter-driven client interaction with selective server recomputation when needed
- robust loading, empty, error, and partial-data states

Out of scope for the first prototype:

- Top Issue page
- Test Coverage page
- a full AI copilot panel
- rewriting the QGate analysis model around SQLite-first contracts in phase one
- replacing all current Dash or static QGate outputs
- deep backend refactors unrelated to this page

## Current State

The current QGate KPI experience is split across three surfaces:

1. [qgate.py](qgate.py)
   - file-first Dash analysis UI
   - reads `qgate/defect` and `qgate/history`

2. [report/generate_qgate_kpi_dashboard.py](report/generate_qgate_kpi_dashboard.py)
   - generates a standalone HTML dashboard
   - already defines a useful payload contract through `build_payload(...)`

3. [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html)
   - current KPI-style static output
   - includes hero KPI, filters, coverage, transition analysis, summary, and drilldown

The repository README describes a Next.js-based agent UI, but the current workspace does not contain a real `agent_ui/` directory or an existing Next.js app scaffold. This means the prototype should not assume a reusable frontend project already exists.

## Product Intent

The first screen must communicate this before anything else:

> Under the currently selected scope, what is the QGate health of each team, where is history coverage weak, and which transition patterns need attention right now?

This page is an analysis workbench, not a chat product. AI is intentionally deferred for the first prototype so the dashboard itself remains the primary focus.

## Data Parity Requirement

The prototype does not need to visually mirror the static HTML dashboard, but it must preserve the same data scope and core interpretation.

At minimum, the new page must cover the same information families currently represented in [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html):

- overview / hero KPI
- generated insights
- filters
- team coverage and history completeness
- transition analysis
- team × group phase efficiency summary
- ticket drilldown

The underlying values for these sections should be derived from the same logic path currently used by [report/generate_qgate_kpi_dashboard.py](report/generate_qgate_kpi_dashboard.py), unless a later phase explicitly replaces that logic.

## UX Direction

### Chosen direction

Use a balanced modern analysis workbench layout:

- first screen emphasizes hero KPI, insights, filters, coverage, and team/group efficiency
- second screen holds deeper transition analysis and drilldown details
- the design looks premium and modern, but preserves analytical density

### Rejected directions

- ChatGPT/OpenWebUI-style full-page chat layout
  - rejected because the page is analysis-first, not conversation-first

- literal 1:1 migration of the static HTML page
  - rejected because it would preserve information parity but not sufficiently prove the value of the new frontend stack

- management-only narrative dashboard
  - rejected because it would reduce drilldown utility for analysts

## Information Architecture

### Page structure

#### First screen

1. Hero header
   - page title
   - data source summary
   - current scope label
   - last generated / freshness state

2. Hero KPI cards
   - `team_count`
   - `total_defects`
   - `history_success_rate`
   - `transition_samples`
   - optionally `unique_tickets` if layout allows without weakening hierarchy

3. Insight strip
   - 3-4 key insight cards derived from the current generated insight set

4. Global filter bar
   - years
   - teams
   - groups
   - changed by
   - FiF
   - timespan min / max
   - min transition count

5. Coverage section
   - primary chart for team coverage / history completeness
   - secondary risk summary for weak completeness or data quality anomalies

6. Team × Group efficiency summary
   - modernized visual summary of group efficiency by team
   - click/selection drives lower drilldown state

#### Second screen

7. Transition analysis section
   - grouped transition analysis view
   - slowest / highest volume cues

8. Summary table section
   - tabular comparison of team/group counts and efficiency

9. Ticket drilldown section
   - tickets for the active selection
   - links out to Octane when available

## Technical Architecture

### Frontend

Create a new standalone Next.js application in this repository.

Recommended stack:

- Next.js 16
- React 19
- App Router
- TanStack Query for server state
- ECharts for charts
- TanStack Table or AG Grid for drilldown and summary tables
- CSS variables for design tokens

The frontend should be isolated from the current Dash application so the prototype can evolve independently.

### Backend

Add a lightweight Python API gateway that reuses existing QGate/report calculation logic rather than replacing it in phase one.

The backend in this phase is a compatibility and orchestration layer, not a new analytical source of truth.

Primary reuse points:

- [report/generate_qgate_kpi_dashboard.py](report/generate_qgate_kpi_dashboard.py)
- [qgate.py](qgate.py)
- existing file outputs under `qgate/defect` and `qgate/history`

### Data source strategy

Phase-one source priority:

1. existing QGate file outputs under `qgate/defect` and `qgate/history`
2. current analysis logic in `qgate.py` / `report/generate_qgate_kpi_dashboard.py`

Not phase one:

- moving the homepage contract to a SQLite-first model
- redesigning the aggregation model around new database tables only

This preserves data parity and allows the API implementation to be swapped later without breaking the frontend contract.

## API Contract

### Main endpoint

`GET /api/qgate/kpi-dashboard`

Purpose:

- return the full homepage payload aligned with the current static dashboard output

Inputs:

- `years`
- `teams`
- `groups`
- `changed_by`
- `fif`
- `timespan_min`
- `timespan_max`
- `min_transition_count`

Output families:

- `generated_from`
- `overview`
- `insights`
- `options`
- `meta`
- `coverage`
- `issues`
- `tickets`

The output should remain semantically aligned with the payload built in [report/generate_qgate_kpi_dashboard.py](report/generate_qgate_kpi_dashboard.py#L260).

### Meta endpoint

`GET /api/qgate/meta`

Purpose:

- expose lightweight page state metadata for environment and data-source presentation

Output:

- current defect/history directories
- available teams
- available years
- last generated timestamp or cache timestamp
- data health / completeness state

## Interaction Model

### Frontend-first filtering

The initial page load should fetch a full payload for the scoped default state.

Then:

- lightweight filtering interactions should be applied client-side when possible
- expensive recomputation inputs can trigger a refetch of the main endpoint

This approach is chosen because the prototype goal is experience-first. It reduces round trips and makes the new frontend feel substantially faster than the current file/static flow.

### Linked interactions

Required linked behavior:

- selecting a team or group updates coverage and summary emphasis
- selecting a summary segment updates drilldown content
- filters update both charts and tables consistently
- reset returns the page to the default scoped state

## Visual Design Direction

### Chosen visual language

Use a premium industrial analytics look:

- dark, cool-toned background
- translucent panel surfaces
- restrained but high-contrast accent colors
- strong typography hierarchy
- minimal but meaningful motion

This avoids both generic enterprise admin styling and chat-product styling.

### Token direction

Initial token intent:

- background: deep blue/graphite
- panel: dark translucent slate
- primary accent: teal/green
- secondary accent: electric blue
- warning accent: amber
- danger accent: soft red
- large rounded corners and soft deep shadows

Typography intent:

- display/headline: Space Grotesk or Sora
- body: IBM Plex Sans or Inter Tight
- KPI numerals: JetBrains Mono or Geist Mono

## Responsive Behavior

### Desktop

- full dual-layer workbench
- first screen emphasizes hero, coverage, and summary
- second screen holds deeper analysis and tables

### Tablet

- stack sections vertically
- compress hero density
- filters collapse into a more compact control surface

### Mobile

- provide an understandable summary view rather than a full workstation clone
- show KPI, insights, and simplified charts first
- progressive disclosure for tables and drilldowns

## States And Error Handling

The prototype must support explicit UI states for:

### Loading

- skeleton header
- skeleton KPI cards
- chart placeholders

### Empty

- message explaining the current filter combination produced no matches
- clear reset or widen-scope action

### Error

- clear failure message in-page
- distinction between network/API failure and analysis/data failure when possible

### Partial / stale data

- page-level data status badge or banner
- communicate if results are partial, incomplete, or older than expected

This is required because QGate data quality and availability can vary by team and history completeness.

## Performance Strategy

- server-side initial payload fetch for better first render
- cache the main payload at the API layer when possible
- keep high-frequency interactions client-side when safe
- avoid rendering very large drilldown tables without pagination or virtualization
- use searchable popovers or compact multi-selects for large option sets such as `Changed By`
- prefer fast chart rendering and avoid excessive animation

## Accessibility Requirements

- AA-level text contrast on dark surfaces
- keyboard-reachable filters, tables, and drilldown actions
- visible focus states for every interactive element
- reduced-motion support for animated sections
- avoid encoding state using color alone

## Component Boundaries

The first prototype should decompose into reusable units that can later support Top Issue and Test Coverage pages.

Recommended boundary set:

- app shell
- page header / data status
- hero KPI section
- insights strip
- global filter bar
- coverage panel
- team/group summary panel
- transition analysis panel
- summary table panel
- ticket drilldown panel
- shared loading / empty / error components
- shared payload adapter utilities

## Testing Strategy

Phase-one verification should cover:

- API payload contract correctness for default scoped responses
- parity checks against current payload families and key metric values
- frontend render tests for hero and core panels
- filter interaction tests for linked updates
- empty/error state rendering tests

Manual validation should confirm:

- the first screen reveals the most important KPI immediately
- the new page feels materially more polished than the current static dashboard
- the displayed metrics remain aligned with [report/qgate_kpi_dashboard.html](report/qgate_kpi_dashboard.html)

## Acceptance Criteria

The prototype is considered successful when:

1. the page displays the same core data scope as the current static QGate KPI dashboard
2. the hero KPI and generated insight experience is visibly stronger than the current HTML report
3. filters work across the full page and update the visual state coherently
4. team/group selection drives a meaningful drilldown experience
5. loading, empty, error, and partial-data states are explicitly designed and implemented
6. the project structure can support future Top Issue and Test Coverage pages without redesigning the app foundation

## Follow-On Work

Expected later phases after this prototype:

- add Top Issue page on the same app shell and token system
- add Test Coverage page
- add optional AI entry point
- gradually replace file-first analysis internals with more formal API/data services if needed