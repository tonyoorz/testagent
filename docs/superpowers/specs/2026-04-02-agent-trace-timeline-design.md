# Agent Trace Timeline Design

## Goal

Expose the real execution path of the chat agent so users can see route decisions, tool calls, retries, fallback behavior, evidence gaps, and final answer synthesis instead of only a compressed reasoning summary.

## Problem

The current chat UI shows a compact reasoning block built from mutable fields such as `progress`, `reasoning`, and `response`.

This hides the actual sequence of execution:

- route decisions are compressed into a few lines
- tool activity is reduced to short text snippets
- SQL generation and execution are not presented as first-class steps
- retries and fallback behavior are hard to distinguish from ordinary progress
- users cannot tell whether an incomplete answer was caused by routing, SQL generation, data gaps, or summarization

## Requirements

1. Keep the current lightweight streaming response.
2. Keep a compact reasoning summary for quick reading.
3. Add a full append-only event timeline per task.
4. Show the timeline in the chat stream while the task is still running.
5. Remove the message titles `AI思考` and `调试时间线` from the chat body.
6. Make failure causes explicit, especially for database-direct questions.

## Non-Goals

1. Rebuild the chat transport with SSE or WebSocket.
2. Expose hidden model chain-of-thought.
3. Replace existing routing or SQL logic as part of this change.
4. Create a separate admin-only debug page.

## Data Model

Each `streaming_data[task_id]` entry keeps both summary state and a timeline.

Summary state remains:

- `status`
- `progress`
- `response`
- `reasoning`

New timeline state:

```python
"events": [
    {
        "id": "evt_001",
        "ts": 1712030000.12,
        "kind": "route_decision",
        "title": "路由到 Agent (数据库直读)",
        "status": "ok",
        "summary": "命中高级查询，进入 Agent 路径",
        "details": {
            "handler": "SKILL_AGENT",
            "handler_label": "Agent (数据库直读)",
            "reason": "高级查询保持数据库直读链路"
        }
    }
]
```

The timeline is append-only. Existing events are never overwritten.

## Event Types

Required event kinds:

- `route_decision`
- `context_ready`
- `plan_created`
- `tool_start`
- `tool_result`
- `replan`
- `fallback`
- `sql_generated`
- `sql_result`
- `evidence_gap`
- `llm_phase`
- `final_answer`
- `error`

## Evidence Gap Rules

For database-direct flows, incomplete answers must produce explicit `evidence_gap` events.

Examples:

- missing `showstopper candidate` filter or classification
- no feature-like field available for a question asking `哪些功能`
- aggregate SQL used for a detail question
- zero-hit result after retries

## UI Design

The chat stream shows two assistant-side debug artifacts when execution detail is enabled:

1. A compact reasoning block with no title.
2. A detailed timeline block with no title.

The timeline block renders event cards in chronological order.

Each event card shows:

- elapsed time relative to task start
- event title
- status badge
- optional summary text
- optional expandable details

Default expansion behavior:

- open for `error`, `fallback`, and `evidence_gap`
- closed for normal success events

## Implementation Scope

Main file:

- `agent/core/enhanced_ai_chat_manager.py`

Tests:

- `agent/evaluation/test_enhanced_chat_reasoning.py`

Secondary touchpoints may include agent progress callbacks already emitted by:

- `agent/core/intelligent_agent.py`

## Acceptance Criteria

1. A successful agent query shows route, plan, tool start, tool result, synthesize, and final answer in order.
2. A failed or degraded run shows explicit `error`, `fallback`, or `evidence_gap` events.
3. A database-summary query can show generated SQL, SQL result metadata, and evidence gaps.
4. The chat body no longer shows the headings `AI思考` or `调试时间线`.
5. Existing streaming answer behavior continues to work.