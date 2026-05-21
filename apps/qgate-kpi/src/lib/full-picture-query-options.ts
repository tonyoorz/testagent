import type { FullPictureDashboardFilters } from "./full-picture-types";

function appendMultiValue(searchParams: URLSearchParams, key: string, values: string[]) {
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized) {
      continue;
    }

    searchParams.append(key, normalized);
  }
}

export function buildFullPictureDashboardSearchParams(filters: FullPictureDashboardFilters) {
  const searchParams = new URLSearchParams();

  appendMultiValue(searchParams, "years", filters.years);
  appendMultiValue(searchParams, "projects", filters.projects);
  appendMultiValue(searchParams, "assigned_ecus", filters.assignedEcus);
  appendMultiValue(searchParams, "problem_finder_teams", filters.problemFinderTeams);
  appendMultiValue(searchParams, "aidas", filters.aidas);
  appendMultiValue(searchParams, "phases", filters.phases);
  appendMultiValue(searchParams, "solution_clusters", filters.solutionClusters);
  appendMultiValue(searchParams, "pus", filters.pus);
  appendMultiValue(searchParams, "markets", filters.markets);
  appendMultiValue(searchParams, "lead_models", filters.leadModels);
  appendMultiValue(searchParams, "groups", filters.groups);

  return searchParams;
}

export function buildFullPictureDashboardUrl(apiBaseUrl: string, filters: FullPictureDashboardFilters) {
  const normalizedBaseUrl = apiBaseUrl.replace(/\/$/, "");
  const searchParams = buildFullPictureDashboardSearchParams(filters);

  return `${normalizedBaseUrl}/api/full-picture/dashboard?${searchParams.toString()}`;
}
