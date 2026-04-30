# Vizion Theme Migration Guide

## Goal
Restyle the existing Dash application to match the vizion-lab (Lovable) design system. **DO NOT change any data logic, callbacks, chart data, or functionality.** Only change visual presentation, layout structure, and CSS.

## Reference: vizion-lab Design System

### Color System (HSL CSS Variables)
```
--primary: 215 70% 48% (blue)
--success: 152 60% 40% (green)
--warning: 38 92% 50% (amber)
--destructive: 0 72% 51% (red)
--background: 220 20% 97% (light gray)
--card: 0 0% 100% (white)
--border: 220 16% 90% (light border)
--muted-foreground: 220 10% 50% (secondary text)
--foreground: 220 25% 10% (primary text)
--sidebar-bg: 220 25% 12% (dark sidebar)
--sidebar-fg: 220 10% 75% (sidebar text)
--sidebar-active: 215 70% 48% (active nav item)
--sidebar-hover: 220 20% 18% (hover state)
```

### Typography
- Primary font: 'DM Sans', system-ui, sans-serif
- Mono font: 'JetBrains Mono', monospace
- KPI values: text-3xl font-bold tracking-tight (JetBrains Mono)
- Labels: text-sm font-medium text-muted-foreground
- Filter labels: text-xs font-semibold uppercase tracking-wider

### Card Style (dashboard-card)
- bg-white, rounded-xl (12px), border 1px solid border-color, shadow-sm
- Hover: translateY(-2px), shadow-md

### Sidebar
- Fixed left, dark background (hsl(220 25% 12%))
- Collapsible (240px ↔ 68px)
- Nav items: rounded-lg, 10px padding, icon + label
- Active: bg-primary/15 text-primary
- Inactive: text-sidebar-fg, hover:bg-sidebar-hover

### Sticky Header
- Fixed top, white bg, backdrop-blur, border-bottom
- Left: page title (bold) + subtitle (small muted)
- Right: sync status indicator (green dot + text)

### KPI Cards (4-column grid)
- Each: icon (colored bg circle), value (large bold), label (small muted), trend arrow + change %
- Fade-in animation with staggered delay

### Charts
- No grid lines or minimal
- Rounded tooltips
- Gradient fills for area charts
- Clean, minimal axes

### Tables
- Sticky header row
- Badge-style tags for status/severity (colored backgrounds)
- Row hover highlight
- Rounded corners, overflow hidden

### Filter Panel
- Search bar at top with icon
- Expandable filter grid below
- Collapsible via toggle button
- Each filter field has label + dropdown/input

## Files to Modify

### 1. assets/style.css — COMPLETE REWRITE
Replace with vizion-lab design system CSS. Keep all existing class names that are referenced in Python code (like `.kpi-card`, `.kpi-value`, `.kpi-label`, `.filter-container`, `.chart-container`, `.sidebar-nav`, `.nav-item`, `.nav-toggle-btn`, etc.) but restyle them to match vizion-lab.

### 2. assets/responsive.css — UPDATE
Update responsive breakpoints to match vizion-lab patterns.

### 3. dash_common_styles.py — UPDATE COLORS & HELPERS
- Update color constants to match vizion-lab palette
- Update theme manager to use new CSS variables
- Update chart template (Plotly layout template) to vizion-lab style (minimal, clean)

### 4. navigation_manager.py — RESTYLE
- The sidebar nav items should use vizion-lab styling
- Already has icon + label pattern, just need color/style updates
- Colors update to dark sidebar (hsl(220 25% 12%))

### 5. page_components.py — RESTYLE
- Update inline styles in create_sidebar_nav, create_breadcrumb, KPI cards, etc.
- Match vizion-lab color palette and spacing

### 6. defect_explore.py — LAYOUT & STYLE CHANGES ONLY
In the `app.layout` and `create_sidebar_nav()` function:
- Update the top header bar to match vizion-lab (sticky, with title + subtitle + sync indicator)
- Update sidebar colors to dark theme
- Update main content area styling
- Keep ALL callback functions, data processing, chart generation logic UNTOUCHED
- Only modify inline styles, layout structure, and visual elements

## Key Rules
1. **DO NOT touch any callback function logic** — only change style parameters
2. **DO NOT change any data processing** — SQL queries, pandas operations, etc.
3. **DO NOT remove any component IDs** — they're used by callbacks
4. **Keep all existing CSS class names** that Python code references
5. **Test that all nav items still work** after restyling
6. **The AI chat (SiSi) stays as-is** in functionality, just visual refresh

## What Success Looks Like
- Same tabs/pages/navigation work identically
- Same charts render with same data, but look cleaner
- Dark sidebar on left, light content area
- KPI cards have vizion-lab styling
- Filter panel looks like vizion-lab's filter panel
- Tables have vizion-lab badge styles
- Plotly charts use vizion-lab color scheme and minimal gridlines
