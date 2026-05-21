# Full Picture Dashboard Design

## Goal

Build a new Full Picture dashboard focused on Octane ticket closure quality and ticket-level drilldown, using the existing QGate/Octane data foundations in this repository but not being constrained by the current QGate KPI payload shape.

The first implementation should answer three management questions clearly:

1. Under the current filter scope, how many tickets were truly fixed and closed forward?
2. Under the same scope, how many tickets were directly rejected and closed without being solved?
3. Which exact tickets are behind that picture right now?

## Scope

In scope for the first version:

- a new Full Picture page in the existing Next.js dashboard surface
- default initial scope based on 2026 defect data
- filter-driven analysis over Octane defect and history-backed ticket data
- a left-top positive vs negative outcome chart
- a right-top expansion of the same positive vs negative logic by defect finder team
- a ticket detail table below the charts
- modern multi-filter UI aligned with the current dashboard visual language

Out of scope for the first version:

- Top Issue aggregation or a Top Issue ranking chart
- title-based clustering
- AI assistant interactions
- deeper matrix widgets from the handwritten draft
- extra lower panels not directly needed for chart-to-ticket drilldown

## Product Intent

This page is a management workbench, not an exploratory issue-mining console.

The page should prioritize fast comparison and clear accountability:

- first show whether the current scope closes tickets well or closes them badly
- then show which problem finder teams differ most
- then show the actual tickets responsible for the current picture

## Chosen Direction

Use a dedicated Full Picture dashboard backed by a new API contract that combines Octane defect fields, processed Defect Explore dimensions, and ticket history transitions.

This is the correct direction because the current QGate KPI payload does not expose enough dimensions for the required filters:

- project
- assigned ECU
- problem finder team
- AIDA
- phase
- solution cluster
- PU
- market
- Lead Model
- group

### Rejected alternatives

#### Extend the existing QGate KPI payload only

Rejected because the current payload is optimized for QGate coverage and transition summaries, not for broad defect-side dimensional filtering.

#### Ship a static pre-aggregated page first

Rejected because it would make the filters untrustworthy and would likely be thrown away once the real interactions are needed.

## Data Scope

### Initial load scope

The first page load should default to 2026 defect data.

This default is an initial scope only, not a permanent denominator rule.

### Denominator rule

All percentages on the positive vs negative chart family use the same denominator:

> all tickets mapped from the currently filtered defect scope

This means the denominator changes whenever the user changes filters.

It is not hard-bound to 2026 after initial load if later filters expand beyond that scope.

## Data Sources

The Full Picture dashboard should use a hybrid source path:

- Octane defect-side fields and processed dashboard dimensions from the existing defect data path
- Octane history transition data from the existing history-backed path
- existing group mapping logic derived from QGate phase classification

The first implementation should prefer repository-local processed data and DB-backed history where available, while staying compatible with the existing Octane history retrieval conventions already used in this workspace.

## Required Filters

All required filters should be available in the first version and support multi-select with default All behavior.

Required filters:

- year
- project
- assigned ECU
- problem finder team
- AIDA
- phase
- solution cluster
- PU
- market
- Lead Model
- group

### Filter behavior

- all filters are multi-select
- all filters default to All, except initial year scope which starts at 2026
- changing any filter recomputes the charts and ticket detail table
- the UI should show active scope clearly near the top of the page

### Display naming

- `aida_english` should be displayed as `AIDA`
- field labels should use the more business-readable naming already familiar from Defect Explore

## Group Definition

`group` is the higher-level categorization of phase.

The first version should reuse the existing QGate grouping vocabulary:

- Q-Gate
- Integration
- CoC
- Other

This grouping must be consistent across:

- chart legends
- filter options
- ticket detail display

## Core Metrics

### Positive outcome

Positive outcome means a ticket shows a forward completion path from phase 08 to phase 06.

Displayed label recommendation:

- `Resolved Forward (08 -> 06)`

### Negative outcome

Negative outcome means a ticket shows a direct reject-close path from phase 01 to phase 09.

Displayed label recommendation:

- `Rejected Directly (01 -> 09)`

### Percentage display

Each bar should show:

- count
- percentage above or on the bar

The percentage is:

$$
\text{rate} = \frac{\text{tickets in selected outcome path}}{\text{all tickets in current filtered scope}} \times 100\%
$$

## Information Architecture

### Section 1: Hero and filters

The page should open with:

- dashboard title
- short explanation of what the page measures
- scope summary
- filter grid

The visual style should stay aligned with the current premium blue-and-white QGate dashboard language.

### Section 2: Portfolio outcome chart

The left-top chart is the first focal point.

It should show two bars only:

- Resolved Forward (08 -> 06)
- Rejected Directly (01 -> 09)

Each bar should show:

- ticket count
- percentage based on the current denominator

This section answers whether the filtered scope is closing tickets well or closing them badly.

### Section 3: Team expansion chart

To the right of the portfolio chart, show the same logic expanded by defect finder team.

For each defect finder team, display two bars:

- resolved forward
- rejected directly

The x-axis or row dimension is defect finder team, such as:

- DTSV_China
- FIT_LAENDER_CHINA
- other available testing teams in scope

This section is a direct horizontal comparison of how teams differ under the same evaluation logic.

### Section 4: Ticket Detail table

Below the charts, show a single Ticket Detail table instead of a Top Issue area.

The table should default to all tickets in the current filtered scope.

Initial columns:

- Octane Ticket ID
- Name
- Status
- Group

This table is the first drilldown layer and should be the only lower section in version one.

## Interaction Model

### Filter-to-chart interaction

- changing filters immediately updates both chart areas and the ticket detail table
- all three surfaces always remain in sync

### Chart-to-table interaction

The table should support secondary narrowing when users interact with the charts.

Required interactions:

- selecting the positive outcome bar narrows the table to tickets counted in the positive path
- selecting the negative outcome bar narrows the table to tickets counted in the negative path
- selecting a team bar in the team comparison chart narrows the table to that team and outcome
- clearing the chart selection restores the table to the current filter scope

This creates a simple drilldown without introducing extra lower panels.

## API Design

The first implementation should add a new dedicated Full Picture API instead of overloading the existing QGate KPI endpoint.

### Recommended endpoint

`GET /api/full-picture/dashboard`

### Responsibilities

- accept the required multi-select filters
- load the filtered defect scope
- map defects to ticket-level transition history
- compute positive and negative outcome counts
- compute per-team positive and negative outcome counts
- return ticket detail rows for the current filter scope
- return filter option sets for the UI

### Response families

- `generated_from`
- `filters`
- `overview`
- `outcome_summary`
- `team_outcome_rows`
- `ticket_rows`

## Data Model Notes

The backend contract should preserve enough fields to avoid re-querying when the user clicks chart selections.

Each ticket detail row should carry at least:

- ticket id
- ticket name
- current status
- problem finder team
- group
- phase
- flags for `is_resolved_forward` and `is_rejected_directly`

This allows the client to narrow the already-loaded rows for chart selection states.

## UI Style

The page should not look like a raw data admin screen.

Desired styling direction:

- strong blue hero header
- compact but premium filter cards
- outcome bars with explicit positive and negative colors
- clean white panel surfaces
- restrained but clear data table styling

The ticket detail table should remain readable even when the page is used as a management snapshot.

## Error Handling

The page should preserve the non-blocking startup behavior already used in the experimental dashboard.

Required behavior:

- page shell can render before the API payload is fully ready
- filter controls can be disabled until ready state exists
- empty filtered results should show a clear no-data state instead of an empty broken chart
- malformed payloads should fail explicitly
- slow backend should not make the initial page feel hung

## Testing

Required first-version test coverage:

1. filter state updates the portfolio outcome counts correctly
2. filter state updates team comparison rows correctly
3. chart selection narrows the ticket detail table correctly
4. ticket detail table renders the required columns
5. group mapping is displayed consistently
6. loading and empty states render coherently

## Acceptance Criteria

The first version is acceptable when:

- the page loads with default 2026 defect scope
- all required filters are present and multi-select
- the left-top chart shows positive and negative outcome counts and percentages
- the right-top chart compares defect finder teams across the same two outcomes
- the ticket detail table updates with both filters and chart interactions
- no Top Issue aggregation section is shown
- the page visually fits the current modern QGate dashboard family

## Implementation Boundary

This design is intentionally focused enough for a single implementation plan.

Future phases may add:

- Top Issue aggregation as an optional secondary panel
- title-based clustering
- additional KPI cards
- export behavior

Those are intentionally excluded from version one so the first slice stays coherent and testable.