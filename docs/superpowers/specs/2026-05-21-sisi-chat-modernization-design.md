# SiSi Chat Modernization Design

## Goal

Refine the current SiSi Chat experience in Defect Explore into an Open WebUI-inspired chat workspace while preserving the current Dash callback contract, agent behavior, and data flow.

This phase should prove four things:

- the current chat can adopt the same structural feel as Open WebUI without changing backend behavior
- the first-screen impression can shift from boxed tool panel to immersive chat product
- advanced controls can remain available without occupying the main stage
- a static mockup can represent the target layout closely enough to guide implementation

## Scope

In scope for this phase:

- redesign the SiSi Chat page inside Defect Explore
- align the page shell with the Open WebUI interaction model
- introduce a persistent left navigation rail
- introduce a sparse center stage for empty-state chat
- redesign the composer into a floating rounded input dock that matches Defect Explore's light visual system
- move mode, model, known issue, and reasoning controls into a secondary surface
- produce a revised static HTML mockup representing the target direction

Out of scope for this phase:

- copying Open WebUI source code or branded assets directly
- changing the underlying AI routing logic
- changing Dash callback inputs or outputs
- changing the message store structure or streaming state machine
- introducing a new frontend framework for chat
- changing duplicate-search behavior or analytical semantics

## Current State

The current SiSi Chat page is rendered from:

- [defect_explore.py](c:/Users/q446328/Desktop/TPMDashbaord/defect_explore.py)
- [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/enhanced_ai_chat_manager.py)

The current structure already supports:

- a dedicated chat history region
- multi-mode chat controls
- model selection
- quick prompt buttons
- streaming and stop behavior
- reasoning-detail toggles
- session-backed message and state stores

The current problem is primarily visual architecture.

The interface still reads as a bordered utility card with controls stacked around it. Open WebUI feels better because it behaves like an application shell: fixed navigation, sparse stage, minimal chrome, and a single dominant composer.

## Product Intent

SiSi Chat should feel like a full chat workspace embedded inside Defect Explore, not a dashboard widget.

The page should answer this sequence naturally:

1. Where am I in the chat workspace?
2. Which assistant or model is active?
3. Where do I start typing?
4. Where do advanced controls live when I need them?

The product should feel immersive, calm, and chat-first.

## Chosen UX Direction

Use an Open WebUI-inspired shell with five layers:

1. `App rail`
   - persistent left navigation surface with a softer light panel treatment
   - new chat entry and lightweight session/history groupings

2. `Minimal top bar`
   - active model selector on the left
   - utility actions on the right

3. `Center stage`
   - large empty canvas with a centered assistant identity block
   - no heavy cards competing with the composer

4. `Floating composer dock`
   - dominant rounded input surface near the lower center
   - attach, voice, and send/stop actions integrated into the dock

5. `Secondary controls`
   - Agent, Skill, RAG, model, known issue, and reasoning controls moved into a collapsed or auxiliary strip

This direction was chosen because the user explicitly wants the Open WebUI feel, and that feel comes mostly from layout hierarchy rather than isolated component styling.

### Rejected alternatives

#### Keep the current dashboard-card layout and only recolor it

Rejected because it would still feel like a tool panel instead of an immersive chat app.

#### Keep the previous light mockup with premium-card styling

Rejected because it did not match the reference product's sparse dark-stage structure.

## Information Architecture

### Section 1: App rail

The left side should become a persistent dark rail similar in role to Open WebUI.
The left side should keep the same role as Open WebUI, but its palette should be adapted to Defect Explore rather than staying dark.

Required elements:

- SiSi brand mark and name
- primary new chat action
- lightweight navigation items or feature shortcuts
- conversation history groups
- user identity area anchored at the bottom

This rail is not a feature dump. It is a stable anchor that makes the workspace feel like an application.

### Section 2: Minimal top bar

The main stage should begin with a minimal control strip.

Required elements:

- active model selector
- optional set-as-default or mode summary text
- utility icons on the right for advanced controls or session settings

This top bar should stay visually quiet.

### Section 3: Empty-state center stage

Before the user starts chatting, the center of the page should remain intentionally sparse.

Required elements:

- centered SiSi identity mark
- active model title or mode title
- optional one-line helper text

This stage should not use a large bordered welcome card. Open WebUI feels modern because the empty state leaves room for the composer to dominate. In this adaptation, that sparse stage should sit on a light dashboard canvas rather than a dark theater background.

### Section 4: Composer dock

The main interaction surface should be a floating rounded dock.

Required behavior:

- rounded rectangle with subtle border, soft shadow, and shallow inset depth
- multi-line text input with low visual noise
- attach and capability affordances on the left
- voice and send actions on the right
- stop action replacing or pairing with send during streaming

The composer should be the strongest call to action on the page.

### Section 5: Suggested prompts

Prompt suggestions should live below the composer in the empty state.

Required behavior:

- short stacked suggestions, not colorful pills
- low-contrast supporting text
- disappear or collapse once the chat becomes active

### Section 6: Active conversation state

Once the user starts chatting, the center stage should transition into a message timeline without losing the same shell.

Required changes:

1. Assistant messages
   - left-aligned inside the main stage
   - minimal bubble or near-bubble treatment

2. User messages
   - right-aligned and visually distinct
   - restrained color so the dark shell remains primary

3. Execution detail handling
   - reasoning, route detail, and tool execution traces should be hidden behind expandable detail regions
   - the default message view should show the answer first

4. Duplicate-search and rich result blocks
   - preserve custom result rendering
   - visually attach them to assistant answers rather than separate dashboard-like boxes

### Section 7: Advanced controls surface

The current controls remain useful but must move out of the hero area.

Controls to retain:

- mode selection
- model selection
- known issue toggle
- show reasoning toggle

Recommended presentation:

- a compact slide-down panel from the top right controls icon, or
- a subdued strip immediately above the composer dock

The default state should keep these controls visible enough to access but not visually dominant.

## Component Structure

Implementation should stay centered in [agent/core/enhanced_ai_chat_manager.py](c:/Users/q446328/Desktop/TPMDashbaord/agent/core/enhanced_ai_chat_manager.py) for the chat UI shell, while the page-level wrapper in [defect_explore.py](c:/Users/q446328/Desktop/TPMDashbaord/defect_explore.py) stays thin.

Recommended UI boundaries inside the existing chat interface function:

- `AppRail`
- `StageTopBar`
- `EmptyStage`
- `ConversationTimeline`
- `ComposerDock`
- `SuggestionList`
- `AdvancedControlsPanel`

These do not need to become standalone Python classes immediately. Local helper rendering blocks are sufficient if that keeps the change compact.

## Data Flow

The underlying data flow remains unchanged:

1. Defect Explore creates the page shell
2. Enhanced chat manager creates the interface and stores
3. Existing callbacks update message history, streaming state, and conversation state
4. The new layout renders the same stored content under a different visual hierarchy

No new endpoint, store contract, or callback payload format is needed for this phase.

## Error Handling

The redesign must preserve current explicit states:

- initial empty-state workspace
- active conversation state
- streaming state
- stopped or completed state
- AI unavailable fallback state

The unavailable fallback should use the same light application-shell language rather than dropping back to a plain utility box.

## Styling Direction

The visual language should stay close to the Open WebUI reference in structure, while matching Defect Explore in palette:

- soft blue-gray page background using the existing Defect Explore visual family
- white and off-white application surfaces instead of graphite fields
- dark slate text with restrained blue accents
- rounded, floating composer dock with subtle shadow and border
- minimal separators and quiet typography in navigation and utility controls
- sparse spacing that keeps the center of the screen calm

This phase should prioritize structural fidelity to the reference feel while keeping color and contrast aligned with the surrounding Defect Explore product.

## Documentation

This phase should maintain two design artifacts:

1. this written spec
2. a static mockup HTML file for review

The mockup is a design review artifact, not implementation code.

## Testing

Required validation for the eventual implementation phase:

1. empty-state rendering still works
2. normal conversation rendering still works
3. streaming state still updates the UI correctly
4. stop button state remains valid during streaming
5. mode and model controls still map to the same callback behavior
6. duplicate-search rich blocks still render correctly
7. narrow-window layout remains usable

This design phase does not require browser automation or callback rewrites.

## Implementation Notes

Preferred implementation order:

1. replace the current boxed chat wrapper with a full application shell
2. add the persistent left app rail
3. build the minimal top bar and centered empty stage
4. redesign the input as a floating composer dock
5. move advanced controls into a secondary panel
6. migrate active conversation rendering into the new shell without changing callback contracts

## Acceptance Criteria

This design is complete when:

- SiSi Chat visually reads as an application workspace rather than a dashboard widget
- the page shell clearly resembles the Open WebUI interaction model
- the composer dock is the strongest visual action on the screen
- advanced controls remain available without dominating the stage
- the design can be reviewed from both spec and static mockup artifacts

## Mockup Artifact

The review mockup for this design lives at:

- [docs/superpowers/mockups/2026-05-21-sisi-chat-modernization-mockup.html](c:/Users/q446328/Desktop/TPMDashbaord/docs/superpowers/mockups/2026-05-21-sisi-chat-modernization-mockup.html)

## Follow-on Work

Later phases can build on this by adding:

- richer markdown formatting inside assistant answers
- a more faithful active-chat timeline treatment after the empty state is approved
- dark/light theme switching if the product later needs theme parity with other dashboard surfaces
