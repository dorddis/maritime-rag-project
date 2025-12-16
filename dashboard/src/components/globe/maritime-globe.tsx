"use client";

/**
 * Maritime Globe Visualization
 *
 * 3D interactive globe showing real-time ship positions.
 * Dark ships shown in red, AIS-enabled ships in cyan.
 * Includes sensor coverage overlays (radar, drone, satellite).
 */

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import type { Ship } from "@/lib/types";
import { fetchFleetShips } from "@/lib/api";

// Dynamic import to avoid SSR issues with Three.js
const Globe = dynamic(() => import("react-globe.gl"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-slate-900 rounded-xl">
      <div className="text-cyan-400 animate-pulse">Loading Globe...</div>
    </div>
  ),
});

// =============================================================================
// SENSOR COVERAGE DATA
// =============================================================================

// Radar stations (from radar_generator.py)
interface RadarStation {
  id: string;
  name: string;
  lat: number;
  lng: number;
  range_nm: number;
  color: string;
}

const RADAR_STATIONS: RadarStation[] = [
  { id: "RAD-MUM", name: "Mumbai Coastal", lat: 18.94, lng: 72.84, range_nm: 50, color: "#ff6b6b" },
  { id: "RAD-CHN", name: "Chennai Coastal", lat: 13.08, lng: 80.27, range_nm: 50, color: "#ff6b6b" },
  { id: "RAD-KOC", name: "Kochi Coastal", lat: 9.93, lng: 76.27, range_nm: 40, color: "#ff6b6b" },
  { id: "RAD-VIZ", name: "Vizag Naval", lat: 17.69, lng: 83.22, range_nm: 80, color: "#ff6b6b" },
  { id: "RAD-KAR", name: "Karwar Naval", lat: 14.81, lng: 74.13, range_nm: 60, color: "#ff6b6b" },
  { id: "RAD-KOL", name: "Kolkata Port", lat: 22.55, lng: 88.35, range_nm: 45, color: "#ff6b6b" },
  { id: "RAD-TUT", name: "Tuticorin Coastal", lat: 8.76, lng: 78.13, range_nm: 40, color: "#ff6b6b" },
];

// Drone patrol zones (5 regions in the Indian Ocean)
interface DroneZone {
  id: string;
  name: string;
  coordinates: [number, number][]; // [lng, lat] pairs for GeoJSON
  color: string;
}

// Drone patrol zones - positioned along actual shipping lanes
const DRONE_PATROL_ZONES: DroneZone[] = [
  {
    id: "DRN-ZONE-1",
    name: "Mumbai-Goa Corridor",
    coordinates: [[71, 20], [75, 20], [75, 14], [71, 14], [71, 20]],
    color: "#1dd1a1",
  },
  {
    id: "DRN-ZONE-2",
    name: "Kerala Coast",
    coordinates: [[74, 14], [78, 14], [78, 8], [74, 8], [74, 14]],
    color: "#1dd1a1",
  },
  {
    id: "DRN-ZONE-3",
    name: "Sri Lanka - Malacca Route",
    coordinates: [[79, 10], [86, 10], [86, 4], [79, 4], [79, 10]],
    color: "#1dd1a1",
  },
  {
    id: "DRN-ZONE-4",
    name: "Chennai-Vizag Coast",
    coordinates: [[79, 18], [85, 18], [85, 12], [79, 12], [79, 18]],
    color: "#1dd1a1",
  },
  {
    id: "DRN-ZONE-5",
    name: "Andaman Strait",
    coordinates: [[91, 12], [97, 12], [97, 6], [91, 6], [91, 12]],
    color: "#1dd1a1",
  },
];

// Satellite ground tracks (simulated orbital paths)
interface SatellitePath {
  id: string;
  name: string;
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: string;
}

const SATELLITE_PATHS: SatellitePath[] = [
  { id: "SAT-S1A", name: "Sentinel-1A", startLat: 25, startLng: 60, endLat: 5, endLng: 100, color: "#feca57" },
  { id: "SAT-S2A", name: "Sentinel-2A", startLat: 20, startLng: 55, endLat: 8, endLng: 95, color: "#feca57" },
  { id: "SAT-PLN", name: "Planet-Dove", startLat: 22, startLng: 70, endLat: 5, endLng: 90, color: "#feca57" },
];

// Ship type colors
const SHIP_COLORS: Record<string, string> = {
  cargo: "#00d9ff",
  tanker: "#ff9f43",
  container: "#00d9ff",
  fishing: "#1dd1a1",
  passenger: "#a55eea",
  naval: "#ff6b6b",
  tug: "#feca57",
  unknown: "#ff5252",
};

// Get ship color based on type and AIS status
function getShipColor(ship: Ship): string {
  if (!ship.ais) return "#ff5252"; // Dark ship = red
  return SHIP_COLORS[ship.type] || "#00d9ff";
}

// Get ship size - small dots for clean visualization
function getShipSize(ship: Ship): number {
  if (!ship.ais) return 0.18; // Dark ships slightly larger (attention)
  const sizes: Record<string, number> = {
    container: 0.15,
    tanker: 0.15,
    cargo: 0.12,
    passenger: 0.12,
    naval: 0.1,
    fishing: 0.08,
    tug: 0.08,
  };
  return sizes[ship.type] || 0.1;
}

interface MaritimeGlobeProps {
  className?: string;
  onShipSelect?: (ship: Ship | null) => void;
}

export function MaritimeGlobe({ className = "", onShipSelect }: MaritimeGlobeProps) {
  const globeRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [ships, setShips] = useState<Ship[]>([]);
  const [selectedShip, setSelectedShip] = useState<Ship | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [globeReady, setGlobeReady] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  // Overlay visibility toggles
  const [showRadar, setShowRadar] = useState(true);
  const [showDrones, setShowDrones] = useState(true);
  const [showSatellites, setShowSatellites] = useState(true);

  // Prepare rings data for radar coverage (convert nm to degrees roughly)
  const radarRingsData = useMemo(() => {
    if (!showRadar) return [];
    return RADAR_STATIONS.map(station => ({
      ...station,
      maxR: station.range_nm / 60, // Approximate conversion (1 degree ~ 60 nm)
      propagationSpeed: 2,
      repeatPeriod: 1500,
    }));
  }, [showRadar]);

  // Prepare polygon data for drone patrol zones (GeoJSON format)
  const dronePolygonsData = useMemo(() => {
    if (!showDrones) return [];
    return DRONE_PATROL_ZONES.map(zone => ({
      ...zone,
      geometry: {
        type: "Polygon" as const,
        coordinates: [zone.coordinates],
      },
    }));
  }, [showDrones]);

  // Prepare arcs data for satellite paths
  const satelliteArcsData = useMemo(() => {
    if (!showSatellites) return [];
    return SATELLITE_PATHS.map(sat => ({
      ...sat,
    }));
  }, [showSatellites]);

  // Track container dimensions
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight,
        });
      }
    };

    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  // Fetch ships periodically
  const fetchShips = useCallback(async () => {
    try {
      const data = await fetchFleetShips();
      if (data.ships) {
        setShips(data.ships);
      }
      setIsLoading(false);
    } catch (err) {
      console.error("Failed to fetch ships:", err);
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchShips();
    const interval = setInterval(fetchShips, 2000); // Update every 2 seconds
    return () => clearInterval(interval);
  }, [fetchShips]);

  // Center globe on Indian Ocean when ready
  useEffect(() => {
    if (globeReady && globeRef.current) {
      // Center on Indian Ocean (where our simulation runs)
      // Lat 15, Lon 82.5 is center of simulation area (5-25 lat, 65-100 lon)
      globeRef.current.pointOfView({
        lat: 15,
        lng: 82.5,
        altitude: 1.8, // Closer zoom for better visibility
      }, 1000); // Animate over 1 second
    }
  }, [globeReady]);

  // Handle globe ready callback
  const handleGlobeReady = useCallback(() => {
    setGlobeReady(true);
  }, []);

  // Handle ship click
  const handleShipClick = useCallback(
    (point: any) => {
      const ship = point as Ship;
      setSelectedShip(ship);
      onShipSelect?.(ship);
    },
    [onShipSelect]
  );

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {dimensions.width > 0 && dimensions.height > 0 && (
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          onGlobeReady={handleGlobeReady}
          // Standard textures (NASA ones have CORS issues)
          globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
          bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
          backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
          showAtmosphere={true}
          atmosphereAltitude={0.15}
          // Ship points
          pointsData={ships}
          pointLat="lat"
          pointLng="lng"
          pointColor={(d: object) => getShipColor(d as Ship)}
          pointAltitude={0.01}
          pointRadius={(d: object) => getShipSize(d as Ship)}
          pointsMerge={false}
          pointLabel={(d: object) => {
            const ship = d as Ship;
            return `
              <div style="
                background: rgba(0,0,0,0.9);
                padding: 10px 14px;
                border-radius: 8px;
                border: 2px solid ${ship.ais ? "#00d9ff" : "#ff5252"};
                font-family: monospace;
                font-size: 13px;
                min-width: 180px;
              ">
                <div style="color: ${ship.ais ? "#00d9ff" : "#ff5252"}; font-weight: bold; font-size: 14px;">
                  ${ship.name}
                </div>
                <div style="color: #666; font-size: 11px; margin-top: 2px;">
                  MMSI: ${ship.mmsi}
                </div>
                <hr style="border: none; border-top: 1px solid #333; margin: 8px 0;" />
                <div style="color: #aaa; margin-top: 6px;">
                  Type: <span style="color: #fff;">${ship.type.toUpperCase()}</span>
                </div>
                <div style="color: #aaa;">
                  Speed: <span style="color: #fff;">${ship.speed.toFixed(1)} kts</span>
                </div>
                <div style="color: #aaa;">
                  Course: <span style="color: #fff;">${ship.course.toFixed(0)}</span>
                </div>
                <div style="margin-top: 6px; padding: 4px 8px; border-radius: 4px; display: inline-block; background: ${ship.ais ? "#00c85333" : "#ff525233"}; color: ${ship.ais ? "#00c853" : "#ff5252"}; font-weight: bold;">
                  ${ship.ais ? "AIS ON" : "DARK SHIP"}
                </div>
              </div>
            `;
          }}
          onPointClick={handleShipClick}
          // Radar coverage rings (pulsing circles)
          ringsData={radarRingsData}
          ringLat="lat"
          ringLng="lng"
          ringMaxRadius="maxR"
          ringPropagationSpeed="propagationSpeed"
          ringRepeatPeriod="repeatPeriod"
          ringColor={() => "rgba(255, 107, 107, 0.6)"}
          ringAltitude={0.001}
          // Drone patrol zones (polygons)
          polygonsData={dronePolygonsData}
          polygonCapColor={() => "rgba(29, 209, 161, 0.15)"}
          polygonSideColor={() => "rgba(29, 209, 161, 0.3)"}
          polygonStrokeColor={() => "#1dd1a1"}
          polygonAltitude={0.002}
          polygonLabel={(d: object) => {
            const zone = d as DroneZone;
            return `<div style="background: rgba(0,0,0,0.8); padding: 6px 10px; border-radius: 4px; border: 1px solid #1dd1a1; font-family: monospace; font-size: 12px; color: #1dd1a1;">${zone.name}</div>`;
          }}
          // Satellite paths (arcs)
          arcsData={satelliteArcsData}
          arcStartLat="startLat"
          arcStartLng="startLng"
          arcEndLat="endLat"
          arcEndLng="endLng"
          arcColor={() => "#feca57"}
          arcDashLength={0.4}
          arcDashGap={0.2}
          arcDashAnimateTime={2000}
          arcStroke={0.5}
          arcAltitudeAutoScale={0.3}
          arcLabel={(d: object) => {
            const sat = d as SatellitePath;
            return `<div style="background: rgba(0,0,0,0.8); padding: 6px 10px; border-radius: 4px; border: 1px solid #feca57; font-family: monospace; font-size: 12px; color: #feca57;">${sat.name}</div>`;
          }}
          // Globe styling
          atmosphereColor="#00d9ff"
          atmosphereAltitude={0.2}
          // Performance
          animateIn={true}
        />
      )}

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 rounded-xl">
          <div className="text-cyan-400 animate-pulse">Loading ships...</div>
        </div>
      )}

      {/* Ship count overlay */}
      <div className="absolute top-4 left-4 bg-slate-900/90 rounded-lg px-4 py-3 border border-slate-700">
        <div className="text-xs text-slate-400 uppercase tracking-wide">Ships on Globe</div>
        <div className="text-2xl font-bold text-cyan-400">{ships.length}</div>
        {ships.length === 0 && (
          <div className="text-xs text-yellow-400 mt-1">Start World Simulator first</div>
        )}
      </div>

      {/* Instructions overlay */}
      {ships.length === 0 && !isLoading && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="bg-slate-900/95 rounded-xl p-6 border border-yellow-500/50 text-center max-w-md">
            <div className="text-yellow-400 text-lg font-bold mb-2">No Ships Detected</div>
            <div className="text-slate-400 text-sm">
              Start the <span className="text-yellow-400 font-semibold">World Simulator</span> in
              the Simulation Controls below to create ships.
            </div>
          </div>
        </div>
      )}

      {/* Selected ship info */}
      {selectedShip && (
        <div className="absolute bottom-4 left-4 bg-slate-900/95 rounded-lg p-4 border border-cyan-500/50 max-w-xs">
          <div className="flex justify-between items-start">
            <div>
              <div className={`text-sm font-bold ${selectedShip.ais ? "text-cyan-400" : "text-red-400"}`}>
                {selectedShip.name}
              </div>
              <div className="text-xs text-slate-400 mt-1">MMSI: {selectedShip.mmsi}</div>
            </div>
            <button
              onClick={() => {
                setSelectedShip(null);
                onShipSelect?.(null);
              }}
              className="text-slate-400 hover:text-white text-sm px-2"
            >
              X
            </button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-slate-500">Type:</span>
              <span className="ml-1 text-slate-300">{selectedShip.type}</span>
            </div>
            <div>
              <span className="text-slate-500">Speed:</span>
              <span className="ml-1 text-slate-300">{selectedShip.speed.toFixed(1)} kts</span>
            </div>
            <div>
              <span className="text-slate-500">Course:</span>
              <span className="ml-1 text-slate-300">{selectedShip.course.toFixed(0)}deg</span>
            </div>
            <div>
              <span className="text-slate-500">Status:</span>
              <span className={`ml-1 ${selectedShip.ais ? "text-green-400" : "text-red-400"}`}>
                {selectedShip.ais ? "AIS ON" : "DARK"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Legend & Layer Controls */}
      <div className="absolute bottom-4 right-4 bg-slate-900/90 rounded-lg px-3 py-2 border border-slate-700 min-w-[180px]">
        <div className="text-xs text-slate-400 mb-2">Legend</div>
        <div className="flex gap-3 text-xs mb-3">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-cyan-400" />
            <span className="text-slate-300">AIS On</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-slate-300">Dark</span>
          </span>
        </div>

        <div className="border-t border-slate-700 pt-2 mt-2">
          <div className="text-xs text-slate-400 mb-2">Sensor Layers</div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={showRadar}
                onChange={(e) => setShowRadar(e.target.checked)}
                className="w-3 h-3 rounded accent-red-500"
              />
              <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
              <span className="text-slate-300">Radar Coverage</span>
            </label>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={showDrones}
                onChange={(e) => setShowDrones(e.target.checked)}
                className="w-3 h-3 rounded accent-green-500"
              />
              <span className="w-2.5 h-2.5 rounded bg-green-400/50 border border-green-400" />
              <span className="text-slate-300">Drone Zones</span>
            </label>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={showSatellites}
                onChange={(e) => setShowSatellites(e.target.checked)}
                className="w-3 h-3 rounded accent-yellow-500"
              />
              <span className="w-6 h-0.5 bg-yellow-400" style={{ borderStyle: "dashed" }} />
              <span className="text-slate-300">Satellite Paths</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}
