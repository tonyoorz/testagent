# Proactive Insight Mode Design

## Goal

Build the second-stage proactive insight mode so the local agent can explicitly enter a harness-style exploratory analysis path that discovers defect-and-test linked hotspots, anomalies, divergences, and turning points. The mode must preserve normal question-answering behavior by living behind a dedicated entrypoint and by keeping its internal analysis outputs structured before generating a user-facing narrative report.

## Scope

This design covers only the explicit proactive insight mode.

Included:

- a dedicated proactive insight entrypoint
- defect + test linked insight discovery
- structured internal insight objects
- complete user-facing natural-language report generation
- storage of structured insight results in response context
- focused tests proving the mode does not regress the standard agent path

Excluded:

- prediction and forecasting
- root-cause inference chains
- recommendation engines
- background precomputation
- automatic routing from ordinary questions into proactive insight mode
- changes to packaged tool registration unrelated to the proactive insight path

## Context

The first-stage harness runtime skeleton is already in place through:

- [agent/core/guardrails.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/guardrails.py)
- [agent/core/runtime_state_machine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/runtime_state_machine.py)
- [agent/core/recovery_policy.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/recovery_policy.py)
- [agent/core/conversation_orchestrator.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/conversation_orchestrator.py)
- [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/enhanced_ai_chat_manager.py)

That skeleton improved operational discipline, but it did not yet add a meaningful new analysis capability. This second stage introduces a capability gap filler that matches harness engineer methodology: explicit exploratory mode, structured evidence-first analysis, and controlled report synthesis.

## Product Intent

The user wants the agent to learn from harness engineer methodology and fill real capability gaps. For this stage, that means:

- not just answering a prompted question
- proactively surfacing linked defect/test imbalances
- keeping the analysis path explicit instead of silently mixing it into general chat
- producing outputs that are both evaluable and explainable

The mode is intentionally explicit. It is not a hidden enhancement to normal chat. It is a deliberate analysis mode for exploratory insight generation.

## Design Principles

### 1. Dedicated entrypoint first

The new mode must not pollute ordinary question-answering. A user or caller explicitly invokes the proactive insight path. This keeps the standard agent path stable and makes evaluation much easier.

### 2. Structured analysis before prose

The engine first emits structured insight objects. Natural language comes afterward through a reporter layer. This preserves evidence, supports future UI cards, and keeps the analysis path testable.

### 3. Defect and test data are analyzed together

This mode is not just a defect anomaly scanner or a test anomaly scanner. The first useful version is about their relationship. The highest-value findings come from mismatches and coordinated changes between the two sides.

### 4. Stay inside current operational boundaries

This stage must build on the first-stage runtime skeleton. It should not introduce a separate orchestration framework, background jobs, or large new data infrastructure.

## Proposed Modules

### New: [agent/core/proactive_insight_models.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/proactive_insight_models.py)

Purpose:

- define stable data structures for requests, evidence, insight cards, and final reports
- provide a consistent contract across router, engine, reporter, tests, and future UI consumers

Suggested types:

- `ProactiveInsightRequest`
- `InsightEvidence`
- `InsightCard`
- `ProactiveInsightReport`

Suggested `InsightCard` fields:

- `type`
- `title`
- `summary`
- `scope`
- `confidence`
- `severity`
- `evidence`
- `metrics`

### New: [agent/core/proactive_insight_router.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/proactive_insight_router.py)

Purpose:

- determine whether a request explicitly targets proactive insight mode
- parse the request into a structured `ProactiveInsightRequest`
- keep entrypoint recognition independent from analysis logic

Initial responsibilities:

- explicit entrypoint detection via request flags, command prefix, or extra context markers
- normalization of optional scope fields such as time window, dimensions, and datasets
- reject malformed proactive insight requests early

### New: [agent/core/proactive_insight_engine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/proactive_insight_engine.py)

Purpose:

- compute linked defect + test insights from the current runtime data context
- return a list of structured `InsightCard` objects

Initial supported insight types:

- `hotspot`
- `anomaly`
- `divergence`
- `turning_point`

Initial analysis surface:

- project-level hotspots
- AIDA-level hotspots
- severity-level concentration
- weekly defect/test imbalance
- activity divergence between defect and test signals

### New: [agent/core/proactive_insight_reporter.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/proactive_insight_reporter.py)

Purpose:

- convert structured insight cards into a complete natural-language report
- keep user-facing language separate from evidence computation

Suggested report sections:

- overview
- key hotspots and anomalies
- defect-test divergence findings
- turning points worth attention
- analysis limits and data caveats

### Modified: [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/enhanced_ai_chat_manager.py)

New responsibilities:

- ask the proactive insight router whether the request is a proactive insight request
- if not matched, continue through the standard first-stage harness runtime skeleton path
- if matched, execute the proactive insight path and return a compatible response payload

This file must still avoid owning analysis logic. It should route, not analyze.

## Execution Flow

The proactive insight mode should follow this sequence:

1. the chat manager receives the request
2. the proactive insight router decides whether this is an explicit proactive insight request
3. if not matched, the request continues through the normal runtime path
4. if matched, the router returns a `ProactiveInsightRequest`
5. the proactive insight engine reads the available defect and test datasets and emits structured `InsightCard` objects
6. the reporter converts those cards into a complete natural-language report
7. the final response returns:
   - report text for the user
   - structured insight cards in context for trace, evaluation, and later UI use

## Insight Types for Version One

### Hotspot

Detect concentration of defect or test activity in a project, AIDA bucket, severity slice, or week that dominates the surrounding distribution.

### Anomaly

Detect unusual spikes, drops, or empty segments relative to a recent local baseline.

### Divergence

Detect cases where defect and test signals move in ways that suggest imbalance, for example:

- defects rise while test activity stays flat
- defects concentrate in areas with weak test movement
- test activity rises without corresponding defect stabilization

### Turning Point

Detect local change points where a stable direction meaningfully changes, especially when defect and test signals stop moving together.

## Output Contract

### Internal output

The engine outputs `InsightCard[]`.

Each insight card must contain evidence and not just conclusions. That evidence should include the compared signals or aggregates used to justify the finding.

### External output

The reporter outputs a full natural-language report suitable for direct chat display.

The response payload should keep the report text as the main visible answer while placing the underlying structured cards into a context field for downstream reuse.

## Integration Contract

The proactive insight mode must integrate with the existing runtime skeleton but remain logically separate from ordinary Q&A.

Required constraints:

- normal `process_with_agent` requests must continue to work when the router does not match proactive insight mode
- proactive insight results must still fit the current Dash response shape without breaking existing consumers
- runtime trace or context should clearly indicate that the proactive insight path was used

## Testing Strategy

### New tests

- [agent/evaluation/test_proactive_insight_router.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_proactive_insight_router.py)
  - explicit proactive entry recognition
  - malformed or incomplete request rejection
- [agent/evaluation/test_proactive_insight_engine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_proactive_insight_engine.py)
  - hotspot detection
  - anomaly detection
  - divergence detection
  - turning-point detection
- [agent/evaluation/test_proactive_insight_reporter.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_proactive_insight_reporter.py)
  - deterministic generation of narrative report sections from structured cards

### Modified tests

- [agent/evaluation/test_enhanced_chat_manager_spine.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/evaluation/test_enhanced_chat_manager_spine.py)
  - router hit enters proactive insight path
  - router miss keeps ordinary runtime path unchanged

## Acceptance Criteria

This second-stage task is complete when all of the following are true:

- a dedicated proactive insight entrypoint exists
- the mode performs linked defect + test analysis rather than single-table-only analysis
- the engine emits structured insight cards before prose generation
- the reporter emits a complete natural-language report
- the standard agent path remains unchanged when the new entrypoint is not used
- structured insight outputs are preserved in the returned context
- no prediction, recommendation, or root-cause subsystems are introduced into this stage

## Risks and Controls

### Risk: the mode becomes a second chat system instead of a bounded analysis path

Control:

- keep entrypoint explicit
- keep the router narrow and analysis-specific

### Risk: the engine emits narrative conclusions with weak evidence

Control:

- require every insight card to include evidence and supporting metrics
- keep reporting separate from analysis

### Risk: ordinary chat behavior changes accidentally

Control:

- add explicit router-hit and router-miss integration tests in the chat manager spine suite

### Risk: the mode scope grows into prediction or recommendation too early

Control:

- keep version one limited to hotspot, anomaly, divergence, and turning-point findings only

## Out of Scope for This Stage

The following are deferred to later stages:

- forecasting and predictive trend extrapolation
- recommendation engines
- root-cause analyzers
- background insight precomputation
- auto-routing from ordinary natural-language requests into proactive insight mode

## Implementation Follow-Up

After this spec is approved, the next artifact should be a detailed implementation plan for proactive insight mode using TDD. That plan should verify router separation early so the ordinary Q&A path remains stable while the new mode is introduced.