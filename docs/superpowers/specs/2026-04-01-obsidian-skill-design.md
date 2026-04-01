# Obsidian Skill Design

## Summary

Create a personal Copilot skill named `obsidian` that helps with three recurring workflows:

- Knowledge capture and structured note consolidation
- Worklog creation for daily progress, meetings, and action items
- Export bridging from repository artifacts into Obsidian-friendly Markdown

The skill should prefer writing directly into the user's Obsidian vault, while also keeping a mirrored export copy inside this repository for traceability and reuse.

## Context

- Skill scope: personal Copilot skill installed under `~/.copilot/skills/obsidian`
- Primary vault root: `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault`
- Vault output base: `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot`
- Repository mirror base: `obsidian_export`
- User priorities:
  - knowledge organization
  - work records
  - export bridging
- Obsidian is already installed and the vault path is reachable from this machine.

## Goals

1. Make Obsidian note generation a repeatable, on-demand Copilot workflow rather than ad hoc Markdown drafting.
2. Produce notes with predictable structure, metadata, and file naming.
3. Support both direct vault writing and repository-side mirrored exports.
4. Handle unavailable network storage gracefully without blocking note creation.
5. Keep the skill independent from Obsidian plugins so it works with plain Markdown files.

## Non-Goals

1. Building a full bidirectional sync engine between vault and repository.
2. Managing attachments, images, canvas files, or other non-Markdown Obsidian assets.
3. Editing arbitrary existing notes beyond controlled append behavior.
4. Requiring any Obsidian community plugin to function.
5. Replacing project documentation or source-of-truth files inside the repository.

## Output Model

The skill uses a vault-first, mirror-second write strategy.

### Primary target

- `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot\knowledge\YYYY\`
- `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot\worklog\YYYY\MM\`
- `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot\export\YYYY\`

### Mirror target

- `obsidian_export/knowledge/YYYY/`
- `obsidian_export/worklog/YYYY/MM/`
- `obsidian_export/export/YYYY/`

Both targets should contain equivalent Markdown content. The mirror copy may include additional provenance metadata such as the final vault path.

## Note Types

The skill supports three note types.

### 1. Knowledge

Use for:

- architecture understanding
- root-cause summaries
- implementation learnings
- domain concept notes
- comparison and conclusion writeups

Required frontmatter fields:

- `title`
- `type`
- `date`
- `tags`
- `source_repo`
- `source_path`
- `summary`
- `related_topics`
- `vault_path`

Required body sections:

- `## Summary`
- `## Background`
- `## Key Concepts`
- `## Conclusions`
- `## Evidence`
- `## Source`
- `## Links`
- `## Open Questions`

### 2. Worklog

Use for:

- daily logs
- weekly summaries
- meeting notes
- task progress records
- action item tracking

Required frontmatter fields:

- `title`
- `type`
- `date`
- `tags`
- `project`
- `participants`
- `status`
- `next_actions`
- `vault_path`

Required body sections:

- `## Done`
- `## Decisions`
- `## Issues`
- `## Risks`
- `## Next Steps`
- `## Action Items`
- `## Source`
- `## Links`

### 3. Export

Use for:

- exporting repository notes into vault format
- transforming analysis outputs into Obsidian-ready Markdown
- converting AI-generated summaries into persistent notes
- bridging prompt or documentation assets into the vault

Required frontmatter fields:

- `title`
- `type`
- `date`
- `tags`
- `source_repo`
- `source_path`
- `export_reason`
- `vault_path`

Required body sections:

- `## Export Purpose`
- `## Original Source`
- `## Transformation Rules`
- `## Output`
- `## Usage Notes`
- `## Source`
- `## Links`

## Naming Rules

### File names

- Knowledge: `YYYY-MM-DD-topic.md`
- Worklog: `YYYY-MM-DD-worklog.md`
- Export: `YYYY-MM-DD-source-export.md`

### Safety rules

1. Remove or normalize characters invalid for Windows file systems.
2. Collapse repeated whitespace or punctuation into single hyphens.
3. Preserve date prefixes for sortability.
4. Prefer short topical suffixes over long sentence-style filenames.

## Frontmatter Standard

All generated files should include at least this normalized metadata block:

```yaml
---
title: ""
type: knowledge
date: 2026-04-01
tags: []
source_repo: TPMDashbaord
source_path: ""
vault_path: ""
generated_by: copilot-obsidian-skill
---
```

The `type` value changes between `knowledge`, `worklog`, and `export`.

## Triggering Model

The skill should be discoverable for requests that indicate note creation, consolidation, or Obsidian export work.

### Expected trigger phrases

- `organize into Obsidian notes`
- `write a knowledge note`
- `summarize this into Obsidian`
- `create a worklog`
- `write daily report`
- `write meeting notes`
- `export to Obsidian`
- `generate vault markdown`
- `sync to vault`
- `整理成 Obsidian 笔记`
- `沉淀知识`
- `总结成笔记`
- `写日报`
- `会议纪要`
- `工作记录`
- `导出到 Obsidian`
- `同步到 vault`

### Should not trigger for

- ordinary code edits
- generic Markdown formatting unrelated to note workflows
- repository documentation changes that should stay inside the repo
- requests that only ask questions without wanting a persistent note artifact

## Write Behavior

The skill should follow this decision flow:

1. Classify the request as `knowledge`, `worklog`, or `export`.
2. Build the target filename from the current date and topic.
3. Render standardized frontmatter.
4. Render the body template for the selected type.
5. Attempt to write the primary vault copy first.
6. Write the repository mirror copy second.
7. Return both paths to the user.

## Existing File Policy

Default behavior for an existing target file should be append, not overwrite.

Rules:

1. If the target file exists and the user did not explicitly request overwrite, append a new timestamped section.
2. If the user explicitly requests replacement, allow full overwrite.
3. If the file exists but the type or title no longer matches, create a new file instead of merging unrelated content.

## Failure and Degradation Strategy

### Vault unavailable

If the network vault path is unavailable:

1. Do not fail the whole workflow.
2. Write only the repository mirror copy.
3. Add a visible note near the top of the body stating `vault unavailable, export-only fallback`.
4. Return that the export succeeded but direct vault write did not.

### Invalid file name input

If the requested title contains unsafe characters:

1. Sanitize automatically.
2. Keep the readable title in frontmatter.
3. Use the sanitized version only for the file name.

### Missing source context

If the request asks for export or knowledge consolidation but source inputs are incomplete:

1. Still create a note if the user intent is clear.
2. Mark missing fields explicitly instead of fabricating provenance.
3. Prefer empty strings or placeholder bullets over invented evidence.

## Implementation Shape

The personal skill is expected to live under a dedicated folder and may include supporting references or templates.

Planned files:

- `C:/Users/q446328/.copilot/skills/obsidian/SKILL.md`
- optional reference templates under the same skill folder if the main file grows too large

The skill content should emphasize procedure, decision rules, output locations, and note templates. It does not need executable scripts for the first version.

## Quality Bar

The first implementation should be considered successful if it can reliably do the following:

1. Generate one note of each type with valid frontmatter.
2. Write to the reachable vault path.
3. Mirror the same note into `obsidian_export`.
4. Fall back cleanly when the vault path is unavailable.
5. Avoid destructive overwrites unless explicitly requested.

## Validation Plan

After implementation, verify these scenarios:

1. Knowledge note creation from repository context.
2. Worklog note creation from a status summary or meeting summary.
3. Export note creation from an existing repository Markdown file.
4. Vault path unavailable fallback.
5. Existing file append behavior.
6. Unsafe title sanitization.

## Open Decisions Resolved In This Spec

The following choices are intentionally fixed by this design:

1. Output model is vault-first with repository mirroring.
2. Only three note types are supported in v1.
3. Obsidian plugin dependencies are out of scope.
4. Existing files append by default.
5. Mirror path structure matches the vault structure for easier lookup.

## Next Step

Once this design is reviewed and approved, the next step is to write an implementation plan for creating and installing the personal `obsidian` skill.