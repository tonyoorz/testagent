# Proactive Insight Entry Points Design

## Goal

Expose the already-implemented proactive insight mode through the existing Dash chat shell so users can explicitly trigger it from the UI without changing ordinary chat behavior.

This stage does not introduce a new analysis engine. It only adds a stable, explicit entry layer for the proactive insight mode that already exists in the runtime.

## Scope

This design covers only the stage-three Dash entrypoint work.

Included:

- a dual entry model for proactive insight mode
- one preset button entry inside the existing chat UI
- one slash-command entry inside the existing input box
- normalization of both entry types into the same explicit runtime mode signal
- lightweight UI messaging that makes the active mode visible
- focused regression tests proving that ordinary chat behavior remains unchanged

Excluded:

- new dashboards or standalone pages
- a separate proactive insight callback tree
- changes to the proactive insight engine, router, reporter, or card schema except where a thin integration seam requires it
- auto-routing ordinary natural-language questions into proactive insight mode
- background scheduling, caching, or offline generation of insight reports

## Context

Stage two already added the capability layer:

- [agent/core/proactive_insight_models.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/proactive_insight_models.py)
- [agent/core/proactive_insight_router.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/proactive_insight_router.py)
- [agent/core/proactive_insight_engine.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/proactive_insight_engine.py)
- [agent/core/proactive_insight_reporter.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/proactive_insight_reporter.py)

The remaining gap is usability and discoverability. The current chat shell already has all the right wiring points:

- preset question definitions in [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/enhanced_ai_chat_manager.py#L953)
- chat UI rendering in [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/enhanced_ai_chat_manager.py#L1608)
- unified send/preset callback handling in [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/enhanced_ai_chat_manager.py#L3758)

So the correct stage-three move is not to add a new view. It is to route both UI entry forms into the same existing proactive insight mode.

## Product Intent

The user explicitly chose a dual-entry model:

- a visible preset button for discoverability
- a slash command for power users and explicit invocation

Both entry forms must feel like the same feature, not two different paths that happen to reach similar outputs.

## Design Principles

### 1. Explicit means explicit

The system must only enter proactive insight mode when the user intentionally requests it through a dedicated entry. Normal questions must not be silently rewritten into proactive insight mode.

### 2. One mode signal, not two parallel paths

The button and slash command are separate UX affordances, but internally they must normalize into the same explicit signal:

- `mode = "proactive_insight"`

This keeps runtime routing, traceability, and future extensions clean.

### 3. Reuse the current chat shell

This stage should live entirely inside the existing chat manager UI and callback system. Creating a separate proactive insight page or callback stack would multiply risk without adding meaningful value.

### 4. Preserve ordinary chat behavior

If the new entrypoints are not used, the current Dash chat behavior must remain unchanged.

## Entry Model

### Preset Button Entry

Add a new preset question key in the existing `preset_questions` structure:

- key: `proactive_insight`
- label text: a clear explicit phrase such as `请做主动洞察`

This key should be included in the relevant dashboard groups that already expose the enhanced chat UI. The button should reuse the existing preset button rendering loop. No new component type is needed.

### Slash Command Entry

Support a slash command in the input box:

- `/proactive-insight`

This command is parsed inside the existing send flow before ordinary question execution begins. It is not a second callback. It is only a special-case normalization step inside the current handler.

## Normalization Contract

Both entry types must converge into the same normalized request contract before `process_with_agent(...)` is called.

Required normalized signal:

- `extra_context["mode"] = "proactive_insight"`

Recommended additional metadata:

- `extra_context["entry_point"] = "proactive_insight_button" | "proactive_insight_slash"`

The user-facing question text may remain human-readable, but routing must depend on the explicit mode field rather than on brittle text matching.

## Proposed Implementation Surface

### Modified: [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/core/enhanced_ai_chat_manager.py)

This stage should primarily modify three areas in this file.

#### 1. Preset definitions

Extend `self.preset_questions` to include a `proactive_insight` item in the relevant dashboard presets.

#### 2. UI rendering

Reuse the existing preset button rendering loop in `create_enhanced_chat_interface(...)` so the new preset key automatically renders a button.

#### 3. Unified callback handler

Update the main enhanced chat callback to:

- detect when the proactive insight preset button triggered the request
- detect when the input begins with `/proactive-insight`
- normalize both paths into a shared `extra_context` mode payload
- keep the rest of the send flow unchanged

## Data Flow

The intended request flow is:

1. user clicks the proactive insight preset button or submits `/proactive-insight`
2. the existing chat callback identifies the trigger type
3. the callback constructs normalized context with `mode="proactive_insight"`
4. the callback continues through the existing request construction path
5. `process_with_agent(...)` receives the explicit mode and the stage-two proactive insight router matches it
6. the proactive insight branch returns its report and structured cards
7. the Dash UI displays the result inside the same existing chat surface

## Failure Handling

### Entry recognition failure

If neither the proactive button nor the slash command is used, the request remains on the ordinary chat path with no behavioral change.

### Insufficient data for proactive analysis

If proactive insight mode is explicitly requested but the current data context is insufficient for defect-plus-test analysis, the system must remain in proactive insight semantics and return a controlled message about data boundaries or insufficient scope.

It must not silently fall back to ordinary Q&A and pretend to have answered a normal chat question.

### Runtime errors inside proactive mode

This stage should reuse the existing runtime skeleton and proactive insight path behavior. It does not add a separate recovery framework.

## UI Behavior

The UI should remain lightweight.

### Required visible changes

- a new preset button for proactive insight
- slash command support in the input box

### Recommended lightweight messaging

When proactive insight mode is triggered, the response or status area may include a short mode indicator such as:

- `已进入主动洞察模式`

This should remain additive. No new panel, tab, or dedicated view is required.

## Testing Strategy

### Modified tests

Add focused tests around the existing enhanced chat callback and request normalization path.

Minimum required coverage:

- preset button trigger normalizes to `mode="proactive_insight"`
- slash command trigger normalizes to the same mode
- ordinary send behavior remains unchanged when the new entries are not used
- proactive insight mode with insufficient data still returns a mode-consistent controlled result
- existing proactive insight tests remain green after the UI entry changes

Likely touched tests:

- [agent/evaluation/test_enhanced_chat_manager_spine.py](c:/Users/q446328/Desktop/TPMDashbaord/.worktrees/proactive-insight-mode/agent/evaluation/test_enhanced_chat_manager_spine.py)

If callback normalization logic is extracted into a helper, add a narrow test file for that helper rather than trying to prove everything only through the full callback surface.

## Acceptance Criteria

This stage is complete when all of the following are true:

- the chat UI includes a proactive insight preset button
- `/proactive-insight` is recognized in the existing input flow
- both entries normalize into the same explicit runtime mode signal
- the proactive insight mode runs inside the current chat shell rather than a separate page
- ordinary chat behavior is unchanged when these entries are not used
- proactive mode stays explicit even when data is insufficient

## Risks and Controls

### Risk: button and slash command drift into different behaviors

Control:

- require both to normalize into the same `mode` field before request execution

### Risk: entry logic leaks into general chat behavior

Control:

- confine the detection logic to two explicit entry forms only
- do not auto-route ordinary natural-language questions

### Risk: UI wiring becomes more complex than the feature warrants

Control:

- reuse the existing preset rendering and callback structure
- avoid new stores, new pages, or new callback trees

## Out of Scope

The following remain out of scope for this stage:

- proactive insight scheduling or background jobs
- a standalone proactive insight dashboard page
- visualization-specific UI for cards
- new mode-selection dropdowns or tabs
- changes to the proactive insight algorithm itself unless required for a minimal integration seam

## Implementation Follow-Up

After this spec is approved, the next artifact should be a stage-three implementation plan focused on dual-entry wiring, normalization, and regression tests in the isolated proactive insight worktree.