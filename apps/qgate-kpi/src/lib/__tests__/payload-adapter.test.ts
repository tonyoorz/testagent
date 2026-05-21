import { describe, expect, it } from "vitest";

import { adaptQGateDashboardPayload, QGatePayloadValidationError } from "../payload-adapter";
import type { QGateDashboardPayload } from "../types";

const samplePayload: QGateDashboardPayload = {
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

describe("adaptQGateDashboardPayload", () => {
  it("normalizes the backend payload into a typed frontend model", () => {
    const adapted = adaptQGateDashboardPayload(samplePayload);

    expect(adapted.generatedFrom).toEqual({
      defectDir: "qgate/defect",
      historyDir: "qgate/history",
      teams: ["DTSV_China"],
      minTransitionCount: 200,
    });
    expect(adapted.overview.totalDefects).toBe(4);
    expect(adapted.metaRows).toEqual([
      {
        team: "DTSV_China",
        defects: 4,
        historyOk: 3,
        historyMissingOrError: 1,
      },
    ]);
    expect(adapted.coverageRows[0]).toEqual({
      team: "DTSV_China",
      year: "2026",
      defects: 4,
      historyOk: 3,
      historyMissingOrError: 1,
    });
    expect(adapted.ticketRows[0].ticketUrl).toBe("https://octane/1001");
    expect(adapted.issueRows[0]).toEqual({
      year: "2026",
      team: "DTSV_China",
      ticketId: "1001",
      phaseTransition: "02-QGate -> 03-Analysis",
      group: "Q-Gate",
      durationHours: 24,
      changedBy: "Alice",
      fif: "Global",
      ticketTimespanDays: 2,
    });
  });

  it("rejects payloads with missing required dataset columns", () => {
    expect(() =>
      adaptQGateDashboardPayload({
        ...samplePayload,
        issues: {
          columns: ["Year", "Team"],
          rows: [["2026", "DTSV_China"]],
        },
      }),
    ).toThrow(QGatePayloadValidationError);
  });

  it("rejects payloads with non-numeric values in numeric columns", () => {
    expect(() =>
      adaptQGateDashboardPayload({
        ...samplePayload,
        issues: {
          ...samplePayload.issues,
          rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", "oops", "Alice", "Global", 2]],
        },
      }),
    ).toThrow(QGatePayloadValidationError);
  });

  it("rejects payloads with malformed nested options fields", () => {
    expect(() =>
      adaptQGateDashboardPayload({
        ...samplePayload,
        options: {
          ...samplePayload.options,
          teams: null,
        },
      }),
    ).toThrow(QGatePayloadValidationError);
  });

  it("rejects payloads with malformed overview scalar fields", () => {
    expect(() =>
      adaptQGateDashboardPayload({
        ...samplePayload,
        overview: {
          ...samplePayload.overview,
          total_defects: "oops",
        },
      }),
    ).toThrow(QGatePayloadValidationError);
  });

  it("rejects payloads with non-string values in string dataset columns", () => {
    expect(() =>
      adaptQGateDashboardPayload({
        ...samplePayload,
        tickets: {
          ...samplePayload.tickets,
          rows: [["1001", { href: "https://octane/1001" }, "Ticket 1001", "Alice"]],
        },
      }),
    ).toThrow(QGatePayloadValidationError);
  });

  it("preserves null ticket timespans instead of coercing them to zero", () => {
    const adapted = adaptQGateDashboardPayload({
      ...samplePayload,
      issues: {
        ...samplePayload.issues,
        rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", null]],
      },
    });

    expect(adapted.issueRows[0].ticketTimespanDays).toBeNull();
  });

  it("rejects boolean values in required numeric dataset columns", () => {
    expect(() =>
      adaptQGateDashboardPayload({
        ...samplePayload,
        issues: {
          ...samplePayload.issues,
          rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", true, "Alice", "Global", 2]],
        },
      }),
    ).toThrow(QGatePayloadValidationError);
  });
});