---
name: analysissnapshot
description: Use when exporting defect_explore or related Dash pages into a shareable multi-page static HTML snapshot site.
---

# Analysis Snapshot

Use this skill whenever you need to share dashboard results without requiring the recipient to run Python or access the live Dash service.

## What this skill does

Generates a static website snapshot from one or more running dashboard URLs:

1. Captures rendered page DOM using Playwright.
2. Downloads page CSS/image assets into a local assets folder.
3. Removes runtime scripts to make pages stable as static snapshots.
4. Creates a landing page (`site_index.html`) linking all exported pages.

Output folder default:

- `report/analysis_snapshots/YYYYMMDD_HHMMSS/`

## Standard command

Run from repository root (recommended venv Python):

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe analysis_snapshot.py --base-url http://127.0.0.1:8051 --routes /,/risk_analysis,/test_coverage
```

## Export specific URLs (ignores --routes)

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe analysis_snapshot.py --urls http://127.0.0.1:8051/ http://127.0.0.1:8051/risk_analysis?team=DTSV_China
```

## Useful options

- `--output-dir <path>`: custom output directory
- `--wait-ms 6000`: wait longer for heavy charts before capture
- `--timeout-sec 60`: increase navigation/download timeout
- `--download-external-assets`: also download external CDN assets (default is same-origin only)
- `--headed`: open visible browser for troubleshooting

## Prerequisites

1. Dash app is already running and reachable (for example `defect_explore.py` on `:8051`).
2. Playwright is installed in venv:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m pip install playwright
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m playwright install chromium
```

## Validation checklist

1. Confirm output directory exists under `report/analysis_snapshots/`.
2. Confirm `site_index.html` exists.
3. Confirm each target page has an exported `.html` file.
4. Confirm `assets/` exists and contains css/images.
5. Open `site_index.html` and verify each page can be opened locally.

## Notes and limitations

- This export is a static snapshot, not a live dashboard.
- Server-side callbacks and interactive filters are frozen at capture state.
- By default, external CDN assets are not downloaded to avoid timeout in restricted networks; their original URLs are kept in HTML.
- For best fidelity, wait until charts and tables are fully loaded before capture.
