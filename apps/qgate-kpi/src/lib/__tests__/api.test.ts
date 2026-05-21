import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchQGateDashboardPayload, QGateApiRequestError, resolveQGateApiBaseUrl } from "../api";
import { QGatePayloadValidationError } from "../payload-adapter";
import { getDefaultQGateDashboardFilters } from "../default-filters";

afterEach(() => {
  vi.restoreAllMocks();
});

const samplePayload = {
  generated_from: {
    defect_dir: "qgate/defect",
    history_dir: "qgate/history",
    teams: ["DTSV_China"],
    min_transition_count: 200,
  },
  overview: {
    team_count: 1,
    total_defects: 4,
    history_ok: 3,
    history_bad: 1,
    history_success_rate: 75,
    transition_samples: 2,
    unique_transitions: 2,
    unique_tickets: 1,
    changed_by_count: 1,
    timespan_max: 3,
  },
  insights: ["sample"],
  options: {
    teams: ["DTSV_China"],
    years: ["2026"],
    groups: ["Q-Gate"],
    changedBy: ["Alice"],
    fif: ["Global"],
    timespanMax: 3,
  },
  meta: {
    columns: ["Team", "Defects", "History_OK", "History_Missing_or_Error"],
    rows: [["DTSV_China", 4, 3, 1]],
  },
  coverage: {
    columns: ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"],
    rows: [["DTSV_China", "2026", 4, 3, 1]],
  },
  tickets: {
    columns: ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"],
    rows: [["1001", "https://octane/1001", "Ticket 1001", "Alice"]],
  },
  issues: {
    columns: [
      "Year",
      "Team",
      "Ticket_ID",
      "Phase_Transition",
      "Group",
      "Duration_Hours",
      "Changed_By",
      "FiF",
      "Ticket_Timespan_Days",
    ],
    rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", 2]],
  },
};

describe("fetchQGateDashboardPayload", () => {
  it("defaults to the dedicated local qgate backend on port 8011 when no env override is present", () => {
    vi.stubEnv("QGATE_API_BASE", undefined);
    vi.stubEnv("NEXT_PUBLIC_QGATE_API_BASE", undefined);

    expect(resolveQGateApiBaseUrl()).toBe("http://127.0.0.1:8011");
  });

  it("returns a validated payload for a healthy API response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(samplePayload), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    const payload = await fetchQGateDashboardPayload(getDefaultQGateDashboardFilters());

    expect(payload.generated_from.teams).toEqual(["DTSV_China"]);
  });

  it("propagates backend detail for non-ok responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "No QGate data found." }), {
        status: 422,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    const request = fetchQGateDashboardPayload(getDefaultQGateDashboardFilters());

    await expect(request).rejects.toThrow(QGateApiRequestError);
    await expect(request).rejects.toThrow("No QGate data found.");
  });

  it("rejects malformed successful payloads before the route adapter consumes them", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...samplePayload,
          issues: {
            columns: ["Year"],
            rows: [["2026"]],
          },
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(fetchQGateDashboardPayload(getDefaultQGateDashboardFilters())).rejects.toThrow(QGatePayloadValidationError);
  });

  it("rejects malformed nested payload fields as schema drift", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...samplePayload,
          options: {
            ...samplePayload.options,
            teams: null,
          },
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(fetchQGateDashboardPayload(getDefaultQGateDashboardFilters())).rejects.toThrow(QGatePayloadValidationError);
  });

  it("rejects invalid JSON bodies from successful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{invalid-json", {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }),
    );

    await expect(fetchQGateDashboardPayload(getDefaultQGateDashboardFilters())).rejects.toThrow(QGatePayloadValidationError);
  });

  it("treats TimeoutError as a request timeout instead of an unreachable API", async () => {
    const timeoutError = new Error("The operation was aborted due to timeout.");
    timeoutError.name = "TimeoutError";

    vi.spyOn(globalThis, "fetch").mockRejectedValue(timeoutError);

    await expect(fetchQGateDashboardPayload(getDefaultQGateDashboardFilters())).rejects.toThrow(QGateApiRequestError);
    await expect(fetchQGateDashboardPayload(getDefaultQGateDashboardFilters())).rejects.toThrow(
      "QGate API request timed out.",
    );
  });

  it("preserves nullable ticket timespans from successful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...samplePayload,
          issues: {
            ...samplePayload.issues,
            rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", 24, "Alice", "Global", null]],
          },
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    const payload = await fetchQGateDashboardPayload(getDefaultQGateDashboardFilters());

    expect(payload.issues.rows[0][8]).toBeNull();
  });

  it("rejects boolean numeric dataset cells from successful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ...samplePayload,
          issues: {
            ...samplePayload.issues,
            rows: [["2026", "DTSV_China", "1001", "02-QGate -> 03-Analysis", "Q-Gate", true, "Alice", "Global", 2]],
          },
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    await expect(fetchQGateDashboardPayload(getDefaultQGateDashboardFilters())).rejects.toThrow(QGatePayloadValidationError);
  });
});