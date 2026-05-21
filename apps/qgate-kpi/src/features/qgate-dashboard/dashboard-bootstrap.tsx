"use client";

import { startTransition, useEffect, useEffectEvent, useRef, useState } from "react";

import { fetchQGateDashboardPayload } from "../../lib/api";
import { getDefaultQGateDashboardFilters } from "../../lib/default-filters";
import { adaptQGateDashboardPayload } from "../../lib/payload-adapter";
import { INITIAL_DASHBOARD_TIMEOUT_MESSAGE, resolveQGateDashboardShellState } from "./bootstrap-state";
import { QGateDashboardPage, type QGateDashboardPageProps } from "./dashboard-page";

export function QGateDashboardBootstrap(initialProps: QGateDashboardPageProps) {
  const [pageProps, setPageProps] = useState<QGateDashboardPageProps>(initialProps);
  const hasAttemptedHydrationRef = useRef(initialProps.state !== "loading");

  const hydrateDashboard = useEffectEvent(async () => {
    try {
      const payload = await fetchQGateDashboardPayload(getDefaultQGateDashboardFilters());
      const initialData = adaptQGateDashboardPayload(payload);

      startTransition(() => {
        setPageProps({
          state: "ready",
          initialData,
        });
      });
    } catch (error) {
      const shellState = resolveQGateDashboardShellState(error);

      startTransition(() => {
        setPageProps(
          shellState.state === "loading"
            ? {
                state: "placeholder",
                statusMessage: INITIAL_DASHBOARD_TIMEOUT_MESSAGE,
              }
            : shellState,
        );
      });
    }
  });

  useEffect(() => {
    if (pageProps.state !== "loading" || hasAttemptedHydrationRef.current) {
      return;
    }

    hasAttemptedHydrationRef.current = true;
    void hydrateDashboard();
  }, [pageProps.state]);

  return <QGateDashboardPage {...pageProps} />;
}