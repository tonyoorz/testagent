export type FullPictureOutcomePayloadKey = "resolved_forward" | "rejected_directly";

export type FullPictureOutcomeKey = "resolvedForward" | "rejectedDirectly";

export type FullPictureFilterValues = {
  years: string[];
  projects: string[];
  assignedEcus: string[];
  problemFinderTeams: string[];
  aidas: string[];
  phases: string[];
  solutionClusters: string[];
  pus: string[];
  markets: string[];
  leadModels: string[];
  groups: string[];
};

export type FullPictureDashboardFilters = FullPictureFilterValues;

export type FullPictureFilterValuesPayload = {
  years: string[];
  projects: string[];
  assigned_ecus: string[];
  problem_finder_teams: string[];
  aidas: string[];
  phases: string[];
  solution_clusters: string[];
  pus: string[];
  markets: string[];
  lead_models: string[];
  groups: string[];
};

export type FullPictureGeneratedFromPayload = FullPictureFilterValuesPayload & {
  defect_db_path: string;
  history_db_path: string;
};

export type FullPictureOverviewPayload = {
  ticket_count: number;
  resolved_forward_count: number;
  rejected_directly_count: number;
  resolved_forward_percent: number;
  rejected_directly_percent: number;
};

export type FullPictureOutcomeSummaryRowPayload = {
  key: FullPictureOutcomePayloadKey;
  label: string;
  count: number;
  percent: number;
  denominator: number;
};

export type FullPictureTeamOutcomeRowPayload = {
  problem_finder_team: string;
  total_tickets: number;
  resolved_forward_count: number;
  rejected_directly_count: number;
  resolved_forward_team_percent: number;
  rejected_directly_team_percent: number;
  team_denominator: number;
};

export type FullPictureTicketRowPayload = {
  ticket_id: string;
  ticket_name: string;
  status: string;
  problem_finder_team: string;
  group: string;
  phase: string;
  is_resolved_forward: boolean;
  is_rejected_directly: boolean;
  year: string;
  project: string;
  assigned_ecu: string;
  aida: string;
  solution_cluster: string;
  pu: string;
  market: string;
  lead_model: string;
};

export type FullPictureDashboardPayload = {
  generated_from: FullPictureGeneratedFromPayload;
  filters: FullPictureFilterValuesPayload;
  overview: FullPictureOverviewPayload;
  outcome_summary: FullPictureOutcomeSummaryRowPayload[];
  team_outcome_rows: FullPictureTeamOutcomeRowPayload[];
  ticket_rows: FullPictureTicketRowPayload[];
};

export type FullPictureGeneratedFrom = FullPictureFilterValues & {
  defectDbPath: string;
  historyDbPath: string;
};

export type FullPictureOverview = {
  ticketCount: number;
  resolvedForwardCount: number;
  rejectedDirectlyCount: number;
  resolvedForwardPercent: number;
  rejectedDirectlyPercent: number;
};

export type FullPictureOutcomeSummaryRow = {
  key: FullPictureOutcomeKey;
  label: string;
  count: number;
  percent: number;
  denominator: number;
};

export type FullPictureTeamOutcomeRow = {
  problemFinderTeam: string;
  totalTickets: number;
  resolvedForwardCount: number;
  rejectedDirectlyCount: number;
  resolvedForwardTeamPercent: number;
  rejectedDirectlyTeamPercent: number;
  teamDenominator: number;
};

export type FullPictureTicketRow = {
  ticketId: string;
  ticketName: string;
  status: string;
  problemFinderTeam: string;
  group: string;
  phase: string;
  isResolvedForward: boolean;
  isRejectedDirectly: boolean;
  year: string;
  project: string;
  assignedEcu: string;
  aida: string;
  solutionCluster: string;
  pu: string;
  market: string;
  leadModel: string;
};

export type FullPictureDashboardViewModel = {
  generatedFrom: FullPictureGeneratedFrom;
  filters: FullPictureFilterValues;
  overview: FullPictureOverview;
  outcomeSummary: FullPictureOutcomeSummaryRow[];
  teamOutcomeRows: FullPictureTeamOutcomeRow[];
  ticketRows: FullPictureTicketRow[];
};

export type FullPictureChartSelection = {
  outcomeKey?: FullPictureOutcomeKey | null;
  team?: string | null;
};
