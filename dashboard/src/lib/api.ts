/**
 * REST API client for Maritime Dashboard
 *
 * In demo mode (NEXT_PUBLIC_DEMO_MODE=true), returns mock data
 * instead of calling the real backend. Falls back to mock data
 * if API calls fail and demo mode is enabled.
 */

import type {
  IngestersStatus,
  StreamStats,
  ActionResult,
  StartRequest,
  FleetData,
  FleetMetadata,
  FusionTracksData,
  DarkShipsData,
  FusedTrackDetail,
  FusionStatus,
} from "./types";
import { isDemoMode } from "./demo-mode";
import {
  getMockFleetData,
  MOCK_FLEET_METADATA,
  MOCK_FUSION_STATUS,
  getMockFusionTracks,
  getMockDarkShips,
  MOCK_INGESTERS_STATUS,
  MOCK_STREAM_STATS,
  MOCK_LOGS,
} from "./mock-data";

// API base URL - defaults to port 8001
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/**
 * Fetch all ingesters with their status
 */
export async function fetchIngesters(): Promise<IngestersStatus> {
  if (isDemoMode()) return MOCK_INGESTERS_STATUS;
  const res = await fetch(`${API_BASE}/api/ingesters`);
  if (!res.ok) throw new Error(`Failed to fetch ingesters: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch single ingester status
 */
export async function fetchIngester(name: string): Promise<IngestersStatus[string]> {
  if (isDemoMode()) return MOCK_INGESTERS_STATUS[name] || MOCK_INGESTERS_STATUS.world;
  const res = await fetch(`${API_BASE}/api/ingesters/${name}`);
  if (!res.ok) throw new Error(`Failed to fetch ingester ${name}: ${res.statusText}`);
  return res.json();
}

/**
 * Start an ingester (no-op in demo mode)
 */
export async function startIngester(
  name: string,
  args?: Record<string, string>
): Promise<ActionResult> {
  if (isDemoMode()) {
    return { success: true, message: `[Demo] ${name} ingester simulated start` };
  }
  const body: StartRequest = args ? { args } : {};
  const res = await fetch(`${API_BASE}/api/ingesters/${name}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    return { success: false, error: error.detail || res.statusText };
  }

  return res.json();
}

/**
 * Stop an ingester (no-op in demo mode)
 */
export async function stopIngester(name: string): Promise<ActionResult> {
  if (isDemoMode()) {
    return { success: true, message: `[Demo] ${name} ingester simulated stop` };
  }
  const res = await fetch(`${API_BASE}/api/ingesters/${name}/stop`, {
    method: "POST",
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    return { success: false, error: error.detail || res.statusText };
  }

  return res.json();
}

/**
 * Stop all ingesters (no-op in demo mode)
 */
export async function stopAllIngesters(): Promise<Record<string, ActionResult>> {
  if (isDemoMode()) {
    return { all: { success: true, message: "[Demo] All ingesters simulated stop" } };
  }
  const res = await fetch(`${API_BASE}/api/ingesters/stop-all`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to stop all: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch Redis stream statistics
 */
export async function fetchStreamStats(): Promise<StreamStats> {
  if (isDemoMode()) return MOCK_STREAM_STATS;
  const res = await fetch(`${API_BASE}/api/streams/stats`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch logs for a specific ingester
 */
export async function fetchIngesterLogs(
  name: string,
  lines: number = 50
): Promise<{ name: string; logs: string[] }> {
  if (isDemoMode()) {
    return { name, logs: MOCK_LOGS[name] || [] };
  }
  const res = await fetch(`${API_BASE}/api/ingesters/${name}/logs?lines=${lines}`);
  if (!res.ok) throw new Error(`Failed to fetch logs: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch logs for all ingesters
 */
export async function fetchAllLogs(): Promise<Record<string, string[]>> {
  if (isDemoMode()) return MOCK_LOGS;
  const res = await fetch(`${API_BASE}/api/logs`);
  if (!res.ok) throw new Error(`Failed to fetch logs: ${res.statusText}`);
  return res.json();
}

/**
 * Get WebSocket URL for dashboard updates
 */
export function getWebSocketUrl(): string {
  const wsBase = API_BASE.replace(/^http/, "ws");
  return `${wsBase}/ws/dashboard`;
}

/**
 * Fetch all ships for globe visualization
 */
export async function fetchFleetShips(): Promise<FleetData> {
  if (isDemoMode()) return getMockFleetData();
  try {
    const res = await fetch(`${API_BASE}/api/fleet/ships`);
    if (!res.ok) throw new Error(`Failed to fetch ships: ${res.statusText}`);
    return res.json();
  } catch (err) {
    // Fallback to mock data if backend unreachable
    console.warn("[API] Fleet fetch failed, using mock data:", err);
    return getMockFleetData();
  }
}

/**
 * Fetch fleet metadata
 */
export async function fetchFleetMetadata(): Promise<FleetMetadata> {
  if (isDemoMode()) return MOCK_FLEET_METADATA;
  const res = await fetch(`${API_BASE}/api/fleet/metadata`);
  if (!res.ok) throw new Error(`Failed to fetch fleet metadata: ${res.statusText}`);
  return res.json();
}

// ============ Fusion API ============

/**
 * Fetch fusion engine status
 */
export async function fetchFusionStatus(): Promise<FusionStatus> {
  if (isDemoMode()) return MOCK_FUSION_STATUS;
  const res = await fetch(`${API_BASE}/api/fusion/status`);
  if (!res.ok) throw new Error(`Failed to fetch fusion status: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch all fused tracks
 */
export async function fetchFusionTracks(): Promise<FusionTracksData> {
  if (isDemoMode()) return getMockFusionTracks();
  const res = await fetch(`${API_BASE}/api/fusion/tracks`);
  if (!res.ok) throw new Error(`Failed to fetch fusion tracks: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch all dark ship alerts
 */
export async function fetchDarkShips(): Promise<DarkShipsData> {
  if (isDemoMode()) return getMockDarkShips();
  try {
    const res = await fetch(`${API_BASE}/api/fusion/dark-ships`);
    if (!res.ok) throw new Error(`Failed to fetch dark ships: ${res.statusText}`);
    return res.json();
  } catch (err) {
    console.warn("[API] Dark ships fetch failed, using mock data:", err);
    return getMockDarkShips();
  }
}

/**
 * Fetch single track details
 */
export async function fetchFusionTrack(trackId: string): Promise<FusedTrackDetail> {
  if (isDemoMode()) {
    // Return a synthetic detail for demo
    const tracks = getMockFusionTracks();
    const track = tracks.tracks.find((t) => t.track_id === trackId) || tracks.tracks[0];
    return {
      ...track,
      velocity_north_ms: (track.speed_knots || 0) * 0.5144 * Math.cos((track.course || 0) * Math.PI / 180),
      velocity_east_ms: (track.speed_knots || 0) * 0.5144 * Math.sin((track.course || 0) * Math.PI / 180),
      vessel_length_m: 120 + Math.random() * 200,
      identity_source: track.mmsi ? "AIS" : "UNKNOWN",
      alert_reason: track.is_dark_ship ? "AIS transponder disabled" : null,
      ais_gap_seconds: track.is_dark_ship ? 3600 + Math.random() * 7200 : null,
      correlation_confidence: track.track_quality,
      update_count: Math.floor(Math.random() * 500) + 50,
      created_at: new Date(Date.now() - 7200000).toISOString(),
    } as FusedTrackDetail;
  }
  const res = await fetch(`${API_BASE}/api/fusion/track/${trackId}`);
  if (!res.ok) throw new Error(`Failed to fetch track ${trackId}: ${res.statusText}`);
  return res.json();
}
