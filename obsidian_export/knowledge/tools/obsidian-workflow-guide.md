---
title: Obsidian Workflow Guide
type: knowledge
date: 2026-04-13
tags: [obsidian, workflow, knowledge-management]
source_repo: personal
description: Detailed workflow guide for using Obsidian with Copilot
---

# Obsidian Workflow Guide

Based on Andrej Karpathy LLM Wiki methodology.

## Philosophy

### Three-Layer Memory Architecture

Layer 1: Working Memory (inbox/)
- Quick capture
- Temporary notes
- Current session context

Layer 2: External Knowledge Base (knowledge/)
- Structured notes
- Interconnected concepts
- Long-term storage

Layer 3: Model Weights (LLM training)
- Not directly modifiable
- Externalized through notes

### Core Principles

1. Externalize Knowledge: Notes are frozen thoughts
2. Atomic Notes: One concept per note
3. Bidirectional Links: Connect everything
4. Progressive Construction: Iterate from fragments to complete

---

## Note Types

### 1. Knowledge Notes

Purpose: Capture concepts, architecture, learnings, decisions

Location: knowledge/

Template: templates/knowledge-template.md

Trigger Phrases:
- 整理成 Obsidian 知识笔记
- create knowledge note
- write architecture note

Required Sections:
- Summary
- Background
- Key Concepts
- Conclusions
- Evidence
- Source
- Links
- Open Questions

Example:
- knowledge/concepts/risk-scoring-algorithm.md
- knowledge/projects/preanalysis/architecture-overview.md

---

### 2. Worklog Notes

Purpose: Track daily work, meetings, progress, action items

Location: worklog/

Template: templates/worklog-template.md

Trigger Phrases:
- 写日报
- create worklog
- write meeting notes

Required Sections:
- Done
- Decisions
- Issues
- Risks
- Next Steps
- Action Items
- Source
- Links

File Naming:
- Daily: YYYY-MM-DD-worklog.md
- Meeting: YYYY-MM-DD-meeting-topic.md
- Weekly: YYYY-WW-weekly.md

---

### 3. Export Notes

Purpose: Import external content into vault

Location: export/

Types:
- Copilot conversation export
- Repository documentation export
- Web clips
- Literature notes

Trigger Phrases:
- 导出 Copilot 对话
- export conversation
- sync to vault

Conversation Export Rules:
- Summary-only (no chain-of-thought)
- Current session or local cache only
- No full-history claims

---

## Daily Workflow

### Morning Routine

1. Open Obsidian
2. Review MOC-Home.md for overview
3. Check worklog/daily/ for yesterday note
4. Create today worklog using Copilot

### During Work

Quick Capture:
Use Copilot: 整理这个发现成知识笔记

After Code Review:
Use Copilot: 把这个架构理解写成 Obsidian 笔记

After Meeting:
Use Copilot: 写会议纪要到 Obsidian

### End of Day

1. Update today worklog
2. Create knowledge notes for new learnings
3. Review and update MOC if needed

---

## Copilot Integration

### Using the Obsidian Skill

Skill location: ~/.copilot/skills/obsidian/SKILL.md

Supported Commands:

| Command | Action |
|---------|--------|
| 整理成 Obsidian 知识笔记 | Create knowledge note |
| 写日报 | Create daily worklog |
| 写会议纪要 | Create meeting notes |
| 导出当前对话 | Export conversation summary |
| 同步到 vault | Export to vault |

### Vault-First Workflow

1. Skill writes to vault path first (if reachable)
2. Creates mirror copy in obsidian_export/
3. If vault unavailable, mirror-only fallback

### Conversation Export

Supported:
- Current session
- Locally cached sessions on this machine

Not Supported:
- Account-wide history
- Other machines
- Cloud-only history

---

## MOC System

### MOC-Home.md - Main Entry

maps/MOC-Home.md
├── Domains
│   ├── MOC-Testing
│   └── MOC-AI-ML
├── Projects
│   └── MOC-PreAnalysis
└── Tools
    └── obsidian-skill-usage

### Creating New MOC

1. Create file: maps/MOC-Topic.md
2. Add frontmatter
3. List related notes with wiki-links
4. Link from MOC-Home

---

## Best Practices

### Note Quality Checklist

- Title is clear and descriptive
- Frontmatter is complete
- Summary captures essence
- Key concepts are explained
- Evidence supports conclusions
- Links to related notes
- Open questions documented

### Linking Strategy

1. Always add wiki-links: [[note-name]]
2. Link to concepts, not just files
3. Update MOC when adding new notes
4. Use tags for categorization

### Maintenance Routine

Weekly:
- Review recent notes
- Update MOC indexes
- Clean up inbox/

Monthly:
- Archive old notes
- Consolidate similar notes
- Update broken links

---

## Directory Structure Reference

obsidian_export/
├── inbox/                    # Quick capture
├── knowledge/                # Structured knowledge
│   ├── concepts/
│   ├── domains/
│   ├── projects/
│   └── tools/
├── worklog/                  # Work records
│   ├── daily/
│   ├── meetings/
│   └── weekly/
├── export/                   # External imports
├── maps/                     # MOC indexes
└── templates/                # Note templates

---

## Links

- [[MOC-Home]]
- [[obsidian-skill-usage]]
- [[architecture-overview]]
- [[risk-scoring-algorithm]]
