import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { act, render, screen } from "@testing-library/react";

import {
  buildFullPictureBootstrapExhaustedMessage,
  FULL_PICTURE_BOOTSTRAP_MAX_RETRIES,
  FULL_PICTURE_BOOTSTRAP_RETRY_MS,
  INITIAL_FULL_PICTURE_TIMEOUT_MESSAGE,
} from "../bootstrap-state";
import { FullPictureDashboardBootstrap, resetFullPictureBootstrapRequestState } from "../full-picture-bootstrap";
import type { FullPictureDashboardViewModel } from "../../../lib/full-picture-types";

const {
  fetchFullPictureDashboardPayload,
  adaptFullPictureDashboardPayload,
  getDefaultFullPictureDashboardFilters,
  MockFullPictureApiRequestError,
  MockFullPicturePayloadValidationError,
} = vi.hoisted(() => {
  class FullPictureApiRequestError extends Error {
    kind: "timeout" | "network" | "http";
    status: number | null;
    detail: string | null;

    constructor(
      message: string,
      options: {
        kind: "timeout" | "network" | "http";
        status?: number;
        detail?: string | null;
      },
    ) {
      super(message);
      this.name = "FullPictureApiRequestError";
      this.kind = options.kind;
      this.status = options.status ?? null;
      this.detail = options.detail ?? null;
    }
  }

  class FullPicturePayloadValidationError extends Error {
    constructor(message: string) {
      super(message);
      this.name = "FullPicturePayloadValidationError";
    }
  }

  return {
    fetchFullPictureDashboardPayload: vi.fn(),
    adaptFullPictureDashboardPayload: vi.fn(),
    getDefaultFullPictureDashboardFilters: vi.fn(() => ({
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
    })),
    MockFullPictureApiRequestError: FullPictureApiRequestError,
    MockFullPicturePayloadValidationError: FullPicturePayloadValidationError,
  };
});

vi.mock("../../../lib/full-picture-api", () => ({
  fetchFullPictureDashboardPayload,
  FullPictureApiRequestError: MockFullPictureApiRequestError,
}));

vi.mock("../../../lib/full-picture-payload-adapter", () => ({
  adaptFullPictureDashboardPayload,
  FullPicturePayloadValidationError: MockFullPicturePayloadValidationError,
}));

vi.mock("../../../lib/full-picture-default-filters", () => ({
  getDefaultFullPictureDashboardFilters,
}));

const sampleDashboardData: FullPictureDashboardViewModel = {
  generatedFrom: {
    defectDbPath: "qgate/qgate_data.db",
    historyDbPath: "qgate/qgate_data.db",
    years: ["2026"],
    projects: ["Project A"],
    assignedEcus: ["ECU-A"],
    problemFinderTeams: ["Team A"],
    aidas: ["AIDA-1"],
    phases: ["08-Resolved"],
    solutionClusters: ["Cluster 1"],
    pus: ["PU-1"],
    markets: ["CN"],
    leadModels: ["Model 1"],
    groups: ["Q-Gate"],
  },
  filters: {
    years: ["2026"],
    projects: ["Project A"],
    assignedEcus: ["ECU-A"],
    problemFinderTeams: ["Team A"],
    aidas: ["AIDA-1"],
    phases: ["08-Resolved"],
    solutionClusters: ["Cluster 1"],
    pus: ["PU-1"],
    markets: ["CN"],
    leadModels: ["Model 1"],
    groups: ["Q-Gate"],
  },
  overview: {
    ticketCount: 1,
    resolvedForwardCount: 1,
    rejectedDirectlyCount: 0,
    resolvedForwardPercent: 100,
    rejectedDirectlyPercent: 0,
  },
  outcomeSummary: [
    { key: "resolvedForward", label: "Resolved Forward (08 -> 06)", count: 1, percent: 100, denominator: 1 },
    { key: "rejectedDirectly", label: "Rejected Directly (01 -> 09)", count: 0, percent: 0, denominator: 1 },
  ],
  teamOutcomeRows: [
    {
      problemFinderTeam: "Team A",
      totalTickets: 1,
      resolvedForwardCount: 1,
      rejectedDirectlyCount: 0,
      resolvedForwardTeamPercent: 100,
      rejectedDirectlyTeamPercent: 0,
      teamDenominator: 1,
    },
  ],
  ticketRows: [
    {
      ticketId: "1001",
      ticketName: "Forward only",
      status: "08-Resolved",
      problemFinderTeam: "Team A",
      group: "Q-Gate",
      phase: "08-Resolved",
      isResolvedForward: true,
      isRejectedDirectly: false,
      year: "2026",
      project: "Project A",
      assignedEcu: "ECU-A",
      aida: "AIDA-1",
      solutionCluster: "Cluster 1",
      pu: "PU-1",
      market: "CN",
      leadModel: "Model 1",
    },
  ],
};

beforeEach(() => {
  vi.useFakeTimers();
  resetFullPictureBootstrapRequestState();
  fetchFullPictureDashboardPayload.mockReset();
  adaptFullPictureDashboardPayload.mockReset();
  getDefaultFullPictureDashboardFilters.mockClear();
});

async function flushBootstrapWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const sampleApiBaseUrl = "https://dashboard.example";

afterEach(() => {
  resetFullPictureBootstrapRequestState();
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("FullPictureDashboardBootstrap", () => {
  it("keeps retrying after a timeout shell until the dashboard becomes ready", async () => {
    fetchFullPictureDashboardPayload
      .mockRejectedValueOnce(new MockFullPictureApiRequestError("Full Picture API request timed out.", { kind: "timeout" }))
      .mockResolvedValueOnce({ payload: "ok" });
    adaptFullPictureDashboardPayload.mockReturnValue(sampleDashboardData);

    render(
      <FullPictureDashboardBootstrap
        apiBaseUrl={sampleApiBaseUrl}
        initialPageProps={{
          state: "loading",
          statusMessage: "Initial Full Picture data is still warming the API. The browser keeps loading in the background.",
        }}
      />,
    );

    expect(screen.getByText(INITIAL_FULL_PICTURE_TIMEOUT_MESSAGE)).toBeInTheDocument();

    await flushBootstrapWork();

    expect(fetchFullPictureDashboardPayload).toHaveBeenCalledTimes(1);
    expect(fetchFullPictureDashboardPayload.mock.calls[0]?.[0]).toEqual({
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
    expect(fetchFullPictureDashboardPayload.mock.calls[0]?.[1]).toMatchObject({ baseUrl: sampleApiBaseUrl });
    expect(fetchFullPictureDashboardPayload.mock.calls[0]?.[1]?.signal).toBeDefined();
    expect(getDefaultFullPictureDashboardFilters).toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(FULL_PICTURE_BOOTSTRAP_RETRY_MS);
    });

    await flushBootstrapWork();

    expect(fetchFullPictureDashboardPayload).toHaveBeenCalledTimes(2);

    expect(screen.getByText("Portfolio outcome mix")).toBeInTheDocument();
  });

  it("keeps retrying after a server-side placeholder failure until the API recovers", async () => {
    fetchFullPictureDashboardPayload
      .mockRejectedValueOnce(
        new MockFullPictureApiRequestError("Backend is warming history indexes.", {
          kind: "http",
          status: 503,
          detail: "Backend is warming history indexes.",
        }),
      )
      .mockResolvedValueOnce({ payload: "ok" });
    adaptFullPictureDashboardPayload.mockReturnValue(sampleDashboardData);

    render(
      <FullPictureDashboardBootstrap
        apiBaseUrl={sampleApiBaseUrl}
        initialPageProps={{ state: "placeholder", statusMessage: "Initial Full Picture data unavailable." }}
      />,
    );

    await flushBootstrapWork();

    expect(screen.getByText("Initial Full Picture request failed: Backend is warming history indexes.")).toBeInTheDocument();
    expect(fetchFullPictureDashboardPayload).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(FULL_PICTURE_BOOTSTRAP_RETRY_MS);
    });

    await flushBootstrapWork();

    expect(fetchFullPictureDashboardPayload).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Portfolio outcome mix")).toBeInTheDocument();
  });

  it("falls back to a stable placeholder after the retry budget is exhausted", async () => {
    fetchFullPictureDashboardPayload.mockRejectedValue(
      new MockFullPictureApiRequestError("Full Picture API request timed out.", { kind: "timeout" }),
    );

    render(
      <FullPictureDashboardBootstrap
        apiBaseUrl={sampleApiBaseUrl}
        initialPageProps={{ state: "loading", statusMessage: INITIAL_FULL_PICTURE_TIMEOUT_MESSAGE }}
      />,
    );

    for (let attempt = 0; attempt < FULL_PICTURE_BOOTSTRAP_MAX_RETRIES; attempt += 1) {
      await flushBootstrapWork();

      if (attempt < FULL_PICTURE_BOOTSTRAP_MAX_RETRIES - 1) {
        await act(async () => {
          vi.advanceTimersByTime(FULL_PICTURE_BOOTSTRAP_RETRY_MS);
        });
      }
    }

    expect(fetchFullPictureDashboardPayload).toHaveBeenCalledTimes(FULL_PICTURE_BOOTSTRAP_MAX_RETRIES);
    expect(screen.getByText(buildFullPictureBootstrapExhaustedMessage(FULL_PICTURE_BOOTSTRAP_MAX_RETRIES))).toBeInTheDocument();
  });

  it("hydrates from an initial placeholder shell once the client can reach the API", async () => {
    fetchFullPictureDashboardPayload.mockResolvedValue({ payload: "ok" });
    adaptFullPictureDashboardPayload.mockReturnValue(sampleDashboardData);

    render(
      <FullPictureDashboardBootstrap
        apiBaseUrl={sampleApiBaseUrl}
        initialPageProps={{ state: "placeholder", statusMessage: "Initial Full Picture data unavailable." }}
      />,
    );

    expect(screen.getByText("Initial Full Picture data unavailable.")).toBeInTheDocument();

    await flushBootstrapWork();

    expect(fetchFullPictureDashboardPayload).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Portfolio outcome mix")).toBeInTheDocument();
  });
});