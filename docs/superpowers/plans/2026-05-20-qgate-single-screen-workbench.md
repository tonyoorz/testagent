# QGate Single-Screen Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the current QGate Next.js prototype into a single-screen management workbench with a deeper detail band, a read-only context rail, and concise startup guidance while keeping the current typed API contract and single-route architecture intact.

**Architecture:** Keep the existing server-rendered data flow unchanged and focus implementation inside the current `apps/qgate-kpi` page slice. Add a second analytical band and a read-only context rail by deriving richer presentation state from the existing `QGateDashboardViewModel`, then document local startup alongside the UI so the experimental frontend is understandable without extra navigation or new backend endpoints.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Testing Library, CSS custom properties, existing FastAPI QGate API.

---

Git commit steps are intentionally omitted because the workspace policy requires explicit user approval before any commit.

## Planned File Map

- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
  Purpose: reshape the single page into overview, deep-dive, and context sections while keeping placeholder/loading/ready semantics.
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
  Purpose: pin the new deep-dive and context-rail behavior plus ready-empty fallbacks.
- Modify: `apps/qgate-kpi/app/__tests__/page.test.tsx`
  Purpose: verify the route renders the new single-screen structure with fetched data and preserves placeholder behavior.
- Modify: `apps/qgate-kpi/app/globals.css`
  Purpose: add layout and responsive styling for the deeper single-screen structure and context rail.
- Modify: `README.md`
  Purpose: document how to start the Python API and the Next.js frontend for this experimental QGate app.

### Task 1: Add Failing UI Coverage For The Single-Screen Structure

**Files:**
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Modify: `apps/qgate-kpi/app/__tests__/page.test.tsx`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Test: `apps/qgate-kpi/app/__tests__/page.test.tsx`

- [ ] **Step 1: Write failing component assertions for the deep-dive layer and context rail**

```tsx
it("renders the deep-dive detail band and read-only context rail in ready state", () => {
  render(<QGateDashboardPage state="ready" initialData={sampleDashboardData} />);

  expect(screen.getByText("Coverage detail")).toBeInTheDocument();
  expect(screen.getByText("Transition breakdown")).toBeInTheDocument();
  expect(screen.getByText("Scope and startup")).toBeInTheDocument();
  expect(screen.getByText("Default server-side scope")).toBeInTheDocument();
});

it("keeps the context rail visible when the page is in placeholder state", () => {
  render(<QGateDashboardPage state="placeholder" statusMessage="Initial dashboard data unavailable." />);

  expect(screen.getByText("Scope and startup")).toBeInTheDocument();
  expect(screen.getByText("Frontend dev server")).toBeInTheDocument();
});
```

- [ ] **Step 2: Write a failing route test for inline startup guidance**

```tsx
it("renders startup guidance and scope details from the fetched payload", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(createJsonResponse(samplePayload));

  render(await HomePage());

  expect(screen.getByText("Scope and startup")).toBeInTheDocument();
  expect(screen.getByText("qgate/defect")).toBeInTheDocument();
  expect(screen.getByText("http://127.0.0.1:8001")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the focused frontend tests and verify they fail for the missing sections**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test -- src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx app/__tests__/page.test.tsx ; Pop-Location`

Expected: FAIL because the page currently has only the hero/workbench panels and does not expose a context rail or the new deep-dive section titles.

### Task 2: Implement The Single-Screen Deep-Dive Band And Context Rail

**Files:**
- Modify: `apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx`
- Modify: `apps/qgate-kpi/app/globals.css`
- Test: `apps/qgate-kpi/src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx`
- Test: `apps/qgate-kpi/app/__tests__/page.test.tsx`

- [ ] **Step 1: Add the minimal deep-dive/context markup to make the new tests pass**

```tsx
<section className="dashboard-sections" aria-label="QGate dashboard sections">
  <section className="deep-dive-band" aria-label="QGate deep dive">
    <article className="workbench-panel deep-dive-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Deep dive</p>
          <h2>Coverage detail</h2>
        </div>
      </div>
    </article>
    <article className="workbench-panel deep-dive-panel">
      <div className="panel-heading">
        <div>
          <p className="panel-kicker">Deep dive</p>
          <h2>Transition breakdown</h2>
        </div>
      </div>
    </article>
  </section>

  <aside className="context-rail" aria-label="Scope and startup">
    <div className="panel-heading">
      <div>
        <p className="panel-kicker">Context</p>
        <h2>Scope and startup</h2>
      </div>
    </div>
    <p className="context-label">Default server-side scope</p>
    <p>{initialData.generatedFrom.defectDir}</p>
    <p>{initialData.generatedFrom.historyDir}</p>
    <p>Frontend dev server</p>
    <p>http://127.0.0.1:8001</p>
  </aside>
</section>
```

- [ ] **Step 2: Replace placeholder deep-dive content with derived ready-state detail and explicit placeholder/context behavior**

```tsx
const coverageDetailRows = state === "ready"
  ? initialData.coverageRows
      .map((row) => ({
        ...row,
        health: row.defects === 0 ? 0 : (row.historyOk / row.defects) * 100,
      }))
      .sort((left, right) => right.defects - left.defects || right.health - left.health)
  : [];

const availableGroups = state === "ready" ? initialData.options.groups.join(", ") || "No group options" : "Unavailable";
```

- [ ] **Step 3: Add layout and responsive styles for the new single-screen structure**

```css
.dashboard-sections {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(18rem, 0.85fr);
  gap: 1rem;
  margin-top: 1rem;
}

.deep-dive-band {
  display: grid;
  gap: 1rem;
}

.context-rail {
  position: sticky;
  top: 1.25rem;
  align-self: start;
  border: 1px solid var(--color-panel-border);
  border-radius: calc(var(--radius-panel) - 8px);
  background: var(--color-panel-strong);
  padding: 1.35rem;
}
```

- [ ] **Step 4: Run the same focused tests and verify they pass**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test -- src/features/qgate-dashboard/__tests__/dashboard-page.test.tsx app/__tests__/page.test.tsx ; Pop-Location`

Expected: PASS with the new deep-dive and context assertions green.

### Task 3: Add Startup Docs And Full Validation

**Files:**
- Modify: `README.md`
- Test: `apps/qgate-kpi`

- [ ] **Step 1: Add a concise README section for the experimental QGate frontend**

```md
### QGate Next.js experimental frontend

Backend API:

```bash
python -m uvicorn qgate_api:app --host 127.0.0.1 --port 8001 --reload
```

Frontend:

```bash
cd apps/qgate-kpi
copy .env.local.example .env.local
npm install
npm run dev
```

Set `NEXT_PUBLIC_QGATE_API_BASE=http://127.0.0.1:8001` when the API is not running on the default local address.
```

- [ ] **Step 2: Run the full frontend validation suite**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run lint ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run typecheck ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run build ; Pop-Location`

Expected: all commands PASS and the build keeps `/` as the only dynamic QGate route.

- [ ] **Step 3: Sanity-check the root README formatting**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord' ; git diff -- README.md apps/qgate-kpi/src/features/qgate-dashboard/dashboard-page.tsx apps/qgate-kpi/app/globals.css ; Pop-Location`

Expected: the docs and UI changes are limited to the Task 6 single-screen workbench scope.
