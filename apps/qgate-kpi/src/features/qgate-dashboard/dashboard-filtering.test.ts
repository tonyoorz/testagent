import { describe, expect, it } from "vitest";

import type { QGateDashboardFilters, QGateDashboardViewModel } from "../../lib/types";

import { applyDashboardFilters, createDashboardFilterOptionsSummary } from "./dashboard-filtering";

const sampleData: QGateDashboardViewModel = {
  generatedFrom: {
    defectDir: "qgate/defect",
    historyDir: "qgate/history",
    teams: ["DTSV_China", "DTSV_CE"],
    minTransitionCount: 200,
  },
  overview: {
    teamCount: 2,
    totalDefects: 6,
    historyOk: 4,
    historyBad: 2,
    historySuccessRate: 66.7,
    transitionSamples: 3,
    uniqueTransitions: 2,
    uniqueTickets: 2,
    changedByCount: 2,
    timespanMax: 5,
  },
  insights: ["Seed insight"],
  options: {
    teams: ["DTSV_China", "DTSV_CE"],
    years: ["2025", "2026"],
    groups: ["Q-Gate", "CoC"],
    changedBy: ["Alice", "Bob"],
    fif: ["Global", "Local"],
    timespanMax: 5,
  },
  metaRows: [
    { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
  ],
  coverageRows: [
    { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    { team: "DTSV_CE", year: "2025", defects: 2, historyOk: 1, historyMissingOrError: 1 },
  ],
  ticketRows: [],
  issueRows: [
    {
      year: "2026",
      team: "DTSV_China",
      ticketId: "1001",
      phaseTransition: "02-QGate -> 03-Analysis",
      group: "Q-Gate",
      durationHours: 24,
      changedBy: "Alice",
      fif: "Global",
      ticketTimespanDays: 2,
    },
    {
      year: "2025",
      team: "DTSV_CE",
      ticketId: "1002",
      phaseTransition: "03-Analysis -> 04-Fix",
      group: "CoC",
      durationHours: 12,
      changedBy: "Bob",
      fif: "Local",
      ticketTimespanDays: 1,
    },
  ],
};

function buildFilters(overrides: Partial<QGateDashboardFilters>): QGateDashboardFilters {
  return {
    defectDir: "qgate/defect",
    historyDir: "qgate/history",
    teams: [],
    years: [],
    groups: [],
    changedBy: [],
    fif: [],
    timespanMin: 0,
    timespanMax: null,
    minTransitionCount: 200,
    analysisWorkers: 0,
    cacheDir: "qgate_cache",
    useCache: true,
    ...overrides,
  };
}

describe("applyDashboardFilters", () => {
  it("filters issue and coverage rows by the active chips and numeric inputs", () => {
    const result = applyDashboardFilters(
      sampleData,
      buildFilters({
        teams: ["DTSV_China"],
        years: ["2026"],
        groups: ["Q-Gate"],
        changedBy: ["Alice"],
        fif: ["Global"],
        timespanMin: 1,
        timespanMax: 3,
      }),
    );

    expect(result.issueRows).toHaveLength(1);
    expect(result.issueRows[0]?.ticketId).toBe("1001");
    expect(result.coverageRows).toEqual([
      { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    ]);
    expect(result.metaRows).toEqual([
      { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
    ]);
  });

  it("builds a compact active-filter summary for the UI", () => {
    const summary = createDashboardFilterOptionsSummary(
      buildFilters({ teams: ["DTSV_China"], groups: ["Q-Gate"], changedBy: ["Alice"] }),
    );

    expect(summary).toEqual(["1 team", "1 group", "Alice", "Timespan >= 0d", "Min transitions 200"]);
  });
});