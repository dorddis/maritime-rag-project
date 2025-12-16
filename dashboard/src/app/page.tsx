"use client";

/**
 * Maritime Surveillance Dashboard - Main Page
 *
 * Features:
 * - 3D Globe visualization of ship positions
 * - Real-time sensor status and statistics
 * - Ingester control panel
 */

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/use-websocket";
import { DashboardHeader } from "@/components/dashboard/header";
import { IngesterGrid } from "@/components/dashboard/ingester-grid";
import { StreamStats } from "@/components/dashboard/stream-stats";
import { MaritimeGlobe } from "@/components/globe/maritime-globe";
import { FleetStatsPanel } from "@/components/globe/fleet-stats-panel";
import { fetchFleetShips } from "@/lib/api";
import type { Ship } from "@/lib/types";

export default function DashboardPage() {
  // Connect to WebSocket for real-time updates
  useWebSocket();

  // Fleet state
  const [totalShips, setTotalShips] = useState(0);
  const [darkShips, setDarkShips] = useState(0);
  const [selectedShip, setSelectedShip] = useState<Ship | null>(null);

  // Fetch fleet stats
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await fetchFleetShips();
        setTotalShips(data.count || 0);
        setDarkShips(data.dark_count || 0);
      } catch (err) {
        console.error("Failed to fetch fleet stats:", err);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto max-w-[1600px]">
        <DashboardHeader />

        <main className="py-4 px-4 space-y-6">
          {/* Globe Section - Full Width Hero */}
          <section className="relative">
            <div className="flex gap-4">
              {/* Globe Container */}
              <div className="flex-1 h-[500px] bg-slate-900 rounded-xl overflow-hidden border border-slate-700">
                <MaritimeGlobe
                  className="w-full h-full"
                  onShipSelect={setSelectedShip}
                />
              </div>

              {/* Stats Panel */}
              <div className="w-80 flex-shrink-0">
                <FleetStatsPanel
                  totalShips={totalShips}
                  darkShips={darkShips}
                  className="h-[500px] overflow-y-auto"
                />
              </div>
            </div>

            {/* Quick stats bar */}
            <div className="mt-4 grid grid-cols-4 gap-4">
              <QuickStat
                label="Total Ships"
                value={totalShips}
                color="cyan"
              />
              <QuickStat
                label="AIS Visible"
                value={totalShips - darkShips}
                color="green"
              />
              <QuickStat
                label="Dark Ships"
                value={darkShips}
                color="red"
                highlight
              />
              <QuickStat
                label="Dark Rate"
                value={`${totalShips > 0 ? ((darkShips / totalShips) * 100).toFixed(1) : 0}%`}
                color="yellow"
              />
            </div>
          </section>

          {/* Ingester Controls */}
          <section>
            <h2 className="text-lg font-semibold text-cyan-400 mb-4 uppercase tracking-wide">
              Simulation Controls
            </h2>
            <IngesterGrid />
          </section>

          {/* Stream Statistics */}
          <StreamStats />
        </main>
      </div>
    </div>
  );
}

// Quick stat component
function QuickStat({
  label,
  value,
  color,
  highlight = false,
}: {
  label: string;
  value: string | number;
  color: "cyan" | "green" | "red" | "yellow";
  highlight?: boolean;
}) {
  const colorClasses = {
    cyan: "text-cyan-400 border-cyan-500/30",
    green: "text-green-400 border-green-500/30",
    red: "text-red-400 border-red-500/30",
    yellow: "text-yellow-400 border-yellow-500/30",
  };

  return (
    <div
      className={`
        bg-slate-900/80 rounded-lg p-4 border
        ${colorClasses[color]}
        ${highlight ? "ring-1 ring-red-500/50" : ""}
      `}
    >
      <div className={`text-2xl font-bold ${colorClasses[color].split(" ")[0]}`}>
        {value}
      </div>
      <div className="text-xs text-slate-400 mt-1">{label}</div>
    </div>
  );
}
