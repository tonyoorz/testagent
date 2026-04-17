---
name: qgate-kpi-report-generator
description: Use when regenerating QGate KPI reports after data refresh, especially when team coverage appears incomplete or comparison report generation fails in local environments.
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

When bilingual compare output is enabled, two additional files are generated:

4. kpi_report_2024_2025_YYYYMMDD_HHMMSS_en.html
5. kpi_report_2024_2025_YYYYMMDD_HHMMSS_en.xlsx

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

Recommended on Windows repo-local venv:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_dual_kpi_reports.py
```

Generate Chinese + English compare reports in one run:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_dual_kpi_reports.py --compare-bilingual
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

Generate compare report in English only:

```powershell
python report/generate_dual_kpi_reports.py --compare-lang en
```

## Reliability mode (recommended after latest data refresh)

If Team Coverage shows only a subset of teams with non-zero values:

1. Set history data source fallback mode before generating QGate dashboard.
2. Regenerate reports in the same shell session.

```powershell
$env:OCTANE_DATA_SOURCE='file_fallback'
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_dual_kpi_reports.py
```

Why: history analysis defaults to DB-priority mode in some environments, and certain teams may have complete history JSON files but incomplete DB history rows, causing false "History_Missing_or_Error" inflation.

## Fallback for compare-report import errors

If dual generator fails with ModuleNotFoundError (for example: octane_db) when running kpi_analysis_2024_2025.py:

1. Keep the generated timestamp folder from the failed run.
2. Re-run comparison report directly with PYTHONPATH set to repo root.

```powershell
$env:PYTHONPATH='C:/Users/q446328/Desktop/TPMDashbaord'
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/kpi_analysis_2024_2025.py --output-html report/generated_runs/<TIMESTAMP>/kpi_report_2024_2025_<TIMESTAMP>.html --output-xlsx report/generated_runs/<TIMESTAMP>/kpi_report_2024_2025_<TIMESTAMP>.xlsx
```

## Required validation after generation

1. Confirm the 3 output files exist.
2. If bilingual mode was used, confirm both _en.html and _en.xlsx exist.
3. Confirm files are stored under the latest timestamp directory (directory name matches ^\d{8}_\d{6}$).
4. Open HTML files and check title blocks and section tables load correctly.
5. If custom output paths were used, confirm files are present at target paths.
6. Confirm KPI HTML timestamp and top metrics match the latest run data.
7. Confirm Team Coverage does not show unexpected 0% across non-empty teams.

## Implementation notes

- This skill delegates all report logic to existing scripts:
  - report/generate_qgate_kpi_dashboard.py
  - report/kpi_analysis_2024_2025.py
- The orchestrator script is:
  - report/generate_dual_kpi_reports.py
- The comparison report generator supports explicit output paths:
  - report/kpi_analysis_2024_2025.py --output-html ... --output-xlsx ...
- For reproducible local generation, prefer running from repo root and pinning venv Python executable.
