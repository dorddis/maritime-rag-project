/**
 * Zustand store for log buffers and real-time state
 */

import { create } from "zustand";
import type { IngestersStatus, DashboardUpdate, FusionStatus } from "@/lib/types";

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

  // Fleet stats
  fleet: { total_ships: number; dark_ships: number };
  setFleet: (fleet: { total_ships: number; dark_ships: number }) => void;

  // Fusion state
  fusion: FusionStatus;
  setFusion: (fusion: FusionStatus) => void;

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
    fusion: [],
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

  // Fleet stats
  fleet: { total_ships: 0, dark_ships: 0 },
  setFleet: (fleet) => set({ fleet }),

  // Fusion state
  fusion: { running: false, active_tracks: 0, dark_ships: 0 },
  setFusion: (fusion) => set({ fusion }),

  // Process full WebSocket update
  processUpdate: (update) => {
    const { status, logs, streams, fleet, fusion, redis_connected } = update;
    set({
      status,
      logs,
      streams,
      fleet: fleet || { total_ships: 0, dark_ships: 0 },
      fusion: fusion || { running: false, active_tracks: 0, dark_ships: 0 },
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
    fusion: { rate: 2.0 },
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
      fusion: { rate: 2.0 },
    };
    set((state) => ({
      config: { ...state.config, [name]: defaults[name] },
    }));
  },
}));
