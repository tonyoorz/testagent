import type {
  QGateCoverageRow,
  QGateDashboardFilters,
  QGateDashboardViewModel,
  QGateIssueRow,
  QGateMetaRow,
} from "../../lib/types";

type FilteredDashboardData = Pick<QGateDashboardViewModel, "metaRows" | "coverageRows" | "issueRows">;

export const EXPLICIT_EMPTY_FILTER_VALUE = "__none__";

function matchesListFilter(activeValues: string[], candidate: string) {
  if (activeValues.includes(EXPLICIT_EMPTY_FILTER_VALUE)) {
    return false;
  }

  return activeValues.length === 0 || activeValues.includes(candidate);
}

function matchesTimespan(issue: QGateIssueRow, filters: QGateDashboardFilters) {
  const value = issue.ticketTimespanDays;

  if (value === null) {
    return filters.timespanMax === null;
  }

  if (value < filters.timespanMin) {
    return false;
  }

  return filters.timespanMax === null || value <= filters.timespanMax;
}

function buildMetaRows(coverageRows: QGateCoverageRow[]): QGateMetaRow[] {
  return Array.from(
    coverageRows.reduce((accumulator, row) => {
      const current = accumulator.get(row.team) ?? {
        team: row.team,
        defects: 0,
        historyOk: 0,
        historyMissingOrError: 0,
      };

      current.defects += row.defects;
      current.historyOk += row.historyOk;
      current.historyMissingOrError += row.historyMissingOrError;
      accumulator.set(row.team, current);
      return accumulator;
    }, new Map<string, QGateMetaRow>()),
  ).map(([, row]) => row);
}

export function applyDashboardFilters(
  viewModel: QGateDashboardViewModel,
  filters: QGateDashboardFilters,
): FilteredDashboardData {
  const issueRows = viewModel.issueRows.filter(
    (row) =>
      matchesListFilter(filters.teams, row.team) &&
      matchesListFilter(filters.years, row.year) &&
      matchesListFilter(filters.groups, row.group) &&
      matchesListFilter(filters.changedBy, row.changedBy) &&
      matchesListFilter(filters.fif, row.fif) &&
      matchesTimespan(row, filters),
  );

  const coverageRows = viewModel.coverageRows.filter(
    (row) => matchesListFilter(filters.teams, row.team) && matchesListFilter(filters.years, row.year),
  );

  return {
    issueRows,
    coverageRows,
    metaRows: buildMetaRows(coverageRows),
  };
}

export function createDashboardFilterOptionsSummary(filters: QGateDashboardFilters) {
  const summary: string[] = [];

  if (filters.teams.includes(EXPLICIT_EMPTY_FILTER_VALUE)) {
    summary.push("No teams");
  } else if (filters.teams.length > 0) {
    summary.push(`${filters.teams.length} team${filters.teams.length > 1 ? "s" : ""}`);
  }

  if (filters.groups.length > 0) {
    summary.push(`${filters.groups.length} group${filters.groups.length > 1 ? "s" : ""}`);
  }

  if (filters.changedBy.length === 1) {
    summary.push(filters.changedBy[0]);
  }

  summary.push(`Timespan >= ${filters.timespanMin}d`);
  summary.push(`Min transitions ${filters.minTransitionCount}`);

  return summary;
}