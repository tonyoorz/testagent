# Phase Transfer Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone HTML report that visualizes per-ticket phase durations and transfer details for an explicit defect ID list.

**Architecture:** Add focused timeline-segment helpers to the existing phase-analysis module, then build a dedicated report generator under `report/` that converts those segments into a self-contained Plotly HTML page. Keep the report independent from Dash so the user can generate it on demand from the command line.

**Tech Stack:** Python, sqlite3, pandas, plotly, existing `longrunner_analysis.py` helpers, `unittest`

---

### Task 1: Add timeline segment tests

**Files:**
- Modify: `tests/test_phase_transfer_report.py`
- Test: `tests/test_phase_transfer_report.py`

- [ ] **Step 1: Write the failing test for an open last segment**

```python
def test_build_phase_segments_extends_latest_open_phase(self):
    history_data = {
        "data": [
            {
                "timestamp": "2026-04-01T08:00:00Z",
                "user_name": "tester",
                "change_set": [
                    {"field_name": "phase", "old_value_text": "01-New", "value_text": "02-In Pre-Analysis"}
                ],
            },
            {
                "timestamp": "2026-04-03T08:00:00Z",
                "user_name": "tester",
                "change_set": [
                    {"field_name": "phase", "old_value_text": "02-In Pre-Analysis", "value_text": "03-In Analysis"}
                ],
            },
        ]
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase_transfer_report.PhaseTransferReportTests.test_build_phase_segments_extends_latest_open_phase -v`
Expected: FAIL because the segment builder does not exist or does not extend the last open phase.

- [ ] **Step 3: Write the failing test for multi-ticket report rows**

```python
def test_build_report_rows_combines_multiple_tickets(self):
    ticket_rows = build_phase_report_rows([
        {"ticket_id": "1", "ticket_name": "Alpha", "segments": [{"phase": "02-In Pre-Analysis"}]},
        {"ticket_id": "2", "ticket_name": "Beta", "segments": [{"phase": "03-In Analysis"}]},
    ])
    self.assertEqual([row["ticket_id"] for row in ticket_rows], ["1", "2"])
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m unittest tests.test_phase_transfer_report.PhaseTransferReportTests.test_build_report_rows_combines_multiple_tickets -v`
Expected: FAIL because the report row builder does not exist yet.

### Task 2: Implement reusable phase segment helpers

**Files:**
- Modify: `longrunner_analysis.py`
- Test: `tests/test_phase_transfer_report.py`

- [ ] **Step 1: Add the minimal segment builder**

```python
def build_phase_segments(history_data: Dict, ticket_meta: Optional[Dict] = None, now: Optional[datetime] = None) -> List[Dict]:
    ...
```

- [ ] **Step 2: Run focused tests to verify they pass**

Run: `python -m unittest tests.test_phase_transfer_report -v`
Expected: PASS for the new segment and row tests.

- [ ] **Step 3: Refactor only if duplication remains after green**

```python
# Keep `extract_phase_changes()` as the raw history parser.
# Build `build_phase_segments()` on top of it so the report generator can reuse one normalized structure.
```

### Task 3: Implement standalone HTML report generator

**Files:**
- Create: `report/generate_phase_transfer_report.py`
- Modify: `tests/test_phase_transfer_report.py`
- Test: `tests/test_phase_transfer_report.py`

- [ ] **Step 1: Write the failing HTML generation test**

```python
def test_render_html_report_contains_ticket_names_and_summary(self):
    html_text = render_phase_transfer_report_html(sample_payload)
    self.assertIn("Phase Transfer Report", html_text)
    self.assertIn("2595772", html_text)
    self.assertIn("Avg Duration", html_text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase_transfer_report.PhaseTransferReportTests.test_render_html_report_contains_ticket_names_and_summary -v`
Expected: FAIL because the renderer does not exist yet.

- [ ] **Step 3: Add the minimal report generator**

```python
def render_phase_transfer_report_html(payload: Dict[str, Any]) -> str:
    ...

def main() -> int:
    ...
```

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `python -m unittest tests.test_phase_transfer_report -v`
Expected: PASS.

### Task 4: Generate the requested report file

**Files:**
- Create: `report/phase_transfer_report_*.html`
- Modify: none
- Test: generated HTML output

- [ ] **Step 1: Run the generator with the provided ticket IDs**

Run: `python report/generate_phase_transfer_report.py --ticket-ids 2595772,2597367,...,2654082 --output report/phase_transfer_report_requested.html`
Expected: exit code 0 and generated HTML file.

- [ ] **Step 2: Verify the file exists and includes at least one target ticket ID**

Run: `Get-Item report/phase_transfer_report_requested.html`
Expected: file metadata returned.

### Task 5: Final verification

**Files:**
- Modify: none
- Test: `tests/test_phase_transfer_report.py`, generated HTML output

- [ ] **Step 1: Re-run the focused test suite**

Run: `python -m unittest tests.test_phase_transfer_report -v`
Expected: all tests pass.

- [ ] **Step 2: Re-run the exact report generation command fresh**

Run: `python report/generate_phase_transfer_report.py --ticket-ids 2595772,2597367,...,2654082 --output report/phase_transfer_report_requested.html`
Expected: exit code 0 and updated output file.