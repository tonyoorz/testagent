import type { Metadata } from "next";

import { FullPictureDashboardBootstrap } from "../../src/features/full-picture-dashboard/full-picture-bootstrap";
import {
  createFullPictureBootstrapTimeoutSignal,
  resolveFullPictureDashboardShellState,
} from "../../src/features/full-picture-dashboard/bootstrap-state";
import type { FullPicturePageProps } from "../../src/features/full-picture-dashboard/full-picture-page";
import { fetchFullPictureDashboardPayload, resolveFullPictureApiBaseUrl } from "../../src/lib/full-picture-api";
import { getDefaultFullPictureDashboardFilters } from "../../src/lib/full-picture-default-filters";
import { adaptFullPictureDashboardPayload } from "../../src/lib/full-picture-payload-adapter";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Full Picture | QGate KPI Dashboard",
  description: "Full Picture management workbench for outcome flow, team expansion, and ticket detail scope.",
};

export default async function FullPictureRoutePage() {
  let pageProps: FullPicturePageProps;
  const apiBaseUrl = resolveFullPictureApiBaseUrl();

  try {
    const payload = await fetchFullPictureDashboardPayload(getDefaultFullPictureDashboardFilters(), {
      baseUrl: apiBaseUrl,
      signal: createFullPictureBootstrapTimeoutSignal(),
    });
    const initialData = adaptFullPictureDashboardPayload(payload);
    pageProps = { state: "ready", initialData };
  } catch (error) {
    const shellState = resolveFullPictureDashboardShellState(error);

    if (shellState.state === "loading") {
      console.warn("Initial Full Picture payload timed out during SSR bootstrap. Continuing in the browser.");
    } else {
      console.error("Unable to fetch initial Full Picture payload.", error);
    }

    pageProps = shellState;
  }

  return <FullPictureDashboardBootstrap apiBaseUrl={apiBaseUrl} initialPageProps={pageProps} />;
}