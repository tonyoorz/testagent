import { QGateApiRequestError } from "../../lib/api";
import { QGatePayloadValidationError } from "../../lib/payload-adapter";
import type { QGateDashboardPageProps } from "./dashboard-page";

export const INITIAL_DASHBOARD_BOOTSTRAP_TIMEOUT_MS = 3000;
export const INITIAL_DASHBOARD_TIMEOUT_MESSAGE =
  "Initial dashboard data is still warming the QGate API. The browser keeps loading in the background.";

export function resolveQGateDashboardShellState(error: unknown): Extract<QGateDashboardPageProps, { state: "placeholder" | "loading" }> {
  if (error instanceof QGatePayloadValidationError) {
    return {
      state: "placeholder",
      statusMessage: "Initial dashboard data was rejected because the API payload shape changed.",
    };
  }

  if (error instanceof QGateApiRequestError) {
    if (error.message === "QGate API request timed out.") {
      return {
        state: "loading",
        statusMessage: INITIAL_DASHBOARD_TIMEOUT_MESSAGE,
      };
    }

    return {
      state: "placeholder",
      statusMessage:
        error.message === "Unable to reach the QGate API."
          ? "Initial dashboard data unavailable. Showing the shell until the API becomes reachable."
          : `Initial dashboard request failed: ${error.message}`,
    };
  }

  return {
    state: "placeholder",
    statusMessage: "Initial dashboard bootstrap failed unexpectedly. Showing the shell only.",
  };
}