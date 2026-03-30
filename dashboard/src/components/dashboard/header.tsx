"use client";

/**
 * Dashboard header with title, connection status, and demo mode indicator
 */

import Link from "next/link";
import { Anchor, Wifi, WifiOff, MessageSquare, FlaskConical } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLogStore } from "@/stores/log-store";
import { isDemoMode } from "@/lib/demo-mode";

export function DashboardHeader() {
  const { connected, redisConnected } = useLogStore();
  const demoMode = isDemoMode();

  return (
    <>
      {/* Demo Mode Banner */}
      {demoMode && (
        <div className="bg-amber-600/20 border-b border-amber-500/40 px-4 py-2 flex items-center justify-center gap-2">
          <FlaskConical className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-medium text-amber-300">
            Demo Mode — Displaying simulated data. No backend connected.
          </span>
        </div>
      )}

      <header className="flex items-center justify-between py-6 px-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Anchor className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              Maritime Ingestion Dashboard
            </h1>
            <p className="text-sm text-muted-foreground">
              Multi-format data pipeline control panel
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link href="/chat">
            <Button variant="outline" size="sm" className="gap-2">
              <MessageSquare className="h-4 w-4" />
              RAG Chat
            </Button>
          </Link>

          {demoMode ? (
            <Badge
              variant="outline"
              className="flex items-center gap-1.5 border-amber-500/50 text-amber-400"
            >
              <FlaskConical className="h-3 w-3" />
              Demo Mode
            </Badge>
          ) : (
            <Badge
              variant={connected ? "default" : "destructive"}
              className="flex items-center gap-1.5"
            >
              {connected ? (
                <>
                  <Wifi className="h-3 w-3" />
                  WebSocket Connected
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3" />
                  Disconnected
                </>
              )}
            </Badge>
          )}

          <Badge
            variant={redisConnected || demoMode ? "outline" : "secondary"}
            className="flex items-center gap-1.5"
          >
            <div
              className={`h-2 w-2 rounded-full ${
                redisConnected || demoMode ? "bg-green-500" : "bg-yellow-500"
              }`}
            />
            Redis: {redisConnected || demoMode ? "OK" : "Offline"}
          </Badge>
        </div>
      </header>
    </>
  );
}
