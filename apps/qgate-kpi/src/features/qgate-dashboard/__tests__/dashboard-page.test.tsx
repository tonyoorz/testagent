import { describe, expect, it } from "vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { within } from "@testing-library/react";

import { QGateDashboardPage } from "../dashboard-page";

const sampleDashboardData = {
  generatedFrom: {
    defectDir: "qgate/defect",
    historyDir: "qgate/history",
    teams: ["DTSV_China"],
    minTransitionCount: 200,
  },
  overview: {
    teamCount: 1,
    totalDefects: 4,
    historyOk: 3,
    historyBad: 1,
    historySuccessRate: 75,
    transitionSamples: 2,
    uniqueTransitions: 2,
    uniqueTickets: 1,
    changedByCount: 1,
    timespanMax: 3,
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
  metaRows: [
    {
      team: "DTSV_China",
      defects: 4,
      historyOk: 3,
      historyMissingOrError: 1,
    },
  ],
  coverageRows: [
    {
      team: "DTSV_China",
      year: "2026",
      defects: 4,
      historyOk: 3,
      historyMissingOrError: 1,
    },
  ],
  ticketRows: [
    {
      ticketId: "1001",
      ticketUrl: "https://octane/1001",
      ticketName: "Ticket 1001",
      tester: "Alice",
    },
  ],
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
  ],
};

describe("QGateDashboardPage", () => {
  it("renders the hero title and loading skeleton", () => {
    render(<QGateDashboardPage state="loading" />);

    expect(screen.getByText("QGate KPI Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Loading dashboard data...")).toBeInTheDocument();
  });

  it("renders the placeholder state before the data layer is wired", () => {
    render(<QGateDashboardPage state="placeholder" />);

    expect(screen.getByText("QGate KPI Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Dashboard shell")).toBeInTheDocument();
  });

  it("renders the ready state when initial data exists", () => {
    render(<QGateDashboardPage state="ready" initialData={sampleDashboardData} />);

    expect(screen.getByText("QGate KPI Dashboard")).toBeInTheDocument();
    expect(screen.getAllByText("Teams").length).toBeGreaterThan(0);
    expect(screen.getByText("Scoped defects")).toBeInTheDocument();
    expect(screen.getByText("Tickets in View")).toBeInTheDocument();
    expect(screen.getByText("QGate Efficiency")).toBeInTheDocument();
    expect(screen.getAllByText(/Team Distribution/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Phase Efficiency Summary/)).toBeInTheDocument();
    expect(screen.getByText("Grouped Stacked View")).toBeInTheDocument();
    expect(screen.getByText("Team × Group Efficiency")).toBeInTheDocument();
    expect(screen.getByText(/Transition Analysis/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument();
    expect(screen.queryByText("PreAnalysis experimental frontend")).not.toBeInTheDocument();
    expect(screen.queryByText("Dashboard ready.")).not.toBeInTheDocument();
  });

  it("treats an empty object as ready data instead of loading", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: [],
          },
          metaRows: [],
          coverageRows: [],
          issueRows: [],
          ticketRows: [],
        }}
      />,
    );

    expect(screen.getByText("No team distribution rows matched the current QGate scope.")).toBeInTheDocument();
    expect(screen.getByText("No transition samples are available for the current ready payload.")).toBeInTheDocument();
    expect(screen.getByText("No summary rows are available for the current QGate scope.")).toBeInTheDocument();
  });

  it("allows the shell status copy to be overridden when the initial fetch fails", () => {
    render(
      <QGateDashboardPage
        state="placeholder"
        statusMessage="Initial dashboard data unavailable. Showing the shell until the API becomes reachable."
      />,
    );

    expect(screen.getByText("QGate KPI Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Initial dashboard data unavailable. Showing the shell until the API becomes reachable.")).toBeInTheDocument();
  });

  it("aggregates transition and phase summary activity for the workbench panels", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          issueRows: [
            ...sampleDashboardData.issueRows,
            {
              year: "2026",
              team: "DTSV_China",
              ticketId: "1001",
              phaseTransition: "02-QGate -> 03-Analysis",
              group: "Q-Gate",
              durationHours: 48,
              changedBy: "Alice",
              fif: "Global",
              ticketTimespanDays: null,
            },
            {
              year: "2026",
              team: "DTSV_China",
              ticketId: "1002",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "Q-Gate",
              durationHours: 12,
              changedBy: "Bob",
              fif: "Global",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    expect(screen.getAllByText("2 samples")).toHaveLength(1);
    expect(screen.getAllByText("1.5d avg")).toHaveLength(1);
    expect(screen.getByRole("table", { name: "Phase efficiency summary" })).toBeInTheDocument();
  });

  it("scales transition bars across groups using the same duration baseline", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            groups: ["Q-Gate", "CoC"],
          },
          issueRows: [
            {
              year: "2026",
              team: "DTSV_China",
              ticketId: "1001",
              phaseTransition: "02-QGate -> 03-Analysis",
              group: "Q-Gate",
              durationHours: 48,
              changedBy: "Alice",
              fif: "Global",
              ticketTimespanDays: 2,
            },
            {
              year: "2026",
              team: "DTSV_China",
              ticketId: "1002",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "CoC",
              durationHours: 12,
              changedBy: "Alice",
              fif: "Global",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    const transitionRoot = screen.getByLabelText("Transition analysis");
    const qgateSection = within(transitionRoot).getAllByText("Q-Gate")[0]?.closest("section");
    const cocSection = within(transitionRoot).getAllByText("CoC")[0]?.closest("section");

    expect(qgateSection?.querySelector(".bar-fill")?.getAttribute("style")).toContain("width: 100%");
    expect(cocSection?.querySelector(".bar-fill")?.getAttribute("style")).toContain("width: 25%");
  });

  it("shows only teams with transition data in the team group efficiency chart", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: ["DTSV_China", "DTSV_CE"],
          },
          metaRows: [
            { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", defects: 2, historyOk: 0, historyMissingOrError: 2 },
          ],
          coverageRows: [
            { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", year: "2026", defects: 2, historyOk: 0, historyMissingOrError: 2 },
          ],
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
          ],
        }}
      />,
    );

    const chartBox = screen.getByText("Team × Group Efficiency").closest(".chart-box");

    expect(chartBox).not.toBeNull();
    expect(within(chartBox as HTMLElement).getByText("DTSV_China")).toBeInTheDocument();
    expect(within(chartBox as HTMLElement).queryByText("DTSV_CE")).not.toBeInTheDocument();
  });

  it("renders the HTML-parity filter section in ready state", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: ["DTSV_China", "DTSV_CE"],
            years: ["2025", "2026"],
            groups: ["Q-Gate", "CoC"],
          },
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All years" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All teams" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No teams" })).toBeInTheDocument();
    expect(screen.getAllByText("Click to toggle").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Reset filters" })).toBeInTheDocument();
  });

  it("supports the HTML-style team none action", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: ["DTSV_China", "DTSV_CE"],
          },
          coverageRows: [
            { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", year: "2026", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
          metaRows: [
            { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
          issueRows: [
            ...sampleDashboardData.issueRows,
            {
              year: "2026",
              team: "DTSV_CE",
              ticketId: "1002",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "Q-Gate",
              durationHours: 12,
              changedBy: "Bob",
              fif: "Global",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "No teams" }));

    expect(screen.getByText("No team distribution rows matched the current QGate scope.")).toBeInTheDocument();
    expect(screen.getByText("No transition samples are available for the current ready payload.")).toBeInTheDocument();
  });

  it("updates the visible dashboard sections when filters change and reset", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: ["DTSV_China", "DTSV_CE"],
            years: ["2025", "2026"],
            groups: ["Q-Gate", "CoC"],
            changedBy: ["Alice", "Bob"],
          },
          coverageRows: [
            { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", year: "2025", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
          metaRows: [
            { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
          issueRows: [
            ...sampleDashboardData.issueRows,
            {
              year: "2025",
              team: "DTSV_CE",
              ticketId: "1002",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "CoC",
              durationHours: 12,
              changedBy: "Bob",
              fif: "Global",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "DTSV_CE" }));

    expect(screen.getByText("03-Analysis -> 04-Fix")).toBeInTheDocument();
    expect(screen.queryByText("02-QGate -> 03-Analysis")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));

    expect(screen.getByText("02-QGate -> 03-Analysis")).toBeInTheDocument();
    expect(screen.getByText("03-Analysis -> 04-Fix")).toBeInTheDocument();
  });

  it("filters transition rows by minimum sample count", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
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
              year: "2026",
              team: "DTSV_China",
              ticketId: "1002",
              phaseTransition: "02-QGate -> 03-Analysis",
              group: "Q-Gate",
              durationHours: 36,
              changedBy: "Alice",
              fif: "Global",
              ticketTimespanDays: 3,
            },
            {
              year: "2026",
              team: "DTSV_China",
              ticketId: "1003",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "Q-Gate",
              durationHours: 12,
              changedBy: "Bob",
              fif: "Global",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Min samples"), { target: { value: "2" } });

    expect(screen.getByText("02-QGate -> 03-Analysis")).toBeInTheDocument();
    expect(screen.queryByText("03-Analysis -> 04-Fix")).not.toBeInTheDocument();
  });

  it("supports searchable changed-by and FiF filters", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            changedBy: ["Alice", "Bob"],
            fif: ["Global", "China Specific"],
          },
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
              year: "2026",
              team: "DTSV_China",
              ticketId: "1002",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "CoC",
              durationHours: 12,
              changedBy: "Bob",
              fif: "China Specific",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Changed by"), { target: { value: "Bob" } });
    fireEvent.click(screen.getByRole("button", { name: "Bob" }));

    expect(screen.getByText("03-Analysis -> 04-Fix")).toBeInTheDocument();
    expect(screen.queryByText("02-QGate -> 03-Analysis")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("FiF"), { target: { value: "China" } });
    fireEvent.click(screen.getByRole("button", { name: "China Specific" }));

    expect(screen.getByText("03-Analysis -> 04-Fix")).toBeInTheDocument();
    expect(screen.queryByText("02-QGate -> 03-Analysis")).not.toBeInTheDocument();
  });

  it("shows the phase summary empty state instead of zero-transition team rows when issue-only filters remove all issues", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: ["DTSV_China", "DTSV_CE"],
            changedBy: ["Alice", "Bob"],
          },
          metaRows: [
            { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
          coverageRows: [
            { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", year: "2026", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
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
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Changed by"), { target: { value: "Bob" } });
    fireEvent.click(screen.getByRole("button", { name: "Bob" }));

    const summaryChartBox = screen.getByText("Team × Group Efficiency").closest(".chart-box");

    expect(
      screen.getByText(
        "No transition samples matched the current issue filters (Changed by: Bob). The scoped defects still exist in the database, but B/C only render issue history rows.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("No summary rows matched the current issue filters (Changed by: Bob). Reset the issue filters to repopulate B/C.")).toBeInTheDocument();
    expect(summaryChartBox).not.toBeNull();
    expect(within(summaryChartBox as HTMLElement).getByText("No team and group efficiency bars are visible because the current issue filters removed all transition rows.")).toBeInTheDocument();
    expect(within(summaryChartBox as HTMLElement).queryByText("DTSV_China")).not.toBeInTheDocument();
    expect(within(summaryChartBox as HTMLElement).queryByText("DTSV_CE")).not.toBeInTheDocument();
  });

  it("hides zero-transition teams from the efficiency chart when issue-only filters leave only some teams", () => {
    render(
      <QGateDashboardPage
        state="ready"
        initialData={{
          ...sampleDashboardData,
          options: {
            ...sampleDashboardData.options,
            teams: ["DTSV_China", "DTSV_CE"],
            changedBy: ["Alice", "Bob"],
          },
          metaRows: [
            { team: "DTSV_China", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
          coverageRows: [
            { team: "DTSV_China", year: "2026", defects: 4, historyOk: 3, historyMissingOrError: 1 },
            { team: "DTSV_CE", year: "2026", defects: 2, historyOk: 1, historyMissingOrError: 1 },
          ],
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
              year: "2026",
              team: "DTSV_CE",
              ticketId: "1002",
              phaseTransition: "03-Analysis -> 04-Fix",
              group: "CoC",
              durationHours: 12,
              changedBy: "Bob",
              fif: "Global",
              ticketTimespanDays: 1,
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Changed by"), { target: { value: "Alice" } });
    fireEvent.click(screen.getByRole("button", { name: "Alice" }));

    const summaryChartBox = screen.getByText("Team × Group Efficiency").closest(".chart-box");

    expect(summaryChartBox).not.toBeNull();
    expect(within(summaryChartBox as HTMLElement).getByText("DTSV_China")).toBeInTheDocument();
    expect(within(summaryChartBox as HTMLElement).queryByText("DTSV_CE")).not.toBeInTheDocument();
  });

  it("does not render the old ticket watch section in ready state", () => {
    render(<QGateDashboardPage state="ready" initialData={sampleDashboardData} />);

    expect(screen.queryByText("Most active tickets")).not.toBeInTheDocument();
    expect(screen.queryByText("Ticket watch")).not.toBeInTheDocument();
  });
});