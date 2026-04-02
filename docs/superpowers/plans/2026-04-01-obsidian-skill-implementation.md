# Obsidian Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and install a personal `obsidian` Copilot skill that writes structured notes to the user's Obsidian vault, mirrors them into the repository export folder, and documents the practical limits of summary-only syncing for current-session or machine-local cached Copilot conversation content.

**Architecture:** The implementation is documentation-first and personal-skill scoped. The skill lives under the user's global Copilot skill directory, with one main `SKILL.md` entrypoint and two focused reference documents: one for note templates and write behavior, one for summary-only Copilot conversation export scope, filtering, and limitations.

**Tech Stack:** GitHub Copilot personal skills, Markdown, VS Code workspace storage, Windows PowerShell

---

## File Map

- Create: `C:/Users/q446328/.copilot/skills/obsidian/SKILL.md`
- Create: `C:/Users/q446328/.copilot/skills/obsidian/references/note-templates.md`
- Create: `C:/Users/q446328/.copilot/skills/obsidian/references/conversation-sync.md`
- Create: `C:/Users/q446328/.copilot/skills/obsidian/assets/frontmatter-snippets.md`
- Verify existing: `C:/Users/q446328/AppData/Roaming/Code/User/prompts/superpowers.instructions.md`
- Verify existing: `docs/superpowers/specs/2026-04-01-obsidian-skill-design.md`

### Task 1: Create Personal Skill Entry Point

**Files:**
- Create: `C:/Users/q446328/.copilot/skills/obsidian/SKILL.md`

- [ ] **Step 1: Write the failing discovery checklist**

Create this scratch checklist locally before writing the skill so discovery failures are concrete:

```markdown
# Obsidian Skill Discovery Checklist

- Prompt: 整理成 Obsidian 笔记
  - Current expected state before implementation: no dedicated obsidian skill available
- Prompt: 写日报到 Obsidian
  - Current expected state before implementation: no dedicated obsidian skill available
- Prompt: 导出到 Obsidian vault
  - Current expected state before implementation: no dedicated obsidian skill available
- Prompt: 同步 Copilot 对话到 Obsidian
  - Current expected state before implementation: no dedicated obsidian skill available
```

- [ ] **Step 2: Verify the skill folder does not already exist**

Run:

```powershell
Test-Path "C:\Users\q446328\.copilot\skills\obsidian"
```

Expected: `False`

- [ ] **Step 3: Create the skill folder structure**

Run:

```powershell
New-Item -ItemType Directory -Path "C:\Users\q446328\.copilot\skills\obsidian\references" -Force | Out-Null
New-Item -ItemType Directory -Path "C:\Users\q446328\.copilot\skills\obsidian\assets" -Force | Out-Null
```

- [ ] **Step 4: Write the main skill file with focused trigger wording**

Create `C:/Users/q446328/.copilot/skills/obsidian/SKILL.md` with content shaped like this:

```markdown
---
name: obsidian
description: Use when writing Obsidian notes, knowledge summaries, worklogs, meeting notes, vault markdown exports, mirror exports, or summary-only Copilot conversation exports for the current chat or locally cached sessions on this machine.
argument-hint: "Describe the note or export you want, and optionally include the target note type"
---

# Obsidian Note Workflow

## When to Use

- Persist knowledge into Obsidian
- Write daily or meeting worklogs
- Export repository context into vault-ready markdown
- Sync the current conversation or locally cached Copilot chat artifacts into Obsidian notes as summary-only exports

## Procedure

1. Classify the request as `knowledge`, `worklog`, or `export`
2. Build a safe filename using the per-type rules: knowledge uses `YYYY-MM-DD-<topic-slug>.md`, worklog uses `YYYY-MM-DD-worklog.md`, export uses `YYYY-MM-DD-<source-slug>-export.md`, current-session conversation export uses `YYYY-MM-DD-copilot-current-session-export.md`, and local-cache conversation export uses `YYYY-MM-DD-copilot-cache-<session-folder-name>-export.md` after Windows-safe slug normalization
3. Write the vault copy first when the vault path is reachable
4. Mirror the content into the repository export tree
5. If the vault path is unavailable, write mirror-only storage fallback output without changing the note type
6. If the source is a Copilot conversation, export only converged summary content and exclude process chatter or execution traces

## Required References

- Use [note templates](./references/note-templates.md) for frontmatter, directory, and body rules
- Use [conversation sync](./references/conversation-sync.md) before claiming Copilot chat history can be exported
- Use [frontmatter snippets](./assets/frontmatter-snippets.md) for normalized metadata blocks
```

- [ ] **Step 5: Verify the skill file exists and has valid frontmatter**

Run:

```powershell
Get-Content "C:\Users\q446328\.copilot\skills\obsidian\SKILL.md" -TotalCount 20
```

Expected: frontmatter starts with `---`, `name: obsidian`, and a `description` containing both `Obsidian` and `Copilot` triggers.

- [ ] **Step 6: Commit**

```bash
git add -- docs/superpowers/plans/2026-04-01-obsidian-skill-implementation.md
git commit -m "docs: add obsidian skill implementation plan"
```

### Task 2: Add Template and Write-Behavior References

**Files:**
- Create: `C:/Users/q446328/.copilot/skills/obsidian/references/note-templates.md`
- Create: `C:/Users/q446328/.copilot/skills/obsidian/assets/frontmatter-snippets.md`

- [ ] **Step 1: Write the failing template checklist**

Use this checklist to guard against vague template output:

```markdown
- Knowledge notes must include Summary, Background, Key Concepts, Conclusions, Evidence, Source, Links, Open Questions
- Worklogs must include Done, Decisions, Issues, Risks, Next Steps, Action Items, Source, Links
- Export notes must include Export Purpose, Original Source, Transformation Rules, Output, Usage Notes, Source, Links
- Every note must include normalized frontmatter with vault_path, vault_status, and mirror_path
```

- [ ] **Step 2: Write the note template reference**

Create `C:/Users/q446328/.copilot/skills/obsidian/references/note-templates.md` with explicit sections for:

```markdown
# Note Templates

## Output Paths

- Vault knowledge: `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot\knowledge\YYYY\`
- Vault worklog: `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot\worklog\YYYY\MM\`
- Vault export: `\\uh19230029.bmwgroup.net\home$\Q446328\Obsidian Vault\copilot\export\YYYY\`
- Mirror knowledge: `obsidian_export/knowledge/YYYY/`
- Mirror worklog: `obsidian_export/worklog/YYYY/MM/`
- Mirror export: `obsidian_export/export/YYYY/`

## File Naming

- Knowledge: `YYYY-MM-DD-<topic-slug>.md`
- Worklog: `YYYY-MM-DD-worklog.md` by default, or `YYYY-MM-DD-worklog-<topic-slug>.md` when multiple same-day worklogs are needed
- Export: `YYYY-MM-DD-<source-slug>-export.md`
- Conversation-derived export: `YYYY-MM-DD-copilot-current-session-export.md` for current-session exports, or `YYYY-MM-DD-copilot-cache-<session-folder-name>-export.md` for local-cache exports after Windows-safe slug normalization

## Existing File Policy

- Append by default when the file already exists
- Overwrite only when the user explicitly asks
- Create a new file when title or note type changes materially
- If the vault is unavailable, keep the same note type and write a mirror-only storage fallback
```

- [ ] **Step 3: Add normalized frontmatter snippets**

Create `C:/Users/q446328/.copilot/skills/obsidian/assets/frontmatter-snippets.md` with exact blocks like:

```markdown
# Frontmatter Snippets

## Knowledge

```yaml
---
title: ""
type: knowledge
date: 2026-04-01
tags: []
source_repo: ""
source_path: ""
summary: ""
related_topics: []
vault_path: ""
vault_status: written
mirror_path: ""
generated_by: copilot-obsidian-skill
---
```

## Worklog

```yaml
---
title: ""
type: worklog
date: 2026-04-01
tags: []
source_repo: ""
source_path: ""
project: ""
participants: []
status: ""
next_actions: []
vault_path: ""
vault_status: written
mirror_path: ""
generated_by: copilot-obsidian-skill
---
```
```

- [ ] **Step 4: Verify the reference files load cleanly**

Run:

```powershell
Get-ChildItem "C:\Users\q446328\.copilot\skills\obsidian\references"
Get-Content "C:\Users\q446328\.copilot\skills\obsidian\assets\frontmatter-snippets.md" -TotalCount 60
```

Expected: both reference files exist and include explicit output paths and frontmatter blocks.

- [ ] **Step 5: Commit**

```bash
git add -- docs/superpowers/plans/2026-04-01-obsidian-skill-implementation.md
git commit -m "docs: checkpoint obsidian skill template plan"
```

### Task 3: Add Copilot Conversation Sync Scope Reference

**Files:**
- Create: `C:/Users/q446328/.copilot/skills/obsidian/references/conversation-sync.md`

- [ ] **Step 1: Write the failing scope statement**

Document the unsupported claim explicitly before writing the reference:

```markdown
False claim to avoid: "the skill can sync every Copilot conversation from the user's account"
False claim to avoid: "the skill can export raw Copilot transcripts including hidden reasoning or tool traces"
Reason it fails: only locally cached session artifacts available on this machine can be inspected from this environment, and the approved design limits exports to summary-only content
```

- [ ] **Step 2: Write the conversation sync reference with hard limits**

Create `C:/Users/q446328/.copilot/skills/obsidian/references/conversation-sync.md` with content shaped like this:

```markdown
# Copilot Conversation Sync Scope

## What the skill can sync

- Summary-only takeaways from the current conversation when its content is available in the session
- Summary-only takeaways from locally cached Copilot chat session artifacts stored under VS Code workspace storage on this machine

## What the skill should keep

- conclusions
- decisions
- action items
- curated evidence
- final summaries
- user-facing takeaways

## What the skill must exclude

- chain-of-thought
- route reasoning
- tool calls
- tool arguments
- progress heartbeats
- retries
- partial intermediate drafts
- other execution traces

## What the skill cannot promise

- All Copilot conversations across the user's account
- Conversations from other machines
- Conversations no longer present in local cache
- Cloud-only history that is not exposed through local files or supported APIs
- Raw transcript export that includes excluded execution details

## Source Metadata Rules

- Current-session exports use `source_repo: github-copilot-chat` and `source_path: copilot://current-session`
- Local-cache exports use `source_repo: github-copilot-chat-cache` and `source_path: copilot-cache://<session-folder-name>`

## Local Evidence

- Current machine currently shows `2` `chat-session-resources` roots
- Current machine currently shows `4` cached session folders

## Export Guidance

When asked to sync Copilot conversations, first state whether the request targets:

1. current conversation only
2. locally cached sessions on this machine
3. all historical account conversations

Only categories 1 and 2 should be offered as supported in this skill.
```

- [ ] **Step 3: Verify the local evidence command**

Run:

```powershell
$dirs = Get-ChildItem "$env:APPDATA\Code\User\workspaceStorage" -Recurse -Directory -Filter "chat-session-resources" -ErrorAction SilentlyContinue
$sessionCount = 0
foreach ($d in $dirs) { $sessionCount += (Get-ChildItem $d.FullName -Directory -ErrorAction SilentlyContinue | Measure-Object).Count }
"DIRS=$($dirs.Count)"
"SESSIONS=$sessionCount"
```

Expected: `DIRS=2` and `SESSIONS=4` on the current machine, unless local cache changes between runs.

- [ ] **Step 4: Commit**

```bash
git add -- docs/superpowers/plans/2026-04-01-obsidian-skill-implementation.md
git commit -m "docs: checkpoint obsidian conversation sync plan"
```

### Task 4: Install and Validate the Personal Skill

**Files:**
- Verify: `C:/Users/q446328/.copilot/skills/obsidian/SKILL.md`
- Verify: `C:/Users/q446328/.copilot/skills/obsidian/references/note-templates.md`
- Verify: `C:/Users/q446328/.copilot/skills/obsidian/references/conversation-sync.md`

- [ ] **Step 1: Confirm the personal skill is discoverable on disk**

Run:

```powershell
Get-ChildItem "C:\Users\q446328\.copilot\skills\obsidian" -Recurse
```

Expected: `SKILL.md`, `references/`, and `assets/` all exist.

- [ ] **Step 2: Validate a knowledge-note trigger manually**

Use this prompt in a fresh Copilot Chat session:

```text
请把这个问题整理成 Obsidian 知识笔记，并保留 vault 和 export 两份路径
```

Expected: the agent follows the `obsidian` note workflow rather than generic Markdown drafting.

- [ ] **Step 3: Validate a worklog trigger manually**

Use this prompt:

```text
请把今天的工作内容写成 Obsidian worklog
```

Expected: the output uses the worklog sections and frontmatter instead of a freeform summary.

- [ ] **Step 4: Validate a conversation-sync prompt manually**

Use this prompt:

```text
把当前 Copilot 对话同步到 Obsidian，并说明是不是全量历史同步
```

Expected: the agent supports current-session export, mentions local cache scope, and refuses to claim full account-wide history sync.
Expected: the agent exports only summary-level takeaways, mentions local cache scope, and refuses to claim full account-wide history sync or raw transcript export.

- [ ] **Step 5: Commit**

```bash
git add -- docs/superpowers/plans/2026-04-01-obsidian-skill-implementation.md
git commit -m "docs: finalize obsidian skill implementation plan"
```

## Self-Review

### Spec coverage

- Vault-first plus mirror export: covered in Tasks 1 and 2
- Three note types: covered in Task 2
- Trigger phrases and discovery wording: covered in Task 1
- Existing-file append behavior: covered in Task 2
- Vault-unavailable fallback: covered in Task 1 and Task 2 instructions
- Conversation sync boundary and summary-only filtering: covered in Task 3 and Task 4

### Placeholder scan

- No `TODO` or `TBD` placeholders remain
- File paths are explicit
- Validation commands are concrete

### Type consistency

- The plan consistently uses the same note types: `knowledge`, `worklog`, `export`
- The same vault base and mirror base are used throughout
- The conversation-sync capability is consistently limited to current-session and locally cached content
- Conversation export is consistently described as summary-only and never as raw transcript or full-history sync

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-01-obsidian-skill-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?