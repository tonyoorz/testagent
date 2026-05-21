import type { QGateDashboardFilters } from "./types";

export const DEFAULT_QGATE_DASHBOARD_FILTERS: Readonly<QGateDashboardFilters> = Object.freeze({
  defectDir: "qgate/defect",
  historyDir: "qgate/history",
  teams: [],
  years: [],
  groups: [],
  changedBy: [],
  fif: [],
  timespanMin: 0,
  timespanMax: null,
  minTransitionCount: 0,
  analysisWorkers: 0,
  cacheDir: "qgate_cache",
  useCache: true,
});

export function getDefaultQGateDashboardFilters(): QGateDashboardFilters {
  return {
    ...DEFAULT_QGATE_DASHBOARD_FILTERS,
    teams: [...DEFAULT_QGATE_DASHBOARD_FILTERS.teams],
    years: [...DEFAULT_QGATE_DASHBOARD_FILTERS.years],
    groups: [...DEFAULT_QGATE_DASHBOARD_FILTERS.groups],
    changedBy: [...DEFAULT_QGATE_DASHBOARD_FILTERS.changedBy],
    fif: [...DEFAULT_QGATE_DASHBOARD_FILTERS.fif],
  };
}