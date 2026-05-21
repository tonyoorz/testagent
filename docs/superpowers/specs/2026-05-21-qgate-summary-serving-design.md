# QGate Summary Serving Design

## Goal

Replace the current request-time QGate KPI computation path with a database-backed serving layer that returns the same payload shape with materially lower latency.

This design keeps the existing frontend contract intact and moves heavy history parsing out of the API request path.

## Problem Statement

The current QGate KPI API path is functionally correct in `db_only` mode, but it is too slow for interactive use.

Observed behavior for two teams:

- `Plant-Dadong FIT`
- `Plant-Tiexi FIT`

Measured service-layer payload build time is about 144.6 seconds.

The root cause is that `build_dashboard_payload()` still depends on runtime ticket-by-ticket history parsing:

- defect scope is loaded from `octane_defects`
- history payloads are loaded from `octane_defect_histories.payload_json`
- phase transitions are parsed in Python per ticket
- KPI aggregates are computed on every request

This architecture scales with source data volume and cannot provide stable dashboard latency.

## Decision

Introduce a QGate-specific summary table in SQLite and switch the KPI API to read from that serving table instead of performing request-time history analysis.

This is the recommended target architecture because it provides the largest latency improvement and matches common dashboard and BI serving patterns.

## Non-Goals

- Do not change the frontend payload schema.
- Do not require `octane_defect_history_events` as an input dependency.
- Do not redesign the existing QGate UI.
- Do not add a new database technology.

## Approaches Considered

### Option A: Keep online computation and optimize reads

Examples:

- batch-load `octane_defect_histories`
- reuse preloaded cache inside `longrunner_analysis`

Pros:

- smallest code change
- low migration risk

Cons:

- request latency still grows with ticket count
- does not remove Python parsing from the hot path
- unlikely to reach reliable dashboard-grade latency

### Option B: Use `octane_defect_history_events` for request-time aggregation

Pros:

- faster than parsing raw `payload_json`
- useful if other features need event-level history queries

Cons:

- still performs aggregation during requests
- still scales with data volume
- introduces dependency on a table the user does not want to require

### Option C: Build a QGate summary serving table

Pros:

- best latency profile
- stable API performance
- standard dashboard architecture
- no frontend contract change

Cons:

- requires an offline refresh step
- requires storage for derived rows

### Recommendation

Choose Option C as the primary solution.

Option A remains useful as a short-term optimization or fallback during migration, but it is not the end-state architecture.

## Architecture

### Current Path

`qgate_api_service.py` -> `report/generate_qgate_kpi_dashboard.py` -> `qgate.py` -> `longrunner_analysis.py` -> `octane_defect_histories.payload_json`

### Target Path

`qgate_api_service.py` -> `report/generate_qgate_kpi_dashboard.py` -> QGate summary repository -> SQLite summary tables

Raw source ingestion remains unchanged:

- `octane_defects`
- `octane_defect_histories`

Derived serving data is built offline and stored in SQLite.

## Data Model

### Primary Serving Table

Create a derived table named `qgate_kpi_issue_transitions`.

Each row represents one parsed transition sample for one ticket.

Proposed columns:

- `team TEXT NOT NULL`
- `ticket_id TEXT NOT NULL`
- `year TEXT`
- `ticket_name TEXT`
- `tester TEXT`
- `ticket_url TEXT`
- `phase_transition TEXT NOT NULL`
- `group_name TEXT`
- `changed_by TEXT`
- `fif TEXT`
- `duration_hours REAL NOT NULL`
- `duration_days REAL NOT NULL`
- `ticket_timespan_days REAL`
- `start_time TEXT`
- `end_time TEXT`
- `source_history_hash TEXT NOT NULL`
- `source_team TEXT`
- `refreshed_at TEXT NOT NULL`

Primary key:

- `(team, ticket_id, phase_transition, start_time, end_time)`

Recommended indexes:

- `(team)`
- `(year)`
- `(team, year)`
- `(phase_transition)`
- `(group_name)`
- `(changed_by)`
- `(fif)`
- `(ticket_id)`

### Coverage Support

Coverage and defect totals require scoped ticket counts even when no parsed transition row exists.

Create a second lightweight serving table named `qgate_kpi_ticket_scope`.

Each row represents one scoped ticket eligible for QGate reporting.

Proposed columns:

- `team TEXT NOT NULL`
- `ticket_id TEXT NOT NULL`
- `year TEXT`
- `ticket_name TEXT`
- `tester TEXT`
- `ticket_url TEXT`
- `has_history INTEGER NOT NULL`
- `history_parse_ok INTEGER NOT NULL`
- `source_history_hash TEXT`
- `refreshed_at TEXT NOT NULL`

Primary key:

- `(team, ticket_id)`

Recommended indexes:

- `(team)`
- `(year)`
- `(team, year)`
- `(history_parse_ok)`

## Refresh Strategy

### Phase 1

Implement full refresh only.

Rationale:

- simplest implementation
- easiest to validate against current payloads
- lowest migration ambiguity

Full refresh behavior:

1. read scoped tickets from `octane_defects`
2. read corresponding history payloads from `octane_defect_histories`
3. parse transitions using the existing QGate phase-analysis logic
4. rebuild `qgate_kpi_issue_transitions`
5. rebuild `qgate_kpi_ticket_scope`

### Phase 2

Add incremental refresh keyed by `ticket_id` plus `source_history_hash`.

Incremental refresh is explicitly deferred until the full-refresh implementation is correct and verified.

## API Behavior

`qgate_api_service.py` continues to expose the same query interface and response payload.

`build_dashboard_payload()` gains a summary-serving mode that:

- reads `qgate_kpi_ticket_scope` for coverage and meta totals
- reads `qgate_kpi_issue_transitions` for issue rows and transition-derived metrics
- applies the existing filters for teams, years, groups, changed_by, fif, and timespan
- emits the same payload sections:
  - `generated_from`
  - `overview`
  - `insights`
  - `options`
  - `meta`
  - `coverage`
  - `tickets`
  - `issues`

The frontend remains unchanged.

## Fallback Policy

If the summary tables are missing or stale, the API should fail fast with a clear error instead of silently falling back to the slow request-time computation path.

Rationale:

- avoids accidental regression back to multi-minute latency
- makes operational state explicit
- keeps production behavior predictable

Expected behavior:

- return a clear backend error stating that QGate summary data has not been built
- optionally include last refresh timestamp when available

## Implementation Boundaries

### New Responsibilities

`octane_db.py`

- create summary table schema helpers
- create indexes for serving tables

New module, recommended name `qgate_summary_store.py`

- refresh summary tables from raw source tables
- provide read helpers for dashboard payload generation

`report/generate_qgate_kpi_dashboard.py`

- switch from online computation to summary-table reads when summary mode is enabled
- preserve existing payload shape

`qgate_api_service.py`

- default to summary-serving mode
- surface clear errors if summary data is unavailable

### Existing Logic to Reuse

The offline builder should reuse existing ticket transition parsing logic wherever practical so that summary results match current semantics.

This is especially important for:

- phase transition naming
- group classification
- FiF derivation
- changed_by derivation
- ticket timespan logic

## Validation Plan

### Correctness

Add tests that prove:

- summary refresh writes expected transition rows from minimal defect and history fixtures
- summary coverage rows match expected defect and history counts
- payload generated from summary tables matches the current payload shape
- filters applied on summary-backed payloads preserve current behavior

### Performance

Measure the same two-team query currently used for validation:

- `Plant-Dadong FIT`
- `Plant-Tiexi FIT`

Success criterion for phase 1:

- response time improves materially versus the current 144.6 second baseline
- runtime no longer performs raw ticket-by-ticket history parsing inside the request path

The exact latency target can be tightened after first measurement, but the intended direction is dashboard-interactive response time rather than batch-job latency.

## Rollout Plan

1. add summary table schema
2. add full-refresh builder
3. add summary-backed payload reader
4. switch API to summary-backed mode
5. validate correctness against current payloads for selected teams
6. measure latency improvement
7. optionally add incremental refresh

## Risks

### Semantic Drift

Offline refresh may produce results that differ from current online logic if parsing code paths diverge.

Mitigation:

- reuse existing parsing helpers
- add fixture-based comparison tests

### Staleness

Summary data can become outdated if refresh is not run after source updates.

Mitigation:

- store refresh timestamp
- fail clearly when summary tables are absent
- later add operational hooks to refresh after downloader runs

### Storage Growth

Transition-level serving rows will consume more disk than a single aggregated table.

Mitigation:

- keep only fields required by the dashboard
- defer secondary aggregates until needed

## Open Decisions Resolved

- Use full refresh first: yes
- Do not require `octane_defect_history_events`: yes
- Do not silently fall back to slow online computation when summary data is missing: yes

## Implementation Recommendation

Proceed with the summary-table design as the primary QGate KPI serving architecture.

If additional short-term relief is still needed during migration, batch DB preload improvements may be added, but they should be treated as transitional work rather than the final solution.