# Full Picture Workbench V2 Design

## Goal

Build a new interactive, data-backed Full Picture workbench as the `Main` dashboard experience in the existing Next.js frontend while preserving the current Full Picture page unchanged.

This phase should prove five things clearly:

1. the repository can carry two Full Picture experiences at the same time without destabilizing the current page
2. the existing Full Picture payload, adapter, and filtering logic are already strong enough to support a cleaner and more faithful dashboard shell
3. the new workbench can feel much closer to the reference dashboard visual language without introducing decorative noise
4. the main screen can stay focused on filters, metrics, team comparison, and ticket drilldown without AI explanation blocks competing for attention
5. the browser experience can avoid the current cross-origin fallback problems by moving the interactive fetch path behind a same-origin bridge

## Scope

In scope for this phase:

- migrate the app root `/` so it serves the new `Main` Full Picture workbench
- keep the existing `/full-picture` route intact and behaviorally unchanged
- reuse the current Full Picture API contract, payload validation, adapter, and client-side filter derivation logic
- build a new visual shell and page composition for the workbench
- support real interactive filtering and chart-to-ticket drilldown using the existing typed view model
- remove AI explanation blocks from the primary workbench surface
- add a same-origin proxy path in the Next.js app for Full Picture dashboard requests
- document how the new route and data path relate to the legacy page

Out of scope for this phase:

- removing or replacing the current `/full-picture` page
- changing the backend Full Picture aggregation semantics
- adding new outcome definitions beyond the existing two tracked outcomes
- introducing generative AI content into the main workbench canvas
- redesigning unrelated QGate dashboard routes

## Current State

The current frontend already has the pieces needed to support a second Full Picture experience:

- route bootstrap at [apps/qgate-kpi/app/full-picture/page.tsx](apps/qgate-kpi/app/full-picture/page.tsx)
- browser hydration and retry logic at [apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-bootstrap.tsx](apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-bootstrap.tsx)
- typed payload fetch and validation at [apps/qgate-kpi/src/lib/full-picture-api.ts](apps/qgate-kpi/src/lib/full-picture-api.ts)
- payload adaptation at [apps/qgate-kpi/src/lib/full-picture-payload-adapter.ts](apps/qgate-kpi/src/lib/full-picture-payload-adapter.ts)
- client-side filter and drilldown derivation at [apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.ts](apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.ts)

That means this phase is not a backend redesign. It is a new frontend shell at the app root on top of an already usable Full Picture data model.

## Product Intent

The new workbench should answer this sequence quickly:

1. What is the current scope?
2. How many tickets in that scope resolve forward versus reject directly?
3. Which teams are driving that picture under their own local denominator?
4. Which exact tickets explain the currently selected slice?

The workbench is a management cockpit, not an explanation-heavy assistant surface.

The page should feel controlled, dense, and visually disciplined.

## Chosen Direction

Use a dedicated second-generation Full Picture experience at the app root with a new visual shell, but keep the existing data contract and behavioral semantics.

This is the correct direction because the current problems are concentrated in frontend presentation and request topology, not in the underlying payload:

- the old route should remain available for continuity and regression comparison
- the new page needs freedom to adopt a new shell and information hierarchy
- the current payload already contains the overview, outcome summary, team rows, ticket rows, and filter values needed for the intended workbench
- the browser-side instability comes from the transport path, which can be fixed independently of the dashboard logic

### Rejected alternatives

#### Keep refining the current `/full-picture` page in place

Rejected because the user wants a new experience while preserving the current page. In-place redesign would entangle validation of new UI with regression risk in the existing route.

#### Build a purely mocked prototype first and connect data later

Rejected because the next decision point is no longer conceptual. The user explicitly asked for a version with real interactions and real data behavior.

## Route and Navigation

### Route strategy

Use the app root as the new `Main` entry point:

- `/`

Keep the current route:

- `/full-picture`

The app root becomes the new `Main` workbench entry. The old Full Picture route remains the continuity path.

### Navigation intent

This phase adds a `Main`-style shell around the new workbench but does not require a complete multi-page navigation system.

The new route should provide a visible local path back to the legacy experience, for example a small secondary action such as `Open legacy Full Picture`.

This keeps comparison easy while avoiding accidental ambiguity about which page is the approved workbench.

## Information Architecture

The new page should use a single-screen workbench structure with four vertical layers.

### Section 1: Compact header

The header should contain:

- page title
- one-line purpose statement
- readiness / freshness state
- a small action cluster such as refresh and legacy-link actions

The header should not behave like a marketing hero. It should be tight and operational.

### Section 2: Filter workbench

The top interaction layer should be a compact filter workbench with:

- search input for ticket ID or title text matching if already supported by current client state, otherwise omit until supported
- multi-select filter groups based on the existing Full Picture dimensions
- active scope summary
- clear reset action

Required filters remain:

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

Behavior rules:

- all filters are multi-select
- `year` defaults to `2026` on first entry
- all other filters default to `All`
- filter changes recompute the workbench client-side from the existing typed view model
- the active scope summary stays visible near the top

### Section 3: Outcome and team analysis band

This is the main analytical band.

It should contain:

1. `KPI strip`
   - tickets in scope
   - resolved forward count and percent
   - rejected directly count and percent
   - teams in scope

2. `Portfolio outcome card`
   - a simple two-outcome view based on the existing summary data
   - no decorative story text inside the chart area

3. `Team expansion card`
   - team rows comparing `resolvedForward` and `rejectedDirectly`
   - use team-local denominator percentages exactly as the current payload defines them
   - selecting a team row changes the ticket detail slice below

The KPI and analysis band should be the primary visual focus.

### Section 4: Ticket Detail

The lower region remains a single `Ticket Detail` table.

It should:

- respond to both filters and chart selection
- show all current-scope tickets when nothing is selected
- narrow to the chosen outcome or team slice when selected
- avoid tabs or unrelated lower panels in this phase

Recommended columns:

- Ticket ID
- Title
- Team
- Status
- Outcome
- Phase
- Group
- Project

If horizontal density becomes a problem on smaller screens, lower-priority metadata can collapse or hide responsively.

## Visual Direction

The new workbench should pursue high fidelity to the reference dashboard language, not a loose interpretation.

## Copy Language

All user-visible copy introduced in this phase must be English-only.

This applies to:

- navigation labels
- page titles and subtitles
- filter labels and placeholders
- buttons and helper text
- KPI labels
- chart labels
- table headers and empty states
- loading and error copy

Mixed Chinese and English UI copy is out of scope for this route.

The development conversation may still happen in Chinese, but the website surface must remain English.

### Visual principles

- restrained, not glossy
- compact, not airy
- analytical, not explanatory
- premium through consistency, not decoration

### Tokens

Use a deliberate token set in the new route styles:

- font families: `DM Sans` for UI text and `JetBrains Mono` for small numeric or technical labels
- shell background: soft cool gray
- primary surfaces: white cards
- left navigation or local rail surfaces: deep navy
- borders: low-contrast cool gray
- radii: mostly small to medium
- shadows: light and infrequent

Suggested token baseline:

- `--fpw-bg: #f4f7fb`
- `--fpw-panel: #ffffff`
- `--fpw-line: #e2e8f0`
- `--fpw-text: #0f172a`
- `--fpw-muted: #64748b`
- `--fpw-primary: #2f6fed`
- `--fpw-sidebar: #121c2f`

### Explicit anti-goals

Do not add:

- large AI explanation cards in the main canvas
- glassmorphism
- oversized hero gradients
- oversized radii that weaken scan density
- decorative copy blocks that compete with the metrics

## Component Structure

Implement the new page as a separate feature slice instead of mutating the existing Full Picture page component in place.

Recommended structure:

- [apps/qgate-kpi/app/page.tsx](apps/qgate-kpi/app/page.tsx)
  - route-level server bootstrap for the new `Main` page

- [apps/qgate-kpi/src/features/full-picture-workbench/workbench-bootstrap.tsx](apps/qgate-kpi/src/features/full-picture-workbench/workbench-bootstrap.tsx)
  - client hydration and retry handling for the new `Main` workbench

- [apps/qgate-kpi/src/features/full-picture-workbench/workbench-page.tsx](apps/qgate-kpi/src/features/full-picture-workbench/workbench-page.tsx)
  - main interactive page container

- [apps/qgate-kpi/src/features/full-picture-workbench/components/*](apps/qgate-kpi/src/features/full-picture-workbench/components/)
  - compact subcomponents for header, filters, KPI strip, portfolio card, team card, and ticket table

Shared logic that should remain reused rather than duplicated:

- [apps/qgate-kpi/src/lib/full-picture-api.ts](apps/qgate-kpi/src/lib/full-picture-api.ts)
- [apps/qgate-kpi/src/lib/full-picture-payload-adapter.ts](apps/qgate-kpi/src/lib/full-picture-payload-adapter.ts)
- [apps/qgate-kpi/src/lib/full-picture-types.ts](apps/qgate-kpi/src/lib/full-picture-types.ts)
- [apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.ts](apps/qgate-kpi/src/features/full-picture-dashboard/full-picture-filtering.ts)

If minor shared helpers need to be extracted from the legacy page to support reuse, that extraction is allowed. A wholesale rewrite of the old page is not.

## Data Flow

### Core rule

The new route uses the same backend payload semantics as the current Full Picture implementation.

### Transport rule

The new route should stop relying on direct browser calls to `http://127.0.0.1:8001`.

Instead, add a same-origin bridge inside the Next.js app.

Recommended shape:

1. browser calls a Next route handler such as `/api/full-picture/dashboard`
2. the Next route handler forwards the request to the configured backend API base
3. the existing validation and adaptation layer remains in the frontend codebase

This same-origin bridge should be used by the new workbench bootstrap and any later client refresh path.

### Derivation rule

Within `ready` state:

- all filter changes recompute from the in-memory typed view model
- team rows and outcome summary reuse current derivation behavior
- ticket detail selection continues to rely on the existing chart selection model

No new backend query contract is required for this phase.

## State Model and Error Handling

The new route should preserve the same broad page states as the current Full Picture experience:

- `ready`
- `loading`
- `placeholder`

Behavior expectations:

- `ready`
  - full workbench renders with interactive filters and ticket drilldown

- `loading`
  - shell renders with a clear warming/loading message
  - filter and table surfaces should appear structurally stable, not jumpy

- `placeholder`
  - shell remains visible
  - primary metrics do not fake data
  - the page explains whether the issue is schema or API reachability

The new route should not introduce AI-generated fallback explanations.

## Responsive Behavior

Desktop behavior:

- header and filter workbench stay above the KPI and analysis band
- portfolio and team analysis sit in a strong two-column relationship when space allows
- ticket detail stays below the analysis band

Tablet behavior:

- filter groups wrap into fewer columns
- KPI cards reduce to two columns
- analysis band may collapse to one column if necessary

Mobile behavior:

- route remains usable as a vertical stack
- filter chips and controls remain keyboard and touch accessible
- ticket detail can reduce columns rather than forcing unreadable overflow wherever possible

## Accessibility and Usability

The new route must include:

- visible keyboard focus states on chips, buttons, and table actions
- readable contrast on muted text and pill badges
- clear active states for filters and selected team/outcome slices
- reduced-motion-friendly transitions
- explicit empty states rather than blank cards or blank tables

## Documentation

Document the new route and transport topology in repository docs.

At minimum, explain:

- that `/` now serves the new `Main` Full Picture workbench
- that `/full-picture` remains the legacy route
- that the new interactive path uses a same-origin bridge to the backend API
- which environment variable still controls the backend target

## Testing

Required coverage for this phase:

1. route-level test for the new `/` bootstrap
2. component tests for ready-state filter interaction and KPI updates
3. component tests for team selection driving ticket table narrowing
4. regression tests for loading and placeholder shell behavior
5. API bridge test covering forwarding behavior and error passthrough
6. lint, typecheck, and production build validation for the Next app

Browser automation is optional for this phase. It is useful, but not required if component and route tests cover the core interactions.

## Implementation Notes

Preferred implementation order:

1. add the same-origin bridge for Full Picture dashboard requests
2. switch the app root to the new `Main` workbench bootstrap while keeping the old `/full-picture` route untouched
3. build the new page shell with compact header and filter workbench
4. wire KPI strip, portfolio outcome view, and team expansion from the existing view model
5. wire ticket table drilldown from the current selection model
6. add legacy-link affordance and docs updates
7. validate with tests, lint, typecheck, and production build

## Acceptance Criteria

This phase is complete when:

- `/full-picture` still works as before
- `/` serves the new `Main` Full Picture workbench
- the new route uses real Full Picture data and real filter interactions
- the main surface contains no AI explanation cards
- the visual language is materially closer to the reference dashboard than the previous mocks
- browser-side interactions no longer depend on direct cross-origin calls to `8001`
- ticket detail narrows correctly from both filters and team/outcome selection
- the Next app passes the required validation commands

## Follow-on Work

Later phases can decide whether to:

- promote the new workbench into a more visible navigation position
- add a fuller left-rail navigation shell around multiple analysis pages
- replace the legacy `/full-picture` route after adoption confidence is high
- add richer ticket search or server-driven query parameters if the current client-side model becomes too heavy