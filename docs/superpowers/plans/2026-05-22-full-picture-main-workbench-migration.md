# Full Picture Main Workbench Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the redesigned Full Picture experience into the app root `/` as the new `Main` dashboard, preserve the current `/full-picture` route as the legacy view, and remove browser dependence on direct cross-origin calls to `http://127.0.0.1:8001` by adding a same-origin Next.js bridge.

**Architecture:** Keep the existing Full Picture backend contract, payload adapter, default filters, and client-side derivation logic. Add a small server-side proxy layer inside `apps/qgate-kpi` so browser hydration talks to `/api/full-picture/dashboard` on the same origin, while SSR pages still fetch the Python backend through a shared server helper. Build the redesigned `Main` UI in a separate `full-picture-workbench` feature slice so the legacy `/full-picture` page keeps rendering the current `full-picture-dashboard` slice unchanged.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Testing Library, existing FastAPI `qgate_api.py` backend on port `8001`

---

Git commit steps are intentionally omitted because the workspace policy requires explicit user approval before any commit.

## Planned File Map

- Create: `apps/qgate-kpi/app/api/full-picture/dashboard/route.ts`
  Purpose: same-origin proxy endpoint that forwards Full Picture dashboard requests to the Python backend.
- Create: `apps/qgate-kpi/app/api/full-picture/dashboard/route.test.ts`
  Purpose: pin query forwarding and error passthrough for the same-origin proxy.
- Create: `apps/qgate-kpi/src/lib/full-picture-server-api.ts`
  Purpose: shared server-only helper for resolving the backend base URL and forwarding requests for both route handlers and SSR pages.
- Modify: `apps/qgate-kpi/src/lib/full-picture-api.ts`
  Purpose: split browser-facing base URL resolution from backend-facing resolution so browser bootstrap defaults to the same-origin bridge.
- Modify: `apps/qgate-kpi/src/lib/__tests__/full-picture-api.test.ts`
  Purpose: lock the browser transport onto `/api/full-picture` and keep existing payload/error coverage intact.
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/workbench-page.tsx`
  Purpose: render the new `Main` shell, compact filter rail, KPI cards, outcome band, team expansion, and ticket table using existing Full Picture data.
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/workbench-bootstrap.tsx`
  Purpose: reuse the current non-blocking Full Picture hydration behavior for the new `Main` page.
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-page.test.tsx`
  Purpose: pin the redesigned `Main` shell, English-only labels, and ticket drilldown interactions.
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-bootstrap.test.tsx`
  Purpose: pin retry behavior and ensure browser hydration goes through the same-origin bridge.
- Modify: `apps/qgate-kpi/app/page.tsx`
  Purpose: switch the app root from the old QGate dashboard slice to the new Full Picture `Main` workbench bootstrap.
- Modify: `apps/qgate-kpi/app/__tests__/page.test.tsx`
  Purpose: verify the app root now renders the new `Main` workbench with fetched Full Picture data.
- Create: `apps/qgate-kpi/app/full-picture/__tests__/page.test.tsx`
  Purpose: verify the legacy `/full-picture` route still renders the original dashboard slice.
- Modify: `apps/qgate-kpi/app/full-picture/page.tsx`
  Purpose: keep the legacy route behavior while switching its browser hydration path to the same-origin bridge.
- Modify: `apps/qgate-kpi/app/globals.css`
  Purpose: add the new `Main` shell, sidebar, card, filter, and responsive layout styles that match the approved visual direction.
- Modify: `README.md`
  Purpose: document the new `Main` route behavior and the local startup flow for the Python backend plus Next.js frontend.

## Task 1: Add failing coverage for the same-origin Full Picture bridge

**Files:**
- Modify: `apps/qgate-kpi/src/lib/__tests__/full-picture-api.test.ts`
- Create: `apps/qgate-kpi/app/api/full-picture/dashboard/route.test.ts`
- Test: `apps/qgate-kpi/src/lib/__tests__/full-picture-api.test.ts`
- Test: `apps/qgate-kpi/app/api/full-picture/dashboard/route.test.ts`

- [ ] **Step 1: Add a failing browser-base assertion to the existing Full Picture API tests**

```ts
it("defaults browser callers to the same-origin bridge when no full-picture override is set", () => {
  vi.stubEnv("FULL_PICTURE_API_BASE", undefined);
  vi.stubEnv("NEXT_PUBLIC_FULL_PICTURE_API_BASE", undefined);

  expect(resolveFullPictureBrowserApiBaseUrl()).toBe("/api/full-picture");
});
```

- [ ] **Step 2: Add a failing route-handler test for repeated query params and backend error passthrough**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

const requestFullPictureDashboardFromBackend = vi.hoisted(() => vi.fn());

vi.mock("../../../../src/lib/full-picture-server-api", () => ({
  requestFullPictureDashboardFromBackend,
}));

import { GET } from "./route";

describe("GET /api/full-picture/dashboard", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("forwards repeated filter params and relays the backend response", async () => {
    requestFullPictureDashboardFromBackend.mockResolvedValue(
      new Response(JSON.stringify({ overview: { ticket_count: 3 } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await GET(
      new Request(
        "http://localhost:3001/api/full-picture/dashboard?years=2026&projects=Project%20A&projects=Project%20B",
      ),
    );

    expect(requestFullPictureDashboardFromBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        requestUrl: expect.any(URL),
      }),
    );
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ overview: { ticket_count: 3 } });
  });

  it("keeps backend detail payloads intact for non-ok responses", async () => {
    requestFullPictureDashboardFromBackend.mockResolvedValue(
      new Response(JSON.stringify({ detail: "No Full Picture data found." }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await GET(new Request("http://localhost:3001/api/full-picture/dashboard"));

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toEqual({ detail: "No Full Picture data found." });
  });
});
```

- [ ] **Step 3: Run the focused transport tests and verify they fail for the missing same-origin bridge**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test -- src/lib/__tests__/full-picture-api.test.ts app/api/full-picture/dashboard/route.test.ts ; Pop-Location`

Expected: FAIL because `resolveFullPictureBrowserApiBaseUrl` and the route handler do not exist yet.

## Task 2: Implement the bridge and split browser/server Full Picture transport

**Files:**
- Create: `apps/qgate-kpi/src/lib/full-picture-server-api.ts`
- Create: `apps/qgate-kpi/app/api/full-picture/dashboard/route.ts`
- Modify: `apps/qgate-kpi/src/lib/full-picture-api.ts`
- Test: `apps/qgate-kpi/src/lib/__tests__/full-picture-api.test.ts`
- Test: `apps/qgate-kpi/app/api/full-picture/dashboard/route.test.ts`

- [ ] **Step 1: Add the shared server helper for backend forwarding**

```ts
const DEFAULT_FULL_PICTURE_BACKEND_BASE = "http://127.0.0.1:8001";

export function resolveFullPictureBackendBaseUrl() {
  return process.env.FULL_PICTURE_API_BASE ?? DEFAULT_FULL_PICTURE_BACKEND_BASE;
}

export async function requestFullPictureDashboardFromBackend({
  requestUrl,
  signal,
}: {
  requestUrl: URL;
  signal?: AbortSignal;
}) {
  const backendUrl = new URL("/api/full-picture/dashboard", resolveFullPictureBackendBaseUrl());

  requestUrl.searchParams.forEach((value, key) => {
    backendUrl.searchParams.append(key, value);
  });

  return fetch(backendUrl, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });
}
```

- [ ] **Step 2: Implement the Next.js route handler as a thin proxy**

```ts
import { requestFullPictureDashboardFromBackend } from "../../../../src/lib/full-picture-server-api";

export async function GET(request: Request) {
  const backendResponse = await requestFullPictureDashboardFromBackend({
    requestUrl: new URL(request.url),
  });

  return new Response(await backendResponse.text(), {
    status: backendResponse.status,
    headers: {
      "Content-Type": backendResponse.headers.get("Content-Type") ?? "application/json",
    },
  });
}
```

- [ ] **Step 3: Update the browser-facing Full Picture client to default to the same-origin bridge**

```ts
export function resolveFullPictureBrowserApiBaseUrl() {
  return process.env.NEXT_PUBLIC_FULL_PICTURE_API_BASE ?? "/api/full-picture";
}

export async function fetchFullPictureDashboardPayload(
  filters: FullPictureDashboardFilters = getDefaultFullPictureDashboardFilters(),
  options: FetchFullPictureDashboardPayloadOptions = {},
) {
  const apiBaseUrl = options.baseUrl ?? resolveFullPictureBrowserApiBaseUrl();
  // existing fetch, HTTP error handling, and payload validation stay unchanged
}
```

- [ ] **Step 4: Re-run the same focused transport tests and verify they pass**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test -- src/lib/__tests__/full-picture-api.test.ts app/api/full-picture/dashboard/route.test.ts ; Pop-Location`

Expected: PASS with browser callers now targeting `/api/full-picture/dashboard` and the proxy relaying backend status/detail intact.

## Task 3: Add failing coverage for the new `Main` workbench slice and route switch

**Files:**
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-page.test.tsx`
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-bootstrap.test.tsx`
- Modify: `apps/qgate-kpi/app/__tests__/page.test.tsx`
- Create: `apps/qgate-kpi/app/full-picture/__tests__/page.test.tsx`
- Test: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-page.test.tsx`
- Test: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-bootstrap.test.tsx`
- Test: `apps/qgate-kpi/app/__tests__/page.test.tsx`
- Test: `apps/qgate-kpi/app/full-picture/__tests__/page.test.tsx`

- [ ] **Step 1: Add a failing component test for the redesigned `Main` shell and interaction model**

```tsx
it("renders the Main workbench shell with the required Full Picture sections", () => {
  render(<FullPictureWorkbenchPage state="ready" initialData={sampleDashboardData} />);

  expect(screen.getByText("Main")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Portfolio Outcome" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Team Expansion" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Ticket Detail" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open legacy Full Picture" })).toHaveAttribute("href", "/full-picture");
});

it("narrows the Ticket Detail table when an outcome card and a team outcome row are selected", () => {
  render(<FullPictureWorkbenchPage state="ready" initialData={sampleDashboardData} />);

  fireEvent.click(screen.getByRole("button", { name: /^Portfolio Resolved Forward/i }));
  fireEvent.click(screen.getByRole("button", { name: /Team A .* Resolved Forward/i }));

  expect(screen.getByText("2 matching tickets")).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Ticket detail table" })).getByText("1001")).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Ticket detail table" })).getByText("1002")).toBeInTheDocument();
});
```

- [ ] **Step 2: Add a failing bootstrap test that forces placeholder hydration through the same-origin bridge**

```tsx
it("retries through the same-origin bridge when SSR falls back to placeholder", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(samplePayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(
    <FullPictureWorkbenchBootstrap
      apiBaseUrl="/api/full-picture"
      initialPageProps={{ state: "placeholder", statusMessage: "API warming up." }}
    />,
  );

  await screen.findByRole("heading", { name: "Portfolio Outcome" });

  const requestUrl = new URL(String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0]), "http://localhost:3001");
  expect(requestUrl.pathname).toBe("/api/full-picture/dashboard");
});
```

- [ ] **Step 3: Add failing route tests for the new root behavior and legacy route preservation**

```tsx
it("renders the Main workbench at the app root with server-fetched Full Picture data", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(createJsonResponse(samplePayload));

  render(await HomePage());

  expect(screen.getByRole("heading", { name: "Portfolio Outcome" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open legacy Full Picture" })).toHaveAttribute("href", "/full-picture");
});
```

```tsx
it("keeps the legacy /full-picture route on the original dashboard page", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(createJsonResponse(samplePayload));

  render(await FullPictureRoutePage());

  expect(screen.getByText("Full Picture Management Workbench")).toBeInTheDocument();
  expect(screen.queryByText("Main")).not.toBeInTheDocument();
});
```

- [ ] **Step 4: Run the focused UI and route tests and verify they fail for the missing workbench slice**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test -- src/features/full-picture-workbench/__tests__/workbench-page.test.tsx src/features/full-picture-workbench/__tests__/workbench-bootstrap.test.tsx app/__tests__/page.test.tsx app/full-picture/__tests__/page.test.tsx ; Pop-Location`

Expected: FAIL because the `full-picture-workbench` feature slice and the root route switch do not exist yet.

## Task 4: Implement the new `Main` workbench and switch the app root

**Files:**
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/workbench-page.tsx`
- Create: `apps/qgate-kpi/src/features/full-picture-workbench/workbench-bootstrap.tsx`
- Modify: `apps/qgate-kpi/app/page.tsx`
- Modify: `apps/qgate-kpi/app/full-picture/page.tsx`
- Modify: `apps/qgate-kpi/app/globals.css`
- Test: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-page.test.tsx`
- Test: `apps/qgate-kpi/src/features/full-picture-workbench/__tests__/workbench-bootstrap.test.tsx`
- Test: `apps/qgate-kpi/app/__tests__/page.test.tsx`
- Test: `apps/qgate-kpi/app/full-picture/__tests__/page.test.tsx`

- [ ] **Step 1: Build the workbench page by reusing the existing Full Picture filtering and selection logic**

```tsx
const [filters, setFilters] = useState(getDefaultFullPictureDashboardFilters());
const [chartSelection, setChartSelection] = useState<FullPictureChartSelection | null>(null);

const filteredData = state === "ready" ? applyFullPictureDashboardFilters(initialData, filters) : null;
const visibleTicketRows = filteredData
  ? selectTicketRowsForChartSelection(filteredData.ticketRows, chartSelection)
  : [];
```

Required UI constraints for this file:

- render a dark left sidebar with `Main` as the active item
- keep all user-visible copy in English
- use compact dropdown-style filters, not the old chip-only filter wall
- show only `Ticket Detail` as the lower drilldown surface
- include a small secondary action linking to `/full-picture`
- avoid AI explanation cards or narrative analysis blocks

- [ ] **Step 2: Mirror the existing non-blocking Full Picture bootstrap behavior for the new page**

```tsx
export function FullPictureWorkbenchBootstrap({ apiBaseUrl, initialPageProps }: FullPictureWorkbenchBootstrapProps) {
  const [pageProps, setPageProps] = useState<FullPictureWorkbenchPageProps>(initialPageProps);

  const hydrateDashboard = useEffectEvent(async () => {
    const payload = await fetchFullPictureDashboardPayload(getDefaultFullPictureDashboardFilters(), {
      baseUrl: apiBaseUrl,
      signal: createFullPictureBootstrapTimeoutSignal(),
    });

    startTransition(() => {
      setPageProps({
        state: "ready",
        initialData: adaptFullPictureDashboardPayload(payload),
      });
    });
  });

  // keep the same retry / placeholder semantics as the existing full-picture bootstrap
}
```

- [ ] **Step 3: Switch the app root to the new workbench while preserving the legacy page**

```tsx
// app/page.tsx
const payload = await fetchFullPictureDashboardPayload(getDefaultFullPictureDashboardFilters(), {
  baseUrl: resolveFullPictureBackendBaseUrl(),
  signal: createFullPictureBootstrapTimeoutSignal(),
});

return (
  <FullPictureWorkbenchBootstrap
    apiBaseUrl={resolveFullPictureBrowserApiBaseUrl()}
    initialPageProps={pageProps}
  />
);
```

```tsx
// app/full-picture/page.tsx
return (
  <FullPictureDashboardBootstrap
    apiBaseUrl={resolveFullPictureBrowserApiBaseUrl()}
    initialPageProps={pageProps}
  />
);
```

Important scope boundary for this task:

- do not delete `src/features/qgate-dashboard/*` in this pass
- do not mutate `src/features/full-picture-dashboard/full-picture-page.tsx`
- keep `/full-picture` on the current legacy UI

- [ ] **Step 4: Add the approved visual shell and responsive layout styling**

```css
.main-workbench-shell {
  display: grid;
  grid-template-columns: 16.5rem minmax(0, 1fr);
  gap: 1rem;
  min-height: 100vh;
}

.main-workbench-sidebar {
  position: sticky;
  top: 0;
  min-height: 100vh;
  padding: 1rem;
  border-right: 1px solid rgba(205, 214, 226, 0.9);
  background: #0f1723;
  color: #f7fafc;
}

.main-workbench-content {
  display: grid;
  gap: 0.9rem;
  padding: 1rem;
}
```

- [ ] **Step 5: Re-run the same focused UI and route tests and verify they pass**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test -- src/features/full-picture-workbench/__tests__/workbench-page.test.tsx src/features/full-picture-workbench/__tests__/workbench-bootstrap.test.tsx app/__tests__/page.test.tsx app/full-picture/__tests__/page.test.tsx ; Pop-Location`

Expected: PASS with `/` rendering the new `Main` workbench and `/full-picture` still rendering the legacy dashboard.

## Task 5: Document the route change and run full validation

**Files:**
- Modify: `README.md`
- Test: `apps/qgate-kpi`

- [ ] **Step 1: Add a concise README note for the new `Main` route and local startup flow**

```md
### QGate KPI Next.js frontend

- `/` now serves the Full Picture `Main` workbench.
- `/full-picture` remains the legacy Full Picture route.
- Browser-side Full Picture requests go through the same-origin Next.js bridge at `/api/full-picture/dashboard`.

Backend:

```bash
python -m uvicorn qgate_api:app --host 127.0.0.1 --port 8001 --reload
```

Frontend:

```bash
cd apps/qgate-kpi
npm install
npm run dev
```
```

- [ ] **Step 2: Run the full frontend validation suite**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord\apps\qgate-kpi' ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run test ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run lint ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run typecheck ; & 'C:\Users\q446328\AppData\Local\nvm\v24.14.0\npm.cmd' run build ; Pop-Location`

Expected: PASS with the app root rendering the new `Main` workbench, `/full-picture` preserved, and the bridge route compiling cleanly.

- [ ] **Step 3: Run the backend Full Picture regression suite as a transport sanity check**

Run: `Push-Location 'C:\Users\q446328\Desktop\TPMDashbaord' ; python -m pytest tests/test_full_picture_api.py -q ; Pop-Location`

Expected: PASS, confirming the Python payload contract used by the new workbench remains unchanged.
