---
title: MOC PreAnalysis
type: moc
date: 2026-04-13
tags: [moc, preanalysis, project]
---

# MOC PreAnalysis

Automotive testing data analysis platform for BMW DTSV team.

## Architecture

- [[architecture-overview]] - High-level architecture
- [[repository-instructions]] - Development guide
- [[repository-location]] - Repository locations

## Core Concepts

- [[risk-scoring-algorithm]] - Defect prioritization algorithm

## AI System

- [[ai-system-prompts]] - AI prompts for dashboards
- [[triage-prompt]] - Defect triage prompt

## Documentation

- [[obsidian-workflow-guide]] - Knowledge management workflow
- [[obsidian-skill-usage]] - Obsidian skill usage

## Dashboard Modules

| Module | Port | Description |
|--------|------|-------------|
| defect_explore.py | 8051 | Main dashboard |
| defect_matrix.py | 8053 | Matrix analysis |
| risk_analysis.py | 8057 | Risk assessment |
| test_coverage.py | 8055 | Test coverage |

## Links

- [[MOC-Home]]
- [[MOC-Testing]]
