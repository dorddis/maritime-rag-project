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
import { DarkShipsPanel } from "@/components/dashboard/dark-ships-panel";
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

        <main className="py-4 px-4 space-y-4">
          {/* Globe - Full Width */}
          <section className="h-[500px] bg-slate-900 rounded-xl overflow-hidden border border-slate-700">
            <MaritimeGlobe
              className="w-full h-full"
              onShipSelect={setSelectedShip}
            />
          </section>

          {/* Stats Panels - Horizontal Layout */}
          <section className="grid grid-cols-2 gap-4">
            {/* Fleet Stats Panel */}
            <FleetStatsPanel
              totalShips={totalShips}
              darkShips={darkShips}
            />

            {/* Dark Ships Panel */}
            <DarkShipsPanel />
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
