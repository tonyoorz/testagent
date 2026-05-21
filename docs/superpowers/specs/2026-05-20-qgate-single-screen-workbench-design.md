# QGate Single-Screen Workbench Design

## Goal

Refine the current QGate Next.js prototype into a single-screen management workbench that is clearer to scan, easier to implement, and easier to extend than a multi-screen split.

This phase should prove three things:

- the homepage can carry both executive summary and analytical drill-down without becoming structurally messy
- the current typed API contract is already strong enough to support a denser single-screen experience
- startup and environment guidance can live both in docs and in the page itself without introducing interactive filter complexity yet

## Scope

In scope for this phase:

- keep the QGate dashboard as a single route at `/`
- preserve the current server-rendered bootstrap and typed payload pipeline
- reorganize the page into clear single-screen sections with stronger hierarchy
- add a deeper second layer of content below the current first-screen workbench
- add a read-only context rail or context section for scope, status, source, and startup information
- document how to run the frontend and backend together for local use

Out of scope for this phase:

- adding a second page or second route for QGate analysis
- making filters interactive
- adding client-side refetch or search-param driven server refresh
- introducing new backend endpoints or changing the payload contract
- adding AI chat or cross-dashboard navigation

## Current State

The current prototype already has:

- a standalone Next.js app in [apps/qgate-kpi](apps/qgate-kpi)
- a typed data layer and server bootstrap through [apps/qgate-kpi/src/lib/api.ts](apps/qgate-kpi/src/lib/api.ts)
- payload validation and adaptation through [apps/qgate-kpi/src/lib/payload-adapter.ts](apps/qgate-kpi/src/lib/payload-adapter.ts)
- a first-screen workbench in [apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx](apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx)

That means this phase is not about standing up new infrastructure. It is about improving information architecture on top of a now-stable data contract.

## Product Intent

The homepage should answer this sequence in one screen:

1. What is the current overall QGate health?
2. Where are the main pressure points right now?
3. What deeper evidence supports that summary?
4. Under what scope, source, and startup assumptions should the user interpret this page?

The page is still analysis-first, but this phase leans slightly toward a manager-friendly cockpit rather than a tool-heavy analyst console.

## Chosen UX Direction

Use a single-screen management cockpit with three vertical layers:

1. `Overview band`
	- strong title, readiness state, hero KPI, lead insight

2. `Deep dive band`
	- denser operational detail for coverage, transitions, and active tickets

3. `Context rail`
	- read-only scope, source, and startup guidance

This direction was chosen over a second screen because it is clearer, cheaper to implement, and avoids premature navigation complexity while the dashboard is still validating its core structure.

## Information Architecture

### Section 1: Overview band

Keep and refine the current hero section:

- title and subcopy
- readiness / placeholder status
- hero KPI cards
- primary lead insight

This remains the first visual stop and should stay concise.

### Section 2: Deep dive band

Below the hero, extend the page into a denser workbench region.

Required blocks:

1. Coverage detail
	- retain team coverage health
	- expand to show year-aware rows using `coverageRows`
	- show a clearer completeness/risk reading per team-year

2. Transition detail
	- keep the top pressure list
	- add a more explicit ranked breakdown for transition frequency and average duration
	- preserve empty-ready handling

3. Active ticket detail
	- keep the top active ticket list
	- extend each ticket card with richer metadata already present in the typed view model
	- preserve orphan-ticket fallback behavior when activity exists without ticket metadata

### Section 3: Context rail

Add a clearly separated read-only context block.

This block should contain:

1. Current scope snapshot
	- defect directory
	- history directory
	- teams in scope
	- min transition threshold

2. Filter baseline
	- explain that the page is using default server-side filters in this phase
	- optionally list years / groups / changed-by availability from `options`

3. Data interpretation notes
	- explain what placeholder means
	- explain what schema fallback means
	- explain that this phase is read-only and does not yet live-refresh

4. Startup guidance
	- backend command
	- frontend command
	- environment variable reminder for API base

Desktop layout should prefer a right-side rail when space allows. Mobile should collapse the rail below the deep-dive band as a standard content section.

## Component Structure

Keep implementation centered in [apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx](apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx) for now, but split rendering into smaller local subcomponents if needed.

Recommended component boundaries:

- `OverviewBand`
- `DeepDiveBand`
- `CoverageDetailPanel`
- `TransitionDetailPanel`
- `TicketDetailPanel`
- `ContextRail`

The page should continue to accept the same top-level state union:

- `placeholder`
- `loading`
- `ready`

This phase should not introduce additional route-level state complexity.

## Data Flow

The existing data flow remains unchanged:

1. [apps/qgate-kpi/app/page.tsx](apps/qgate-kpi/app/page.tsx) fetches the payload on the server
2. [apps/qgate-kpi/src/lib/api.ts](apps/qgate-kpi/src/lib/api.ts) validates transport-level correctness
3. [apps/qgate-kpi/src/lib/payload-adapter.ts](apps/qgate-kpi/src/lib/payload-adapter.ts) adapts the payload into the typed view model
4. [apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx](apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx) derives view-specific aggregations from that view model

No new backend fetch path is needed for this phase.

## Error Handling

The current state model stays intact:

- `ready`
  - all overview, deep-dive, and context blocks render

- `placeholder`
  - overview remains visible
  - deep-dive blocks do not pretend to have data
  - context rail still explains what happened and how to start the stack

- malformed payload or unreachable API
  - continue to surface schema or request fallback copy from [apps/qgate-kpi/app/page.tsx](apps/qgate-kpi/app/page.tsx)

Within `ready`, each panel must preserve explicit empty states rather than rendering blank containers.

## Styling Direction

Preserve the existing industrial analytics visual system in [apps/qgate-kpi/app/globals.css](apps/qgate-kpi/app/globals.css), but strengthen hierarchy with:

- clearer vertical spacing between overview, deep-dive, and context layers
- a more deliberate section title style for the deep-dive band
- a quieter but still readable context rail
- mobile-friendly overflow behavior for denser tables

This phase should avoid introducing a second visual language or adding decorative complexity that competes with the data.

## Documentation

Add startup guidance in two places:

1. inline in the page via the context rail
2. in repository docs, with a short section that explains:
	- how to start the Python API
	- how to start the Next.js frontend
	- which env var controls the API base URL

The docs update should be concise and specific to this experimental frontend.

## Testing

Required coverage for this phase:

1. component tests for the new deep-dive and context sections in ready state
2. component tests for explicit empty-ready behavior in the new detail panels
3. route-level test confirming startup/context information appears with fetched data
4. regression coverage for placeholder state after the layout expansion
5. lint, typecheck, and production build validation

This phase does not require browser automation.

## Implementation Notes

Preferred implementation order:

1. reshape the page layout into overview, deep dive, and context sections
2. add the read-only context rail using existing view-model data and static startup copy
3. extend coverage / transition / ticket detail below the current first-screen workbench
4. update tests to pin the new structure and empty states
5. update docs with frontend startup guidance

## Acceptance Criteria

This phase is complete when:

- the QGate dashboard remains a single page
- the page has a visibly clearer three-layer structure
- the page includes a read-only context rail or section with scope and startup info
- the page shows a deeper second band of analytical detail without adding new API endpoints
- placeholder and ready states remain explicit and readable
- tests, lint, typecheck, and build all pass

## Follow-on Work

Later phases can build on this by adding:

- truly interactive filters
- search-param or client-state driven refetch
- drill-through navigation
- charting libraries for richer visual density
- migration of Top Issue and Test Coverage into the same frontend system
