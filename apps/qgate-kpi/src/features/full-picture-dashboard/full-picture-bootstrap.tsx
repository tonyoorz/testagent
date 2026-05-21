"use client";

import { startTransition, useEffect, useEffectEvent, useRef, useState } from "react";

import { fetchFullPictureDashboardPayload } from "../../lib/full-picture-api";
import { getDefaultFullPictureDashboardFilters } from "../../lib/full-picture-default-filters";
import { adaptFullPictureDashboardPayload } from "../../lib/full-picture-payload-adapter";
import {
  buildFullPictureBootstrapExhaustedMessage,
  createFullPictureBootstrapTimeoutSignal,
  FULL_PICTURE_BOOTSTRAP_MAX_RETRIES,
  FULL_PICTURE_BOOTSTRAP_RETRY_MS,
  resolveFullPictureDashboardShellState,
  shouldRetryFullPictureDashboardBootstrap,
} from "./bootstrap-state";
import { FullPicturePage, type FullPicturePageProps } from "./full-picture-page";

type FullPictureDashboardBootstrapProps = {
  apiBaseUrl: string;
  initialPageProps: FullPicturePageProps;
};

type BootstrapHydrationResult =
  | {
      ok: true;
      source: "network";
      initialData: Awaited<ReturnType<typeof adaptFullPictureDashboardPayload>>;
    }
  | {
      ok: false;
      source: "network" | "cached-failure";
      error: unknown;
    };

const pendingBootstrapRequests = new Map<string, Promise<BootstrapHydrationResult>>();
const cachedRetryableBootstrapFailures = new Map<
  string,
  {
    expiresAt: number;
    result: Extract<BootstrapHydrationResult, { ok: false }>;
  }
>();

export function resetFullPictureBootstrapRequestState() {
  pendingBootstrapRequests.clear();
  cachedRetryableBootstrapFailures.clear();
}

function getSharedBootstrapHydration(apiBaseUrl: string) {
  const cachedFailure = cachedRetryableBootstrapFailures.get(apiBaseUrl);

  if (cachedFailure) {
    if (Date.now() < cachedFailure.expiresAt) {
      return Promise.resolve({
        ...cachedFailure.result,
        source: "cached-failure",
      });
    }

    cachedRetryableBootstrapFailures.delete(apiBaseUrl);
  }

  const existingRequest = pendingBootstrapRequests.get(apiBaseUrl);

  if (existingRequest) {
    return existingRequest;
  }

  const request = (async (): Promise<BootstrapHydrationResult> => {
    try {
      const payload = await fetchFullPictureDashboardPayload(getDefaultFullPictureDashboardFilters(), {
        baseUrl: apiBaseUrl,
        signal: createFullPictureBootstrapTimeoutSignal(),
      });

      return {
        ok: true,
        source: "network",
        initialData: adaptFullPictureDashboardPayload(payload),
      };
    } catch (error) {
      if (shouldRetryFullPictureDashboardBootstrap(error)) {
        const result = {
          ok: false,
          source: "network",
          error,
        } as const;

        cachedRetryableBootstrapFailures.set(apiBaseUrl, {
          expiresAt: Date.now() + FULL_PICTURE_BOOTSTRAP_RETRY_MS,
          result,
        });

        return result;
      }

      return {
        ok: false,
        source: "network",
        error,
      };
    } finally {
      pendingBootstrapRequests.delete(apiBaseUrl);
    }
  })();

  pendingBootstrapRequests.set(apiBaseUrl, request);
  return request;
}

export function FullPictureDashboardBootstrap({ apiBaseUrl, initialPageProps }: FullPictureDashboardBootstrapProps) {
  const [pageProps, setPageProps] = useState<FullPicturePageProps>(initialPageProps);
  const [retryTick, setRetryTick] = useState(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);

  const clearRetryTimer = useEffectEvent(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  });

  const scheduleRetry = useEffectEvent(() => {
    if (retryTimerRef.current !== null) {
      return;
    }

    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null;

      startTransition(() => {
        setRetryTick((current) => current + 1);
      });
    }, FULL_PICTURE_BOOTSTRAP_RETRY_MS);
  });

  const hydrateDashboard = useEffectEvent(async () => {
    const result = await getSharedBootstrapHydration(apiBaseUrl);

    if (result.ok) {
      clearRetryTimer();
      retryCountRef.current = 0;

      startTransition(() => {
        setPageProps({
          state: "ready",
          initialData: result.initialData,
        });
      });

      return;
    }

    const error = result.error;
    const shellState = resolveFullPictureDashboardShellState(error);

    startTransition(() => {
      setPageProps(shellState);
    });

    if (shouldRetryFullPictureDashboardBootstrap(error)) {
      if (result.source === "network") {
        retryCountRef.current += 1;
      }

      if (retryCountRef.current >= FULL_PICTURE_BOOTSTRAP_MAX_RETRIES) {
        clearRetryTimer();

        startTransition(() => {
          setPageProps({
            state: "placeholder",
            statusMessage: buildFullPictureBootstrapExhaustedMessage(retryCountRef.current),
          });
        });

        return;
      }

      scheduleRetry();
      return;
    }

    clearRetryTimer();
  });

  useEffect(() => {
    if (initialPageProps.state === "ready") {
      return;
    }

    void hydrateDashboard();

    return () => {
      clearRetryTimer();
      retryCountRef.current = 0;
    };
  }, []);

  useEffect(() => {
    if (retryTick === 0 || pageProps.state === "ready") {
      return;
    }

    void hydrateDashboard();
  }, [pageProps.state, retryTick]);

  return <FullPicturePage {...pageProps} />;
}