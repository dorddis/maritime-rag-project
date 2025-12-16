/**
 * REST API client for Maritime Dashboard
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

// API base URL - defaults to port 8001
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/**
 * Fetch all ingesters with their status
 */
export async function fetchIngesters(): Promise<IngestersStatus> {
  const res = await fetch(`${API_BASE}/api/ingesters`);
  if (!res.ok) throw new Error(`Failed to fetch ingesters: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch single ingester status
 */
export async function fetchIngester(name: string): Promise<IngestersStatus[string]> {
  const res = await fetch(`${API_BASE}/api/ingesters/${name}`);
  if (!res.ok) throw new Error(`Failed to fetch ingester ${name}: ${res.statusText}`);
  return res.json();
}

/**
 * Start an ingester
 */
export async function startIngester(
  name: string,
  args?: Record<string, string>
): Promise<ActionResult> {
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
 * Stop an ingester
 */
export async function stopIngester(name: string): Promise<ActionResult> {
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
 * Stop all ingesters
 */
export async function stopAllIngesters(): Promise<Record<string, ActionResult>> {
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
  const res = await fetch(`${API_BASE}/api/ingesters/${name}/logs?lines=${lines}`);
  if (!res.ok) throw new Error(`Failed to fetch logs: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch logs for all ingesters
 */
export async function fetchAllLogs(): Promise<Record<string, string[]>> {
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
  const res = await fetch(`${API_BASE}/api/fleet/ships`);
  if (!res.ok) throw new Error(`Failed to fetch ships: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch fleet metadata
 */
export async function fetchFleetMetadata(): Promise<FleetMetadata> {
  const res = await fetch(`${API_BASE}/api/fleet/metadata`);
  if (!res.ok) throw new Error(`Failed to fetch fleet metadata: ${res.statusText}`);
  return res.json();
}

// ============ Fusion API ============

/**
 * Fetch fusion engine status
 */
export async function fetchFusionStatus(): Promise<FusionStatus> {
  const res = await fetch(`${API_BASE}/api/fusion/status`);
  if (!res.ok) throw new Error(`Failed to fetch fusion status: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch all fused tracks
 */
export async function fetchFusionTracks(): Promise<FusionTracksData> {
  const res = await fetch(`${API_BASE}/api/fusion/tracks`);
  if (!res.ok) throw new Error(`Failed to fetch fusion tracks: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch all dark ship alerts
 */
export async function fetchDarkShips(): Promise<DarkShipsData> {
  const res = await fetch(`${API_BASE}/api/fusion/dark-ships`);
  if (!res.ok) throw new Error(`Failed to fetch dark ships: ${res.statusText}`);
  return res.json();
}

/**
 * Fetch single track details
 */
export async function fetchFusionTrack(trackId: string): Promise<FusedTrackDetail> {
  const res = await fetch(`${API_BASE}/api/fusion/track/${trackId}`);
  if (!res.ok) throw new Error(`Failed to fetch track ${trackId}: ${res.statusText}`);
  return res.json();
}
