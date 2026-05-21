import type {
  QGateCoverageRow,
  QGateDashboardPayload,
  QGateDashboardViewModel,
  QGateDataset,
  QGateDatasetValue,
  QGateIssueRow,
  QGateMetaRow,
  QGateTicketRow,
} from "./types";

const META_COLUMNS = ["Team", "Defects", "History_OK", "History_Missing_or_Error"];
const COVERAGE_COLUMNS = ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"];
const TICKET_COLUMNS = ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"];
const ISSUE_COLUMNS = [
  "Year",
  "Team",
  "Ticket_ID",
  "Phase_Transition",
  "Group",
  "Duration_Hours",
  "Changed_By",
  "FiF",
  "Ticket_Timespan_Days",
];

type DatasetColumnKind = "string" | "number" | "nullable-number";

const META_COLUMN_KINDS: Record<string, DatasetColumnKind> = {
  Team: "string",
  Defects: "number",
  History_OK: "number",
  History_Missing_or_Error: "number",
};

const COVERAGE_COLUMN_KINDS: Record<string, DatasetColumnKind> = {
  Team: "string",
  Year: "string",
  Defects: "number",
  History_OK: "number",
  History_Missing_or_Error: "number",
};

const TICKET_COLUMN_KINDS: Record<string, DatasetColumnKind> = {
  Ticket_ID: "string",
  Ticket_URL: "string",
  Ticket_Name: "string",
  Tester: "string",
};

const ISSUE_COLUMN_KINDS: Record<string, DatasetColumnKind> = {
  Year: "string",
  Team: "string",
  Ticket_ID: "string",
  Phase_Transition: "string",
  Group: "string",
  Duration_Hours: "number",
  Changed_By: "string",
  FiF: "string",
  Ticket_Timespan_Days: "nullable-number",
};

export class QGatePayloadValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QGatePayloadValidationError";
  }
}

function assertString(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string") {
    throw new QGatePayloadValidationError(`${label} must be a string.`);
  }
}

function assertNumber(value: unknown, label: string): asserts value is number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new QGatePayloadValidationError(`${label} must be a finite number.`);
  }
}

function assertRecord(value: unknown, label: string): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new QGatePayloadValidationError(`${label} must be an object.`);
  }
}

function assertStringArray(value: unknown, label: string): asserts value is string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new QGatePayloadValidationError(`${label} must be a string array.`);
  }
}

function assertDataset(
  value: unknown,
  label: string,
  requiredColumns: string[],
  columnKinds?: Record<string, DatasetColumnKind>,
): asserts value is QGateDataset {
  assertRecord(value, label);

  const columns = Reflect.get(value, "columns");
  const rows = Reflect.get(value, "rows");

  if (!Array.isArray(columns) || columns.some((column) => typeof column !== "string")) {
    throw new QGatePayloadValidationError(`${label}.columns must be a string array.`);
  }

  if (!Array.isArray(rows) || rows.some((row) => !Array.isArray(row))) {
    throw new QGatePayloadValidationError(`${label}.rows must be an array of row arrays.`);
  }

  for (const requiredColumn of requiredColumns) {
    if (!columns.includes(requiredColumn)) {
      throw new QGatePayloadValidationError(`${label} is missing required column ${requiredColumn}.`);
    }
  }

  if (!columnKinds) {
    return;
  }

  for (const row of rows) {
    for (const [column, kind] of Object.entries(columnKinds)) {
      const columnIndex = columns.indexOf(column);
      const cellValue = row[columnIndex] ?? null;

      if (kind === "string") {
        assertString(cellValue, `${label}.${column}`);
        continue;
      }

      if (kind === "number") {
        assertNumber(cellValue, `${label}.${column}`);
        continue;
      }

      if (cellValue !== null) {
        assertNumber(cellValue, `${label}.${column}`);
      }
    }
  }
}

function toStringValue(value: QGateDatasetValue, label: string) {
  if (typeof value !== "string") {
    throw new QGatePayloadValidationError(`${label} must be a string.`);
  }

  return value;
}

function toNumberValue(value: QGateDatasetValue, label: string) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new QGatePayloadValidationError(`${label} must be numeric.`);
  }

  return value;
}

function toNullableNumberValue(value: QGateDatasetValue, label: string) {
  if (value === null) {
    return null;
  }

  return toNumberValue(value, label);
}

function getDatasetCell(dataset: QGateDataset, row: QGateDatasetValue[], column: string) {
  const columnIndex = dataset.columns.indexOf(column);
  if (columnIndex < 0) {
    throw new QGatePayloadValidationError(`Dataset is missing required column ${column}.`);
  }

  if (columnIndex >= row.length) {
    throw new QGatePayloadValidationError(`Dataset row is missing a value for column ${column}.`);
  }

  return row[columnIndex] ?? null;
}

function mapDatasetRows<RowType>(
  dataset: QGateDataset,
  mapper: (row: QGateDatasetValue[]) => RowType,
) {
  return dataset.rows.map((row) => mapper(row));
}

function adaptMetaRows(dataset: QGateDataset): QGateMetaRow[] {
  return mapDatasetRows(dataset, (row) => ({
    team: toStringValue(getDatasetCell(dataset, row, "Team"), "meta.Team"),
    defects: toNumberValue(getDatasetCell(dataset, row, "Defects"), "meta.Defects"),
    historyOk: toNumberValue(getDatasetCell(dataset, row, "History_OK"), "meta.History_OK"),
    historyMissingOrError: toNumberValue(
      getDatasetCell(dataset, row, "History_Missing_or_Error"),
      "meta.History_Missing_or_Error",
    ),
  }));
}

function adaptCoverageRows(dataset: QGateDataset): QGateCoverageRow[] {
  return mapDatasetRows(dataset, (row) => ({
    team: toStringValue(getDatasetCell(dataset, row, "Team"), "coverage.Team"),
    year: toStringValue(getDatasetCell(dataset, row, "Year"), "coverage.Year"),
    defects: toNumberValue(getDatasetCell(dataset, row, "Defects"), "coverage.Defects"),
    historyOk: toNumberValue(getDatasetCell(dataset, row, "History_OK"), "coverage.History_OK"),
    historyMissingOrError: toNumberValue(
      getDatasetCell(dataset, row, "History_Missing_or_Error"),
      "coverage.History_Missing_or_Error",
    ),
  }));
}

function adaptTicketRows(dataset: QGateDataset): QGateTicketRow[] {
  return mapDatasetRows(dataset, (row) => ({
    ticketId: toStringValue(getDatasetCell(dataset, row, "Ticket_ID"), "tickets.Ticket_ID"),
    ticketUrl: toStringValue(getDatasetCell(dataset, row, "Ticket_URL"), "tickets.Ticket_URL"),
    ticketName: toStringValue(getDatasetCell(dataset, row, "Ticket_Name"), "tickets.Ticket_Name"),
    tester: toStringValue(getDatasetCell(dataset, row, "Tester"), "tickets.Tester"),
  }));
}

function adaptIssueRows(dataset: QGateDataset): QGateIssueRow[] {
  return mapDatasetRows(dataset, (row) => ({
    year: toStringValue(getDatasetCell(dataset, row, "Year"), "issues.Year"),
    team: toStringValue(getDatasetCell(dataset, row, "Team"), "issues.Team"),
    ticketId: toStringValue(getDatasetCell(dataset, row, "Ticket_ID"), "issues.Ticket_ID"),
    phaseTransition: toStringValue(getDatasetCell(dataset, row, "Phase_Transition"), "issues.Phase_Transition"),
    group: toStringValue(getDatasetCell(dataset, row, "Group"), "issues.Group"),
    durationHours: toNumberValue(getDatasetCell(dataset, row, "Duration_Hours"), "issues.Duration_Hours"),
    changedBy: toStringValue(getDatasetCell(dataset, row, "Changed_By"), "issues.Changed_By"),
    fif: toStringValue(getDatasetCell(dataset, row, "FiF"), "issues.FiF"),
    ticketTimespanDays: toNullableNumberValue(
      getDatasetCell(dataset, row, "Ticket_Timespan_Days"),
      "issues.Ticket_Timespan_Days",
    ),
  }));
}

export function validateQGateDashboardPayload(value: unknown): QGateDashboardPayload {
  assertRecord(value, "QGate dashboard payload");

  const generatedFrom = Reflect.get(value, "generated_from");
  const overview = Reflect.get(value, "overview");
  const options = Reflect.get(value, "options");

  assertRecord(generatedFrom, "generated_from");
  assertRecord(overview, "overview");
  assertRecord(options, "options");

  assertString(Reflect.get(generatedFrom, "defect_dir"), "generated_from.defect_dir");
  assertString(Reflect.get(generatedFrom, "history_dir"), "generated_from.history_dir");
  assertStringArray(Reflect.get(generatedFrom, "teams"), "generated_from.teams");
  assertNumber(Reflect.get(generatedFrom, "min_transition_count"), "generated_from.min_transition_count");

  assertNumber(Reflect.get(overview, "team_count"), "overview.team_count");
  assertNumber(Reflect.get(overview, "total_defects"), "overview.total_defects");
  assertNumber(Reflect.get(overview, "history_ok"), "overview.history_ok");
  assertNumber(Reflect.get(overview, "history_bad"), "overview.history_bad");
  assertNumber(Reflect.get(overview, "history_success_rate"), "overview.history_success_rate");
  assertNumber(Reflect.get(overview, "transition_samples"), "overview.transition_samples");
  assertNumber(Reflect.get(overview, "unique_transitions"), "overview.unique_transitions");
  assertNumber(Reflect.get(overview, "unique_tickets"), "overview.unique_tickets");
  assertNumber(Reflect.get(overview, "changed_by_count"), "overview.changed_by_count");
  assertNumber(Reflect.get(overview, "timespan_max"), "overview.timespan_max");

  assertStringArray(Reflect.get(options, "teams"), "options.teams");
  assertStringArray(Reflect.get(options, "years"), "options.years");
  assertStringArray(Reflect.get(options, "groups"), "options.groups");
  assertStringArray(Reflect.get(options, "changedBy"), "options.changedBy");
  assertStringArray(Reflect.get(options, "fif"), "options.fif");
  assertNumber(Reflect.get(options, "timespanMax"), "options.timespanMax");

  assertStringArray(Reflect.get(value, "insights"), "insights");
  assertDataset(Reflect.get(value, "meta"), "meta", META_COLUMNS, META_COLUMN_KINDS);
  assertDataset(Reflect.get(value, "coverage"), "coverage", COVERAGE_COLUMNS, COVERAGE_COLUMN_KINDS);
  assertDataset(Reflect.get(value, "tickets"), "tickets", TICKET_COLUMNS, TICKET_COLUMN_KINDS);
  assertDataset(Reflect.get(value, "issues"), "issues", ISSUE_COLUMNS, ISSUE_COLUMN_KINDS);

  return value as QGateDashboardPayload;
}

export function adaptQGateDashboardPayload(rawPayload: QGateDashboardPayload | unknown): QGateDashboardViewModel {
  const payload = validateQGateDashboardPayload(rawPayload);

  return {
    generatedFrom: {
      defectDir: payload.generated_from.defect_dir,
      historyDir: payload.generated_from.history_dir,
      teams: payload.generated_from.teams,
      minTransitionCount: payload.generated_from.min_transition_count,
    },
    overview: {
      teamCount: payload.overview.team_count,
      totalDefects: payload.overview.total_defects,
      historyOk: payload.overview.history_ok,
      historyBad: payload.overview.history_bad,
      historySuccessRate: payload.overview.history_success_rate,
      transitionSamples: payload.overview.transition_samples,
      uniqueTransitions: payload.overview.unique_transitions,
      uniqueTickets: payload.overview.unique_tickets,
      changedByCount: payload.overview.changed_by_count,
      timespanMax: payload.overview.timespan_max,
    },
    insights: [...payload.insights],
    options: {
      teams: [...payload.options.teams],
      years: [...payload.options.years],
      groups: [...payload.options.groups],
      changedBy: [...payload.options.changedBy],
      fif: [...payload.options.fif],
      timespanMax: payload.options.timespanMax,
    },
    metaRows: adaptMetaRows(payload.meta),
    coverageRows: adaptCoverageRows(payload.coverage),
    ticketRows: adaptTicketRows(payload.tickets),
    issueRows: adaptIssueRows(payload.issues),
  };
}