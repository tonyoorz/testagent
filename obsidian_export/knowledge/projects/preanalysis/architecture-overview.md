---
title: PreAnalysis Architecture Overview
type: knowledge
date: 2026-04-13
tags: [architecture, preanalysis, dashboard]
source_repo: TPMDashbaord
source_path: AGENTS.md
summary: High-level architecture of PreAnalysis automotive testing platform
---

# PreAnalysis Architecture Overview

## Summary
PreAnalysis is a comprehensive automotive testing data analysis platform for BMW DTSV team.

## Background
Built to help testing teams understand defect distribution, test coverage, and risk assessment.

## Key Concepts
### Technology Stack
- Backend: Python Dash 2.13.0
- Data: Pandas, SQLite
- Visualization: Plotly
- AI: DeepSeek API

### Main Components
- Main Dashboard (8051): defect_explore.py
- Sub-modules: defect_matrix, trend, risk_analysis, test_coverage
- AI System: agent/ core
- Data Pipeline: download/ octane_downloader

## Evidence
See `AGENTS.md` for full architecture documentation.

## Links
- [[data-pipeline]]
- [[ai-integration]]
- [[MOC-PreAnalysis]]
