"use client";

import { useEffect, useState } from "react";

import { getDefaultQGateDashboardFilters } from "../../lib/default-filters";
import type { QGateDashboardFilters, QGateDashboardState, QGateDashboardViewModel } from "../../lib/types";
import { applyDashboardFilters, EXPLICIT_EMPTY_FILTER_VALUE } from "./dashboard-filtering";

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatPercent(value: number) {
  return `${value.toFixed(1)}%`;
}

function formatHours(value: number) {
  return value >= 24 ? `${(value / 24).toFixed(1)}d` : `${value.toFixed(1)}h`;
}

function isPhase02To03Transition(phaseTransition: string) {
  return /(^|\D)02[^>]*->\s*03(\D|$)/i.test(phaseTransition);
}

function normalizeGroupClassName(group: string) {
  const normalized = group.trim().toLowerCase();

  if (normalized === "q-gate") {
    return "qgate";
  }

  if (normalized === "integration") {
    return "integration";
  }

  if (normalized === "coc") {
    return "coc";
  }

  return "other";
}

type QGateDashboardPageProps =
  | {
      state: Exclude<QGateDashboardState, "ready">;
      initialData?: null;
      statusMessage?: string;
    }
  | {
      state: Extract<QGateDashboardState, "ready">;
      initialData: QGateDashboardViewModel;
      statusMessage?: string;
    };

export type { QGateDashboardPageProps };

function FilterChip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={active ? "filter-chip is-active" : "filter-chip"} onClick={onClick} type="button">
      {label}
    </button>
  );
}

function SearchableSingleSelect({
  allLabel,
  label,
  options,
  selectedValue,
  onChange,
}: {
  allLabel: string;
  label: string;
  options: string[];
  selectedValue: string;
  onChange: (value: string) => void;
}) {
  const [query, setQuery] = useState(selectedValue);

  useEffect(() => {
    setQuery(selectedValue);
  }, [selectedValue]);

  const normalizedQuery = query.trim().toLowerCase();
  const filteredOptions = normalizedQuery
    ? options.filter((value) => value.toLowerCase().includes(normalizedQuery)).slice(0, 25)
    : selectedValue
      ? options.filter((value) => value === selectedValue)
      : [];

  return (
    <label className="filter-field">
      <span className="filter-label">{label}</span>
      <input
        aria-label={label}
        autoComplete="off"
        onChange={(event) => {
          const nextValue = event.target.value;
          setQuery(nextValue);
          if (nextValue === "") {
            onChange("");
          }
        }}
        placeholder={allLabel}
        type="search"
        value={query}
      />
      <div className="chip-row">
        <FilterChip active={selectedValue === ""} label={allLabel} onClick={() => onChange("")} />
        {filteredOptions.map((value) => (
          <FilterChip
            active={selectedValue === value}
            key={value}
            label={value}
            onClick={() => {
              setQuery(value);
              onChange(value);
            }}
          />
        ))}
      </div>
    </label>
  );
}
function FilterChipRow({
  allLabel,
  helperText,
  noneLabel,
  values,
  selectedValues,
  onToggle,
}: {
  allLabel: string;
  helperText?: string;
  noneLabel?: string;
  values: string[];
  selectedValues: string[];
  onToggle: (value: string | null) => void;
}) {
  return (
    <div className="chip-stack">
      {helperText ? <p className="chip-helper">{helperText}</p> : null}
      <div className="chip-row">
        <FilterChip active={selectedValues.length === 0} label={allLabel} onClick={() => onToggle(null)} />
        {noneLabel ? (
          <FilterChip
            active={selectedValues.includes(EXPLICIT_EMPTY_FILTER_VALUE)}
            label={noneLabel}
            onClick={() => onToggle(EXPLICIT_EMPTY_FILTER_VALUE)}
          />
        ) : null}
        {values.map((value) => (
          <FilterChip active={selectedValues.includes(value)} key={value} label={value} onClick={() => onToggle(value)} />
        ))}
      </div>
    </div>
  );
}

function buildOverviewMetrics(filteredData: ReturnType<typeof applyDashboardFilters>) {
  const totalDefects = filteredData.metaRows.reduce((sum, row) => sum + row.defects, 0);
  const ticketsInView = new Set(filteredData.issueRows.map((row) => row.ticketId)).size;
  const efficiencyRows = filteredData.issueRows.filter((row) => isPhase02To03Transition(row.phaseTransition));
  const averageEfficiencyHours =
    efficiencyRows.length === 0 ? null : efficiencyRows.reduce((sum, row) => sum + row.durationHours, 0) / efficiencyRows.length;
  const averageEfficiencyDays = averageEfficiencyHours === null ? null : averageEfficiencyHours / 24;
  const efficiencyTone =
    averageEfficiencyDays === null ? "neutral" : averageEfficiencyDays > 3 ? "bad" : averageEfficiencyDays > 2 ? "warn" : "good";

  return [
    {
      label: "Teams",
      value: formatCompactNumber(filteredData.metaRows.length),
      note: "Teams in current scope",
    },
    {
      label: "Scoped defects",
      value: formatCompactNumber(totalDefects),
      note: "Defects matched by current filters",
    },
    {
      label: "Tickets in View",
      value: formatCompactNumber(ticketsInView),
      note: "Visible tickets in current result",
    },
    {
      label: "QGate Efficiency",
      value: averageEfficiencyHours === null ? "N/A" : formatHours(averageEfficiencyHours),
      note: "Phase 02 -> Phase 03 average time",
      tone: efficiencyTone,
    },
  ];
}

function buildTeamDistributionRows(metaRows: QGateDashboardViewModel["metaRows"]) {
  const totalDefects = metaRows.reduce((sum, row) => sum + row.defects, 0);

  return metaRows
    .map((row) => ({
      team: row.team,
      defects: row.defects,
      share: totalDefects === 0 ? 0 : (row.defects / totalDefects) * 100,
    }))
    .sort((left, right) => right.defects - left.defects || right.share - left.share);
}

function buildTransitionRows(issueRows: QGateDashboardViewModel["issueRows"]) {
  return Array.from(
    issueRows.reduce(
      (accumulator, row) => {
        const key = `${row.group}::${row.phaseTransition}`;
        const current = accumulator.get(key) ?? {
          group: row.group,
          phaseTransition: row.phaseTransition,
          count: 0,
          totalDurationHours: 0,
          teams: new Set<string>(),
        };

        current.count += 1;
        current.totalDurationHours += row.durationHours;
        current.teams.add(row.team);
        accumulator.set(key, current);
        return accumulator;
      },
      new Map<string, { group: string; phaseTransition: string; count: number; totalDurationHours: number; teams: Set<string> }>(),
    ),
  )
    .map(([, row]) => ({
      group: row.group,
      phaseTransition: row.phaseTransition,
      count: row.count,
      averageDurationHours: row.totalDurationHours / row.count,
      teamCount: row.teams.size,
    }))
    .sort((left, right) => right.count - left.count || right.averageDurationHours - left.averageDurationHours);
}

function buildTransitionGroups(transitionRows: ReturnType<typeof buildTransitionRows>) {
  const groupOrder = ["Q-Gate", "Integration", "CoC", "Other"];

  return groupOrder
    .map((group) => {
      const rows = transitionRows.filter((row) => row.group === group);

      return {
        group,
        rows,
      };
    })
    .filter((group) => group.rows.length > 0);
}

function buildSummaryRows(issueRows: QGateDashboardViewModel["issueRows"]) {
  return Array.from(
    issueRows.reduce(
      (accumulator, row) => {
        const key = `${row.team}::${row.group}`;
        const current = accumulator.get(key) ?? {
          key,
          team: row.team,
          group: row.group,
          count: 0,
          totalDurationHours: 0,
        };

        current.count += 1;
        current.totalDurationHours += row.durationHours;
        accumulator.set(key, current);
        return accumulator;
      },
      new Map<string, { key: string; team: string; group: string; count: number; totalDurationHours: number }>(),
    ),
  )
    .map(([, row]) => ({
      ...row,
      averageDurationHours: row.count === 0 ? 0 : row.totalDurationHours / row.count,
    }))
    .sort((left, right) => right.count - left.count || left.team.localeCompare(right.team));
}

function buildSummaryStacks(metaRows: QGateDashboardViewModel["metaRows"], summaryRows: ReturnType<typeof buildSummaryRows>) {
  const summaryByTeam = summaryRows.reduce(
    (accumulator, row) => {
      const current = accumulator.get(row.team) ?? [];
      current.push(row);
      accumulator.set(row.team, current);
      return accumulator;
    },
    new Map<string, Array<(typeof summaryRows)[number]>>(),
  );

  return metaRows
    .map((metaRow) => {
      const teamRows = summaryByTeam.get(metaRow.team) ?? [];
      const totalDurationHours = teamRows.reduce((sum, row) => sum + row.totalDurationHours, 0);
      const totalCount = teamRows.reduce((sum, row) => sum + row.count, 0);

      return {
        team: metaRow.team,
        totalCount,
        totalDurationHours,
        segments: teamRows.map((row) => ({
          group: row.group,
          count: row.count,
          totalDurationHours: row.totalDurationHours,
          averageDurationHours: row.averageDurationHours,
        })),
      };
    })
    .filter((row) => row.totalCount > 0);
}

function filterIssueRowsByMinSamples(issueRows: QGateDashboardViewModel["issueRows"], minTransitionCount: number) {
  if (minTransitionCount <= 0) {
    return issueRows;
  }

  const countsByTransition = issueRows.reduce((accumulator, row) => {
    const key = `${row.group}::${row.phaseTransition}`;
    accumulator.set(key, (accumulator.get(key) ?? 0) + 1);
    return accumulator;
  }, new Map<string, number>());

  return issueRows.filter((row) => {
    const key = `${row.group}::${row.phaseTransition}`;
    return (countsByTransition.get(key) ?? 0) >= minTransitionCount;
  });
}

function updateMultiSelect(currentValues: string[], value: string | null) {
  if (value === null) {
    return [];
  }

  if (value === EXPLICIT_EMPTY_FILTER_VALUE) {
    return [EXPLICIT_EMPTY_FILTER_VALUE];
  }

  if (currentValues.includes(EXPLICIT_EMPTY_FILTER_VALUE)) {
    return [value];
  }

  return currentValues.includes(value)
    ? currentValues.filter((current) => current !== value)
    : [...currentValues, value];
}

function updateSingleSelect(value: string) {
  return value ? [value] : [];
}

function buildIssueOnlyFilterSummary(filters: QGateDashboardFilters) {
  const parts: string[] = [];

  if (filters.groups.length > 0) {
    parts.push(`Group: ${filters.groups.join(", ")}`);
  }

  if (filters.changedBy.length === 1) {
    parts.push(`Changed by: ${filters.changedBy[0]}`);
  }

  if (filters.fif.length === 1) {
    parts.push(`FiF: ${filters.fif[0]}`);
  }

  if (filters.timespanMin > 0 || filters.timespanMax !== null) {
    const maxLabel = filters.timespanMax === null ? "open" : `${filters.timespanMax}d`;
    parts.push(`Timespan: ${filters.timespanMin}d-${maxLabel}`);
  }

  if (filters.minTransitionCount > 0) {
    parts.push(`Min samples: ${filters.minTransitionCount}`);
  }

  return parts;
}

export function QGateDashboardPage({ initialData, state, statusMessage }: QGateDashboardPageProps) {
  const [filters, setFilters] = useState<QGateDashboardFilters>(() => getDefaultQGateDashboardFilters());
  const isReady = state === "ready";
  const shellHeading = state === "loading" ? "Loading dashboard data..." : "Dashboard shell";
  const shellMessage =
    state === "loading"
      ? statusMessage ?? "QGate data is still warming up. The browser will swap in the charts as soon as the API responds."
      : statusMessage ?? "Dashboard data is temporarily unavailable. Check the API process and refresh when it is reachable.";

  const filteredData = isReady ? applyDashboardFilters(initialData, filters) : null;
  const summaryCards = filteredData ? buildOverviewMetrics(filteredData) : [];
  const distributionRows = filteredData ? buildTeamDistributionRows(filteredData.metaRows) : [];
  const filteredTransitionIssueRows = filteredData ? filterIssueRowsByMinSamples(filteredData.issueRows, filters.minTransitionCount) : [];
  const transitionRows = buildTransitionRows(filteredTransitionIssueRows);
  const transitionGroups = buildTransitionGroups(transitionRows);
  const summaryRows = buildSummaryRows(filteredTransitionIssueRows);
  const summaryStacks = filteredData && summaryRows.length > 0 ? buildSummaryStacks(filteredData.metaRows, summaryRows) : [];
  const globalMaxTransitionHours = Math.max(...transitionRows.map((row) => row.averageDurationHours), 1);
  const issueOnlyFilterSummary = buildIssueOnlyFilterSummary(filters);
  const hasScopedDefectsButNoTransitions = Boolean(filteredData && filteredData.metaRows.length > 0 && filteredTransitionIssueRows.length === 0);
  const transitionEmptyMessage = hasScopedDefectsButNoTransitions
    ? issueOnlyFilterSummary.length > 0
      ? `No transition samples matched the current issue filters (${issueOnlyFilterSummary.join("; ")}). The scoped defects still exist in the database, but B/C only render issue history rows.`
      : "No transition samples matched the current issue filters. The scoped defects still exist in the database, but B/C only render issue history rows."
    : "No transition samples are available for the current ready payload.";
  const summaryEmptyMessage = hasScopedDefectsButNoTransitions
    ? issueOnlyFilterSummary.length > 0
      ? `No summary rows matched the current issue filters (${issueOnlyFilterSummary.join("; ")}). Reset the issue filters to repopulate B/C.`
      : "No summary rows matched the current issue filters. Reset the issue filters to repopulate B/C."
    : "No summary rows are available for the current QGate scope.";
  const efficiencyEmptyMessage = hasScopedDefectsButNoTransitions
    ? "No team and group efficiency bars are visible because the current issue filters removed all transition rows."
    : "No team and group efficiency bars are available for the current QGate scope.";

  function toggleField(field: "years" | "teams" | "groups", value: string | null) {
    setFilters((current) => ({
      ...current,
      [field]: updateMultiSelect(current[field], value),
    }));
  }

  function setSelectField(field: "changedBy" | "fif", value: string) {
    setFilters((current) => ({
      ...current,
      [field]: updateSingleSelect(value),
    }));
  }

  function setNumericField(field: "timespanMin" | "timespanMax" | "minTransitionCount", value: string) {
    setFilters((current) => ({
      ...current,
      [field]:
        field === "timespanMax"
          ? value === ""
            ? null
            : Number(value)
          : value === ""
            ? 0
            : Number(value),
    }));
  }

  function resetFilters() {
    setFilters(getDefaultQGateDashboardFilters());
  }

  return (
    <main className="page-shell">
      <section className="hero-panel">
        <div className="hero-header-row">
          <div>
            <h1>QGate KPI Dashboard</h1>
          </div>
        </div>
        {summaryCards.length > 0 ? (
          <div className="hero-metrics" aria-label="QGate dashboard summary">
            {summaryCards.map((card) => (
              <article className={card.tone ? `metric-card metric-card-${card.tone}` : "metric-card"} key={card.label}>
                <p className="metric-label">{card.label}</p>
                <strong className="metric-value">{card.value}</strong>
                <p className="metric-note">{card.note}</p>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      {isReady ? (
        <>
          <section className="filter-panel" aria-label="Dashboard filters">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Scope</p>
                <h2>Filters</h2>
              </div>
              <button className="filter-reset" onClick={resetFilters} type="button">
                Reset filters
              </button>
            </div>

            <div className="filter-grid">
              <div className="filter-group">
                <p className="filter-label">Years</p>
                <FilterChipRow
                  allLabel="All years"
                  helperText="Click to toggle"
                  onToggle={(value) => toggleField("years", value)}
                  selectedValues={filters.years}
                  values={initialData.options.years}
                />
              </div>

              <div className="filter-group">
                <p className="filter-label">Teams</p>
                <FilterChipRow
                  allLabel="All teams"
                  helperText="Click to toggle"
                  noneLabel="No teams"
                  onToggle={(value) => toggleField("teams", value)}
                  selectedValues={filters.teams}
                  values={initialData.options.teams}
                />
              </div>

              <div className="filter-group">
                <p className="filter-label">Groups</p>
                <FilterChipRow
                  allLabel="All groups"
                  helperText="Click to toggle"
                  onToggle={(value) => toggleField("groups", value)}
                  selectedValues={filters.groups}
                  values={initialData.options.groups}
                />
              </div>

              <SearchableSingleSelect
                allLabel="All changed by"
                label="Changed by"
                onChange={(value) => setSelectField("changedBy", value)}
                options={initialData.options.changedBy}
                selectedValue={filters.changedBy[0] ?? ""}
              />

              <SearchableSingleSelect
                allLabel="All FiF"
                label="FiF"
                onChange={(value) => setSelectField("fif", value)}
                options={initialData.options.fif}
                selectedValue={filters.fif[0] ?? ""}
              />

              <label className="filter-field">
                <span className="filter-label">Timespan min</span>
                <input
                  aria-label="Timespan min"
                  min="0"
                  onChange={(event) => setNumericField("timespanMin", event.target.value)}
                  type="number"
                  value={filters.timespanMin}
                />
              </label>

              <label className="filter-field">
                <span className="filter-label">Timespan max</span>
                <input
                  aria-label="Timespan max"
                  min="0"
                  onChange={(event) => setNumericField("timespanMax", event.target.value)}
                  placeholder="Open-ended"
                  type="number"
                  value={filters.timespanMax ?? ""}
                />
              </label>

              <label className="filter-field">
                <span className="filter-label">Min samples</span>
                <input
                  aria-label="Min samples"
                  min="0"
                  onChange={(event) => setNumericField("minTransitionCount", event.target.value)}
                  type="number"
                  value={filters.minTransitionCount}
                />
              </label>
            </div>

          </section>

          <section className="dashboard-grid" aria-label="QGate workbench">
            <article className="workbench-panel workbench-panel-wide">
              <div className="panel-heading">
                <div>
                  <h2>A. Team Distribution</h2>
                </div>
                <p className="panel-meta">Scoped defects by team inside the currently selected scope.</p>
              </div>
              <div className="chart-box">
                <div className="chart-title">
                  <strong>Team Distribution</strong>
                  <span>Scoped defect share for each team in view</span>
                </div>
                {distributionRows.length > 0 ? (
                  <div className="stack-wrap" aria-label="Team distribution">
                    {distributionRows.map((row) => {
                      return (
                        <div className="stack-row" key={row.team}>
                          <span className="label">{row.team}</span>
                          <div className="bar-cell">
                            <span>{formatPercent(row.share)}</span>
                            <div className="bar-bg">
                              <div className="bar-fill" style={{ width: `${row.share}%` }} />
                            </div>
                            <span>{row.defects.toLocaleString()}</span>
                          </div>
                          <span className="tiny">scoped defects</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="panel-empty">No team distribution rows matched the current QGate scope.</p>
                )}
              </div>
            </article>

            <article className="workbench-panel">
              <div className="panel-heading">
                <div>
                  <h2>B. Transition Analysis</h2>
                </div>
                <p className="panel-meta">Average days by transition inside the filtered scope.</p>
              </div>
              <div className="chart-box">
                <div className="chart-title">
                  <strong>Grouped Stacked View</strong>
                  <span>Average days by transition inside Q-Gate / Integration / CoC</span>
                </div>
                {transitionGroups.length > 0 ? (
                  <div className="transition-groups" aria-label="Transition analysis">
                    {transitionGroups.map((group) => {
                      return (
                        <section className="transition-group" key={group.group}>
                          <div className="transition-group-header">
                            <strong>{group.group}</strong>
                            <span>{group.rows.length} transitions</span>
                          </div>
                          <div className="stack-wrap">
                            {group.rows.map((row) => {
                              const width = globalMaxTransitionHours === 0 ? 0 : (row.averageDurationHours / globalMaxTransitionHours) * 100;

                              return (
                                <div className="stack-row transition-row" key={row.phaseTransition}>
                                  <span className="label">{row.phaseTransition.replace(`${group.group} `, "")}</span>
                                  <div className="bar-cell transition-bar-cell">
                                    <span>{formatHours(row.averageDurationHours)} avg</span>
                                    <div className="bar-bg">
                                      <div className="bar-fill" style={{ width: `${Math.max(width, 2)}%` }} />
                                    </div>
                                    <span>{row.count.toLocaleString()} samples</span>
                                  </div>
                                  <span className="tiny">{row.teamCount} teams</span>
                                </div>
                              );
                            })}
                          </div>
                        </section>
                      );
                    })}
                  </div>
                ) : (
                  <p className="panel-empty">{transitionEmptyMessage}</p>
                )}
              </div>
            </article>

            <article className="workbench-panel">
              <div className="panel-heading">
                <div>
                  <h2>C. Phase Efficiency Summary</h2>
                </div>
                <p className="panel-meta">Grouped by team and phase bucket from the filtered issue set.</p>
              </div>
              <div className="legend">
                <span><span className="dot qgate"></span>Q-Gate</span>
                <span><span className="dot integration"></span>Integration</span>
                <span><span className="dot coc"></span>CoC</span>
                <span><span className="dot other"></span>Other</span>
              </div>
              <div className="split-panel">
                <div className="chart-box">
                  <div className="chart-title">
                    <strong>Team × Group Efficiency</strong>
                    <span>Relative transition volume by team and group</span>
                  </div>
                  {summaryRows.length > 0 && summaryStacks.length > 0 ? (
                    <div className="stack-wrap">
                      {summaryStacks.map((row) => (
                        <div className="stack-row" key={row.team}>
                          <span className="label">{row.team}</span>
                          <div className="stack">
                            {row.segments.map((segment) => (
                              <div
                                className={`seg ${normalizeGroupClassName(segment.group)}`}
                                key={`${row.team}-${segment.group}`}
                                style={{ width: `${row.totalDurationHours === 0 ? 0 : (segment.totalDurationHours / row.totalDurationHours) * 100}%` }}
                                title={`${segment.group}: ${segment.count} transitions, ${formatHours(segment.averageDurationHours)} avg`}
                              />
                            ))}
                          </div>
                          <span className="tiny">{row.totalCount} transitions</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="panel-empty">{efficiencyEmptyMessage}</p>
                  )}
                </div>

                <div className="chart-box">
                  <div className="chart-title">
                    <strong>Summary Table</strong>
                    <span>Ticket count and grouped average duration by team and phase bucket</span>
                  </div>
                  <div className="summary-table" role="table" aria-label="Phase efficiency summary">
                    <div className="summary-table-row summary-table-head" role="row">
                      <span role="columnheader">Team</span>
                      <span role="columnheader">Group</span>
                      <span role="columnheader">Transitions</span>
                      <span role="columnheader">Avg duration</span>
                    </div>
                    {summaryRows.length > 0 ? (
                      summaryRows.map((row) => (
                        <div className="summary-table-row" key={row.key} role="row">
                          <span role="cell">{row.team}</span>
                          <span role="cell">{row.group}</span>
                          <span role="cell">{row.count}</span>
                          <span role="cell">{formatHours(row.averageDurationHours)}</span>
                        </div>
                      ))
                    ) : (
                      <div className="summary-table-row" role="row">
                        <span className="coverage-empty-cell" role="cell">
                          {summaryEmptyMessage}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </article>
          </section>

        </>
      ) : (
        <section className="dashboard-grid" aria-label="QGate shell state">
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
      )}
    </main>
  );
}