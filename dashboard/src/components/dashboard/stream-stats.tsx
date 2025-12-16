"use client";

/**
 * Redis stream statistics display
 */

import { Database } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLogStore } from "@/stores/log-store";
import { INGESTER_METADATA } from "@/lib/types";

const STREAM_TO_INGESTER: Record<string, string> = {
  "ais:positions": "ais",
  "radar:contacts": "radar",
  "satellite:detections": "satellite",
  "drone:detections": "drone",
};

export function StreamStats() {
  const { streams, redisConnected } = useLogStore();

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Database className="h-4 w-4 text-primary" />
          Redis Stream Statistics
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!redisConnected ? (
          <p className="text-sm text-muted-foreground">
            Redis not connected. Stream statistics unavailable.
          </p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(STREAM_TO_INGESTER).map(([stream, ingester]) => {
              const metadata = INGESTER_METADATA[ingester];
              const count = streams[stream] || 0;

              return (
                <div
                  key={stream}
                  className="rounded-lg border p-3 space-y-1"
                  style={{ borderColor: `${metadata?.color}40` }}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: metadata?.color }}
                    />
                    <span className="text-xs text-muted-foreground">
                      {stream}
                    </span>
                  </div>
                  <div
                    className="text-2xl font-bold"
                    style={{ color: metadata?.color }}
                  >
                    {count.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">messages</div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
