import { describe, expect, it } from "vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";

import { FullPicturePage } from "../full-picture-page";
import type { FullPictureDashboardViewModel } from "../../../lib/full-picture-types";

const sampleDashboardData: FullPictureDashboardViewModel = {
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
    groups: ["Q-Gate", "Integration", "CoC"],
  },
  filters: {
    years: ["2025", "2026"],
    projects: ["Project A", "Project B"],
    assignedEcus: ["ECU-A", "ECU-B"],
    problemFinderTeams: ["Team A", "Team B"],
    aidas: ["AIDA-1", "AIDA-2"],
    phases: ["08-Resolved", "09-Rejected"],
    solutionClusters: ["Cluster 1", "Cluster 2"],
    pus: ["PU-1", "PU-2"],
    markets: ["CN", "EU"],
    leadModels: ["Model 1", "Model 2"],
    groups: ["Q-Gate", "Integration", "CoC"],
  },
  overview: {
    ticketCount: 3,
    resolvedForwardCount: 2,
    rejectedDirectlyCount: 2,
    resolvedForwardPercent: 66.67,
    rejectedDirectlyPercent: 66.67,
  },
  outcomeSummary: [
    { key: "resolvedForward", label: "Resolved Forward (08 -> 06)", count: 2, percent: 66.67, denominator: 3 },
    { key: "rejectedDirectly", label: "Rejected Directly (01 -> 09)", count: 2, percent: 66.67, denominator: 3 },
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
      totalTickets: 1,
      resolvedForwardCount: 0,
      rejectedDirectlyCount: 1,
      resolvedForwardTeamPercent: 0,
      rejectedDirectlyTeamPercent: 100,
      teamDenominator: 1,
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
      ticketName: "Other year ticket",
      status: "08-Resolved",
      problemFinderTeam: "Team B",
      group: "Q-Gate",
      phase: "08-Resolved",
      isResolvedForward: true,
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

function renderReadyPage(data: FullPictureDashboardViewModel = sampleDashboardData) {
  render(<FullPicturePage state="ready" initialData={data} />);
}

function getTicketTable() {
  return screen.getByRole("table", { name: "Ticket detail table" });
}

describe("FullPicturePage", () => {
  it("renders the loading shell", () => {
    render(<FullPicturePage state="loading" />);

    expect(screen.getByText("Full Picture Management Workbench")).toBeInTheDocument();
    expect(screen.getByText("Loading Full Picture data...")).toBeInTheDocument();
  });

  it("renders the placeholder shell", () => {
    render(<FullPicturePage state="placeholder" statusMessage="API warming up." />);

    expect(screen.getByText("Full Picture Management Workbench")).toBeInTheDocument();
    expect(screen.getByText("Full Picture shell")).toBeInTheDocument();
    expect(screen.getByText("API warming up.")).toBeInTheDocument();
  });

  it("renders the ready state headings and required ticket columns", () => {
    renderReadyPage();

    expect(screen.getByText("Full Picture Management Workbench")).toBeInTheDocument();
    expect(screen.getByText("Portfolio outcome mix")).toBeInTheDocument();
    expect(screen.getByText("Team expansion by outcome")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Project" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Octane Ticket ID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Group" })).toBeInTheDocument();
  });

  it("shows team outcome percentages against each team's own ticket total", () => {
    renderReadyPage();

    expect(screen.getByRole("button", { name: /Team A .* 2 tickets 100% of team total/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Team A .* 1 tickets 50% of team total/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Team B .* 1 tickets 100% of team total/i })).toBeInTheDocument();
  });

  it("renders filters in the right sidebar and allows collapsing them", () => {
    renderReadyPage();

    const sidebar = screen.getByLabelText("Full Picture filters sidebar");

    expect(within(sidebar).getByRole("heading", { name: "Filters" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("heading", { name: "Core scope" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("heading", { name: "Workflow status" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: "Project A" })).toBeInTheDocument();

    fireEvent.click(within(sidebar).getByRole("button", { name: "Collapse" }));

    expect(within(sidebar).getByRole("button", { name: "Open filters" })).toBeInTheDocument();
    expect(within(sidebar).queryByRole("button", { name: "Project A" })).not.toBeInTheDocument();
  });

  it("changes visible counts and ticket scope when filters are toggled", () => {
    renderReadyPage();

    expect(screen.getByText("3 scoped tickets")).toBeInTheDocument();
    expect(within(getTicketTable()).getByText("1001")).toBeInTheDocument();
    expect(within(getTicketTable()).getByText("1002")).toBeInTheDocument();
    expect(within(getTicketTable()).getByText("1003")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Project B" }));

    expect(screen.getByText("1 scoped ticket")).toBeInTheDocument();
    expect(within(getTicketTable()).queryByText("1001")).not.toBeInTheDocument();
    expect(within(getTicketTable()).queryByText("1002")).not.toBeInTheDocument();
    expect(within(getTicketTable()).getByText("1003")).toBeInTheDocument();
  });

  it("reflects filter changes from all dimensions in the active scope summary", () => {
    renderReadyPage();

    expect(screen.getByText(/Active scope: .*Assigned ECU: All ECUs.*Market: All markets/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "ECU-B" }));
    fireEvent.click(screen.getByRole("button", { name: "EU" }));

    expect(screen.getByText(/Active scope: .*Assigned ECU: ECU-B.*Market: EU/i)).toBeInTheDocument();
  });

  it("narrows the table when an outcome summary is selected", () => {
    renderReadyPage();

    const outcomeButton = screen.getByRole("button", { name: /^Portfolio Resolved Forward \(08 -> 06\)/i });

    expect(screen.getByRole("button", { name: "All projects" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Project A" })).toHaveAttribute("aria-pressed", "false");
    expect(outcomeButton).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(outcomeButton);

    expect(screen.getByText("2 matching tickets")).toBeInTheDocument();
    expect(screen.getByText("Outcome: Resolved Forward (08 -> 06)")).toBeInTheDocument();
    expect(outcomeButton).toHaveAttribute("aria-pressed", "true");
    expect(within(getTicketTable()).getByText("1001")).toBeInTheDocument();
    expect(within(getTicketTable()).getByText("1002")).toBeInTheDocument();
    expect(within(getTicketTable()).queryByText("1003")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear chart selection" }));

    expect(screen.getByText("3 matching tickets")).toBeInTheDocument();
  });

  it("narrows the table by team and outcome when a team row is selected", () => {
    renderReadyPage();

    const teamOutcomeButton = screen.getByRole("button", { name: /Team A.*Rejected Directly/i });

    expect(teamOutcomeButton).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(teamOutcomeButton);

    expect(screen.getByText("1 matching ticket")).toBeInTheDocument();
    expect(screen.getByText("Team: Team A")).toBeInTheDocument();
    expect(screen.getByText("Outcome: Rejected Directly (01 -> 09)")).toBeInTheDocument();
    expect(teamOutcomeButton).toHaveAttribute("aria-pressed", "true");
    expect(within(getTicketTable()).queryByText("1001")).not.toBeInTheDocument();
    expect(within(getTicketTable()).getByText("1002")).toBeInTheDocument();
    expect(within(getTicketTable()).queryByText("1003")).not.toBeInTheDocument();
  });


  it("keeps the dual-path ticket visible under either outcome selection", () => {
    renderReadyPage();

    fireEvent.click(screen.getByRole("button", { name: /^Portfolio Resolved Forward \(08 -> 06\)/i }));
    expect(within(getTicketTable()).getByText("1002")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear chart selection" }));
    fireEvent.click(screen.getByRole("button", { name: /^Portfolio Rejected Directly \(01 -> 09\)/i }));
    expect(within(getTicketTable()).getByText("1002")).toBeInTheDocument();
  });

  it("shows a coherent no-data state for an empty ready payload", () => {
    renderReadyPage({
      ...sampleDashboardData,
      filters: {
        ...sampleDashboardData.filters,
        projects: [],
        problemFinderTeams: [],
      },
      overview: {
        ticketCount: 0,
        resolvedForwardCount: 0,
        rejectedDirectlyCount: 0,
        resolvedForwardPercent: 0,
        rejectedDirectlyPercent: 0,
      },
      outcomeSummary: [
        { key: "resolvedForward", label: "Resolved Forward (08 -> 06)", count: 0, percent: 0, denominator: 0 },
        { key: "rejectedDirectly", label: "Rejected Directly (01 -> 09)", count: 0, percent: 0, denominator: 0 },
      ],
      teamOutcomeRows: [],
      ticketRows: [],
    });

    expect(screen.getByText("No Full Picture tickets matched the current scope.")).toBeInTheDocument();
    expect(screen.getByText("No team outcome rows are available for the current scope.")).toBeInTheDocument();
    expect(screen.getByText("No ticket details are available for the current scope.")).toBeInTheDocument();
  });
});