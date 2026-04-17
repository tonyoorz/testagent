---
name: frontend-design
description: Use when designing or refactoring web UI, landing pages, dashboards, or components that need high-end visual direction, strong hierarchy, and production-ready responsive behavior.
---

# Frontend Design

Design interfaces that feel intentional, bold, and modern, not boilerplate.

## When to Use

Use this skill for:
- New pages, sections, components, or visual redesigns
- UI polish before demos or release
- Cases where the current UI looks generic, flat, or inconsistent

Do not use this skill for:
- Pure backend/API tasks
- Non-visual bugfixes with no UI change

## Core Workflow

1. Define intent in one sentence: what this screen must communicate first.
2. Propose 2-3 visual directions with trade-offs, then pick one.
3. Create a design token set before coding: color, type, spacing, radius, shadow, motion.
4. Build with responsive-first structure for mobile and desktop.
5. Add meaningful motion (load reveal, stagger, state transitions), not random animation.
6. Run accessibility and usability checks before finalizing.

## Visual Standards

- Typography: choose expressive, purposeful families; avoid default system look and overused stacks.
- Color: set clear palette variables with a distinct mood; avoid generic purple-on-white defaults.
- Layout: establish strong hierarchy and intentional whitespace.
- Background: use gradients, subtle patterns, or geometric layers when useful; avoid flat emptiness.
- Components: keep interaction states clear (hover/focus/active/disabled/loading).
- Motion: keep transitions short and meaningful; use them to guide attention.

## Output Contract

When responding to design tasks, provide:
1. A concise visual concept summary
2. Token variables (CSS custom properties)
3. Component structure and key interactions
4. Responsive behavior notes (mobile + desktop)
5. Accessibility checks (contrast, keyboard focus, reduced motion)

## Quality Checklist

- Is there a clear primary focal point above the fold?
- Is the typography hierarchy obvious at a glance?
- Is color usage intentional and limited to roles?
- Does it still feel premium on small screens?
- Are loading, empty, and error states covered?
- Are focus states and keyboard navigation usable?
