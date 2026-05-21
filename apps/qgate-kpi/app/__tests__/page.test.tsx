import { afterEach, describe, expect, it, vi } from "vitest";

import { render, screen } from "@testing-library/react";

import HomePage from "../page";

const samplePayload = {
  generated_from: {
    defect_dir: "qgate/defect",
    history_dir: "qgate/history",
    teams: ["DTSV_China"],
    min_transition_count: 200,
  },
  overview: {
    team_count: 1,
    total_defects: 4,
    history_ok: 3,
    history_bad: 1,
    history_success_rate: 75,
    transition_samples: 2,
    unique_transitions: 2,
    unique_tickets: 1,
    changed_by_count: 1,
    timespan_max: 3,
  },
  insights: ["Highest-volume transition is 02-QGate -> 03-Analysis with 2 samples."],
  options: {
    teams: ["DTSV_China"],
    years: ["2026"],
    groups: ["Q-Gate"],
    changedBy: ["Alice"],
    fif: ["Global"],
    timespanMax: 3,
  },
  meta: {
    columns: ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
    rows: [["DTSV_China", 4, 3, 1]],
  },
  coverage: {
    columns: ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
    rows: [["DTSV_China", "2026", 4, 3, 1]],
  },
  tickets: {
    columns: ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
    rows: [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
  },
  issues: {
    columns: [
      "Year",
      "Team",
      "Ticket_ID",
      "Phase_Transition",
      "Group",
      "Duration_Hours",
      "Changed_By",
      "FiF",
      "Ticket_Timespan_Days",
    ],
    rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
  },
};

function createJsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HomePage route", () => {
  it("renders the dashboard with server-fetched initial data at the app root", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(createJsonResponse(samplePayload));

    render(await HomePage());

    expect(screen.getByText("QGate KPI Dashboard")).toBeInTheDocument();
    expect(screen.getAllByText("Teams").length).toBeGreaterThan(0);
    expect(screen.getByText("Scoped defects")).toBeInTheDocument();
    expect(screen.getByText("Tickets in View")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getAllByText("Team Distribution").length).toBeGreaterThan(0);
    expect(screen.getByText("QGate Efficiency")).toBeInTheDocument();
  });

  it("falls back to the shell state when the API is unavailable", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("connect ECONNREFUSED"));

    render(await HomePage());

    expect(screen.getByText("Initial dashboard data unavailable. Showing the shell until the API becomes reachable.")).toBeInTheDocument();
  });

  it("renders the loading shell when the initial API request times out", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    const timeoutError = new Error("The operation was aborted.");
    timeoutError.name = "AbortError";

    vi.spyOn(globalThis, "fetch").mockRejectedValue(timeoutError);

    render(await HomePage());

    expect(
      screen.getByText("Initial dashboard data is still warming the QGate API. The browser keeps loading in the background."),
    ).toBeInTheDocument();
  });

  it("shows a schema-specific fallback when the API returns a malformed success payload", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      createJsonResponse({
        ...samplePayload,
        issues: {
          columns: ["Year"],
          rows: [["2026"]],
        },
      }),
    );

    render(await HomePage());

    expect(screen.getByText("Initial dashboard data was rejected because the API payload shape changed.")).toBeInTheDocument();
  });

  it("shows the schema-specific fallback when nested payload fields drift", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      createJsonResponse({
        ...samplePayload,
        options: {
          ...samplePayload.options,
          teams: null,
        },
      }),
    );

    render(await HomePage());

    expect(screen.getByText("Initial dashboard data was rejected because the API payload shape changed.")).toBeInTheDocument();
  });

  it("shows the schema-specific fallback when a successful response body is invalid JSON", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{invalid-json", {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    render(await HomePage());

    expect(screen.getByText("Initial dashboard data was rejected because the API payload shape changed.")).toBeInTheDocument();
  });

  it("surfaces backend request detail instead of reporting every non-ok response as connectivity loss", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      createJsonResponse({ detail: "No QGate data found." }, 422),
    );

    render(await HomePage());

    expect(screen.getByText("Initial dashboard request failed: No QGate data found.")).toBeInTheDocument();
  });
});