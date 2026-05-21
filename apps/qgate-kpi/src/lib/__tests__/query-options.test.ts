import { describe, expect, it } from "vitest";

import { buildQGateDashboardSearchParams, buildQGateDashboardUrl } from "../query-options";
import type { QGateDashboardFilters } from "../types";

const sampleFilters: QGateDashboardFilters = {
  defectDir: "qgate/defect",
  historyDir: "qgate/history",
  teams: ["DTSV_China"],
  years: ["2026"],
  groups: ["Q-Gate"],
  changedBy: ["Alice"],
  fif: ["Global"],
  timespanMin: 1.5,
  timespanMax: 2.9,
  minTransitionCount: 200,
  analysisWorkers: 3,
  cacheDir: "qgate_cache",
  useCache: false,
};

describe("buildQGateDashboardSearchParams", () => {
  it("serializes the backend filter names exactly as the API expects", () => {
    const searchParams = buildQGateDashboardSearchParams(sampleFilters);

    expect(searchParams.getAll("teams")).toEqual(["DTSV_China"]);
    expect(searchParams.getAll("years")).toEqual(["2026"]);
    expect(searchParams.getAll("groups")).toEqual(["Q-Gate"]);
    expect(searchParams.getAll("changed_by")).toEqual(["Alice"]);
    expect(searchParams.getAll("fif")).toEqual(["Global"]);
    expect(searchParams.get("timespan_min")).toBe("1.5");
    expect(searchParams.get("timespan_max")).toBe("2.9");
    expect(searchParams.get("min_transition_count")).toBe("200");
    expect(searchParams.get("analysis_workers")).toBe("3");
    expect(searchParams.get("use_cache")).toBe("false");
  });

  it("builds the dashboard endpoint url against the configured API base", () => {
    const url = buildQGateDashboardUrl("http://127.0.0.1:8001/", sampleFilters);

    expect(url).toContain("http://127.0.0.1:8001/api/qgate/kpi-dashboard?");
    expect(url).toContain("cache_dir=qgate_cache");
    expect(url).toContain("changed_by=Alice");
    expect(url).toContain("min_transition_count=200");
  });
});