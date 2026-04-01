---
name: qgate-kpi-report-generator
description: Generate both KPI reports after data refresh (QGate interactive dashboard + 2024/2025 KPI comparison report).
---

# QGate KPI Report Generator

Use this skill whenever the user asks to regenerate KPI reports with latest data.

## What this skill generates

By default, every run creates a new timestamp folder:

- report/generated_runs/YYYYMMDD_HHMMSS/

Inside that folder:

1. qgate_kpi_dashboard_YYYYMMDD_HHMMSS.html
2. kpi_report_2024_2025_YYYYMMDD_HHMMSS.html
3. kpi_report_2024_2025_YYYYMMDD_HHMMSS.xlsx

## Data prerequisites

- qgate/defect/*.json and qgate/history/*.json are updated
- mr/*.json is updated
- database/local_data.db contains latest defect data

## Data refresh behavior

- QGate dashboard HTML: generated from latest data
- KPI comparison Excel: generated from latest data
- KPI comparison HTML: generated from latest data by default

Optional: if you want to force a fixed static HTML template for KPI page,
run kpi_analysis_2024_2025.py with --html-template.

## Standard command

Run from repository root:

```powershell
python report/generate_dual_kpi_reports.py
```

The script also supports changing the root folder:

```powershell
python report/generate_dual_kpi_reports.py --output-root report/custom_runs
```

## Optional command variants

Only regenerate QGate dashboard:

```powershell
python report/generate_dual_kpi_reports.py --skip-compare
```

Only regenerate 2024/2025 KPI report:

```powershell
python report/generate_dual_kpi_reports.py --skip-qgate
```

Specify teams and transition threshold for QGate dashboard:

```powershell
python report/generate_dual_kpi_reports.py --teams "[AT]W72-FIT,[AT]W71-FIT" --min-transition-count 150
```

## Required validation after generation

1. Confirm the 3 output files exist.
2. Confirm files are stored under the latest timestamp directory.
3. Open HTML files and check title blocks and section tables load correctly.
4. If custom output paths were used, confirm files are present at target paths.
5. Confirm KPI HTML timestamp and top metrics match the latest run data.

## Implementation notes

- This skill delegates all report logic to existing scripts:
  - report/generate_qgate_kpi_dashboard.py
  - report/kpi_analysis_2024_2025.py
- The orchestrator script is:
  - report/generate_dual_kpi_reports.py
- The comparison report generator supports explicit output paths:
  - report/kpi_analysis_2024_2025.py --output-html ... --output-xlsx ...
