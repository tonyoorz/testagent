import { FullPictureApiRequestError } from "../../lib/full-picture-api";
import { FullPicturePayloadValidationError } from "../../lib/full-picture-payload-adapter";
import type { FullPicturePageProps } from "./full-picture-page";

export const INITIAL_FULL_PICTURE_BOOTSTRAP_TIMEOUT_MS = 30000;
export const FULL_PICTURE_BOOTSTRAP_RETRY_MS = 5000;
export const FULL_PICTURE_BOOTSTRAP_MAX_RETRIES = 3;
export const INITIAL_FULL_PICTURE_TIMEOUT_MESSAGE =
  "Initial Full Picture data is still warming the API. The browser keeps loading in the background.";

export function createFullPictureBootstrapTimeoutSignal() {
  return typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(INITIAL_FULL_PICTURE_BOOTSTRAP_TIMEOUT_MS) : undefined;
}

export function shouldRetryFullPictureDashboardBootstrap(error: unknown) {
  if (!(error instanceof FullPictureApiRequestError)) {
    return false;
  }

  return error.kind === "timeout" || error.kind === "network" || (error.kind === "http" && (error.status ?? 0) >= 500);
}

export function resolveFullPictureDashboardShellState(
  error: unknown,
): Extract<FullPicturePageProps, { state: "placeholder" | "loading" }> {
  if (error instanceof FullPicturePayloadValidationError) {
    return {
      state: "placeholder",
      statusMessage: "Initial Full Picture data was rejected because the API payload shape changed.",
    };
  }

  if (error instanceof FullPictureApiRequestError) {
    if (error.kind === "timeout") {
      return {
        state: "loading",
        statusMessage: INITIAL_FULL_PICTURE_TIMEOUT_MESSAGE,
      };
    }

    return {
      state: "placeholder",
      statusMessage:
        error.kind === "network"
          ? "Initial Full Picture data unavailable. Showing the shell until the API becomes reachable."
          : `Initial Full Picture request failed: ${error.message}`,
    };
  }

  return {
    state: "placeholder",
    statusMessage: "Initial Full Picture bootstrap failed unexpectedly. Showing the shell only.",
  };
}

export function buildFullPictureBootstrapExhaustedMessage(retryCount: number) {
  return `Initial Full Picture data is still unavailable after ${retryCount} bootstrap attempts. Showing the shell until the API is stable.`;
}