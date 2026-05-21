import { describe, expect, it } from "vitest";

import { getDefaultFullPictureDashboardFilters } from "../../lib/full-picture-default-filters";
import type { FullPictureDashboardFilters, FullPictureDashboardViewModel } from "../../lib/full-picture-types";

import { applyFullPictureDashboardFilters, selectTicketRowsForChartSelection } from "./full-picture-filtering";

const sampleData: FullPictureDashboardViewModel = {
  generatedFrom: {
    defectDbPath: "qgate/qgate_data.db",
    historyDbPath: "qgate/qgate_data.db",
    years: ["2026"],
    projects: ["Project A", "Project B"],
    assignedEcus: ["ECU-A", "ECU-B"],
    problemFinderTeams: ["Team A", "Team B"],
    aidas: ["AIDA-1", "AIDA-2"],
    phases: ["08-Resolved", "09-Rejected"],
    solutionClusters: ["Cluster 1", "Cluster 2"],
    pus: ["PU-1", "PU-2"],
    markets: ["CN", "EU"],
    leadModels: ["Model 1", "Model 2"],
    groups: ["Q-Gate", "Integration", "CoC", "Other"],
  },
  filters: {
    years: ["2025", "2026"],
    projects: ["Project A", "Project B"],
    assignedEcus: ["ECU-A", "ECU-B"],
    problemFinderTeams: ["Team A", "Team B"],
    aidas: ["AIDA-1", "AIDA-2"],
    phases: ["08-Resolved", "09-Rejected", "10-Closed"],
    solutionClusters: ["Cluster 1", "Cluster 2"],
    pus: ["PU-1", "PU-2"],
    markets: ["CN", "EU"],
    leadModels: ["Model 1", "Model 2"],
    groups: ["Q-Gate", "Integration", "CoC", "Other"],
  },
  overview: {
    ticketCount: 4,
    resolvedForwardCount: 2,
    rejectedDirectlyCount: 2,
    resolvedForwardPercent: 50,
    rejectedDirectlyPercent: 50,
  },
  outcomeSummary: [
    { key: "resolvedForward", label: "Resolved Forward (08 -> 06)", count: 2, percent: 50, denominator: 4 },
    { key: "rejectedDirectly", label: "Rejected Directly (01 -> 09)", count: 2, percent: 50, denominator: 4 },
  ],
  teamOutcomeRows: [
    {
      problemFinderTeam: "Team A",
      totalTickets: 2,
      resolvedForwardCount: 2,
      rejectedDirectlyCount: 1,
      resolvedForwardTeamPercent: 100,
      rejectedDirectlyTeamPercent: 50,
      teamDenominator: 2,
    },
    {
      problemFinderTeam: "Team B",
      totalTickets: 2,
      resolvedForwardCount: 0,
      rejectedDirectlyCount: 1,
      resolvedForwardTeamPercent: 0,
      rejectedDirectlyTeamPercent: 50,
      teamDenominator: 2,
    },
  ],
  ticketRows: [
    {
      ticketId: "1001",
      ticketName: "Forward only",
      status: "08-Resolved",
      problemFinderTeam: "Team A",
      group: "Q-Gate",
      phase: "08-Resolved",
      isResolvedForward: true,
      isRejectedDirectly: false,
      year: "2026",
      project: "Project A",
      assignedEcu: "ECU-A",
      aida: "AIDA-1",
      solutionCluster: "Cluster 1",
      pu: "PU-1",
      market: "CN",
      leadModel: "Model 1",
    },
    {
      ticketId: "1002",
      ticketName: "Both outcomes",
      status: "09-Rejected",
      problemFinderTeam: "Team A",
      group: "Integration",
      phase: "09-Rejected",
      isResolvedForward: true,
      isRejectedDirectly: true,
      year: "2026",
      project: "Project A",
      assignedEcu: "ECU-B",
      aida: "AIDA-2",
      solutionCluster: "Cluster 2",
      pu: "PU-2",
      market: "EU",
      leadModel: "Model 2",
    },
    {
      ticketId: "1003",
      ticketName: "Rejected only",
      status: "09-Rejected",
      problemFinderTeam: "Team B",
      group: "CoC",
      phase: "09-Rejected",
      isResolvedForward: false,
      isRejectedDirectly: true,
      year: "2026",
      project: "Project B",
      assignedEcu: "ECU-B",
      aida: "AIDA-2",
      solutionCluster: "Cluster 2",
      pu: "PU-2",
      market: "EU",
      leadModel: "Model 2",
    },
    {
      ticketId: "1004",
      ticketName: "Out-of-year ticket",
      status: "10-Closed",
      problemFinderTeam: "Team B",
      group: "Other",
      phase: "10-Closed",
      isResolvedForward: false,
      isRejectedDirectly: false,
      year: "2025",
      project: "Project B",
      assignedEcu: "ECU-A",
      aida: "AIDA-1",
      solutionCluster: "Cluster 1",
      pu: "PU-1",
      market: "CN",
      leadModel: "Model 1",
    },
  ],
};

function buildFilters(overrides: Partial<FullPictureDashboardFilters> = {}): FullPictureDashboardFilters {
  return {
    ...getDefaultFullPictureDashboardFilters(),
    ...overrides,
  };
}

describe("applyFullPictureDashboardFilters", () => {
  it("defaults to year 2026 and derives overview, outcome summary, and team rows from the filtered ticket scope", () => {
    const result = applyFullPictureDashboardFilters(sampleData, buildFilters());

    expect(result.ticketRows.map((row) => row.ticketId)).toEqual(["1001", "1002", "1003"]);
    expect(result.overview).toEqual({
      ticketCount: 3,
      resolvedForwardCount: 2,
      rejectedDirectlyCount: 2,
      resolvedForwardPercent: 66.67,
      rejectedDirectlyPercent: 66.67,
    });
    expect(result.outcomeSummary).toEqual([
      { key: "resolvedForward", label: "Resolved Forward (08 -> 06)", count: 2, percent: 66.67, denominator: 3 },
      { key: "rejectedDirectly", label: "Rejected Directly (01 -> 09)", count: 2, percent: 66.67, denominator: 3 },
    ]);
    expect(result.teamOutcomeRows).toEqual([
      {
        problemFinderTeam: "Team A",
        totalTickets: 2,
        resolvedForwardCount: 2,
        rejectedDirectlyCount: 1,
        resolvedForwardTeamPercent: 100,
        rejectedDirectlyTeamPercent: 50,
        teamDenominator: 2,
      },
      {
        problemFinderTeam: "Team B",
        totalTickets: 1,
        resolvedForwardCount: 0,
        rejectedDirectlyCount: 1,
        resolvedForwardTeamPercent: 0,
        rejectedDirectlyTeamPercent: 100,
        teamDenominator: 1,
      },
    ]);
  });

  it("recomputes team percentages from each team's scoped tickets", () => {
    const result = applyFullPictureDashboardFilters(
      sampleData,
      buildFilters({
        problemFinderTeams: ["Team A"],
      }),
    );

    expect(result.ticketRows.map((row) => row.ticketId)).toEqual(["1001", "1002"]);
    expect(result.outcomeSummary).toEqual([
      { key: "resolvedForward", label: "Resolved Forward (08 -> 06)", count: 2, percent: 100, denominator: 2 },
      { key: "rejectedDirectly", label: "Rejected Directly (01 -> 09)", count: 1, percent: 50, denominator: 2 },
    ]);
    expect(result.teamOutcomeRows).toEqual([
      {
        problemFinderTeam: "Team A",
        totalTickets: 2,
        resolvedForwardCount: 2,
        rejectedDirectlyCount: 1,
        resolvedForwardTeamPercent: 100,
        rejectedDirectlyTeamPercent: 50,
        teamDenominator: 2,
      },
    ]);
  });
});

describe("selectTicketRowsForChartSelection", () => {
  it("narrows tickets by outcome key and optional team without excluding dual-flag tickets from either outcome", () => {
    const filtered = applyFullPictureDashboardFilters(sampleData, buildFilters());

    expect(selectTicketRowsForChartSelection(filtered.ticketRows, { outcomeKey: "resolvedForward" }).map((row) => row.ticketId)).toEqual([
      "1001",
      "1002",
    ]);
    expect(
      selectTicketRowsForChartSelection(filtered.ticketRows, {
        outcomeKey: "rejectedDirectly",
        team: "Team A",
      }).map((row) => row.ticketId),
    ).toEqual(["1002"]);
  });
});