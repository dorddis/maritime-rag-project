/**
 * Zustand store for log buffers and real-time state
 */

import { create } from "zustand";
import type { IngestersStatus, DashboardUpdate } from "@/lib/types";

const MAX_LOG_LINES = 100;

interface LogStore {
  // Connection state
  connected: boolean;
  setConnected: (connected: boolean) => void;

  // Ingester status
  status: IngestersStatus;
  setStatus: (status: IngestersStatus) => void;

  // Log buffers per ingester
  logs: Record<string, string[]>;
  setLogs: (logs: Record<string, string[]>) => void;
  appendLogs: (name: string, newLogs: string[]) => void;
  clearLogs: (name: string) => void;

  // Stream stats
  streams: Record<string, number>;
  setStreams: (streams: Record<string, number>) => void;
  redisConnected: boolean;
  setRedisConnected: (connected: boolean) => void;

  // Process full WebSocket update
  processUpdate: (update: DashboardUpdate) => void;

  // Config state per ingester (for sliders)
  config: Record<string, Record<string, number>>;
  setConfig: (name: string, key: string, value: number) => void;
  resetConfig: (name: string) => void;
}

export const useLogStore = create<LogStore>((set, get) => ({
  // Connection state
  connected: false,
  setConnected: (connected) => set({ connected }),

  // Ingester status
  status: {},
  setStatus: (status) => set({ status }),

  // Log buffers
  logs: {
    world: [],
    ais: [],
    radar: [],
    satellite: [],
    drone: [],
  },
  setLogs: (logs) => set({ logs }),
  appendLogs: (name, newLogs) =>
    set((state) => {
      const existing = state.logs[name] || [];
      const combined = [...existing, ...newLogs].slice(-MAX_LOG_LINES);
      return { logs: { ...state.logs, [name]: combined } };
    }),
  clearLogs: (name) =>
    set((state) => ({ logs: { ...state.logs, [name]: [] } })),

  // Stream stats
  streams: {},
  setStreams: (streams) => set({ streams }),
  redisConnected: false,
  setRedisConnected: (redisConnected) => set({ redisConnected }),

  // Process full WebSocket update
  processUpdate: (update) => {
    const { status, logs, streams, redis_connected } = update;
    set({
      status,
      logs,
      streams,
      redisConnected: redis_connected,
    });
  },

  // Config state for sliders
  config: {
    world: { ships: 500, darkPct: 5.0, rate: 1.0 },
    ais: { ships: 100, rate: 1.0 },
    radar: { tracks: 50, rate: 1.0 },
    satellite: { rate: 0.1 },
    drone: { rate: 0.5 },
  },
  setConfig: (name, key, value) =>
    set((state) => ({
      config: {
        ...state.config,
        [name]: { ...state.config[name], [key]: value },
      },
    })),
  resetConfig: (name) => {
    const defaults: Record<string, Record<string, number>> = {
      world: { ships: 500, darkPct: 5.0, rate: 1.0 },
      ais: { ships: 100, rate: 1.0 },
      radar: { tracks: 50, rate: 1.0 },
      satellite: { rate: 0.1 },
      drone: { rate: 0.5 },
    };
    set((state) => ({
      config: { ...state.config, [name]: defaults[name] },
    }));
  },
}));
