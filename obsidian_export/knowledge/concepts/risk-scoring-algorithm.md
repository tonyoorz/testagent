---
title: Risk Scoring Algorithm
type: knowledge
date: 2026-04-13
tags: [risk, algorithm, testing]
source_repo: TPMDashbaord
source_path: data_processor.py
summary: Risk scoring algorithm for defect prioritization
---

# Risk Scoring Algorithm

## Summary
Risk scoring algorithm used in PreAnalysis for prioritizing defects based on multiple factors.

## Background
In automotive testing, defects need prioritization beyond simple severity. This algorithm combines multiple signals.

## Key Concepts
- Severity weighting
- Detection phase impact
- Historical patterns
- TopIssue flags

## Evidence
Implemented in `data_processor.py` Risk Score calculation.

## Links
- [[defect-matrix-interpretation]]
- [[MOC-Testing]]
