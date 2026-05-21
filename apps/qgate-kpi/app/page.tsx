import { QGateDashboardBootstrap } from "../src/features/qgate-dashboard/dashboard-bootstrap";
import {
  INITIAL_DASHBOARD_BOOTSTRAP_TIMEOUT_MS,
  resolveQGateDashboardShellState,
} from "../src/features/qgate-dashboard/bootstrap-state";
import type { QGateDashboardPageProps } from "../src/features/qgate-dashboard/dashboard-page";
import { fetchQGateDashboardPayload } from "../src/lib/api";
import { getDefaultQGateDashboardFilters } from "../src/lib/default-filters";
import { adaptQGateDashboardPayload } from "../src/lib/payload-adapter";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let pageProps: QGateDashboardPageProps;

  try {
    const payload = await fetchQGateDashboardPayload(getDefaultQGateDashboardFilters(), {
      signal: AbortSignal.timeout(INITIAL_DASHBOARD_BOOTSTRAP_TIMEOUT_MS),
    });
    const initialData = adaptQGateDashboardPayload(payload);
    pageProps = { state: "ready", initialData };
  } catch (error) {
    const shellState = resolveQGateDashboardShellState(error);

    if (shellState.state === "loading") {
      console.warn("Initial QGate dashboard payload timed out during SSR bootstrap. Continuing in the browser.");
    } else {
      console.error("Unable to fetch initial QGate dashboard payload.", error);
    }

    pageProps = shellState;
  }

  return <QGateDashboardBootstrap {...pageProps} />;
}