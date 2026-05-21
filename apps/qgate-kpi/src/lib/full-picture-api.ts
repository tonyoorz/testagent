import { getDefaultFullPictureDashboardFilters } from "./full-picture-default-filters";
import { FullPicturePayloadValidationError, validateFullPictureDashboardPayload } from "./full-picture-payload-adapter";
import { buildFullPictureDashboardUrl } from "./full-picture-query-options";
import type { FullPictureDashboardFilters, FullPictureDashboardPayload } from "./full-picture-types";

const DEFAULT_FULL_PICTURE_API_BASE = "http://127.0.0.1:8001";

export type FullPictureApiRequestErrorKind = "timeout" | "network" | "http";

type FullPictureApiRequestErrorOptions = {
  kind: FullPictureApiRequestErrorKind;
  status?: number;
  detail?: string | null;
};

export class FullPictureApiRequestError extends Error {
  readonly kind: FullPictureApiRequestErrorKind;
  readonly status: number | null;
  readonly detail: string | null;

  constructor(message: string, options: FullPictureApiRequestErrorOptions) {
    super(message);
    this.name = "FullPictureApiRequestError";
    this.kind = options.kind;
    this.status = options.status ?? null;
    this.detail = options.detail ?? null;
  }
}

type FetchFullPictureDashboardPayloadOptions = {
  baseUrl?: string;
  signal?: AbortSignal;
};

function readErrorDetail(value: unknown) {
  if (!value || typeof value !== "object") {
    return null;
  }

  const detail = Reflect.get(value, "detail");
  return typeof detail === "string" && detail.trim() ? detail : null;
}

export function resolveFullPictureApiBaseUrl() {
  return (
    process.env.FULL_PICTURE_API_BASE ??
    process.env.NEXT_PUBLIC_FULL_PICTURE_API_BASE ??
    DEFAULT_FULL_PICTURE_API_BASE
  );
}

export async function fetchFullPictureDashboardPayload(
  filters: FullPictureDashboardFilters = getDefaultFullPictureDashboardFilters(),
  options: FetchFullPictureDashboardPayloadOptions = {},
) {
  let response: Response;
  const apiBaseUrl = options.baseUrl ?? resolveFullPictureApiBaseUrl();

  try {
    response = await fetch(buildFullPictureDashboardUrl(apiBaseUrl, filters), {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof Error && (error.name === "AbortError" || error.name === "TimeoutError")) {
      throw new FullPictureApiRequestError("Full Picture API request timed out.", {
        kind: "timeout",
      });
    }

    throw new FullPictureApiRequestError("Unable to reach the Full Picture API.", {
      kind: "network",
    });
  }

  if (!response.ok) {
    let message = `Full Picture API request failed with status ${response.status}.`;
    let detail: string | null = null;

    try {
      const errorPayload = (await response.json()) as unknown;
      detail = readErrorDetail(errorPayload);
      if (detail) {
        message = detail;
      }
    } catch {
      // Ignore non-JSON error bodies and keep the default status-based message.
    }

    throw new FullPictureApiRequestError(message, {
      kind: "http",
      status: response.status,
      detail,
    });
  }

  let payload: unknown;

  try {
    payload = (await response.json()) as unknown;
  } catch {
    throw new FullPicturePayloadValidationError("Full Picture dashboard payload must be valid JSON.");
  }

  return validateFullPictureDashboardPayload(payload) as FullPictureDashboardPayload;
}
