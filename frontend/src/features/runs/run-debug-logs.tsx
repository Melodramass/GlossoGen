"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";
import type { components } from "@/types/api.gen";
import { LogPanel } from "./log-panel";

type DebugLogEntry = components["schemas"]["DebugLogEntry"];

/** Mount only when Logs is selected, so reading a chat never fetches debug logs. */
export function RunDebugLogs({ runId, liveLogs }: { runId: string; liveLogs: DebugLogEntry[] }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["run-debug-logs", runId],
    gcTime: 30_000,
    queryFn: async ({ signal }) => {
      const { data, error } = await api.GET(
        "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/debug-logs",
        {
          params: { path: splitRunId(runId) },
          signal,
        }
      );
      if (error) {
        throw new Error("Failed to fetch debug logs");
      }
      return data;
    },
  });

  const allDebugLogs = useMemo(() => {
    const restLogs = data?.entries ?? [];
    if (liveLogs.length === 0) return restLogs;
    const seen = new Set(restLogs.map(l => `${l.timestamp}|${l.message}`));
    const newLogs = liveLogs.filter(l => !seen.has(`${l.timestamp}|${l.message}`));
    return [...restLogs, ...newLogs];
  }, [data?.entries, liveLogs]);

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center py-10 text-sm text-muted-foreground"
        role="status"
      >
        Loading debug logs…
      </div>
    );
  }
  if (error) {
    return (
      <div
        className="flex items-center justify-center gap-2 py-10 text-sm text-destructive"
        role="alert"
      >
        Failed to load debug logs.
        <button className="underline" onClick={() => void refetch()}>
          Retry
        </button>
      </div>
    );
  }
  // The API returns an empty list for absent/empty files; LogPanel owns that state.
  return <LogPanel logs={allDebugLogs} />;
}
