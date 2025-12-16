"use client";

/**
 * Dashboard header with title and connection status
 */

import Link from "next/link";
import { Anchor, Wifi, WifiOff, MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLogStore } from "@/stores/log-store";

export function DashboardHeader() {
  const { connected, redisConnected } = useLogStore();

  return (
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

        <Badge
          variant={redisConnected ? "outline" : "secondary"}
          className="flex items-center gap-1.5"
        >
          <div
            className={`h-2 w-2 rounded-full ${
              redisConnected ? "bg-green-500" : "bg-yellow-500"
            }`}
          />
          Redis: {redisConnected ? "OK" : "Offline"}
        </Badge>
      </div>
    </header>
  );
}
