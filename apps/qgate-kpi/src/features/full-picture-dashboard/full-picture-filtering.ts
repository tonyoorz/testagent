import type {
  FullPictureChartSelection,
  FullPictureDashboardFilters,
  FullPictureDashboardViewModel,
  FullPictureOutcomeKey,
  FullPictureOutcomeSummaryRow,
  FullPictureOverview,
  FullPictureTeamOutcomeRow,
  FullPictureTicketRow,
} from "../../lib/full-picture-types";

type FilteredFullPictureDashboardData = Pick<
  FullPictureDashboardViewModel,
  "ticketRows" | "overview" | "outcomeSummary" | "teamOutcomeRows"
>;

const OUTCOME_SERIES: ReadonlyArray<{
  key: FullPictureOutcomeKey;
  label: string;
  flagName: keyof Pick<FullPictureTicketRow, "isResolvedForward" | "isRejectedDirectly">;
}> = [
  {
    key: "resolvedForward",
    label: "Resolved Forward (08 -> 06)",
    flagName: "isResolvedForward",
  },
  {
    key: "rejectedDirectly",
    label: "Rejected Directly (01 -> 09)",
    flagName: "isRejectedDirectly",
  },
];

function matchesListFilter(activeValues: string[], candidate: string) {
  return activeValues.length === 0 || activeValues.includes(candidate);
}

function matchesFilters(row: FullPictureTicketRow, filters: FullPictureDashboardFilters) {
  return (
    matchesListFilter(filters.years, row.year) &&
    matchesListFilter(filters.projects, row.project) &&
    matchesListFilter(filters.assignedEcus, row.assignedEcu) &&
    matchesListFilter(filters.problemFinderTeams, row.problemFinderTeam) &&
    matchesListFilter(filters.aidas, row.aida) &&
    matchesListFilter(filters.phases, row.phase) &&
    matchesListFilter(filters.solutionClusters, row.solutionCluster) &&
    matchesListFilter(filters.pus, row.pu) &&
    matchesListFilter(filters.markets, row.market) &&
    matchesListFilter(filters.leadModels, row.leadModel) &&
    matchesListFilter(filters.groups, row.group)
  );
}

function toPercent(numerator: number, denominator: number) {
  if (denominator <= 0) {
    return 0;
  }

  return Math.round((numerator / denominator) * 10000) / 100;
}

function sortableValue(value: string) {
  const normalized = value.trim();
  if (/^\d+$/.test(normalized)) {
    return [0, Number(normalized)] as const;
  }

  return [1, normalized.toLocaleLowerCase()] as const;
}

function buildOverview(ticketRows: FullPictureTicketRow[]): FullPictureOverview {
  const ticketCount = ticketRows.length;
  const resolvedForwardCount = ticketRows.filter((row) => row.isResolvedForward).length;
  const rejectedDirectlyCount = ticketRows.filter((row) => row.isRejectedDirectly).length;

  return {
    ticketCount,
    resolvedForwardCount,
    rejectedDirectlyCount,
    resolvedForwardPercent: toPercent(resolvedForwardCount, ticketCount),
    rejectedDirectlyPercent: toPercent(rejectedDirectlyCount, ticketCount),
  };
}

function buildOutcomeSummary(ticketRows: FullPictureTicketRow[]): FullPictureOutcomeSummaryRow[] {
  const denominator = ticketRows.length;

  return OUTCOME_SERIES.map((series) => {
    const count = ticketRows.filter((row) => row[series.flagName]).length;

    return {
      key: series.key,
      label: series.label,
      count,
      percent: toPercent(count, denominator),
      denominator,
    };
  });
}

function buildTeamOutcomeRows(ticketRows: FullPictureTicketRow[]): FullPictureTeamOutcomeRow[] {
  const grouped = ticketRows.reduce(
    (accumulator, row) => {
      const current = accumulator.get(row.problemFinderTeam) ?? {
        problemFinderTeam: row.problemFinderTeam,
        totalTickets: 0,
        resolvedForwardCount: 0,
        rejectedDirectlyCount: 0,
        resolvedForwardTeamPercent: 0,
        rejectedDirectlyTeamPercent: 0,
        teamDenominator: 0,
      };

      current.totalTickets += 1;
      if (row.isResolvedForward) {
        current.resolvedForwardCount += 1;
      }
      if (row.isRejectedDirectly) {
        current.rejectedDirectlyCount += 1;
      }

      accumulator.set(row.problemFinderTeam, current);
      return accumulator;
    },
    new Map<string, FullPictureTeamOutcomeRow>(),
  );

  return Array.from(grouped.values())
    .map((row) => ({
      ...row,
      resolvedForwardTeamPercent: toPercent(row.resolvedForwardCount, row.totalTickets),
      rejectedDirectlyTeamPercent: toPercent(row.rejectedDirectlyCount, row.totalTickets),
      teamDenominator: row.totalTickets,
    }))
    .sort((left, right) => {
      if (right.totalTickets !== left.totalTickets) {
        return right.totalTickets - left.totalTickets;
      }

      const leftValue = sortableValue(left.problemFinderTeam);
      const rightValue = sortableValue(right.problemFinderTeam);

      if (leftValue[0] !== rightValue[0]) {
        return leftValue[0] - rightValue[0];
      }

      if (leftValue[1] < rightValue[1]) {
        return -1;
      }

      if (leftValue[1] > rightValue[1]) {
        return 1;
      }

      return 0;
    });
}

function matchesOutcomeSelection(row: FullPictureTicketRow, outcomeKey: FullPictureOutcomeKey | null | undefined) {
  if (!outcomeKey) {
    return true;
  }

  if (outcomeKey === "resolvedForward") {
    return row.isResolvedForward;
  }

  return row.isRejectedDirectly;
}

export function applyFullPictureDashboardFilters(
  viewModel: FullPictureDashboardViewModel,
  filters: FullPictureDashboardFilters,
): FilteredFullPictureDashboardData {
  const ticketRows = viewModel.ticketRows.filter((row) => matchesFilters(row, filters));

  return {
    ticketRows,
    overview: buildOverview(ticketRows),
    outcomeSummary: buildOutcomeSummary(ticketRows),
    teamOutcomeRows: buildTeamOutcomeRows(ticketRows),
  };
}

export function selectTicketRowsForChartSelection(
  ticketRows: FullPictureTicketRow[],
  selection: FullPictureChartSelection = {},
) {
  const normalizedTeam = selection.team?.trim();

  return ticketRows.filter(
    (row) => (!normalizedTeam || row.problemFinderTeam === normalizedTeam) && matchesOutcomeSelection(row, selection.outcomeKey),
  );
}
