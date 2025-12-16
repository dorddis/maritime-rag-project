/**
 * TypeScript interfaces for Maritime Dashboard
 */

// Ship data for globe visualization
export interface Ship {
  mmsi: string;
  name: string;
  type: string;
  lat: number;
  lng: number;
  speed: number;
  course: number;
  ais: boolean;  // true = AIS on, false = dark ship
}

// Fleet data response
export interface FleetData {
  ships: Ship[];
  count: number;
  dark_count: number;
  error?: string;
}

// Fleet metadata
export interface FleetMetadata {
  total_ships: number;
  dark_ships: number;
  initialized_at: string;
  last_update: string;
  bounds: {
    lat_min: number;
    lat_max: number;
    lon_min: number;
    lon_max: number;
  };
  error?: string;
}

// ============ Fusion Types ============

// Unified track from fusion engine
export interface FusedTrack {
  track_id: string;
  latitude: number;
  longitude: number;
  speed_knots: number | null;
  course: number | null;
  mmsi: string | null;
  ship_name: string | null;
  vessel_type: string | null;
  status: "TENTATIVE" | "CONFIRMED" | "COASTING" | "DROPPED";
  is_dark_ship: boolean;
  dark_ship_confidence: number;
  contributing_sensors: string[];
  track_quality: number;
  position_uncertainty_m: number;
  updated_at: string;
}

// Detailed track info (from single track endpoint)
export interface FusedTrackDetail extends FusedTrack {
  velocity_north_ms: number;
  velocity_east_ms: number;
  vessel_length_m: number | null;
  identity_source: "AIS" | "DRONE" | "UNKNOWN";
  alert_reason: string | null;
  ais_gap_seconds: number | null;
  correlation_confidence: number;
  update_count: number;
  created_at: string;
}

// Fusion tracks response
export interface FusionTracksData {
  tracks: FusedTrack[];
  count: number;
  dark_count: number;
  error?: string;
}

// Dark ship alert
export interface DarkShipAlert {
  alert_id: string;
  track_id: string;
  latitude: number;
  longitude: number;
  confidence: number;
  alert_reason: string;
  detected_by: string[];
  timestamp: string;
}

// Dark ships response
export interface DarkShipsData {
  dark_ships: DarkShipAlert[];
  count: number;
  error?: string;
}

// Fusion status
export interface FusionStatus {
  running: boolean;
  active_tracks: number;
  dark_ships: number;
  correlations_made?: number;
  messages_processed?: number;
  tracks_created?: number;
  tracks_dropped?: number;
  dark_ships_flagged?: number;
  errors?: number;
  uptime_seconds?: number;
  rate_hz?: number;
  last_update?: string;
  error?: string;
  message?: string;
}

// Ingester configuration from backend
export interface IngesterConfig {
  name: string;
  description: string;
  running: boolean;
  redis_stream: string;
  status_key: string;
  pid?: number;
  started_at?: string;
  args?: Record<string, string>;
}

// All ingesters status
export type IngestersStatus = Record<string, IngesterConfig>;

// Stream statistics
export interface StreamStats {
  streams: Record<string, number>;
  redis_connected: boolean;
  error?: string;
}

// WebSocket update message
export interface DashboardUpdate {
  type: "update";
  status: IngestersStatus;
  logs: Record<string, string[]>;
  streams: Record<string, number>;
  fleet: { total_ships: number; dark_ships: number };
  fusion: FusionStatus;
  redis_connected: boolean;
}

// Ingester start request
export interface StartRequest {
  args?: Record<string, string>;
}

// Ingester action result
export interface ActionResult {
  success: boolean;
  message?: string;
  error?: string;
  pid?: number;
}

// Ingester-specific config options
export interface IngesterConfigOptions {
  ais: {
    ships: number;
    rate: number;
  };
  radar: {
    tracks: number;
    rate: number;
  };
  satellite: {
    rate: number;
  };
  drone: {
    rate: number;
  };
}

// Technical details for each ingester
export interface TechDetail {
  label: string;
  value: string;
}

// Ingester metadata for UI
export const INGESTER_METADATA: Record<
  string,
  {
    displayName: string;
    format: string;
    color: string;
    icon: string;
    techDetails: TechDetail[];
  }
> = {
  world: {
    displayName: "World Simulator",
    format: "Ground Truth",
    color: "#feca57",
    icon: "Globe",
    techDetails: [
      { label: "Data Store", value: "**Redis Hashes** with atomic updates - production-grade ship state management" },
      { label: "Geography", value: "**1km GLOBE dataset** ocean validation - same as real maritime routing systems" },
      { label: "Shipping Lanes", value: "**7 realistic trade routes** across Indian Ocean - mirrors actual vessel traffic" },
      { label: "Dark Ships", value: "**Random AIS toggle events** - simulates vessels turning off transponders (IUU fishing)" },
    ],
  },
  ais: {
    displayName: "AIS",
    format: "NMEA 0183",
    color: "#00d9ff",
    icon: "Ship",
    techDetails: [
      { label: "Protocol", value: "**NMEA 0183 standard** - same format used by real AIS transponders worldwide" },
      { label: "Message Types", value: "**Type 1/2/3** (position reports), **Type 5** (vessel metadata), **Type 18** (Class B)" },
      { label: "Encoding", value: "**6-bit ASCII armoring** with XOR checksum - industry-standard bit packing" },
      { label: "Limitation", value: "**Only detects AIS-ON ships** - dark vessels are invisible (why fusion matters)" },
    ],
  },
  radar: {
    displayName: "Radar",
    format: "Binary Protocol",
    color: "#ff6b6b",
    icon: "Radio",
    techDetails: [
      { label: "Protocol", value: "**Binary struct packing** (big-endian) - mirrors real coastal radar telemetry" },
      { label: "Coverage", value: "**7 coastal stations** with 40-80nm range - realistic Indian Ocean network" },
      { label: "Noise Model", value: "**Distance-based detection probability** with position/speed jitter - production-grade accuracy" },
      { label: "Advantage", value: "**Detects ALL ships** including dark vessels - key complement to AIS gaps" },
    ],
  },
  satellite: {
    displayName: "Satellite",
    format: "GeoJSON",
    color: "#feca57",
    icon: "Satellite",
    techDetails: [
      { label: "Format", value: "**GeoJSON FeatureCollection** - standard geospatial format for real satellite feeds" },
      { label: "Sensors", value: "**SAR (Sentinel-1)** + **Optical (Maxar/Planet)** - multi-modal like actual programs" },
      { label: "SAR Advantage", value: "**92% detection through clouds** - all-weather capability that optical lacks" },
      { label: "Use Case", value: "**Wide-area dark ship detection** - ideal for finding vessels hiding from AIS" },
    ],
  },
  drone: {
    displayName: "Drone",
    format: "CV JSON",
    color: "#1dd1a1",
    icon: "Plane",
    techDetails: [
      { label: "Model", value: "**YOLOv8 maritime model** with 50-200ms inference - real-time object detection" },
      { label: "Output", value: "**Bounding boxes + geo-projection** - converts pixel coords to lat/lon positions" },
      { label: "Tracking", value: "**Persistent IDs across frames** (T001-T050) - maintains vessel identity over time" },
      { label: "Fleet", value: "**3 drones** patrolling **5 zones** (24-75km swath) - realistic ISR deployment" },
    ],
  },
  fusion: {
    displayName: "Data Fusion",
    format: "Unified Tracks",
    color: "#a855f7",
    icon: "Layers",
    techDetails: [
      { label: "Algorithm", value: "**Gated Global Nearest Neighbor (GNN)** - Hungarian algorithm for optimal assignment" },
      { label: "Position Fusion", value: "**Inverse variance weighting** - combines measurements by accuracy" },
      { label: "Correlation", value: "**3-sigma gates** with kinematic consistency scoring - adaptive thresholds" },
      { label: "Dark Ship Detection", value: "**Multi-sensor correlation** - flags vessels seen by radar/satellite but no AIS" },
    ],
  },
};

// Default config values for sliders
export const DEFAULT_CONFIG = {
  world: { ships: 500, darkPct: 5, speedMult: 60 },
  ais: { ships: 100, rate: 1.0 },
  radar: { tracks: 50, rate: 1.0, rangePct: 100 },
  satellite: { rate: 0.1, cloudCover: 20, vesselsPerPass: 50 },
  drone: { rate: 0.5, detectionsPerFrame: 5 },
  fusion: { rate: 2.0 },
};

// Config slider ranges
export const CONFIG_RANGES = {
  world: {
    ships: { min: 100, max: 1000, step: 50 },
    darkPct: { min: 0, max: 30, step: 1 },
    speedMult: { min: 1, max: 120, step: 1 },
  },
  ais: {
    ships: { min: 1, max: 500, step: 1 },
    rate: { min: 0.1, max: 10, step: 0.1 },
  },
  radar: {
    tracks: { min: 1, max: 200, step: 1 },
    rate: { min: 0.1, max: 10, step: 0.1 },
    rangePct: { min: 50, max: 150, step: 5 },
  },
  satellite: {
    rate: { min: 0.01, max: 1, step: 0.01 },
    cloudCover: { min: 0, max: 80, step: 5 },
    vesselsPerPass: { min: 20, max: 100, step: 5 },
  },
  drone: {
    rate: { min: 0.1, max: 5, step: 0.1 },
    detectionsPerFrame: { min: 1, max: 10, step: 1 },
  },
  fusion: {
    rate: { min: 0.5, max: 10, step: 0.5 },
  },
};
