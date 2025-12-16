"use client";

/**
 * Dark Ships Alert Panel
 *
 * Real-time panel showing flagged dark ships detected by the fusion engine.
 * Shows vessels with AIS turned off or never had AIS.
 */

import { useState, useEffect } from "react";
import { useLogStore } from "@/stores/log-store";
import { fetchDarkShips } from "@/lib/api";
import type { DarkShipAlert } from "@/lib/types";
import {
  AlertTriangle,
  Eye,
  Radio,
  Satellite,
  Plane,
  Ship,
  RefreshCw,
  ChevronRight,
  Layers,
} from "lucide-react";

// Map sensor types to icons
const SENSOR_ICONS: Record<string, typeof Ship> = {
  ais: Ship,
  radar: Radio,
  satellite: Satellite,
  drone: Plane,
};

interface DarkShipsPanelProps {
  onSelectShip?: (lat: number, lng: number, trackId: string) => void;
  className?: string;
}

export function DarkShipsPanel({ onSelectShip, className = "" }: DarkShipsPanelProps) {
  const { fusion, status, redisConnected } = useLogStore();
  const [darkShips, setDarkShips] = useState<DarkShipAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Fetch dark ships periodically
  useEffect(() => {
    const fetchData = async () => {
      if (!redisConnected) return;

      try {
        setLoading(true);
        const data = await fetchDarkShips();
        if (data.error) {
          setError(data.error);
        } else {
          setDarkShips(data.dark_ships);
          setError(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [redisConnected]);

  const fusionRunning = status.fusion?.running ?? false;

  // Format timestamp
  const formatTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return timestamp;
    }
  };

  // Get confidence color
  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return "text-red-400";
    if (confidence >= 0.6) return "text-orange-400";
    return "text-yellow-400";
  };

  return (
    <div className={`bg-slate-900/90 rounded-xl border border-slate-700 p-4 space-y-4 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-purple-400 uppercase tracking-wide flex items-center gap-2">
          <Layers className="w-4 h-4" />
          Dark Ship Alerts
        </h3>
        <div className="flex items-center gap-2">
          {loading && <RefreshCw className="w-3 h-3 text-slate-400 animate-spin" />}
          <div
            className={`w-2 h-2 rounded-full ${
              fusionRunning ? "bg-green-400 animate-pulse" : "bg-slate-600"
            }`}
          />
          <span className="text-xs text-slate-400">
            {fusionRunning ? "Fusion Active" : "Fusion Offline"}
          </span>
        </div>
      </div>

      {/* Fusion Stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-slate-800 rounded-lg p-2 text-center">
          <div className="text-xl font-bold text-purple-400">{fusion.active_tracks}</div>
          <div className="text-xs text-slate-400">Tracks</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-2 text-center">
          <div className="text-xl font-bold text-red-400">{fusion.dark_ships}</div>
          <div className="text-xs text-slate-400">Dark Ships</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-2 text-center">
          <div className="text-xl font-bold text-cyan-400">
            {fusion.correlations_made?.toLocaleString() ?? 0}
          </div>
          <div className="text-xs text-slate-400">Correlations</div>
        </div>
      </div>

      {/* Dark Ships List */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide flex items-center gap-1">
          <AlertTriangle className="w-3 h-3 text-red-400" />
          Recent Alerts ({darkShips.length})
        </h4>

        {error && (
          <div className="text-xs text-red-400 bg-red-900/20 rounded px-2 py-1">{error}</div>
        )}

        {!fusionRunning && !error && (
          <div className="text-xs text-slate-500 text-center py-4">
            Start the Fusion ingester to detect dark ships
          </div>
        )}

        {fusionRunning && darkShips.length === 0 && !error && (
          <div className="text-xs text-slate-500 text-center py-4">
            No dark ships detected yet
          </div>
        )}

        <div className="space-y-1 max-h-64 overflow-y-auto">
          {darkShips.map((ship) => (
            <div
              key={ship.alert_id}
              className={`bg-slate-800/50 rounded-lg border transition-all cursor-pointer ${
                expanded === ship.alert_id
                  ? "border-red-500/50"
                  : "border-transparent hover:border-slate-600"
              }`}
            >
              {/* Main row */}
              <div
                className="flex items-center justify-between px-3 py-2"
                onClick={() => setExpanded(expanded === ship.alert_id ? null : ship.alert_id)}
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                  <span className="text-sm text-slate-300 font-mono">
                    {ship.track_id.slice(0, 8)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium ${getConfidenceColor(ship.confidence)}`}>
                    {(ship.confidence * 100).toFixed(0)}%
                  </span>
                  <ChevronRight
                    className={`w-4 h-4 text-slate-500 transition-transform ${
                      expanded === ship.alert_id ? "rotate-90" : ""
                    }`}
                  />
                </div>
              </div>

              {/* Expanded details */}
              {expanded === ship.alert_id && (
                <div className="px-3 pb-3 space-y-2 border-t border-slate-700/50 pt-2">
                  {/* Position */}
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Position</span>
                    <span className="text-slate-300 font-mono">
                      {ship.latitude.toFixed(4)}, {ship.longitude.toFixed(4)}
                    </span>
                  </div>

                  {/* Alert reason */}
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Reason</span>
                    <span className="text-orange-300">{ship.alert_reason || "Unknown"}</span>
                  </div>

                  {/* Detected by */}
                  <div className="flex justify-between text-xs items-center">
                    <span className="text-slate-500">Detected by</span>
                    <div className="flex gap-1">
                      {ship.detected_by.map((sensor) => {
                        const Icon = SENSOR_ICONS[sensor] || Eye;
                        return (
                          <Icon
                            key={sensor}
                            className="w-3 h-3"
                            style={{
                              color:
                                sensor === "ais"
                                  ? "#00d9ff"
                                  : sensor === "radar"
                                  ? "#ff6b6b"
                                  : sensor === "satellite"
                                  ? "#feca57"
                                  : "#1dd1a1",
                            }}
                            title={sensor.toUpperCase()}
                          />
                        );
                      })}
                    </div>
                  </div>

                  {/* Time */}
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Detected</span>
                    <span className="text-slate-400">{formatTime(ship.timestamp)}</span>
                  </div>

                  {/* View on map button */}
                  {onSelectShip && (
                    <button
                      className="w-full mt-2 text-xs bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 rounded py-1.5 flex items-center justify-center gap-1 transition-colors"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectShip(ship.latitude, ship.longitude, ship.track_id);
                      }}
                    >
                      <Eye className="w-3 h-3" />
                      View on Globe
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
