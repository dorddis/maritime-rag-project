"use client";

/**
 * Ship Result Card - Display a single ship/track result
 */

import { Ship, Navigation, Radio, AlertTriangle, Database, Search, Radar } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ShipResult } from "@/lib/chat-types";

interface ShipResultCardProps {
  result: ShipResult;
}

export function ShipResultCard({ result }: ShipResultCardProps) {
  const {
    track_id,
    mmsi,
    ship_name,
    vessel_type,
    latitude,
    longitude,
    speed_knots,
    course,
    is_dark_ship,
    dark_ship_confidence,
    contributing_sensors,
    fusion_score,
    source,
    similarity,
  } = result;

  const displayName = ship_name || mmsi || track_id || "Unknown";
  const displayId = mmsi || track_id;

  return (
    <Card className="bg-slate-800/50 border-slate-700 p-3 hover:border-cyan-500/30 transition-colors">
      <div className="flex items-start justify-between gap-2">
        {/* Ship Info */}
        <div className="flex items-start gap-2 min-w-0">
          <div className={`p-1.5 rounded ${is_dark_ship ? "bg-red-500/20" : "bg-cyan-500/20"}`}>
            {is_dark_ship ? (
              <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
            ) : (
              <Ship className="h-3.5 w-3.5 text-cyan-400" />
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-slate-200 truncate">
                {displayName}
              </span>
              {is_dark_ship && (
                <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4">
                  DARK SHIP
                </Badge>
              )}
            </div>
            {displayId && displayId !== displayName && (
              <span className="text-xs text-muted-foreground">{displayId}</span>
            )}
          </div>
        </div>

        {/* Source Badge */}
        {source && <SourceBadge source={source} similarity={similarity} />}
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs">
        {/* Vessel Type */}
        {vessel_type && (
          <div>
            <span className="text-muted-foreground">Type: </span>
            <span className="text-slate-300">{vessel_type}</span>
          </div>
        )}

        {/* Position */}
        {latitude !== undefined && longitude !== undefined && (
          <div>
            <span className="text-muted-foreground">Pos: </span>
            <span className="text-slate-300">
              {Number(latitude).toFixed(3)}, {Number(longitude).toFixed(3)}
            </span>
          </div>
        )}

        {/* Speed */}
        {speed_knots !== undefined && (
          <div className="flex items-center gap-1">
            <Navigation className="h-3 w-3 text-muted-foreground" />
            <span className="text-slate-300">{Number(speed_knots).toFixed(1)} kn</span>
          </div>
        )}

        {/* Course */}
        {course !== undefined && (
          <div>
            <span className="text-muted-foreground">Course: </span>
            <span className="text-slate-300">{Number(course).toFixed(0)}</span>
          </div>
        )}

        {/* Dark Ship Confidence */}
        {is_dark_ship && dark_ship_confidence !== undefined && (
          <div>
            <span className="text-muted-foreground">Confidence: </span>
            <span className="text-red-400">{(Number(dark_ship_confidence) * 100).toFixed(0)}%</span>
          </div>
        )}

        {/* Fusion Score */}
        {fusion_score !== undefined && (
          <div>
            <span className="text-muted-foreground">Score: </span>
            <span className="text-cyan-400">{Number(fusion_score).toFixed(3)}</span>
          </div>
        )}
      </div>

      {/* Contributing Sensors */}
      {contributing_sensors && (
        <div className="flex flex-wrap gap-1 mt-2">
          {(Array.isArray(contributing_sensors)
            ? contributing_sensors
            : String(contributing_sensors).split(',').filter(Boolean)
          ).map((sensor) => (
            <Badge
              key={sensor}
              variant="outline"
              className="text-[10px] px-1.5 py-0 h-4"
            >
              {sensor.trim()}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  );
}

function SourceBadge({
  source,
  similarity,
}: {
  source: "structured" | "semantic" | "realtime";
  similarity?: number;
}) {
  const configs = {
    structured: {
      icon: Database,
      label: "SQL",
      color: "text-cyan-400 border-cyan-500/50 bg-cyan-500/10",
    },
    semantic: {
      icon: Search,
      label: similarity ? `${(Number(similarity) * 100).toFixed(0)}%` : "Vector",
      color: "text-purple-400 border-purple-500/50 bg-purple-500/10",
    },
    realtime: {
      icon: Radar,
      label: "Live",
      color: "text-green-400 border-green-500/50 bg-green-500/10",
    },
  };

  const config = configs[source];
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={`text-[10px] px-1.5 py-0 h-4 ${config.color}`}>
      <Icon className="h-2.5 w-2.5 mr-1" />
      {config.label}
    </Badge>
  );
}
