# Harness Runtime Skeleton Design

## Goal

Build the first-stage harness runtime skeleton for the local agent so it learns harness engineer methodology rather than only copying public-branch file layout. This stage adds explicit guardrails, a runtime state machine, recovery and fallback policy, and traceable routing around the existing Dash-facing chat path while preserving current behavior through controlled fallback to legacy logic.

## Scope

This design covers only the first-stage runtime skeleton.

Included:

- explicit guardrail decisions before execution
- explicit runtime stages for request lifecycle
- centralized recovery and fallback rules
- standardized runtime events for route, confirmation, fallback, and failure handling
- orchestration through the current enhanced chat manager entrypoint
- focused regression tests proving safe fallback and compatibility

Excluded:

- DuckDB analytics layers
- predictor, insight engine, root-cause, or recommendation modules
- ML intent routing
- major tool logic rewrites
- breaking changes to Dash response payload shape

## Context

The current codebase already has pieces of an agent spine:

- [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/enhanced_ai_chat_manager.py) remains the Dash-facing runtime entrypoint
- [agent/core/conversation_orchestrator.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/conversation_orchestrator.py) currently builds request shape and initializes stream state
- [agent/core/streaming_protocol.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/streaming_protocol.py) currently supports append-only events but not explicit lifecycle stages
- [agent/core/tool_executor.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/tool_executor.py) already separates packaged tool loading, validation, and execution

What is still missing is the harness-style operational discipline around these pieces:

- decisions are not yet centralized into a guardrail layer
- runtime phase transitions are implicit and spread across multiple branches
- fallback logic is not formalized as a first-class policy
- streaming events exist, but not as a full runtime contract

## Design Principles

### 1. Learn methodology, not surface shape

The local agent should adopt the public harness branch where it improves operational discipline:

- explicit decisions instead of ad-hoc branching
- explicit lifecycle stages instead of loose progress strings
- explicit recovery contracts instead of scattered try/except fallback
- explicit traceability for evaluation and debugging

This stage does not attempt public-branch parity for every module. It selects only the parts that improve stability, routing clarity, and recoverability in the current local system.

### 2. Replace the main path, but preserve operational safety

The user selected a main-path replacement strategy with fallback. That means the new skeleton becomes the default control path, but the existing logic remains available as a recovery target.

The new path must never increase operational fragility. If the new runtime cannot safely continue, it falls back to legacy logic before returning a hard failure.

### 3. Preserve Dash compatibility

The Dash shell is not being redesigned. Existing consumers should continue to receive compatible payloads. New runtime metadata is additive.

## Proposed Modules

### New: [agent/core/guardrails.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/guardrails.py)

Purpose:

- evaluate whether a request should proceed, pause for confirmation, fall back, or be blocked
- normalize guardrail reasons into a structured result
- keep policy separate from business execution

Primary type:

- `GuardrailDecision`

Suggested fields:

- `action`: `allow | confirm | fallback | block`
- `reason_code`: stable short code such as `confirmation_required`, `missing_context`, `unsupported_runtime_state`, `unsafe_reentry`
- `message`: human-readable summary for trace/event use
- `details`: structured dict for diagnostics

Initial decision responsibilities:

- pending confirmation handling
- unsupported or incomplete runtime context
- explicit fallback triggers when request shape cannot be safely handled by the new skeleton
- hard block only for cases where executing or falling back would both be incorrect

### New: [agent/core/runtime_state_machine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/runtime_state_machine.py)

Purpose:

- define canonical lifecycle stages
- validate legal transitions
- emit transition metadata for streaming and trace

Canonical stages:

- `received`
- `guarded`
- `routed`
- `executing`
- `recovering`
- `fallback`
- `completed`
- `failed`

Rules:

- only orchestrator advances stages
- transition attempts return structured errors rather than silently mutating state
- stage metadata is appended as runtime events

### New: [agent/core/recovery_policy.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/recovery_policy.py)

Purpose:

- centralize what happens when the new runtime path cannot safely continue
- determine whether to retry in-place, fall back to legacy flow, or terminate as failed

Primary type:

- `RecoveryDecision`

Suggested fields:

- `action`: `continue | fallback | fail`
- `reason_code`
- `message`
- `preserve_events`: bool
- `legacy_path`: optional identifier for which fallback branch to call

Initial trigger classes:

- guardrail-directed fallback
- orchestration exceptions
- malformed agent output
- tool execution contract violations
- incomplete confirmation state

### Modified: [agent/core/conversation_orchestrator.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/conversation_orchestrator.py)

New role:

- become the runtime coordinator for the first-stage skeleton
- create request context
- initialize runtime state
- call guardrails
- advance runtime stages
- call recovery policy when needed
- aggregate standardized runtime events

New responsibilities to add without making it an all-in-one god object:

- `build_runtime_context(...)`
- `apply_guardrails(...)`
- `advance_stage(...)`
- `record_runtime_event(...)`
- `resolve_recovery(...)`

Execution remains delegated to existing services and managers. The orchestrator coordinates; it does not own full business logic.

### Modified: [agent/core/streaming_protocol.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/streaming_protocol.py)

Extend the protocol from generic append-only events into a stable runtime event contract.

Additive event kinds to support:

- `stage`
- `guardrail`
- `route`
- `confirmation`
- `recovery`
- `fallback`
- `execution`
- `error`

Additive stream metadata:

- `runtime_stage`
- `fallback_active`
- `confirmation_pending`

These must be additive only. Existing consumers reading `status`, `progress`, `response`, or `events` must keep working.

### Modified: [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/enhanced_ai_chat_manager.py)

New role:

- remain the Dash-facing entrypoint
- delegate runtime coordination to orchestrator instead of directly owning scattered decisions

Expected changes:

- main path initializes and uses the new orchestrator lifecycle
- current fallback branches are refactored to call recovery policy rather than ad-hoc local handling
- standardized events are emitted via streaming protocol helpers
- confirmation and fallback status are represented through the runtime contract

This file must not become more tangled. The point of the skeleton is to remove coordination burden from the chat manager.

## Runtime Flow

The first-stage control path is:

1. chat manager receives a request and builds the runtime context through orchestrator
2. orchestrator initializes stream state and marks stage `received`
3. orchestrator calls guardrails and records the decision
4. if decision is `confirm`, stage remains non-terminal and a confirmation checkpoint is returned
5. if decision is `fallback`, orchestrator records fallback intent and hands off through recovery policy
6. if decision is `block`, orchestrator returns a controlled blocked response with events and compatible payload shape
7. if decision is `allow`, orchestrator advances through `guarded -> routed -> executing`
8. if execution succeeds, stage becomes `completed`
9. if execution fails, recovery policy decides whether to continue, fall back, or fail
10. if legacy fallback succeeds, stage becomes `fallback` and final response remains usable
11. only if both new path and fallback path fail does the runtime end as `failed`

## Fallback Rules

Fallback is the main safety feature of this stage. Rules are intentionally simple.

### Fallback to legacy path when:

- guardrails explicitly request fallback
- runtime state transition fails in a non-recoverable way
- agent output violates expected contract
- tool execution returns unusable structure for the current branch
- orchestrator catches an internal exception in the new skeleton path

### Do not hard fail immediately when:

- the new skeleton encounters an internal coordination error
- a new runtime-only decision branch is unsupported
- confirmation state is incomplete but a safe legacy path exists

### Hard fail only when:

- both the new path and fallback path are unavailable or invalid
- the request is explicitly blocked by guardrail policy

## Trace and Event Contract

Every request processed by the first-stage runtime should be reconstructable from its events.

Minimum required trace points:

- guardrail decision
- stage transitions
- route selection
- confirmation checkpoint creation or resume
- recovery decision
- fallback trigger and target path
- final terminal status

Event payloads should favor short stable machine-readable fields over prose-heavy messages. Human-readable summaries are additive, not the primary contract.

## Testing Strategy

### New tests

- [agent/evaluation/test_guardrails.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_guardrails.py)
  - guardrail decisions for allow, confirm, fallback, block
- [agent/evaluation/test_runtime_state_machine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_runtime_state_machine.py)
  - legal and illegal stage transitions
- [agent/evaluation/test_recovery_policy.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_recovery_policy.py)
  - fallback vs fail decisions under representative failures

### Modified tests

- [agent/evaluation/test_enhanced_chat_manager_spine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_enhanced_chat_manager_spine.py)
  - main-path integration through orchestrator
  - confirmation checkpoint behavior
  - fallback to legacy path on orchestrator/runtime failure
- existing focused package and registry tests stay unchanged unless event contract changes require minimal adjustments

### Validation commands

Focused first-stage verification should include:

```powershell
.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_guardrails agent.evaluation.test_runtime_state_machine agent.evaluation.test_recovery_policy agent.evaluation.test_enhanced_chat_manager_spine -v
```

And keep the existing package regression green:

```powershell
.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_tool_package agent.evaluation.test_tool_package_loader agent.evaluation.test_tool_registry -v
```

## Acceptance Criteria

The first-stage task is complete when all of the following are true:

- the main enhanced chat path routes through orchestrator-driven guardrails and recovery
- guardrail decisions are explicit and structured
- runtime stage transitions are explicit and validated
- fallback to legacy path is centralized and test-covered
- runtime events include guardrail, stage, recovery, and fallback information
- current Dash-facing response shape remains compatible
- no second-stage subsystems are introduced into this scope

## Risks and Controls

### Risk: the skeleton adds new indirection without reducing complexity

Control:

- keep each new module narrowly scoped
- move coordination logic out of chat manager instead of duplicating it

### Risk: fallback logic becomes another source of hidden behavior

Control:

- fallback decisions must emit explicit events and stable reason codes

### Risk: stream event changes break existing Dash consumers

Control:

- keep all changes additive
- preserve existing top-level stream keys

### Risk: the stage machine becomes too strict for current real-world branches

Control:

- start with a small set of canonical stages and only validate transitions that matter now

## Out of Scope for Stage One

The following are intentionally deferred:

- DuckDB execution layers
- proactive insight generation
- time-series prediction
- root-cause analysis engines
- test recommendation modules
- ML intent classification
- major prompt and planner redesign beyond what is needed for guardrails and recovery

## Implementation Follow-Up

After this spec is approved, the next artifact should be a detailed implementation plan for the first-stage runtime skeleton. That plan should use TDD and sequence work so that fallback safety is verified early rather than at the end.