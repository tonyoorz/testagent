---
name: defect-qgate-title-guidance
description: Use when generating QGate guidance from defect titles to recommend top_aida, found in function, project, and owner from the local Octane defect database.
---

# Defect QGate Title Guidance

Use this skill when the user wants a reusable QGate recommendation table derived from defect titles.

## Default output

The generator writes one file by default:

- report/ad_hoc/defect_qgate_title_top_aida_function_project_owner_guidance_YYYYMMDD_HHMMSS.csv

It does not write xlsx, markdown summaries, or extra helper csv files unless the script is changed later.

## Standard command

Run from repo root:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_defect_qgate_title_guidance.py
```

## Optional command variants

Write to a fixed file path:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_defect_qgate_title_guidance.py --output report/ad_hoc/defect_qgate_title_top_aida_function_project_owner_guidance.csv
```

Use a different database:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_defect_qgate_title_guidance.py --db-path database/local_data.db
```

Lower thresholds for tiny local test datasets:

```powershell
c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe report/generate_defect_qgate_title_guidance.py --min-feature-total 2 --min-match-count 2
```

## Output columns

- title_keyword
- suggested_top_aida
- candidate_found_in_function
- candidate_project
- candidate_owner
- top_aida_precision
- function_share_in_top_aida
- project_share_within_aida_function
- owner_share_within_aida_function_project

## Validation

1. Confirm exactly one csv file was written for the run.
2. Confirm the file exists and is non-empty.
3. Confirm expected key columns exist: title_keyword, suggested_top_aida, candidate_found_in_function, candidate_project, candidate_owner.

## Implementation notes

- Script: report/generate_defect_qgate_title_guidance.py
- Source table: octane_defects in database/local_data_rebuilt.db by default
- Project values are restricted to the normalized project set used in the dashboard sync.