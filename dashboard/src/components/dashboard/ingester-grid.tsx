"use client";

/**
 * Grid layout for ingester cards
 *
 * Shows World Simulator first (ground truth), then 4 sensor ingesters,
 * then Fusion Engine at the bottom.
 */

import { IngesterCard } from "@/components/ingester/ingester-card";
import { useLogStore } from "@/stores/log-store";

export function IngesterGrid() {
  const { status, logs } = useLogStore();

  const sensorIngesters = ["ais", "radar", "satellite", "drone"];

  return (
    <div className="space-y-4">
      {/* World Simulator - Full Width */}
      <div className="w-full">
        <div className="text-xs uppercase tracking-wide text-yellow-400 mb-2 font-semibold">
          Ground Truth (Start First)
        </div>
        <IngesterCard
          key="world"
          name="world"
          status={status.world || {
            name: "world",
            description: "World Simulator - Ground truth ship positions",
            running: false,
            redis_stream: "",
            status_key: "maritime:fleet:metadata",
          }}
          logs={logs.world || []}
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

      {/* Fusion Engine - Full Width */}
      <div className="w-full">
        <div className="text-xs uppercase tracking-wide text-purple-400 mb-2 font-semibold">
          Data Fusion (Start After Sensors)
        </div>
        <IngesterCard
          key="fusion"
          name="fusion"
          status={status.fusion || {
            name: "fusion",
            description: "Multi-sensor fusion engine - correlates all sensor data",
            running: false,
            redis_stream: "fusion:tracks",
            status_key: "ingester:fusion:status",
          }}
          logs={logs.fusion || []}
        />
      </div>
    </div>
  );
}
