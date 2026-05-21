import { afterEach, describe, expect, it, vi } from "vitest";

import { render, screen, waitFor } from "@testing-library/react";

import { QGateDashboardBootstrap } from "../dashboard-bootstrap";

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

describe("QGateDashboardBootstrap", () => {
  it("continues loading in the browser after the server falls back to the loading shell", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(createJsonResponse(samplePayload));

    render(
      <QGateDashboardBootstrap
        state="loading"
        statusMessage="Initial dashboard data is still warming the QGate API. The browser keeps loading in the background."
      />,
    );

    expect(
      screen.getByText("Initial dashboard data is still warming the QGate API. The browser keeps loading in the background."),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Dashboard ready.")).toBeInTheDocument();
    });

    expect(screen.getByText("Team Coverage")).toBeInTheDocument();
  });
});