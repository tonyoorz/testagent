import type { FullPictureDashboardFilters } from "./full-picture-types";

export const DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS: Readonly<FullPictureDashboardFilters> = Object.freeze({
  years: ["2026"],
  projects: [],
  assignedEcus: [],
  problemFinderTeams: [],
  aidas: [],
  phases: [],
  solutionClusters: [],
  pus: [],
  markets: [],
  leadModels: [],
  groups: [],
});

export function getDefaultFullPictureDashboardFilters(): FullPictureDashboardFilters {
  return {
    years: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.years],
    projects: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.projects],
    assignedEcus: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.assignedEcus],
    problemFinderTeams: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.problemFinderTeams],
    aidas: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.aidas],
    phases: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.phases],
    solutionClusters: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.solutionClusters],
    pus: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.pus],
    markets: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.markets],
    leadModels: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.leadModels],
    groups: [...DEFAULT_FULL_PICTURE_DASHBOARD_FILTERS.groups],
  };
}
