"use client";

import { useMemo, useState } from "react";

import { getDefaultFullPictureDashboardFilters } from "../../lib/full-picture-default-filters";
import type {
  FullPictureChartSelection,
  FullPictureDashboardFilters,
  FullPictureDashboardViewModel,
  FullPictureOutcomeKey,
  FullPictureOutcomeSummaryRow,
  FullPictureTeamOutcomeRow,
  FullPictureTicketRow,
} from "../../lib/full-picture-types";
import { applyFullPictureDashboardFilters, selectTicketRowsForChartSelection } from "./full-picture-filtering";

type FullPicturePageProps =
  | {
      state: "loading" | "placeholder";
      initialData?: null;
      statusMessage?: string;
    }
  | {
      state: "ready";
      initialData: FullPictureDashboardViewModel;
      statusMessage?: string;
    };

export type { FullPicturePageProps };

const OUTCOME_LABELS: Record<FullPictureOutcomeKey, string> = {
  resolvedForward: "Resolved Forward (08 -> 06)",
  rejectedDirectly: "Rejected Directly (01 -> 09)",
};

const FILTER_CONFIG: ReadonlyArray<{
  field: keyof FullPictureDashboardFilters;
  label: string;
  allLabel: string;
  emptyLabel: string;
  section: "Scope" | "Workflow" | "Vehicle";
}> = [
  { field: "years", label: "Year", allLabel: "All years", emptyLabel: "No year options", section: "Scope" },
  { field: "projects", label: "Project", allLabel: "All projects", emptyLabel: "No project options", section: "Scope" },
  { field: "assignedEcus", label: "Assigned ECU", allLabel: "All ECUs", emptyLabel: "No ECU options", section: "Vehicle" },
  {
    field: "problemFinderTeams",
    label: "Problem Finder Team",
    allLabel: "All teams",
    emptyLabel: "No team options",
    section: "Scope",
  },
  { field: "aidas", label: "AIDA", allLabel: "All AIDAs", emptyLabel: "No AIDA options", section: "Vehicle" },
  { field: "phases", label: "Phase", allLabel: "All phases", emptyLabel: "No phase options", section: "Workflow" },
  {
    field: "solutionClusters",
    label: "Solution Cluster",
    allLabel: "All clusters",
    emptyLabel: "No cluster options",
    section: "Workflow",
  },
  { field: "pus", label: "PU", allLabel: "All PUs", emptyLabel: "No PU options", section: "Workflow" },
  { field: "markets", label: "Market", allLabel: "All markets", emptyLabel: "No market options", section: "Vehicle" },
  { field: "leadModels", label: "Lead Model", allLabel: "All lead models", emptyLabel: "No lead model options", section: "Vehicle" },
  { field: "groups", label: "Group", allLabel: "All groups", emptyLabel: "No group options", section: "Workflow" },
];

const FILTER_SECTION_ORDER = ["Scope", "Workflow", "Vehicle"] as const;

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value: number) {
  return `${value.toFixed(value % 1 === 0 ? 0 : 2)}%`;
}

function pluralize(value: number, singular: string, plural: string) {
  return `${formatInteger(value)} ${value === 1 ? singular : plural}`;
}

function summarizeScopeValues(label: string, allLabel: string, values: string[]) {
  if (values.length === 0) {
    return `${label}: ${allLabel}`;
  }

  if (values.length <= 2) {
    return `${label}: ${values.join(", ")}`;
  }

  return `${label}: ${values.length} selected`;
}

function updateMultiSelect(currentValues: string[], value: string | null) {
  if (value === null) {
    return [];
  }

  return currentValues.includes(value)
    ? currentValues.filter((currentValue) => currentValue !== value)
    : [...currentValues, value];
}

function buildScopeSegments(filters: FullPictureDashboardFilters) {
  return FILTER_CONFIG.map((config) => summarizeScopeValues(config.label, config.allLabel, filters[config.field])).join(" • ");
}

function getSectionActiveCount(
  filters: FullPictureDashboardFilters,
  section: (typeof FILTER_SECTION_ORDER)[number],
) {
  return FILTER_CONFIG.filter((config) => config.section === section && filters[config.field].length > 0).length;
}

function getOutcomeCount(row: FullPictureTeamOutcomeRow, outcomeKey: FullPictureOutcomeKey) {
  return outcomeKey === "resolvedForward" ? row.resolvedForwardCount : row.rejectedDirectlyCount;
}

function getOutcomePercent(row: FullPictureTeamOutcomeRow, outcomeKey: FullPictureOutcomeKey) {
  return outcomeKey === "resolvedForward" ? row.resolvedForwardTeamPercent : row.rejectedDirectlyTeamPercent;
}

function getOutcomeTone(outcomeKey: FullPictureOutcomeKey) {
  return outcomeKey === "resolvedForward" ? "good" : "bad";
}

function matchesSelection(selection: FullPictureChartSelection, outcomeKey: FullPictureOutcomeKey, team?: string) {
  return selection.outcomeKey === outcomeKey && (team ? selection.team === team : !selection.team);
}

function FilterChip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button aria-pressed={active} className={active ? "filter-chip is-active" : "filter-chip"} onClick={onClick} type="button">
      {label}
    </button>
  );
}

function FilterChipRow({
  allLabel,
  values,
  selectedValues,
  onToggle,
  emptyLabel,
  labelId,
}: {
  allLabel: string;
  values: string[];
  selectedValues: string[];
  onToggle: (value: string | null) => void;
  emptyLabel: string;
  labelId: string;
}) {
  if (values.length === 0) {
    return <p className="chip-helper">{emptyLabel}</p>;
  }

  return (
    <div aria-labelledby={labelId} className="chip-stack" role="group">
      <p className="chip-helper">Click to toggle</p>
      <div className="chip-row">
        <FilterChip active={selectedValues.length === 0} label={allLabel} onClick={() => onToggle(null)} />
        {values.map((value) => (
          <FilterChip active={selectedValues.includes(value)} key={value} label={value} onClick={() => onToggle(value)} />
        ))}
      </div>
    </div>
  );
}

function TableOutcomeBadges({ row }: { row: FullPictureTicketRow }) {
  const badges: string[] = [];
  if (row.isResolvedForward) {
    badges.push(OUTCOME_LABELS.resolvedForward);
  }
  if (row.isRejectedDirectly) {
    badges.push(OUTCOME_LABELS.rejectedDirectly);
  }

  if (badges.length === 0) {
    badges.push("No tracked outcome");
  }

  return (
    <div className="full-picture-outcome-badges">
      {badges.map((badge) => (
        <span className="full-picture-outcome-pill" key={badge}>
          {badge}
        </span>
      ))}
    </div>
  );
}

export function FullPicturePage({ initialData, state, statusMessage }: FullPicturePageProps) {
  const [filters, setFilters] = useState<FullPictureDashboardFilters>(() => getDefaultFullPictureDashboardFilters());
  const [selection, setSelection] = useState<FullPictureChartSelection>({});
  const [filtersOpen, setFiltersOpen] = useState(true);

  const isReady = state === "ready";
  const shellHeading = state === "loading" ? "Loading Full Picture data..." : "Full Picture shell";
  const shellMessage =
    state === "loading"
      ? statusMessage ?? "Full Picture data is still warming up. The browser will swap in the workbench as soon as the API responds."
      : statusMessage ?? "Full Picture data is temporarily unavailable. Check the API process and refresh when it is reachable.";

  const filteredData = useMemo(() => {
    return isReady ? applyFullPictureDashboardFilters(initialData, filters) : null;
  }, [filters, initialData, isReady]);

  const selectedTicketRows = useMemo(() => {
    return filteredData ? selectTicketRowsForChartSelection(filteredData.ticketRows, selection) : [];
  }, [filteredData, selection]);

  const teamOutcomeMax = Math.max(
    ...(filteredData?.teamOutcomeRows.flatMap((row) => [row.resolvedForwardCount, row.rejectedDirectlyCount]) ?? [0]),
    1,
  );
  const activeScope = buildScopeSegments(filters);
  const readyData = isReady ? filteredData : null;

  function toggleField(field: keyof FullPictureDashboardFilters, value: string | null) {
    setFilters((current) => ({
      ...current,
      [field]: updateMultiSelect(current[field], value),
    }));
    setSelection({});
  }

  function resetFilters() {
    setFilters(getDefaultFullPictureDashboardFilters());
    setSelection({});
  }

  function toggleOutcomeSelection(outcome: FullPictureOutcomeSummaryRow) {
    setSelection((current) =>
      matchesSelection(current, outcome.key)
        ? {}
        : {
            outcomeKey: outcome.key,
            team: null,
          },
    );
  }

  function toggleTeamOutcomeSelection(team: string, outcomeKey: FullPictureOutcomeKey) {
    setSelection((current) =>
      matchesSelection(current, outcomeKey, team)
        ? {}
        : {
            outcomeKey,
            team,
          },
    );
  }

  return (
    <main className="page-shell">
      {readyData ? (
        <div className="full-picture-layout">
          <div className="full-picture-main">
            <section aria-label="Full Picture hero" className="hero-panel full-picture-hero">
              <div className="hero-header-row">
                <div>
                  <p className="eyebrow">Full Picture</p>
                  <h1>Full Picture Management Workbench</h1>
                  <p className="hero-scope">Active scope: {activeScope}</p>
                  <p className="hero-copy">
                    Track the two approved outcome paths across the current management scope, compare team behavior, and inspect the exact ticket detail rows behind each selection.
                  </p>
                </div>
                <p className="dashboard-status">Ready</p>
              </div>

              <div className="hero-metrics" aria-label="Full Picture summary">
                <article className="metric-card">
                  <p className="metric-label">Scoped tickets</p>
                  <strong className="metric-value">{formatInteger(filteredData.overview.ticketCount)}</strong>
                  <p className="metric-note">{pluralize(filteredData.overview.ticketCount, "scoped ticket", "scoped tickets")}</p>
                </article>
                <article className="metric-card">
                  <p className="metric-label">Resolved forward</p>
                  <strong className="metric-value">{formatInteger(filteredData.overview.resolvedForwardCount)}</strong>
                  <p className="metric-note">{formatPercent(filteredData.overview.resolvedForwardPercent)} of scoped tickets</p>
                </article>
                <article className="metric-card">
                  <p className="metric-label">Rejected directly</p>
                  <strong className="metric-value">{formatInteger(filteredData.overview.rejectedDirectlyCount)}</strong>
                  <p className="metric-note">{formatPercent(filteredData.overview.rejectedDirectlyPercent)} of scoped tickets</p>
                </article>
                <article className="metric-card">
                  <p className="metric-label">Table scope</p>
                  <strong className="metric-value">{formatInteger(selectedTicketRows.length)}</strong>
                  <p className="metric-note">Rows after chart selection</p>
                </article>
              </div>
            </section>

            <section className="dashboard-grid" aria-label="Full Picture workbench">
              <article className="workbench-panel workbench-panel-wide">
                <div className="panel-heading">
                  <div>
                    <p className="panel-kicker">Portfolio</p>
                    <h2>Portfolio outcome mix</h2>
                  </div>
                  <p className="panel-meta">All teams inside the current filter scope, recomputed whenever filters change.</p>
                </div>
                <div className="chart-box">
                  <div className="chart-title">
                    <strong>Outcome bars</strong>
                    <span>Current scope total across all teams</span>
                  </div>

                  <div className="full-picture-outcome-grid" role="group" aria-label="Portfolio outcome mix">
                    {readyData.outcomeSummary.map((row) => {
                      const selected = matchesSelection(selection, row.key);
                      const tone = getOutcomeTone(row.key);
                      const width = row.denominator === 0 ? 0 : Math.max(row.percent, row.count > 0 ? 8 : 0);

                      return (
                        <button
                          aria-label={`Portfolio ${row.label} ${formatInteger(row.count)} tickets ${formatPercent(row.percent)} of ${formatInteger(row.denominator)}`}
                          aria-pressed={selected}
                          className={selected ? `full-picture-outcome-card ${tone} is-selected` : `full-picture-outcome-card ${tone}`}
                          key={row.key}
                          onClick={() => toggleOutcomeSelection(row)}
                          type="button"
                        >
                          <span className="full-picture-outcome-header">
                            <span className="full-picture-outcome-label">{row.label}</span>
                            <strong className="full-picture-outcome-value">{formatInteger(row.count)}</strong>
                          </span>
                          <span aria-hidden="true" className="full-picture-outcome-bar">
                            <span className={`full-picture-outcome-fill ${tone}`} style={{ width: `${width}%` }} />
                          </span>
                          <span className="full-picture-outcome-meta">{formatPercent(row.percent)} of {formatInteger(row.denominator)}</span>
                        </button>
                      );
                    })}
                  </div>

                  {readyData.ticketRows.length === 0 ? (
                    <p className="panel-empty">No Full Picture tickets matched the current scope.</p>
                  ) : null}
                </div>
              </article>

              <article className="workbench-panel workbench-panel-wide">
                <div className="panel-heading">
                  <div>
                    <p className="panel-kicker">Teams</p>
                    <h2>Team expansion by outcome</h2>
                  </div>
                  <p className="panel-meta">Each team shows the same two paths, with percentages based on that team's scoped tickets.</p>
                </div>

                <div className="chart-box">
                  <div className="chart-title">
                    <strong>Team comparison bars</strong>
                    <span>Click a bar to narrow the table by team plus the selected outcome</span>
                  </div>

                  {readyData.teamOutcomeRows.length > 0 ? (
                    <div className="full-picture-team-chart" role="group" aria-label="Team expansion by outcome">
                      <div aria-hidden="true" className="full-picture-team-chart-head">
                        <span>Team</span>
                        <span>{OUTCOME_LABELS.resolvedForward}</span>
                        <span>{OUTCOME_LABELS.rejectedDirectly}</span>
                        <span>Tickets</span>
                      </div>
                      {readyData.teamOutcomeRows.map((row) => (
                        <div className="full-picture-team-chart-row" key={row.problemFinderTeam}>
                          <div className="full-picture-team-chart-team">
                            <strong>{row.problemFinderTeam}</strong>
                            <span>{formatInteger(row.totalTickets)} team tickets</span>
                          </div>
                          {(["resolvedForward", "rejectedDirectly"] as const).map((outcomeKey) => {
                            const count = getOutcomeCount(row, outcomeKey);
                            const percent = getOutcomePercent(row, outcomeKey);
                            const selected = matchesSelection(selection, outcomeKey, row.problemFinderTeam);
                            const width = count === 0 ? 0 : Math.max((count / teamOutcomeMax) * 100, 8);

                            return (
                              <button
                                aria-label={`${row.problemFinderTeam} ${OUTCOME_LABELS[outcomeKey]} ${formatInteger(count)} tickets ${formatPercent(percent)} of team total`}
                                aria-pressed={selected}
                                className={selected ? "full-picture-team-button is-selected" : "full-picture-team-button"}
                                key={`${row.problemFinderTeam}-${outcomeKey}`}
                                onClick={() => toggleTeamOutcomeSelection(row.problemFinderTeam, outcomeKey)}
                                type="button"
                              >
                                <span className="full-picture-team-button-bar">
                                  <span
                                    className={`full-picture-team-button-fill ${getOutcomeTone(outcomeKey)}`}
                                    style={{ width: `${width}%` }}
                                  />
                                </span>
                                <span className="full-picture-team-button-metric">
                                  {formatInteger(count)} • {formatPercent(percent)}
                                </span>
                              </button>
                            );
                          })}
                          <div className="full-picture-team-chart-total">{pluralize(row.totalTickets, "ticket", "tickets")}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="panel-empty">No team outcome rows are available for the current scope.</p>
                  )}
                </div>
              </article>

            <article className="workbench-panel workbench-panel-wide">
              <div className="panel-heading">
                <div>
                  <p className="panel-kicker">Tickets</p>
                  <h2>Ticket detail</h2>
                </div>
                <p className="panel-meta">
                  {pluralize(selectedTicketRows.length, "matching ticket", "matching tickets")} inside the current filter scope.
                </p>
              </div>

              <div className="full-picture-selection-bar">
                <span className="full-picture-selection-count">{pluralize(selectedTicketRows.length, "matching ticket", "matching tickets")}</span>
                {selection.outcomeKey ? (
                  <span className="full-picture-selection-chip">Outcome: {OUTCOME_LABELS[selection.outcomeKey]}</span>
                ) : null}
                {selection.team ? <span className="full-picture-selection-chip">Team: {selection.team}</span> : null}
                {selection.outcomeKey || selection.team ? (
                  <button className="full-picture-clear-button" onClick={() => setSelection({})} type="button">
                    Clear chart selection
                  </button>
                ) : null}
              </div>

              <div className="full-picture-table-wrap">
                <table className="full-picture-table" aria-label="Ticket detail table">
                  <thead>
                    <tr>
                      <th scope="col">Octane Ticket ID</th>
                      <th scope="col">Name</th>
                      <th scope="col">Status</th>
                      <th scope="col">Group</th>
                      <th scope="col">Problem Finder Team</th>
                      <th scope="col">Outcome Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedTicketRows.length > 0 ? (
                      selectedTicketRows.map((row) => (
                        <tr key={row.ticketId}>
                          <td>{row.ticketId}</td>
                          <td>
                            <div className="full-picture-ticket-name">{row.ticketName}</div>
                            <div className="full-picture-ticket-meta">{row.project} • {row.phase}</div>
                          </td>
                          <td>{row.status}</td>
                          <td>{row.group}</td>
                          <td>{row.problemFinderTeam}</td>
                          <td>
                            <TableOutcomeBadges row={row} />
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="full-picture-table-empty" colSpan={6}>
                          No ticket details are available for the current scope.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </article>
            </section>
          </div>

          <aside className={filtersOpen ? "full-picture-sidebar" : "full-picture-sidebar is-collapsed"} aria-label="Full Picture filters sidebar">
            <div className="full-picture-sidebar-rail">
              <div className="full-picture-sidebar-toolbar">
                <div>
                  <p className="panel-kicker">Scope</p>
                  <h2>Filters</h2>
                </div>
                <button
                  aria-controls="full-picture-filters-panel"
                  aria-expanded={filtersOpen}
                  className="full-picture-sidebar-toggle"
                  onClick={() => setFiltersOpen((current) => !current)}
                  type="button"
                >
                  {filtersOpen ? "Collapse" : "Open filters"}
                </button>
              </div>

              {filtersOpen ? (
                <div className="filter-panel full-picture-side-filter-panel" aria-label="Full Picture filters" id="full-picture-filters-panel">
                  <div className="panel-heading full-picture-filter-heading">
                    <p className="panel-meta">Multi-select filters with All as the default state.</p>
                    <button className="filter-reset" onClick={resetFilters} type="button">
                      Reset filters
                    </button>
                  </div>

                  <div className="filter-grid full-picture-filter-grid">
                    {FILTER_SECTION_ORDER.map((section) => {
                      const sectionFilters = FILTER_CONFIG.filter((config) => config.section === section);
                      const activeCount = getSectionActiveCount(filters, section);

                      return (
                        <section className="full-picture-filter-section" key={section}>
                          <div className="full-picture-filter-section-header">
                            <div>
                              <p className="full-picture-filter-section-kicker">{section}</p>
                              <h3>{section === "Scope" ? "Core scope" : section === "Workflow" ? "Workflow status" : "Vehicle context"}</h3>
                            </div>
                            <span className="full-picture-filter-section-count">
                              {activeCount === 0 ? "All" : `${activeCount} active`}
                            </span>
                          </div>

                          <div className="full-picture-filter-list">
                            {sectionFilters.map((config) => (
                              <div className="filter-group" key={config.field}>
                                <p className="filter-label" id={`${config.field}-filter-label`}>
                                  {config.label}
                                </p>
                                <FilterChipRow
                                  allLabel={config.allLabel}
                                  emptyLabel={config.emptyLabel}
                                  labelId={`${config.field}-filter-label`}
                                  onToggle={(value) => toggleField(config.field, value)}
                                  selectedValues={filters[config.field]}
                                  values={initialData.filters[config.field]}
                                />
                              </div>
                            ))}
                          </div>
                        </section>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : (
        <>
          <section aria-label="Full Picture hero" className="hero-panel full-picture-hero">
            <div className="hero-header-row">
              <div>
                <p className="eyebrow">Full Picture</p>
                <h1>Full Picture Management Workbench</h1>
              </div>
              <p className="dashboard-status">{state === "loading" ? "Warm-up" : "Shell only"}</p>
            </div>
          </section>

          <section className="dashboard-grid" aria-label="Full Picture shell state">
            <article className="workbench-panel shell-panel">
              <div className="panel-heading">
                <div>
                  <p className="panel-kicker">Startup</p>
                  <h2>{shellHeading}</h2>
                </div>
              </div>
              <p className="panel-meta shell-message">{shellMessage}</p>
              <div className="shell-pulse-grid" aria-hidden="true">
                <div className="shell-pulse shell-pulse-wide" />
                <div className="shell-pulse" />
                <div className="shell-pulse" />
                <div className="shell-pulse" />
              </div>
            </article>
          </section>
        </>
      )}
    </main>
  );
}