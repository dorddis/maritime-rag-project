/**
 * Mock data for demo mode
 *
 * Realistic ship positions, dark ship alerts, sensor coverage,
 * and system state for the Maritime Surveillance Dashboard.
 * Ships are distributed across Indian Ocean shipping lanes.
 */

import type {
  Ship,
  FleetData,
  FleetMetadata,
  FusionTracksData,
  DarkShipsData,
  DarkShipAlert,
  FusedTrack,
  FusionStatus,
  IngestersStatus,
  StreamStats,
  DashboardUpdate,
} from "./types";

// =============================================================================
// SHIP NAME GENERATORS
// =============================================================================

const SHIP_PREFIXES = [
  "MV", "SS", "MT", "MSC", "CMA", "OOCL", "NYK", "MOL", "PIL", "ZIM",
];

const SHIP_NAMES = [
  "Evergreen Fortune", "Maersk Sealand", "Cosco Harmony", "Yang Ming Unity",
  "Hapag Express", "Pacific Voyager", "Indian Enterprise", "Ocean Pioneer",
  "Arabian Star", "Bengal Trader", "Malabar Coast", "Tamil Nadu Pride",
  "Gujarat Merchant", "Mumbai Express", "Chennai Gateway", "Kochi Navigator",
  "Vizag Mariner", "Andaman Explorer", "Lakshadweep Spirit", "Deccan Horizon",
  "Konkan Breeze", "Goa Pearl", "Maldives Dream", "Colombo Connect",
  "Singapore Bridge", "Malacca Transit", "Hormuz Carrier", "Suez Runner",
  "Cape Hope", "Agulhas Current", "Mozambique Channel", "Seychelles Star",
  "Reunion Tide", "Madagascar Wave", "Zanzibar Wind", "Mombasa Dawn",
  "Aden Gateway", "Socotra Passage", "Oman Trader", "Dubai Commerce",
  "Karachi Venture", "Mundra Giant", "Kandla Spirit", "Paradip Sentinel",
  "Haldia Progress", "Tuticorin Coral", "Mangalore Spice", "New Mangalore",
  "Paradiso Shipping", "Blue Whale Logistics",
];

const VESSEL_TYPES = [
  "cargo", "tanker", "container", "fishing", "passenger", "naval", "tug",
];

// =============================================================================
// SHIPPING LANES (Indian Ocean realistic routes)
// =============================================================================

interface ShippingLane {
  name: string;
  waypoints: [number, number][]; // [lat, lng] pairs
}

const SHIPPING_LANES: ShippingLane[] = [
  {
    name: "Mumbai-Singapore",
    waypoints: [[18.9, 72.8], [15.0, 75.0], [10.0, 78.0], [6.0, 82.0], [3.0, 90.0], [1.3, 103.8]],
  },
  {
    name: "Mumbai-Aden",
    waypoints: [[18.9, 72.8], [17.0, 68.0], [15.0, 58.0], [12.8, 45.0]],
  },
  {
    name: "Chennai-Malacca",
    waypoints: [[13.1, 80.3], [10.0, 82.0], [7.0, 87.0], [4.0, 95.0], [2.5, 101.0]],
  },
  {
    name: "Kolkata-Singapore",
    waypoints: [[22.5, 88.3], [18.0, 87.0], [12.0, 85.0], [7.0, 90.0], [1.3, 103.8]],
  },
  {
    name: "Kochi-Maldives-Seychelles",
    waypoints: [[9.9, 76.3], [6.0, 73.0], [2.0, 72.0], [-4.6, 55.5]],
  },
  {
    name: "Vizag-Andaman",
    waypoints: [[17.7, 83.2], [14.0, 85.0], [11.5, 92.7]],
  },
  {
    name: "Coast Guard Patrol",
    waypoints: [[20.0, 70.0], [15.0, 73.0], [10.0, 76.0], [8.0, 77.0]],
  },
];

// =============================================================================
// HELPER: Interpolate along a shipping lane with jitter
// =============================================================================

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function randomJitter(base: number, range: number): number {
  return base + (Math.random() - 0.5) * range;
}

function positionAlongLane(lane: ShippingLane, t: number): [number, number] {
  const waypoints = lane.waypoints;
  const totalSegments = waypoints.length - 1;
  const scaledT = t * totalSegments;
  const segIndex = Math.min(Math.floor(scaledT), totalSegments - 1);
  const segT = scaledT - segIndex;

  const lat = lerp(waypoints[segIndex][0], waypoints[segIndex + 1][0], segT);
  const lng = lerp(waypoints[segIndex][1], waypoints[segIndex + 1][1], segT);

  // Add a small random jitter (ships don't follow exact lines)
  return [randomJitter(lat, 1.5), randomJitter(lng, 1.5)];
}

// =============================================================================
// GENERATE MOCK SHIPS
// =============================================================================

function generateShips(count: number, darkPercentage: number = 5): Ship[] {
  const ships: Ship[] = [];
  const darkCount = Math.floor(count * (darkPercentage / 100));

  for (let i = 0; i < count; i++) {
    const lane = SHIPPING_LANES[i % SHIPPING_LANES.length];
    const t = Math.random();
    const [lat, lng] = positionAlongLane(lane, t);
    const isDark = i < darkCount;
    const vesselType = VESSEL_TYPES[i % VESSEL_TYPES.length];
    const namePrefix = SHIP_PREFIXES[i % SHIP_PREFIXES.length];
    const nameSuffix = SHIP_NAMES[i % SHIP_NAMES.length];

    ships.push({
      mmsi: String(200000000 + i * 137 + Math.floor(Math.random() * 100)),
      name: `${namePrefix} ${nameSuffix}`,
      type: vesselType,
      lat: parseFloat(lat.toFixed(5)),
      lng: parseFloat(lng.toFixed(5)),
      speed: parseFloat((Math.random() * 18 + 2).toFixed(1)),
      course: parseFloat((Math.random() * 360).toFixed(0)),
      ais: !isDark,
    });
  }

  return ships;
}

// =============================================================================
// STATIC MOCK DATA (generated once on import)
// =============================================================================

// Seeded random - use a fixed seed for reproducible positions across hot reloads
// but still realistic distribution
let _cachedShips: Ship[] | null = null;

function getShips(): Ship[] {
  if (!_cachedShips) {
    _cachedShips = generateShips(247, 6);
  }
  return _cachedShips;
}

// Allow refreshing ships with slight position perturbation (simulates movement)
let _perturbCounter = 0;

function getPerturbedShips(): Ship[] {
  const base = getShips();
  _perturbCounter++;

  // Every call, slightly move each ship along its course
  return base.map((ship) => {
    const courseRad = (ship.course * Math.PI) / 180;
    const speedFactor = ship.speed * 0.00002 * _perturbCounter;
    return {
      ...ship,
      lat: parseFloat((ship.lat + Math.cos(courseRad) * speedFactor * (0.8 + Math.random() * 0.4)).toFixed(5)),
      lng: parseFloat((ship.lng + Math.sin(courseRad) * speedFactor * (0.8 + Math.random() * 0.4)).toFixed(5)),
    };
  });
}

// =============================================================================
// DARK SHIP ALERTS
// =============================================================================

function generateDarkShipAlerts(): DarkShipAlert[] {
  const darkShips = getShips().filter((s) => !s.ais);
  const now = new Date();

  return darkShips.slice(0, 12).map((ship, i) => {
    const detectedBy: string[] = [];
    // Dark ships are detected by non-AIS sensors
    if (Math.random() > 0.3) detectedBy.push("radar");
    if (Math.random() > 0.5) detectedBy.push("satellite");
    if (Math.random() > 0.6) detectedBy.push("drone");
    if (detectedBy.length === 0) detectedBy.push("radar"); // At least one

    const reasons = [
      "AIS transponder disabled - vessel detected by radar only",
      "No AIS signal for 6+ hours, radar/satellite correlation",
      "Unidentified vessel in restricted zone - drone surveillance",
      "AIS spoofing suspected - position mismatch with radar",
      "Vessel departed AIS coverage, satellite re-detected",
      "Dark transit through shipping lane - multiple sensor hits",
    ];

    return {
      alert_id: `ALT-${String(1000 + i).padStart(4, "0")}`,
      track_id: `TRK-${ship.mmsi}-${String(i).padStart(3, "0")}`,
      latitude: ship.lat,
      longitude: ship.lng,
      confidence: parseFloat((0.6 + Math.random() * 0.35).toFixed(2)),
      alert_reason: reasons[i % reasons.length],
      detected_by: detectedBy,
      timestamp: new Date(now.getTime() - i * 45000).toISOString(), // Stagger by 45 seconds
    };
  });
}

// =============================================================================
// FUSED TRACKS
// =============================================================================

function generateFusedTracks(): FusedTrack[] {
  const ships = getShips();
  const now = new Date();

  return ships.slice(0, 80).map((ship, i) => ({
    track_id: `TRK-${ship.mmsi}-${String(i).padStart(3, "0")}`,
    latitude: ship.lat,
    longitude: ship.lng,
    speed_knots: ship.speed,
    course: ship.course,
    mmsi: ship.ais ? ship.mmsi : null,
    ship_name: ship.ais ? ship.name : null,
    vessel_type: ship.type,
    status: (["CONFIRMED", "CONFIRMED", "CONFIRMED", "TENTATIVE", "COASTING"] as const)[i % 5],
    is_dark_ship: !ship.ais,
    dark_ship_confidence: ship.ais ? 0 : parseFloat((0.6 + Math.random() * 0.35).toFixed(2)),
    contributing_sensors: ship.ais
      ? ["ais", "radar"]
      : ["radar", ...(Math.random() > 0.5 ? ["satellite"] : []), ...(Math.random() > 0.7 ? ["drone"] : [])],
    track_quality: parseFloat((0.5 + Math.random() * 0.5).toFixed(2)),
    position_uncertainty_m: ship.ais ? 10 + Math.random() * 50 : 200 + Math.random() * 2000,
    updated_at: new Date(now.getTime() - Math.random() * 60000).toISOString(),
  }));
}

// =============================================================================
// EXPORT: Mock API responses
// =============================================================================

export const MOCK_FLEET_DATA: FleetData = {
  ships: getShips(),
  count: getShips().length,
  dark_count: getShips().filter((s) => !s.ais).length,
};

export function getMockFleetData(): FleetData {
  const ships = getPerturbedShips();
  return {
    ships,
    count: ships.length,
    dark_count: ships.filter((s) => !s.ais).length,
  };
}

export const MOCK_FLEET_METADATA: FleetMetadata = {
  total_ships: getShips().length,
  dark_ships: getShips().filter((s) => !s.ais).length,
  initialized_at: new Date(Date.now() - 3600000).toISOString(),
  last_update: new Date().toISOString(),
  bounds: {
    lat_min: -5,
    lat_max: 25,
    lon_min: 45,
    lon_max: 105,
  },
};

export const MOCK_FUSION_STATUS: FusionStatus = {
  running: true,
  active_tracks: 80,
  dark_ships: getShips().filter((s) => !s.ais).length,
  correlations_made: 14832,
  messages_processed: 287451,
  tracks_created: 312,
  tracks_dropped: 47,
  dark_ships_flagged: 23,
  errors: 0,
  uptime_seconds: 3847,
  rate_hz: 2.0,
  last_update: new Date().toISOString(),
};

export function getMockFusionTracks(): FusionTracksData {
  const tracks = generateFusedTracks();
  return {
    tracks,
    count: tracks.length,
    dark_count: tracks.filter((t) => t.is_dark_ship).length,
  };
}

export function getMockDarkShips(): DarkShipsData {
  const alerts = generateDarkShipAlerts();
  return {
    dark_ships: alerts,
    count: alerts.length,
  };
}

export const MOCK_INGESTERS_STATUS: IngestersStatus = {
  world: {
    name: "world",
    description: "World Simulator - Ground truth ship positions",
    running: true,
    redis_stream: "world:state",
    status_key: "maritime:fleet:metadata",
    pid: 12847,
    started_at: new Date(Date.now() - 3600000).toISOString(),
  },
  ais: {
    name: "ais",
    description: "AIS receiver - NMEA 0183 protocol decoder",
    running: true,
    redis_stream: "ais:positions",
    status_key: "ingester:ais:status",
    pid: 12901,
    started_at: new Date(Date.now() - 3500000).toISOString(),
  },
  radar: {
    name: "radar",
    description: "Coastal radar network - 7 stations, binary protocol",
    running: true,
    redis_stream: "radar:contacts",
    status_key: "ingester:radar:status",
    pid: 12955,
    started_at: new Date(Date.now() - 3400000).toISOString(),
  },
  satellite: {
    name: "satellite",
    description: "Satellite imagery processor - SAR + Optical",
    running: true,
    redis_stream: "satellite:detections",
    status_key: "ingester:satellite:status",
    pid: 13012,
    started_at: new Date(Date.now() - 3300000).toISOString(),
  },
  drone: {
    name: "drone",
    description: "Drone fleet processor - YOLOv8 maritime detection",
    running: true,
    redis_stream: "drone:detections",
    status_key: "ingester:drone:status",
    pid: 13078,
    started_at: new Date(Date.now() - 3200000).toISOString(),
  },
  fusion: {
    name: "fusion",
    description: "Multi-sensor fusion engine - correlates all sensor data",
    running: true,
    redis_stream: "fusion:tracks",
    status_key: "ingester:fusion:status",
    pid: 13142,
    started_at: new Date(Date.now() - 3100000).toISOString(),
  },
};

export const MOCK_STREAM_STATS: StreamStats = {
  streams: {
    "ais:positions": 18742,
    "radar:contacts": 9283,
    "satellite:detections": 1247,
    "drone:detections": 3891,
  },
  redis_connected: true,
};

// Mock logs - realistic output from each ingester
export const MOCK_LOGS: Record<string, string[]> = {
  world: [
    "[INFO] World simulator initialized with 247 ships",
    "[INFO] Dark ship percentage: 6%",
    "[INFO] Speed multiplier: 60x (1 real sec = 1 sim min)",
    "[INFO] Shipping lanes loaded: 7 routes across Indian Ocean",
    "[INFO] Ship MV Evergreen Fortune entered Mumbai-Singapore lane",
    "[INFO] Dark event: MT Cosco Harmony disabled AIS transponder",
    "[INFO] Fleet positions updated - 247 ships active",
    "[INFO] 15 dark ships currently in simulation",
  ],
  ais: [
    "[INFO] AIS decoder started on ais:positions stream",
    "[INFO] Processing NMEA 0183 Type 1 position report",
    "[INFO] Decoded 142 AIS messages (5% packet loss simulated)",
    "[INFO] Type 5 static data: MV Maersk Sealand, MMSI 200000137",
    "[INFO] Position update: 18.94N, 72.84E - speed 14.2 kts",
    "[INFO] Class B transponder detected: fishing vessel",
    "[INFO] AIS gap detected for MMSI 200001507 (>30 min silence)",
  ],
  radar: [
    "[INFO] Radar network online - 7 coastal stations active",
    "[INFO] RAD-MUM (Mumbai): 23 contacts in range (50nm)",
    "[INFO] RAD-VIZ (Vizag Naval): 18 contacts in range (80nm)",
    "[INFO] Binary protocol: big-endian struct unpacked",
    "[INFO] Distance-based detection: P=0.94 at 30nm",
    "[INFO] Unidentified contact at 15.23N, 74.56E - no AIS correlation",
    "[WARN] RAD-KOL: High sea clutter detected, filtering enabled",
  ],
  satellite: [
    "[INFO] Satellite processor started - SAR + Optical modes",
    "[INFO] Sentinel-1A SAR pass: 47 vessels detected (clouds ignored)",
    "[INFO] Sentinel-2A optical pass: 31 vessels (8% cloud cover impact)",
    "[INFO] Planet-Dove constellation: 12 detections this orbit",
    "[INFO] GeoJSON FeatureCollection generated with 90 features",
    "[INFO] Dark vessel candidate at 8.45N, 76.12E - SAR only detection",
  ],
  drone: [
    "[INFO] Drone fleet processor active - 3 drones, 5 patrol zones",
    "[INFO] DRN-01 patrolling Mumbai-Goa Corridor (Zone 1)",
    "[INFO] YOLOv8 inference: 87ms per frame, 4 vessels detected",
    "[INFO] Bounding box geo-projected: T023 at 16.5N, 73.2E",
    "[INFO] DRN-02 zone transition: Kerala Coast -> Sri Lanka route",
    "[INFO] Persistent tracking: T041 maintained across 34 frames",
    "[INFO] Unidentified vessel T047 in Andaman Strait - flagged",
  ],
  fusion: [
    "[INFO] Fusion engine started at 2.0 Hz processing rate",
    "[INFO] GNN correlation: 142 AIS + 87 radar + 47 satellite + 31 drone",
    "[INFO] Track TRK-200001507-004: CONFIRMED (3 sensors agree)",
    "[INFO] Dark ship flagged: TRK-200000274-001 (radar+satellite, no AIS)",
    "[INFO] Inverse variance weighting: position uncertainty 45m",
    "[INFO] 3-sigma gate passed for 89% of measurement pairs",
    "[INFO] Active tracks: 80 | Dark ships: 15 | Correlations: 14,832",
    "[WARN] Track TRK-200002190-012 COASTING - no updates for 120s",
  ],
};

// =============================================================================
// MOCK DASHBOARD UPDATE (for WebSocket simulation)
// =============================================================================

const _streamCounters: Record<string, number> = {
  "ais:positions": 18742,
  "radar:contacts": 9283,
  "satellite:detections": 1247,
  "drone:detections": 3891,
};

let _correlationCounter = 14832;

export function getMockDashboardUpdate(): DashboardUpdate {
  // Increment stream counters to simulate activity
  _streamCounters["ais:positions"] += Math.floor(Math.random() * 8) + 2;
  _streamCounters["radar:contacts"] += Math.floor(Math.random() * 4) + 1;
  _streamCounters["satellite:detections"] += Math.random() > 0.7 ? 1 : 0;
  _streamCounters["drone:detections"] += Math.floor(Math.random() * 2);
  _correlationCounter += Math.floor(Math.random() * 5) + 1;

  const ships = getShips();
  const darkCount = ships.filter((s) => !s.ais).length;

  return {
    type: "update",
    status: MOCK_INGESTERS_STATUS,
    logs: MOCK_LOGS,
    streams: { ..._streamCounters },
    fleet: { total_ships: ships.length, dark_ships: darkCount },
    fusion: {
      ...MOCK_FUSION_STATUS,
      correlations_made: _correlationCounter,
      last_update: new Date().toISOString(),
    },
    redis_connected: true,
  };
}
