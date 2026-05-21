import { getDefaultQGateDashboardFilters } from "./default-filters";
import { QGatePayloadValidationError, validateQGateDashboardPayload } from "./payload-adapter";
import { buildQGateDashboardUrl } from "./query-options";
import type { QGateDashboardFilters, QGateDashboardPayload } from "./types";

const DEFAULT_QGATE_API_BASE = "http://127.0.0.1:8011";

export class QGateApiRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "QGateApiRequestError";
  }
}

type FetchQGateDashboardPayloadOptions = {
  signal?: AbortSignal;
};

function readErrorDetail(value: unknown) {
  if (!value || typeof value !== "object") {
    return null;
  }

  const detail = Reflect.get(value, "detail");
  return typeof detail === "string" && detail.trim() ? detail : null;
}

export function resolveQGateApiBaseUrl() {
  return process.env.QGATE_API_BASE ?? process.env.NEXT_PUBLIC_QGATE_API_BASE ?? DEFAULT_QGATE_API_BASE;
}

export async function fetchQGateDashboardPayload(
  filters: QGateDashboardFilters = getDefaultQGateDashboardFilters(),
  options: FetchQGateDashboardPayloadOptions = {},
) {
  let response: Response;

  try {
    response = await fetch(buildQGateDashboardUrl(resolveQGateApiBaseUrl(), filters), {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof Error && (error.name === "AbortError" || error.name === "TimeoutError")) {
      throw new QGateApiRequestError("QGate API request timed out.");
    }

    throw new QGateApiRequestError("Unable to reach the QGate API.");
  }

  if (!response.ok) {
    let message = `QGate API request failed with status ${response.status}.`;

    try {
      const errorPayload = (await response.json()) as unknown;
      const detail = readErrorDetail(errorPayload);
      if (detail) {
        message = detail;
      }
    } catch {
      // Ignore non-JSON error bodies and keep the default status-based message.
    }

    throw new QGateApiRequestError(message);
  }

  let payload: unknown;

  try {
    payload = (await response.json()) as unknown;
  } catch {
    throw new QGatePayloadValidationError("QGate dashboard payload must be valid JSON.");
  }

  return validateQGateDashboardPayload(payload) as QGateDashboardPayload;
}