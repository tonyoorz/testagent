import type {
  FullPictureDashboardPayload,
  FullPictureDashboardViewModel,
  FullPictureFilterValues,
  FullPictureFilterValuesPayload,
  FullPictureGeneratedFrom,
  FullPictureGeneratedFromPayload,
  FullPictureOutcomeKey,
  FullPictureOutcomePayloadKey,
  FullPictureOutcomeSummaryRow,
  FullPictureOutcomeSummaryRowPayload,
  FullPictureTeamOutcomeRow,
  FullPictureTeamOutcomeRowPayload,
  FullPictureTicketRow,
  FullPictureTicketRowPayload,
} from "./full-picture-types";

const OUTCOME_KEY_MAP: Record<FullPictureOutcomePayloadKey, FullPictureOutcomeKey> = {
  resolved_forward: "resolvedForward",
  rejected_directly: "rejectedDirectly",
};

const SUPPORTED_OUTCOME_KEYS = Object.keys(OUTCOME_KEY_MAP) as FullPictureOutcomePayloadKey[];

export class FullPicturePayloadValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FullPicturePayloadValidationError";
  }
}

function assertRecord(value: unknown, label: string): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new FullPicturePayloadValidationError(`${label} must be an object.`);
  }
}

function assertObjectArray(value: unknown, label: string): asserts value is Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    throw new FullPicturePayloadValidationError(`${label} must be an array.`);
  }

  for (const item of value) {
    assertRecord(item, label);
  }
}

function assertString(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string") {
    throw new FullPicturePayloadValidationError(`${label} must be a string.`);
  }
}

function assertStringArray(value: unknown, label: string): asserts value is string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new FullPicturePayloadValidationError(`${label} must be a string array.`);
  }
}

function assertNumber(value: unknown, label: string): asserts value is number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new FullPicturePayloadValidationError(`${label} must be a finite number.`);
  }
}

function assertBoolean(value: unknown, label: string): asserts value is boolean {
  if (typeof value !== "boolean") {
    throw new FullPicturePayloadValidationError(`${label} must be a boolean.`);
  }
}

function toPercent(numerator: number, denominator: number) {
  if (denominator <= 0) {
    return 0;
  }

  return Math.round((numerator / denominator) * 10000) / 100;
}

function assertMatchesDerivedMetric(label: string, actual: number, expected: number) {
  if (actual !== expected) {
    throw new FullPicturePayloadValidationError(`${label} must match the value derived from ticket_rows.`);
  }
}

function validateFilterValuesPayload(value: unknown, label: string): asserts value is FullPictureFilterValuesPayload {
  assertRecord(value, label);

  assertStringArray(Reflect.get(value, "years"), `${label}.years`);
  assertStringArray(Reflect.get(value, "projects"), `${label}.projects`);
  assertStringArray(Reflect.get(value, "assigned_ecus"), `${label}.assigned_ecus`);
  assertStringArray(Reflect.get(value, "problem_finder_teams"), `${label}.problem_finder_teams`);
  assertStringArray(Reflect.get(value, "aidas"), `${label}.aidas`);
  assertStringArray(Reflect.get(value, "phases"), `${label}.phases`);
  assertStringArray(Reflect.get(value, "solution_clusters"), `${label}.solution_clusters`);
  assertStringArray(Reflect.get(value, "pus"), `${label}.pus`);
  assertStringArray(Reflect.get(value, "markets"), `${label}.markets`);
  assertStringArray(Reflect.get(value, "lead_models"), `${label}.lead_models`);
  assertStringArray(Reflect.get(value, "groups"), `${label}.groups`);
}

function validateGeneratedFromPayload(value: unknown): asserts value is FullPictureGeneratedFromPayload {
  validateFilterValuesPayload(value, "generated_from");

  assertString(Reflect.get(value, "defect_db_path"), "generated_from.defect_db_path");
  assertString(Reflect.get(value, "history_db_path"), "generated_from.history_db_path");
}

function validateOverviewPayload(value: unknown) {
  assertRecord(value, "overview");

  assertNumber(Reflect.get(value, "ticket_count"), "overview.ticket_count");
  assertNumber(Reflect.get(value, "resolved_forward_count"), "overview.resolved_forward_count");
  assertNumber(Reflect.get(value, "rejected_directly_count"), "overview.rejected_directly_count");
  assertNumber(Reflect.get(value, "resolved_forward_percent"), "overview.resolved_forward_percent");
  assertNumber(Reflect.get(value, "rejected_directly_percent"), "overview.rejected_directly_percent");
}

function validateOutcomeSummaryRow(value: unknown, index: number): asserts value is FullPictureOutcomeSummaryRowPayload {
  assertRecord(value, `outcome_summary[${index}]`);

  const key = Reflect.get(value, "key");
  assertString(key, `outcome_summary[${index}].key`);

  if (!(key in OUTCOME_KEY_MAP)) {
    throw new FullPicturePayloadValidationError(`outcome_summary[${index}].key must be a supported outcome key.`);
  }

  assertString(Reflect.get(value, "label"), `outcome_summary[${index}].label`);
  assertNumber(Reflect.get(value, "count"), `outcome_summary[${index}].count`);
  assertNumber(Reflect.get(value, "percent"), `outcome_summary[${index}].percent`);
  assertNumber(Reflect.get(value, "denominator"), `outcome_summary[${index}].denominator`);
}

function validateTeamOutcomeRow(value: unknown, index: number): asserts value is FullPictureTeamOutcomeRowPayload {
  assertRecord(value, `team_outcome_rows[${index}]`);

  assertString(Reflect.get(value, "problem_finder_team"), `team_outcome_rows[${index}].problem_finder_team`);
  assertNumber(Reflect.get(value, "total_tickets"), `team_outcome_rows[${index}].total_tickets`);
  assertNumber(Reflect.get(value, "resolved_forward_count"), `team_outcome_rows[${index}].resolved_forward_count`);
  assertNumber(Reflect.get(value, "rejected_directly_count"), `team_outcome_rows[${index}].rejected_directly_count`);
  assertNumber(
    Reflect.get(value, "resolved_forward_team_percent"),
    `team_outcome_rows[${index}].resolved_forward_team_percent`,
  );
  assertNumber(
    Reflect.get(value, "rejected_directly_team_percent"),
    `team_outcome_rows[${index}].rejected_directly_team_percent`,
  );
  assertNumber(Reflect.get(value, "team_denominator"), `team_outcome_rows[${index}].team_denominator`);
}

function validateTicketRow(value: unknown, index: number): asserts value is FullPictureTicketRowPayload {
  assertRecord(value, `ticket_rows[${index}]`);

  assertString(Reflect.get(value, "ticket_id"), `ticket_rows[${index}].ticket_id`);
  assertString(Reflect.get(value, "ticket_name"), `ticket_rows[${index}].ticket_name`);
  assertString(Reflect.get(value, "status"), `ticket_rows[${index}].status`);
  assertString(Reflect.get(value, "problem_finder_team"), `ticket_rows[${index}].problem_finder_team`);
  assertString(Reflect.get(value, "group"), `ticket_rows[${index}].group`);
  assertString(Reflect.get(value, "phase"), `ticket_rows[${index}].phase`);
  assertBoolean(Reflect.get(value, "is_resolved_forward"), `ticket_rows[${index}].is_resolved_forward`);
  assertBoolean(Reflect.get(value, "is_rejected_directly"), `ticket_rows[${index}].is_rejected_directly`);
  assertString(Reflect.get(value, "year"), `ticket_rows[${index}].year`);
  assertString(Reflect.get(value, "project"), `ticket_rows[${index}].project`);
  assertString(Reflect.get(value, "assigned_ecu"), `ticket_rows[${index}].assigned_ecu`);
  assertString(Reflect.get(value, "aida"), `ticket_rows[${index}].aida`);
  assertString(Reflect.get(value, "solution_cluster"), `ticket_rows[${index}].solution_cluster`);
  assertString(Reflect.get(value, "pu"), `ticket_rows[${index}].pu`);
  assertString(Reflect.get(value, "market"), `ticket_rows[${index}].market`);
  assertString(Reflect.get(value, "lead_model"), `ticket_rows[${index}].lead_model`);
}

function buildDerivedOverview(ticketRows: FullPictureTicketRowPayload[]) {
  const ticketCount = ticketRows.length;
  const resolvedForwardCount = ticketRows.filter((row) => row.is_resolved_forward).length;
  const rejectedDirectlyCount = ticketRows.filter((row) => row.is_rejected_directly).length;

  return {
    ticketCount,
    resolvedForwardCount,
    rejectedDirectlyCount,
    resolvedForwardPercent: toPercent(resolvedForwardCount, ticketCount),
    rejectedDirectlyPercent: toPercent(rejectedDirectlyCount, ticketCount),
  };
}

function countOutcome(ticketRows: FullPictureTicketRowPayload[], outcomeKey: FullPictureOutcomePayloadKey) {
  if (outcomeKey === "resolved_forward") {
    return ticketRows.filter((row) => row.is_resolved_forward).length;
  }

  return ticketRows.filter((row) => row.is_rejected_directly).length;
}

function validateOverviewConsistency(payload: FullPictureDashboardPayload) {
  const derivedOverview = buildDerivedOverview(payload.ticket_rows);

  assertMatchesDerivedMetric("overview.ticket_count", payload.overview.ticket_count, derivedOverview.ticketCount);
  assertMatchesDerivedMetric(
    "overview.resolved_forward_count",
    payload.overview.resolved_forward_count,
    derivedOverview.resolvedForwardCount,
  );
  assertMatchesDerivedMetric(
    "overview.rejected_directly_count",
    payload.overview.rejected_directly_count,
    derivedOverview.rejectedDirectlyCount,
  );
  assertMatchesDerivedMetric(
    "overview.resolved_forward_percent",
    payload.overview.resolved_forward_percent,
    derivedOverview.resolvedForwardPercent,
  );
  assertMatchesDerivedMetric(
    "overview.rejected_directly_percent",
    payload.overview.rejected_directly_percent,
    derivedOverview.rejectedDirectlyPercent,
  );
}

function validateOutcomeSummaryConsistency(payload: FullPictureDashboardPayload) {
  if (payload.outcome_summary.length !== SUPPORTED_OUTCOME_KEYS.length) {
    throw new FullPicturePayloadValidationError("outcome_summary must contain exactly the supported outcomes.");
  }

  const rowsByKey = new Map<FullPictureOutcomePayloadKey, FullPictureOutcomeSummaryRowPayload>();

  payload.outcome_summary.forEach((row, index) => {
    if (rowsByKey.has(row.key)) {
      throw new FullPicturePayloadValidationError(`outcome_summary[${index}].key must not be duplicated.`);
    }

    rowsByKey.set(row.key, row);
  });

  const denominator = payload.ticket_rows.length;

  for (const outcomeKey of SUPPORTED_OUTCOME_KEYS) {
    const row = rowsByKey.get(outcomeKey);

    if (!row) {
      throw new FullPicturePayloadValidationError(`outcome_summary must include ${outcomeKey}.`);
    }

    const expectedCount = countOutcome(payload.ticket_rows, outcomeKey);
    assertMatchesDerivedMetric(`outcome_summary.${outcomeKey}.count`, row.count, expectedCount);
    assertMatchesDerivedMetric(`outcome_summary.${outcomeKey}.percent`, row.percent, toPercent(expectedCount, denominator));
    assertMatchesDerivedMetric(`outcome_summary.${outcomeKey}.denominator`, row.denominator, denominator);
  }
}

function buildDerivedTeamOutcomeRows(ticketRows: FullPictureTicketRowPayload[]) {
  const rowsByTeam = new Map<string, FullPictureTeamOutcomeRowPayload>();

  ticketRows.forEach((row) => {
    const current = rowsByTeam.get(row.problem_finder_team) ?? {
      problem_finder_team: row.problem_finder_team,
      total_tickets: 0,
      resolved_forward_count: 0,
      rejected_directly_count: 0,
      resolved_forward_team_percent: 0,
      rejected_directly_team_percent: 0,
      team_denominator: 0,
    };

    current.total_tickets += 1;
    if (row.is_resolved_forward) {
      current.resolved_forward_count += 1;
    }
    if (row.is_rejected_directly) {
      current.rejected_directly_count += 1;
    }

    rowsByTeam.set(row.problem_finder_team, current);
  });

  rowsByTeam.forEach((row) => {
    row.resolved_forward_team_percent = toPercent(row.resolved_forward_count, row.total_tickets);
    row.rejected_directly_team_percent = toPercent(row.rejected_directly_count, row.total_tickets);
    row.team_denominator = row.total_tickets;
  });

  return rowsByTeam;
}

function validateTeamOutcomeRowsConsistency(payload: FullPictureDashboardPayload) {
  const derivedRowsByTeam = buildDerivedTeamOutcomeRows(payload.ticket_rows);

  if (payload.team_outcome_rows.length !== derivedRowsByTeam.size) {
    throw new FullPicturePayloadValidationError("team_outcome_rows must match the teams derived from ticket_rows.");
  }

  const seenTeams = new Set<string>();

  payload.team_outcome_rows.forEach((row, index) => {
    if (seenTeams.has(row.problem_finder_team)) {
      throw new FullPicturePayloadValidationError(`team_outcome_rows[${index}].problem_finder_team must not be duplicated.`);
    }

    seenTeams.add(row.problem_finder_team);

    const derivedRow = derivedRowsByTeam.get(row.problem_finder_team);
    if (!derivedRow) {
      throw new FullPicturePayloadValidationError(
        `team_outcome_rows[${index}].problem_finder_team must exist in ticket_rows.`,
      );
    }

    assertMatchesDerivedMetric(`team_outcome_rows[${index}].total_tickets`, row.total_tickets, derivedRow.total_tickets);
    assertMatchesDerivedMetric(
      `team_outcome_rows[${index}].resolved_forward_count`,
      row.resolved_forward_count,
      derivedRow.resolved_forward_count,
    );
    assertMatchesDerivedMetric(
      `team_outcome_rows[${index}].rejected_directly_count`,
      row.rejected_directly_count,
      derivedRow.rejected_directly_count,
    );
    assertMatchesDerivedMetric(
      `team_outcome_rows[${index}].resolved_forward_team_percent`,
      row.resolved_forward_team_percent,
      derivedRow.resolved_forward_team_percent,
    );
    assertMatchesDerivedMetric(
      `team_outcome_rows[${index}].rejected_directly_team_percent`,
      row.rejected_directly_team_percent,
      derivedRow.rejected_directly_team_percent,
    );
    assertMatchesDerivedMetric(`team_outcome_rows[${index}].team_denominator`, row.team_denominator, derivedRow.team_denominator);
  });
}

function validateDerivedMetricConsistency(payload: FullPictureDashboardPayload) {
  validateOverviewConsistency(payload);
  validateOutcomeSummaryConsistency(payload);
  validateTeamOutcomeRowsConsistency(payload);
}

function adaptFilterValues(value: FullPictureFilterValuesPayload): FullPictureFilterValues {
  return {
    years: [...value.years],
    projects: [...value.projects],
    assignedEcus: [...value.assigned_ecus],
    problemFinderTeams: [...value.problem_finder_teams],
    aidas: [...value.aidas],
    phases: [...value.phases],
    solutionClusters: [...value.solution_clusters],
    pus: [...value.pus],
    markets: [...value.markets],
    leadModels: [...value.lead_models],
    groups: [...value.groups],
  };
}

function adaptGeneratedFrom(value: FullPictureGeneratedFromPayload): FullPictureGeneratedFrom {
  return {
    defectDbPath: value.defect_db_path,
    historyDbPath: value.history_db_path,
    ...adaptFilterValues(value),
  };
}

function adaptOutcomeSummaryRow(row: FullPictureOutcomeSummaryRowPayload): FullPictureOutcomeSummaryRow {
  return {
    key: OUTCOME_KEY_MAP[row.key],
    label: row.label,
    count: row.count,
    percent: row.percent,
    denominator: row.denominator,
  };
}

function adaptTeamOutcomeRow(row: FullPictureTeamOutcomeRowPayload): FullPictureTeamOutcomeRow {
  return {
    problemFinderTeam: row.problem_finder_team,
    totalTickets: row.total_tickets,
    resolvedForwardCount: row.resolved_forward_count,
    rejectedDirectlyCount: row.rejected_directly_count,
    resolvedForwardTeamPercent: row.resolved_forward_team_percent,
    rejectedDirectlyTeamPercent: row.rejected_directly_team_percent,
    teamDenominator: row.team_denominator,
  };
}

function adaptTicketRow(row: FullPictureTicketRowPayload): FullPictureTicketRow {
  return {
    ticketId: row.ticket_id,
    ticketName: row.ticket_name,
    status: row.status,
    problemFinderTeam: row.problem_finder_team,
    group: row.group,
    phase: row.phase,
    isResolvedForward: row.is_resolved_forward,
    isRejectedDirectly: row.is_rejected_directly,
    year: row.year,
    project: row.project,
    assignedEcu: row.assigned_ecu,
    aida: row.aida,
    solutionCluster: row.solution_cluster,
    pu: row.pu,
    market: row.market,
    leadModel: row.lead_model,
  };
}

export function validateFullPictureDashboardPayload(value: unknown): FullPictureDashboardPayload {
  assertRecord(value, "Full Picture dashboard payload");

  validateGeneratedFromPayload(Reflect.get(value, "generated_from"));
  validateFilterValuesPayload(Reflect.get(value, "filters"), "filters");
  validateOverviewPayload(Reflect.get(value, "overview"));

  const outcomeSummary = Reflect.get(value, "outcome_summary");
  const teamOutcomeRows = Reflect.get(value, "team_outcome_rows");
  const ticketRows = Reflect.get(value, "ticket_rows");

  assertObjectArray(outcomeSummary, "outcome_summary");
  assertObjectArray(teamOutcomeRows, "team_outcome_rows");
  assertObjectArray(ticketRows, "ticket_rows");

  outcomeSummary.forEach((row, index) => validateOutcomeSummaryRow(row, index));
  teamOutcomeRows.forEach((row, index) => validateTeamOutcomeRow(row, index));
  ticketRows.forEach((row, index) => validateTicketRow(row, index));

  validateDerivedMetricConsistency(value as FullPictureDashboardPayload);

  return value as FullPictureDashboardPayload;
}

export function adaptFullPictureDashboardPayload(rawPayload: FullPictureDashboardPayload | unknown): FullPictureDashboardViewModel {
  const payload = validateFullPictureDashboardPayload(rawPayload);

  return {
    generatedFrom: adaptGeneratedFrom(payload.generated_from),
    filters: adaptFilterValues(payload.filters),
    overview: {
      ticketCount: payload.overview.ticket_count,
      resolvedForwardCount: payload.overview.resolved_forward_count,
      rejectedDirectlyCount: payload.overview.rejected_directly_count,
      resolvedForwardPercent: payload.overview.resolved_forward_percent,
      rejectedDirectlyPercent: payload.overview.rejected_directly_percent,
    },
    outcomeSummary: payload.outcome_summary.map(adaptOutcomeSummaryRow),
    teamOutcomeRows: payload.team_outcome_rows.map(adaptTeamOutcomeRow),
    ticketRows: payload.ticket_rows.map(adaptTicketRow),
  };
}
