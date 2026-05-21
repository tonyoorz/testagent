import type { QGateDashboardFilters } from "./types";

function appendMultiValue(searchParams: URLSearchParams, key: string, values: string[]) {
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized) {
      continue;
    }

    searchParams.append(key, normalized);
  }
}

export function buildQGateDashboardSearchParams(filters: QGateDashboardFilters) {
  const searchParams = new URLSearchParams();

  searchParams.set("defect_dir", filters.defectDir);
  searchParams.set("history_dir", filters.historyDir);
  searchParams.set("timespan_min", String(filters.timespanMin));
  searchParams.set("min_transition_count", String(filters.minTransitionCount));
  searchParams.set("analysis_workers", String(filters.analysisWorkers));
  searchParams.set("use_cache", String(filters.useCache));

  if (filters.timespanMax !== null) {
    searchParams.set("timespan_max", String(filters.timespanMax));
  }

  searchParams.set("cache_dir", filters.cacheDir);

  appendMultiValue(searchParams, "teams", filters.teams);
  appendMultiValue(searchParams, "years", filters.years);
  appendMultiValue(searchParams, "groups", filters.groups);
  appendMultiValue(searchParams, "changed_by", filters.changedBy);
  appendMultiValue(searchParams, "fif", filters.fif);

  return searchParams;
}

export function buildQGateDashboardUrl(apiBaseUrl: string, filters: QGateDashboardFilters) {
  const normalizedBaseUrl = apiBaseUrl.replace(/\/$/, "");
  const searchParams = buildQGateDashboardSearchParams(filters);

  return `${normalizedBaseUrl}/api/qgate/kpi-dashboard?${searchParams.toString()}`;
}