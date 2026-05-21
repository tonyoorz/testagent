export type QGateDatasetValue = string | number | boolean | null;

export type QGateDataset = {
  columns: string[];
  rows: QGateDatasetValue[][];
};

export type QGateDashboardFilters = {
  defectDir: string;
  historyDir: string;
  teams: string[];
  years: string[];
  groups: string[];
  changedBy: string[];
  fif: string[];
  timespanMin: number;
  timespanMax: number | null;
  minTransitionCount: number;
  analysisWorkers: number;
  cacheDir: string;
  useCache: boolean;
};

export type QGateDashboardPayload = {
  generated_from: {
    defect_dir: string;
    history_dir: string;
    teams: string[];
    min_transition_count: number;
  };
  overview: {
    team_count: number;
    total_defects: number;
    history_ok: number;
    history_bad: number;
    history_success_rate: number;
    transition_samples: number;
    unique_transitions: number;
    unique_tickets: number;
    changed_by_count: number;
    timespan_max: number;
  };
  insights: string[];
  options: {
    teams: string[];
    years: string[];
    groups: string[];
    changedBy: string[];
    fif: string[];
    timespanMax: number;
  };
  meta: QGateDataset;
  coverage: QGateDataset;
  tickets: QGateDataset;
  issues: QGateDataset;
};

export type QGateDashboardState = "placeholder" | "loading" | "ready";

export type QGateGeneratedFrom = {
  defectDir: string;
  historyDir: string;
  teams: string[];
  minTransitionCount: number;
};

export type QGateOverview = {
  teamCount: number;
  totalDefects: number;
  historyOk: number;
  historyBad: number;
  historySuccessRate: number;
  transitionSamples: number;
  uniqueTransitions: number;
  uniqueTickets: number;
  changedByCount: number;
  timespanMax: number;
};

export type QGateDashboardOptions = {
  teams: string[];
  years: string[];
  groups: string[];
  changedBy: string[];
  fif: string[];
  timespanMax: number;
};

export type QGateMetaRow = {
  team: string;
  defects: number;
  historyOk: number;
  historyMissingOrError: number;
};

export type QGateCoverageRow = {
  team: string;
  year: string;
  defects: number;
  historyOk: number;
  historyMissingOrError: number;
};

export type QGateTicketRow = {
  ticketId: string;
  ticketUrl: string;
  ticketName: string;
  tester: string;
};

export type QGateIssueRow = {
  year: string;
  team: string;
  ticketId: string;
  phaseTransition: string;
  group: string;
  durationHours: number;
  changedBy: string;
  fif: string;
  ticketTimespanDays: number | null;
};

export type QGateDashboardViewModel = {
  generatedFrom: QGateGeneratedFrom;
  overview: QGateOverview;
  insights: string[];
  options: QGateDashboardOptions;
  metaRows: QGateMetaRow[];
  coverageRows: QGateCoverageRow[];
  ticketRows: QGateTicketRow[];
  issueRows: QGateIssueRow[];
};