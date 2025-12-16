"use client";

/**
 * Grid layout for ingester cards
 *
 * Shows World Simulator first (ground truth), then 4 sensor ingesters.
 */

import { IngesterCard } from "@/components/ingester/ingester-card";
import { useLogStore } from "@/stores/log-store";

// World simulator first, then sensors
const INGESTER_ORDER = ["world", "ais", "radar", "satellite", "drone"];

export function IngesterGrid() {
  const { status, logs } = useLogStore();

  // Separate world from sensors for different layouts
  const worldIngester = "world";
  const sensorIngesters = ["ais", "radar", "satellite", "drone"];

  return (
    <div className="space-y-4">
      {/* World Simulator - Full Width */}
      <div className="w-full">
        <div className="text-xs uppercase tracking-wide text-yellow-400 mb-2 font-semibold">
          Ground Truth (Start First)
        </div>
        <IngesterCard
          key={worldIngester}
          name={worldIngester}
          status={status[worldIngester] || {
            name: worldIngester,
            description: "World Simulator - Ground truth ship positions",
            running: false,
            redis_stream: "",
            status_key: "maritime:fleet:metadata",
          }}
          logs={logs[worldIngester] || []}
          isWorld={true}
        />
      </div>

      {/* Sensor Ingesters - 2x2 Grid */}
      <div>
        <div className="text-xs uppercase tracking-wide text-cyan-400 mb-2 font-semibold">
          Sensor Ingesters
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sensorIngesters.map((name) => {
            const ingesterStatus = status[name];
            const ingesterLogs = logs[name] || [];

            const defaultStatus = {
              name,
              description: `${name.charAt(0).toUpperCase() + name.slice(1)} sensor ingester`,
              running: false,
              redis_stream: `${name}:${name === "ais" ? "positions" : name === "radar" ? "contacts" : "detections"}`,
              status_key: `ingester:${name}:status`,
            };

            return (
              <IngesterCard
                key={name}
                name={name}
                status={ingesterStatus || defaultStatus}
                logs={ingesterLogs}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
