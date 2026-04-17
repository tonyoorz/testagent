# Phase Transfer Report Design

## Goal

Generate a standalone HTML report for a user-provided defect ID list that shows how long each ticket spent in each phase, using an Octane-like horizontal timeline plus a verification-friendly transfer table.

## Scope

- Input: explicit defect ID list from the user.
- Output: one standalone HTML file under `report/`.
- Data source: `octane_defect_histories` in SQLite, with file fallback through existing helpers.
- Included timing rule: if a ticket is still in its latest phase, the final segment extends to the defect's latest known update time or report generation time.

## Chosen Approach

Use a new report generator script that reuses the existing phase-history parsing logic from `longrunner_analysis.py` and produces a self-contained HTML page.

The page contains:

1. Summary cards for ticket count, transfer count, average duration, and longest segment.
2. A Plotly horizontal timeline grouped by ticket, with one colored bar per phase segment.
3. A sortable details table listing each phase segment with start, end, duration, and whether it is still open.
4. A small missing-data section for ticket IDs with no usable history.

## Data Model

Each rendered segment includes:

- `ticket_id`
- `ticket_name`
- `phase`
- `start_time`
- `end_time`
- `duration_hours`
- `duration_days`
- `is_open_segment`
- `from_phase`
- `to_phase`

## Validation Strategy

Follow TDD for the new behavior that does not exist today:

1. Add a failing test for extending the last open phase segment.
2. Add a failing test for building report rows from multiple tickets.
3. Implement the minimal report generator.
4. Run focused tests.
5. Generate the requested HTML report and verify that the target file exists.

## Non-Goals

- No integration into `defect_explore.py` in this change.
- No new database tables.
- No attempt to restyle existing Dash pages.