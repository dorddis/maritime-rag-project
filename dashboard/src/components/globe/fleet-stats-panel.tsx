"use client";

/**
 * Fleet Statistics Panel
 *
 * Shows real-time stats about the maritime fleet and sensor performance.
 * Displays alongside the globe visualization.
 */

import { useLogStore } from "@/stores/log-store";
import { Ship, Radio, Satellite, Plane, AlertTriangle, Wifi, WifiOff, Activity } from "lucide-react";

// Sensor configurations
const SENSOR_STATS = {
  ais: {
    name: "AIS",
    icon: Ship,
    color: "#00d9ff",
    accuracy: "10m",
    packetLoss: "5%",
    seeDark: false,
  },
  radar: {
    name: "Radar",
    icon: Radio,
    color: "#ff6b6b",
    accuracy: "500m",
    stations: 7,
    range: "45-60nm",
    seeDark: true,
  },
  satellite: {
    name: "Satellite",
    icon: Satellite,
    color: "#feca57",
    accuracy: "2km",
    satellites: 4,
    seeDark: true,
  },
  drone: {
    name: "Drone",
    icon: Plane,
    color: "#1dd1a1",
    accuracy: "50m",
    zones: 5,
    seeDark: true,
  },
};

interface FleetStatsPanelProps {
  totalShips: number;
  darkShips: number;
  className?: string;
}

export function FleetStatsPanel({ totalShips, darkShips, className = "" }: FleetStatsPanelProps) {
  const { status, streams, redisConnected } = useLogStore();

  const visibleShips = totalShips - darkShips;
  const darkPercent = totalShips > 0 ? ((darkShips / totalShips) * 100).toFixed(1) : "0";

  return (
    <div className={`bg-slate-900/90 rounded-xl border border-slate-700 p-4 space-y-4 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-cyan-400 uppercase tracking-wide">
          Fleet Statistics
        </h3>
        <div className="flex items-center gap-2">
          {redisConnected ? (
            <Wifi className="w-4 h-4 text-green-400" />
          ) : (
            <WifiOff className="w-4 h-4 text-red-400" />
          )}
          <span className="text-xs text-slate-400">
            {redisConnected ? "Live" : "Offline"}
          </span>
        </div>
      </div>

      {/* Ship counts */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-cyan-400">{totalShips}</div>
          <div className="text-xs text-slate-400">Total Ships</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-green-400">{visibleShips}</div>
          <div className="text-xs text-slate-400">AIS Visible</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-400">{darkShips}</div>
          <div className="text-xs text-slate-400 flex items-center justify-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            Dark ({darkPercent}%)
          </div>
        </div>
      </div>

      {/* Sensor status */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide">
          Sensor Status
        </h4>
        {Object.entries(SENSOR_STATS).map(([key, sensor]) => {
          const isRunning = status[key]?.running;
          const streamCount = streams[`${key === "ais" ? "ais:positions" : key === "radar" ? "radar:contacts" : key === "satellite" ? "satellite:detections" : "drone:detections"}`] || 0;
          const Icon = sensor.icon;

          return (
            <div
              key={key}
              className="flex items-center justify-between bg-slate-800/50 rounded-lg px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <Icon className="w-4 h-4" style={{ color: sensor.color }} />
                <span className="text-sm text-slate-300">{sensor.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-500">
                  {sensor.seeDark ? (
                    <span className="text-green-400">Sees dark</span>
                  ) : (
                    <span className="text-red-400">No dark</span>
                  )}
                </span>
                <span className="text-xs text-slate-400">
                  {streamCount.toLocaleString()}
                </span>
                <div
                  className={`w-2 h-2 rounded-full ${
                    isRunning ? "bg-green-400 animate-pulse" : "bg-slate-600"
                  }`}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Sensor capabilities */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide">
          Sensor Accuracy
        </h4>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {Object.entries(SENSOR_STATS).map(([key, sensor]) => (
            <div key={key} className="flex justify-between text-slate-400">
              <span style={{ color: sensor.color }}>{sensor.name}</span>
              <span className="text-slate-300">{sensor.accuracy}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Performance indicators */}
      <div className="space-y-2">
        <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wide flex items-center gap-1">
          <Activity className="w-3 h-3" />
          Performance
        </h4>
        <div className="space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-slate-400">AIS Packet Loss</span>
            <span className="text-yellow-400">~5%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Radar Weather Factor</span>
            <span className="text-green-400">95%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Satellite Cloud Cover</span>
            <span className="text-yellow-400">30%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Drone Active Zones</span>
            <span className="text-green-400">5/5</span>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="pt-2 border-t border-slate-700">
        <div className="text-xs text-slate-500 mb-2">Ship Colors</div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            <span className="text-slate-400">AIS On</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-slate-400">Dark Ship</span>
          </span>
        </div>
      </div>
    </div>
  );
}
