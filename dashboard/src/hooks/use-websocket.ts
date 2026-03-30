"use client";

/**
 * WebSocket hook with auto-reconnect for dashboard updates.
 * In demo mode, simulates WebSocket updates with mock data.
 */

import { useEffect, useRef, useCallback } from "react";
import { getWebSocketUrl } from "@/lib/api";
import { isDemoMode } from "@/lib/demo-mode";
import { getMockDashboardUpdate } from "@/lib/mock-data";
import { useLogStore } from "@/stores/log-store";
import type { DashboardUpdate } from "@/lib/types";

const RECONNECT_DELAY = 2000; // 2 seconds
const MAX_RECONNECT_ATTEMPTS = 10;
const DEMO_UPDATE_INTERVAL = 2000; // 2 seconds between mock updates

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const demoIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const connectRef = useRef<() => void>(() => {});

  const { setConnected, processUpdate } = useLogStore();

  // Demo mode: simulate WebSocket with periodic mock updates
  const startDemoMode = useCallback(() => {
    console.log("[WS-Demo] Starting demo mode with simulated updates");
    setConnected(true);

    // Send initial update immediately
    const initialUpdate = getMockDashboardUpdate();
    processUpdate(initialUpdate);

    // Send periodic updates
    demoIntervalRef.current = setInterval(() => {
      const update = getMockDashboardUpdate();
      processUpdate(update);
    }, DEMO_UPDATE_INTERVAL);
  }, [setConnected, processUpdate]);

  const stopDemoMode = useCallback(() => {
    if (demoIntervalRef.current) {
      clearInterval(demoIntervalRef.current);
      demoIntervalRef.current = null;
    }
    setConnected(false);
  }, [setConnected]);

  // Real WebSocket connection
  const connect = useCallback(() => {
    if (isDemoMode()) {
      startDemoMode();
      return;
    }

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    const url = getWebSocketUrl();
    console.log("[WS] Connecting to:", url);

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected");
      setConnected(true);
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const data: DashboardUpdate = JSON.parse(event.data);
        if (data.type === "update") {
          processUpdate(data);
        }
      } catch (err) {
        console.error("[WS] Failed to parse message:", err);
      }
    };

    ws.onerror = (error) => {
      console.error("[WS] Error:", error);
    };

    ws.onclose = (event) => {
      console.log("[WS] Disconnected:", event.code, event.reason);
      setConnected(false);
      wsRef.current = null;

      // Auto-reconnect with backoff
      if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = RECONNECT_DELAY * Math.pow(1.5, reconnectAttempts.current);
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current + 1})`);
        reconnectAttempts.current++;

        reconnectTimeoutRef.current = setTimeout(() => {
          connectRef.current();
        }, delay);
      } else {
        console.error("[WS] Max reconnection attempts reached");
      }
    };
  }, [setConnected, processUpdate, startDemoMode]);

  // Keep ref in sync so reconnect can call latest version
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const disconnect = useCallback(() => {
    if (isDemoMode()) {
      stopDemoMode();
      return;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setConnected(false);
    reconnectAttempts.current = MAX_RECONNECT_ATTEMPTS; // Prevent auto-reconnect
  }, [setConnected, stopDemoMode]);

  useEffect(() => {
    connect();

    return () => {
      if (demoIntervalRef.current) {
        clearInterval(demoIntervalRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    connect,
    disconnect,
  };
}
