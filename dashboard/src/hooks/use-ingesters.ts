"use client";

/**
 * React Query hooks for ingester operations
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { startIngester, stopIngester, stopAllIngesters } from "@/lib/api";
import { useLogStore } from "@/stores/log-store";

/**
 * Hook to start an ingester with optional config
 */
export function useStartIngester() {
  const queryClient = useQueryClient();
  const { config } = useLogStore();

  return useMutation({
    mutationFn: async (name: string) => {
      // Convert config to args format
      const ingesterConfig = config[name];
      const args: Record<string, string> = {};

      if (ingesterConfig) {
        for (const [key, value] of Object.entries(ingesterConfig)) {
          // Map config keys to CLI args
          if (key === "ships") args["--ships"] = String(value);
          else if (key === "tracks") args["--tracks"] = String(value);
          else if (key === "rate") args["--rate"] = String(value);
        }
      }

      return startIngester(name, Object.keys(args).length > 0 ? args : undefined);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ingesters"] });
    },
  });
}

/**
 * Hook to stop an ingester
 */
export function useStopIngester() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (name: string) => stopIngester(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ingesters"] });
    },
  });
}

/**
 * Hook to stop all ingesters
 */
export function useStopAllIngesters() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => stopAllIngesters(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ingesters"] });
    },
  });
}
