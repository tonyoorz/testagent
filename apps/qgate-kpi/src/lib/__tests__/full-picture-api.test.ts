import { afterEach, describe, expect, it, vi } from "vitest";

import { getDefaultFullPictureDashboardFilters } from "../full-picture-default-filters";
import {
  fetchFullPictureDashboardPayload,
  FullPictureApiRequestError,
  resolveFullPictureApiBaseUrl,
} from "../full-picture-api";
import { adaptFullPictureDashboardPayload, FullPicturePayloadValidationError } from "../full-picture-payload-adapter";
import type { FullPictureDashboardPayload, FullPictureDashboardFilters } from "../full-picture-types";

afterEach(() => {
  vi.restoreAllMocks();
});

const samplePayload: FullPictureDashboardPayload = {
  generated_from: {
    defect_db_path: "qgate/qgate_data.db",
    history_db_path: "qgate/qgate_data.db",
    years: ["2026"],
    projects: ["Project A", "Project B"],
    assigned_ecus: ["ECU-A", "ECU-B"],
    problem_finder_teams: ["Team A", "Team B"],
    aidas: ["AIDA-1", "AIDA-2"],
    phases: ["08-Resolved", "09-Rejected"],
    solution_clusters: ["Cluster 1", "Cluster 2"],
    pus: ["PU-1", "PU-2"],
    markets: ["CN", "EU"],
    lead_models: ["Model 1", "Model 2"],
    groups: ["Q-Gate", "Integration", "CoC"],
  },
  filters: {
    years: ["2025", "2026"],
    projects: ["Project A", "Project B"],
    assigned_ecus: ["ECU-A", "ECU-B"],
    problem_finder_teams: ["Team A", "Team B"],
    aidas: ["AIDA-1", "AIDA-2"],
    phases: ["08-Resolved", "09-Rejected"],
    solution_clusters: ["Cluster 1", "Cluster 2"],
    pus: ["PU-1", "PU-2"],
    markets: ["CN", "EU"],
    lead_models: ["Model 1", "Model 2"],
    groups: ["Q-Gate", "Integration", "CoC"],
  },
  overview: {
    ticket_count: 3,
    resolved_forward_count: 2,
    rejected_directly_count: 2,
    resolved_forward_percent: 66.67,
    rejected_directly_percent: 66.67,
  },
  outcome_summary: [
    {
      key: "resolved_forward",
      label: "Resolved Forward (08 -> 06)",
      count: 2,
      percent: 66.67,
      denominator: 3,
    },
    {
      key: "rejected_directly",
      label: "Rejected Directly (01 -> 09)",
      count: 2,
      percent: 66.67,
      denominator: 3,
    },
  ],
  team_outcome_rows: [
    {
      problem_finder_team: "Team A",
      total_tickets: 2,
      resolved_forward_count: 2,
      rejected_directly_count: 1,
      resolved_forward_team_percent: 100,
      rejected_directly_team_percent: 50,
      team_denominator: 2,
    },
    {
      problem_finder_team: "Team B",
      total_tickets: 1,
      resolved_forward_count: 0,
      rejected_directly_count: 1,
      resolved_forward_team_percent: 0,
      rejected_directly_team_percent: 100,
      team_denominator: 1,
    },
  ],
  ticket_rows: [
    {
      ticket_id: "1001",
      ticket_name: "Forward only",
      status: "08-Resolved",
      problem_finder_team: "Team A",
      group: "Q-Gate",
      phase: "08-Resolved",
      is_resolved_forward: true,
      is_rejected_directly: false,
      year: "2026",
      project: "Project A",
      assigned_ecu: "ECU-A",
      aida: "AIDA-1",
      solution_cluster: "Cluster 1",
      pu: "PU-1",
      market: "CN",
      lead_model: "Model 1",
    },
    {
      ticket_id: "1002",
      ticket_name: "Both outcomes",
      status: "09-Rejected",
      problem_finder_team: "Team A",
      group: "Integration",
      phase: "09-Rejected",
      is_resolved_forward: true,
      is_rejected_directly: true,
      year: "2026",
      project: "Project A",
      assigned_ecu: "ECU-B",
      aida: "AIDA-2",
      solution_cluster: "Cluster 2",
      pu: "PU-2",
      market: "EU",
      lead_model: "Model 2",
    },
    {
      ticket_id: "1003",
      ticket_name: "Rejected only",
      status: "09-Rejected",
      problem_finder_team: "Team B",
      group: "CoC",
      phase: "09-Rejected",
      is_resolved_forward: false,
      is_rejected_directly: true,
      year: "2026",
      project: "Project B",
      assigned_ecu: "ECU-B",
      aida: "AIDA-2",
      solution_cluster: "Cluster 2",
      pu: "PU-2",
      market: "EU",
      lead_model: "Model 2",
    },
  ],
};

function buildFilters(overrides: Partial<FullPictureDashboardFilters> = {}): FullPictureDashboardFilters {
  return {
    ...getDefaultFullPictureDashboardFilters(),
    ...overrides,
  };
}

describe("fetchFullPictureDashboardPayload", () => {
  it("defaults to the shared local qgate_api backend base when no env override is present", () => {
    vi.stubEnv("FULL_PICTURE_API_BASE", undefined);
    vi.stubEnv("NEXT_PUBLIC_FULL_PICTURE_API_BASE", undefined);
    vi.stubEnv("QGATE_API_BASE", undefined);
    vi.stubEnv("NEXT_PUBLIC_QGATE_API_BASE", undefined);

    expect(resolveFullPictureApiBaseUrl()).toBe("http://127.0.0.1:8001");
  });

  it("does not inherit the qgate backend override when full-picture env vars are unset", () => {
    vi.stubEnv("FULL_PICTURE_API_BASE", undefined);
    vi.stubEnv("NEXT_PUBLIC_FULL_PICTURE_API_BASE", undefined);
    vi.stubEnv("QGATE_API_BASE", "http://127.0.0.1:8011");
    vi.stubEnv("NEXT_PUBLIC_QGATE_API_BASE", "http://127.0.0.1:8011");

    expect(resolveFullPictureApiBaseUrl()).toBe("http://127.0.0.1:8001");
  });

  it("requests the full-picture endpoint with the backend filter names and validates a healthy response", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(samplePayload), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    const payload = await fetchFullPictureDashboardPayload(
      buildFilters({
        assignedEcus: ["ECU-A"],
        problemFinderTeams: ["Team A"],
        groups: ["Q-Gate"],
      }),
    );

    const requestUrl = new URL(String(fetchSpy.mock.calls[0]?.[0]));

    expect(requestUrl.pathname).toBe("/api/full-picture/dashboard");
    expect(requestUrl.searchParams.getAll("years")).toEqual(["2026"]);
    expect(requestUrl.searchParams.getAll("assigned_ecus")).toEqual(["ECU-A"]);
    expect(requestUrl.searchParams.getAll("problem_finder_teams")).toEqual(["Team A"]);
    expect(requestUrl.searchParams.getAll("groups")).toEqual(["Q-Gate"]);
    expect(payload.ticket_rows).toHaveLength(3);
  });

  it("propagates backend detail for non-ok responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "No Full Picture data found." }), {
        status: 422,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    const request = fetchFullPictureDashboardPayload(buildFilters());

    await expect(request).rejects.toThrow(FullPictureApiRequestError);
    await expect(request).rejects.toMatchObject({
      message: "No Full Picture data found.",
      kind: "http",
      status: 422,
      detail: "No Full Picture data found.",
    });
  });

  it("classifies timeout and network failures with structured error metadata", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(Object.assign(new Error("timed out"), { name: "TimeoutError" }));

    await expect(fetchFullPictureDashboardPayload(buildFilters())).rejects.toMatchObject({
      message: "Full Picture API request timed out.",
      kind: "timeout",
      status: null,
      detail: null,
    });

    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("socket hang up"));

    await expect(fetchFullPictureDashboardPayload(buildFilters())).rejects.toMatchObject({
      message: "Unable to reach the Full Picture API.",
      kind: "network",
      status: null,
      detail: null,
    });
  });

  it("rejects malformed successful payloads before the route adapter consumes them", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...samplePayload,
          ticket_rows: [
            {
              ...samplePayload.ticket_rows[0],
              ticket_id: 1001,
            },
          ],
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(fetchFullPictureDashboardPayload(buildFilters())).rejects.toThrow(FullPicturePayloadValidationError);
  });
});

describe("adaptFullPictureDashboardPayload", () => {
  it("normalizes the backend payload into a typed frontend model", () => {
    const adapted = adaptFullPictureDashboardPayload(samplePayload);

    expect(adapted.generatedFrom).toEqual({
      defectDbPath: "qgate/qgate_data.db",
      historyDbPath: "qgate/qgate_data.db",
      years: ["2026"],
      projects: ["Project A", "Project B"],
      assignedEcus: ["ECU-A", "ECU-B"],
      problemFinderTeams: ["Team A", "Team B"],
      aidas: ["AIDA-1", "AIDA-2"],
      phases: ["08-Resolved", "09-Rejected"],
      solutionClusters: ["Cluster 1", "Cluster 2"],
      pus: ["PU-1", "PU-2"],
      markets: ["CN", "EU"],
      leadModels: ["Model 1", "Model 2"],
      groups: ["Q-Gate", "Integration", "CoC"],
    });
    expect(adapted.filters.problemFinderTeams).toEqual(["Team A", "Team B"]);
    expect(adapted.overview.ticketCount).toBe(3);
    expect(adapted.outcomeSummary[0]).toEqual({
      key: "resolvedForward",
      label: "Resolved Forward (08 -> 06)",
      count: 2,
      percent: 66.67,
      denominator: 3,
    });
    expect(adapted.teamOutcomeRows[0]?.problemFinderTeam).toBe("Team A");
    expect(adapted.ticketRows[1]).toEqual({
      ticketId: "1002",
      ticketName: "Both outcomes",
      status: "09-Rejected",
      problemFinderTeam: "Team A",
      group: "Integration",
      phase: "09-Rejected",
      isResolvedForward: true,
      isRejectedDirectly: true,
      year: "2026",
      project: "Project A",
      assignedEcu: "ECU-B",
      aida: "AIDA-2",
      solutionCluster: "Cluster 2",
      pu: "PU-2",
      market: "EU",
      leadModel: "Model 2",
    });
  });

  it("rejects payloads with malformed nested filters fields as schema drift", () => {
    expect(() =>
      adaptFullPictureDashboardPayload({
        ...samplePayload,
        filters: {
          ...samplePayload.filters,
          groups: null,
        },
      }),
    ).toThrow(FullPicturePayloadValidationError);
  });

  it("rejects payloads with malformed ticket rows", () => {
    expect(() =>
      adaptFullPictureDashboardPayload({
        ...samplePayload,
        ticket_rows: [
          {
            ...samplePayload.ticket_rows[0],
            is_rejected_directly: "yes",
          },
        ],
      }),
    ).toThrow(FullPicturePayloadValidationError);
  });

  it("rejects payloads whose overview counts drift from the ticket rows", () => {
    expect(() =>
      adaptFullPictureDashboardPayload({
        ...samplePayload,
        overview: {
          ...samplePayload.overview,
          resolved_forward_count: 1,
        },
      }),
    ).toThrow(FullPicturePayloadValidationError);
  });

  it("rejects payloads whose outcome summary denominator or counts drift from the ticket rows", () => {
    expect(() =>
      adaptFullPictureDashboardPayload({
        ...samplePayload,
        outcome_summary: [
          {
            ...samplePayload.outcome_summary[0],
            denominator: 2,
          },
          samplePayload.outcome_summary[1],
        ],
      }),
    ).toThrow(FullPicturePayloadValidationError);
  });

  it("rejects payloads whose team outcome rows drift from the ticket rows", () => {
    expect(() =>
      adaptFullPictureDashboardPayload({
        ...samplePayload,
        team_outcome_rows: [
          {
            ...samplePayload.team_outcome_rows[0],
            resolved_forward_team_percent: 50,
          },
          samplePayload.team_outcome_rows[1],
        ],
      }),
    ).toThrow(FullPicturePayloadValidationError);
  });
});