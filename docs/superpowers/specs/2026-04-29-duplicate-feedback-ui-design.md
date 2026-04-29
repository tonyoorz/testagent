# Duplicate Feedback UI Design

## Goal

Add a first-class feedback entry point to duplicate-search results in Agent chat so users can mark each recommended ticket as matching or not matching directly from the result list.

This design upgrades duplicate search output from plain text into a structured, renderable result payload for the local duplicate-search path, while keeping the existing LLM summary/chat flow intact.

## Scope

Included:

- structured assistant message payload for local duplicate-search results
- dedicated renderer for duplicate-search result cards in Agent chat
- per-candidate `👍 匹配` / `👎 不匹配` actions
- persistence through existing `FeedbackStore.submit_feedback()`
- lightweight in-card acknowledgement after feedback submission
- narrow tests for payload generation and feedback submission wiring

Excluded:

- LLM-formatted duplicate-search path UI changes
- redesign of the generic chat message model across the whole app
- new database schema
- automatic training scheduler
- user identity plumbing beyond current optional `user_id`

## Context

### Current State

In [agent/legacy/ai_chat_manager_legacy.py](../../../agent/legacy/ai_chat_manager_legacy.py), the local duplicate-search branch performs these steps:

1. build duplicate candidates from `DuplicateIssueIndex`
2. generate a recommendation summary as plain text
3. append a normal assistant chat message with `content: str`
4. return prebuilt `chat_history_children`

This means duplicate candidates are not represented as structured UI data. Users can read them, but cannot interact with them.

### Existing Backend Support

The backend already supports feedback persistence:

- [feedback_store.py](../../../feedback_store.py) stores `query_text`, `ticket_id`, `signal`, `base_score`, `rank_pos`, `user_id`
- [agent/core/intelligent_agent.py](../../../agent/core/intelligent_agent.py) already defines `SubmitDuplicateSearchFeedbackTool`

The missing piece is the UI contract and callback wiring.

## Problem

Plain text rendering blocks the full feedback loop:

- no direct way for users to label recommended tickets
- no stable ticket-level UI affordance beside each candidate
- no structured candidate payload for future analytics or richer rendering
- duplicate-search feedback depends on manual or indirect tooling instead of the normal user flow

## Design Principles

1. **Ticket-level interaction**: feedback must be attached to each candidate, not to the whole answer.
2. **Structured over free text**: candidate data should stay machine-readable at render time.
3. **Local-path first**: solve the current local duplicate-search result path before extending into LLM-rendered paths.
4. **Backward-compatible**: normal text assistant messages should continue to render unchanged.
5. **Reuse existing persistence**: feedback should go through `FeedbackStore.submit_feedback()` without schema changes.

## Architecture

### Message Model Extension

Keep `chat_messages` as a list of dicts, but allow a duplicate-search message subtype.

Example assistant message:

```python
{
    "role": "assistant",
    "type": "duplicate-search-result",
    "content": "【结论】...",   # summary text shown above cards
    "duplicate_result": {
        "query_text": "IDCEVO 26/07 routing failed",
        "dashboard_type": "defect",
        "candidates": [
            {
                "ticket_id": "1702573",
                "name": "Route planning failed after destination input",
                "project": "IDCEVO",
                "pu": "26-07",
                "status_phase": "03-In Analysis",
                "snippet": "...",
                "score_1_10": 9,
                "similarity": 0.88,
                "rank_pos": 0,
            }
        ]
    }
}
```

Rules:

- `content` remains the recommendation summary so existing text display expectations still work.
- `duplicate_result` carries all card-rendering and feedback payload data.
- only local duplicate-search path emits this message type.

### Rendering Model

Split rendering into two branches:

1. ordinary message renderer
2. duplicate-search result renderer

The duplicate renderer outputs:

- summary block
- candidate cards
- button row per card
- feedback status line per card

### Feedback Submission Flow

```text
User clicks 👍 / 👎
  → Dash pattern-matching callback fires
  → read payload from button id/state
  → FeedbackStore.submit_feedback(
        query_text,
        ticket_id,
        signal,
        base_score,
        rank_pos,
        user_id=None,
    )
  → update in-card status text
```

## UI Design

### Candidate Card Content

Each card shows:

- score badge, e.g. `9 分`
- ticket id
- ticket title
- metadata line: `project / pu / status_phase`
- snippet preview
- action row: `👍 匹配` and `👎 不匹配`
- local acknowledgement text after click

### Feedback State

Each card maintains a simple local state indicator:

- initial: no status text
- after positive feedback: `已记录为正向反馈`
- after negative feedback: `已记录为负向反馈`
- after failure: `反馈提交失败：...`

Buttons may remain enabled for now; duplicate submissions are already moderated by existing flip detection/rate limiting in `FeedbackStore`.

## File Responsibilities

### [agent/legacy/ai_chat_manager_legacy.py](../../../agent/legacy/ai_chat_manager_legacy.py)

Modify:

- local duplicate-search branch to append structured duplicate-result assistant message instead of plain text only
- shared chat-history rendering to detect `type == "duplicate-search-result"`
- add helper(s) to build duplicate-search cards and action ids
- add callback for duplicate feedback button clicks

Potential helper responsibilities inside this file:

- `build_duplicate_summary_message(...)`
- `build_duplicate_result_payload(...)`
- `render_duplicate_result_message(...)`
- `submit_duplicate_feedback(...)`

### [feedback_store.py](../../../feedback_store.py)

No schema change expected.

May only be read/reused by the new callback.

### Tests

Prefer a new narrow test file:

- `tests/test_duplicate_feedback_ui.py`

It should cover:

- structured duplicate result payload contains required feedback fields
- renderer emits expected candidate action targets
- feedback callback writes positive/negative signals into `FeedbackStore`

## Interaction Contract

### Button Payload

Use Dash pattern-matching ids so each candidate is independently addressable.

Example:

```python
{
    "type": "duplicate-feedback-btn",
    "chat": chat_id_prefix,
    "ticket_id": "1702573",
    "signal": "positive",
    "rank_pos": 0,
}
```

The callback must also have access to the associated query context. That context should come from the structured assistant message payload, not from parsing visible text.

### Query Context Storage

Use one dedicated `dcc.Store` per chat panel for the latest duplicate result payload:

- store latest `query_text`
- store candidate metadata keyed by `ticket_id`
- store optional dashboard context

This avoids reconstructing feedback payload from rendered text or DOM structure.

The store is scoped to the latest duplicate-search interaction only, which is sufficient for the current local-path UI.

## Data Flow

```text
User enters query with known-issues enabled
    ↓
DuplicateIssueIndex.search(...)
    ↓
Build summary + structured duplicate_result payload
    ↓
Append assistant message with type=duplicate-search-result
    ↓
Render summary + cards + feedback buttons
    ↓
User clicks button
    ↓
Feedback callback resolves latest duplicate_result store payload
    ↓
FeedbackStore.submit_feedback(...)
    ↓
UI shows acknowledgement text for that card
```

## Why This Is Better Than a Pure Minimal Patch

A minimal patch would insert buttons into the current ad hoc text-rendering branch. That would solve collection, but preserve the core problem: duplicate-search results would still be represented mainly as text.

This design instead establishes a stable UI/data contract for duplicate-search results while still limiting scope to the local path. It gives us:

- clean ticket-level feedback wiring
- future extension path to the LLM summary branch
- safer testing because payload generation is explicit
- no need to parse natural-language message text to recover candidate metadata

## Risks

1. **Legacy callback complexity**: [agent/legacy/ai_chat_manager_legacy.py](../../../agent/legacy/ai_chat_manager_legacy.py) is large and contains duplicated rendering paths. Mitigation: confine change to duplicate result subtype and shared render helper.
2. **Store freshness**: using only the latest duplicate result store means feedback applies to the latest shown duplicate result set, not arbitrary older result sets in scrollback. This is acceptable for the current scope.
3. **Pattern callback collisions**: ids must include chat prefix to avoid cross-panel interference.

## Testing Strategy

Required checks:

1. unit test for payload generation from candidates
2. unit test for feedback callback writing a `positive` record
3. unit test for feedback callback writing a `negative` record
4. regression test ensuring ordinary assistant text messages still render without duplicate payload

Manual verification:

1. open Agent chat with `识别已知问题`
2. submit a known duplicate-style query
3. confirm candidate cards render with `👍 匹配` / `👎 不匹配`
4. click each button and confirm acknowledgement appears
5. confirm record exists in `feedback_records`

## Acceptance Criteria

- duplicate-search local path no longer renders candidates only as plain text
- each candidate has clickable `👍 匹配` and `👎 不匹配` actions
- clicking either button persists a record in `feedback_records`
- the feedback payload includes `query_text`, `ticket_id`, `signal`, `base_score`, and `rank_pos`
- existing non-duplicate chat rendering remains functional
- no database schema changes are required

## Out of Scope Follow-ups

- extend the same structured result rendering to the LLM-formatted duplicate-search path
- show aggregated prior feedback counts on each candidate card
- auto-disable buttons after successful submission
- wire BMW SSO user id into feedback submissions
- trigger automatic model export/training when thresholds are met