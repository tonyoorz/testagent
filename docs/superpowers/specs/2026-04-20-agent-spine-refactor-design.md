# Dash Agent Spine Refactor Design

**Date:** 2026-04-20

**Status:** Draft for review

## 1. Goal

Refactor the existing Dash-integrated agent into a new internal architecture that fully absorbs the newer agent design patterns already validated in the external branch, while preserving the current Dash application as the primary product shell.

This refactor must keep the following user-visible capabilities from regressing:

- streaming output and stepwise response rendering
- page-aware context from current Dash filters and dashboard state
- deterministic SQL and database-question answering paths

The target is not a separate agent product or a new standalone frontend. The target is a stronger internal agent spine behind the existing Dash chat experience, with selective frontend interaction upgrades where they improve clarity and control.

## 2. Constraints

### Product constraints

- Dash remains the primary user-facing shell.
- Existing chat entrypoints and callback integration should remain stable from the Dash layer outward.
- The system should not rely on a long-lived dual-runtime rollout.

### Migration constraints

- New and old internals may coexist only briefly during development and cutover.
- There should be one intentional main cutover point from legacy orchestration to the new orchestrator.
- Legacy behavior needed for stability should remain only as a compatibility adapter or fallback, not as a long-term parallel architecture.

### Engineering constraints

- Current deterministic SQL, streaming, and dashboard-context flows are business-critical and must be modeled as first-class architecture concerns, not cleanup follow-ups.
- The refactor should favor explicit module boundaries over incremental logic drift inside large files.

## 3. Recommended approach

Three approaches were considered:

### Option A: Spine replacement inside the current shell

Keep Dash integration and external chat contracts stable, but rebuild the internal agent around a new orchestrator, unified execution engine, context provider chain, and standardized tool runtime.

**Pros**

- best fit for preserving current product behavior
- maximizes learning transfer from the newer agent design
- avoids locking the team into long-term compatibility debt

**Cons**

- requires disciplined interface design up front
- cutover risk concentrates around orchestration wiring

### Option B: Full `agent_v2` replacement with compatibility shell

Build a separate internal stack and route all existing entrypoints through it quickly.

**Pros**

- cleanest architecture in isolation
- easiest to model directly after the newer branch

**Cons**

- highest cutover risk for streaming, callback, and deterministic SQL parity
- more likely to create hidden behavior mismatches at integration boundaries

### Option C: gradual extraction in place

Extract context, then tools, then engine, while keeping most legacy flow live throughout.

**Pros**

- lowest local change risk per step

**Cons**

- least faithful absorption of the new architecture
- highest chance of ending with a mixed old/new design and permanent debt

### Recommendation

Use **Option A: spine replacement inside the current shell**.

This gives the best balance between full architectural absorption and low product disruption. It preserves Dash as the outer shell but treats the inside of the agent as a new system with clear boundaries.

## 4. Target architecture

The target architecture has five layers.

### 4.1 Dash Integration Layer

This layer remains responsible for:

- Dash callbacks
- dashboard-specific filter state and page context
- streaming event transport to the UI
- chat session state, confirmation state, and message history handoff

This layer should not make planning or tool-routing decisions. Its job is to convert Dash-side state into a normalized agent request and render normalized agent responses back into UI events.

### 4.2 Conversation Orchestrator

This becomes the single agent entrypoint for request handling.

Responsibilities:

- normalize the incoming request
- select the operating mode or fast path
- assemble base context and runtime policy
- invoke the unified execution engine or a specialized fast path
- normalize the final response payload for Dash

The orchestrator replaces scattered branching currently split across chat manager, enhanced chat manager, and intelligent agent pathways.

### 4.3 Unified Execution Engine

This is the internal ReAct runtime shared by rule, agentic, and hybrid flows.

Responsibilities:

- own the iteration loop
- handle step execution, tool budget, and stop conditions
- integrate tracer spans and timing
- invoke self-correction on recoverable tool failures
- emit structured execution traces and streaming-friendly step updates

The key rule is that mode differences affect only how the next decision is made, not how execution is observed, traced, corrected, or returned.

### 4.4 Context and Tool Runtime Layer

This layer contains two standardized subsystems.

#### Context Provider Chain

Providers build layered context in deterministic order:

1. page and filter context from Dash
2. dataset summary and data profiler output
3. semantic catalog and business-rule context
4. relevant conversation history and confirmation state
5. dashboard-specific domain knowledge

This removes prompt/context assembly from large procedural flows and makes context injection testable.

#### Tool Runtime

This includes:

- tool registry
- tool descriptors
- JSON Schema parameter normalization
- tool executor
- tool capability metadata

All tool-facing model interfaces should use one schema path so that function-calling compatibility, harness tests, and observability all point to the same contract.

### 4.5 Specialized Fast Paths

Deterministic SQL and similar high-value fast paths remain first-class.

These are not exceptions outside the architecture. They are orchestrator-managed strategies that can bypass the general ReAct loop when appropriate while still using shared context, trace, and response envelopes.

Examples:

- deterministic SQL question answering
- dashboard summary mode
- direct database aggregation answers
- future precomputed or semantic-catalog-assisted narrow paths

## 5. Proposed module boundaries

The refactor should converge on explicit ownership boundaries like the following.

### Stable external entrypoints

- `ai_chat_manager.py`
- `enhanced_ai_chat_manager.py`
- `intelligent_agent.py`

These remain compatibility wrappers or thin adapters over `agent/core` implementations.

### Core orchestration

- `agent/core/conversation_orchestrator.py`
  - single request entrypoint
  - mode selection
  - fast-path routing
  - response normalization

- `agent/core/execution_engine.py`
  - shared execution loop
  - rule/agentic/hybrid deciders
  - step result model
  - streaming-ready execution events

### Context construction

- `agent/core/context_provider.py`
  - provider base class
  - context chain
  - default provider registration

- `agent/core/page_context_adapter.py`
  - normalize Dash page state, filters, and dataset slices into provider input

### Tool runtime

- `agent/core/tool_executor.py`
  - execution and schema normalization

- `agent/tools/registry.py`
  - registry and descriptor management

- `agent/tools/` submodules
  - each tool family isolated into smaller modules by responsibility

### Fast paths and data reasoning

- `agent/core/deterministic_sql_service.py`
- `agent/core/sql_runtime_service.py`
- `agent/core/agentic_runtime.py`
  - reduced to supporting utilities or folded under the orchestrator/engine model

### Observability and guardrails

- `agent/core/tracer.py`
- `agent/core/self_corrector.py`
- future `agent/core/guardrails.py`

### Frontend-adjacent response shaping

- `agent/core/streaming_protocol.py`
  - one internal representation for timeline, reasoning, stream chunks, tool steps, and final answer payloads

## 6. Frontend interaction alignment

Because Dash remains the primary shell, frontend work is not a separate React rebuild. The goal is to absorb the newer interaction patterns selectively and structurally.

### Must preserve

- progressive streaming text
- step/timeline visibility where already supported
- responses grounded in current dashboard filter state

### Should improve

- clearer separation between reasoning, tool execution, and final answer
- more explicit timeline cards for route selection, SQL execution, tool use, fallback, and errors
- stronger confirmation UX for multi-step or potentially expensive actions
- better rendering of deterministic SQL answers versus multi-tool analytical answers

### Proposed frontend interaction model

Keep the current Dash chat surface but standardize events into four presentation lanes:

1. **status lane**
   - route chosen
   - mode selected
   - fallback triggered

2. **execution lane**
   - tool calls
   - SQL execution
   - timing and completion states

3. **answer lane**
   - streamed answer content
   - structured summary blocks

4. **control lane**
   - confirmations
   - retry prompts
   - clarification prompts

This mirrors the stronger interaction discipline from the newer agent design without replacing Dash.

## 7. Migration plan

The migration should follow four stages.

### Stage A: freeze outer contracts

Document and preserve:

- Dash callback input/output contracts
- streaming event shapes
- deterministic SQL answer envelope
- page-context payload structure
- confirmation-flow state model

This stage defines what cannot change during refactor.

### Stage B: build the new spine behind the shell

Implement internally without mainline cutover:

- orchestrator
- unified execution engine
- context provider chain
- standardized tool runtime
- normalized streaming protocol

This stage is for parity testing, not user-visible dual runtime.

### Stage C: one main cutover

Route the main Dash-integrated agent entrypoint through the new orchestrator.

Legacy internals should remain only as fallback adapters where required during stabilization.

### Stage D: remove legacy orchestration

After cutover verification:

- delete duplicated planning branches
- delete redundant context assembly logic
- delete duplicate schema conversion paths
- reduce legacy modules to wrappers or remove them entirely

## 8. Testing and verification strategy

This refactor should be driven by harness engineering, not just implementation.

### 8.1 Regression layers

#### Layer 1: protocol tests

Verify Dash-facing request/response envelopes stay compatible.

#### Layer 2: fast-path tests

Verify deterministic SQL behavior for key intents, including:

- project breakdown
- execution status questions
- pass/fail and test case status questions
- person and owner queries

#### Layer 3: tool schema tests

Every tool descriptor must produce standard JSON Schema and remain callable.

#### Layer 4: execution engine tests

Verify:

- rule mode execution
- agentic decision handling
- stop reasons
- tool budget behavior
- self-correction integration
- trace generation

#### Layer 5: context-chain tests

Verify provider ordering, merge behavior, page-context injection, and fallback when one provider fails.

#### Layer 6: Dash integration slice tests

Verify the main chat integration still supports:

- streaming chunks
- page-filter-aware answers
- confirmation loop

### 8.2 Migration-specific parity checks

Before cutover, build focused parity suites for:

- deterministic SQL outputs on a fixed query set
- route selection and fallback traces
- tool-schema snapshots
- context keys injected for the same dashboard/question pair

The purpose is not perfect text identity. The purpose is stable capability parity plus better structure.

## 9. Error handling and fallback policy

The new architecture should use explicit fallback rules.

### Engine failures

- if unified engine fails before execution, fall back once to legacy execution path during migration only
- after stabilization, remove this fallback

### Provider failures

- one provider failing must not abort the whole request
- provider failure should be recorded in trace metadata and optional timeline events

### Tool failures

- tool executor returns structured failure payloads
- self-corrector may retry where enabled
- repeated failure should degrade to explanatory answer, not raw crash text

### SQL fast-path failures

- fallback to safer summary or clarification mode when deterministic SQL cannot safely answer
- do not silently fabricate query-based answers

## 10. Non-goals

The following are explicitly out of scope for this refactor:

- replacing Dash with a separate frontend product
- redesigning all dashboards around a new app shell
- adding unrelated data features during the spine rewrite
- long-term maintenance of full legacy and full new orchestration in parallel

## 11. Success criteria

This refactor is successful when all of the following are true:

- Dash chat entrypoints remain stable
- streaming behavior is preserved or clearer than today
- page-aware context remains available and testable through providers
- deterministic SQL remains first-class and covered by regression tests
- tool definitions normalize through one JSON Schema path
- execution logic is centralized in one engine instead of scattered branches
- trace and timeline observability are standard, not bolt-ons
- old orchestration code is materially reduced rather than merely wrapped forever

## 12. Recommended implementation order

1. Freeze Dash contracts and response protocol.
2. Build orchestrator skeleton and request/response models.
3. Move context construction into a provider chain, including page-context injection.
4. Standardize tool schemas and registry contracts.
5. Build and validate unified execution engine.
6. Route deterministic SQL and other fast paths through the orchestrator.
7. Cut over the main Dash entrypoint.
8. Remove legacy orchestration branches.
9. Expand harness coverage around the new spine.

## 13. Open implementation note

The newer branch demonstrates strong patterns in tracer, self-correction, tool registry, context providers, unified execution, and tool regression harnessing. This refactor should absorb those ideas structurally, not cosmetically. The point is not to copy filenames alone. The point is to make this repository's Dash-based agent obey the same architecture principles under its own product constraints.