"use client";

/**
 * Main ingester card component with status, config, logs, and controls
 */

import { useState } from "react";
import { Ship, Radio, Satellite, Plane, Globe2, Layers, ChevronDown, ChevronUp, Loader2, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ConfigPanel } from "./config-panel";
import { LogWindow } from "./log-window";
import { useStartIngester, useStopIngester } from "@/hooks/use-ingesters";
import { INGESTER_METADATA } from "@/lib/types";
import type { IngesterConfig, TechDetail } from "@/lib/types";

const ICONS = {
  Ship,
  Radio,
  Satellite,
  Plane,
  Globe: Globe2,
  Layers,
};

// Simple markdown bold parser - converts **text** to <strong>
function renderBoldText(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

interface IngesterCardProps {
  name: string;
  status: IngesterConfig;
  logs: string[];
  isWorld?: boolean;
}

export function IngesterCard({ name, status, logs, isWorld = false }: IngesterCardProps) {
  const [configOpen, setConfigOpen] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const metadata = INGESTER_METADATA[name];
  const Icon = ICONS[metadata?.icon as keyof typeof ICONS] || Ship;

  const startMutation = useStartIngester();
  const stopMutation = useStopIngester();

  const isLoading = startMutation.isPending || stopMutation.isPending;
  const isRunning = status.running;

  const handleToggle = () => {
    if (isRunning) {
      stopMutation.mutate(name);
    } else {
      startMutation.mutate(name);
    }
  };

  return (
    <Card className={`relative overflow-hidden ${isWorld ? "border-yellow-500/50 bg-yellow-500/5" : ""}`}>
      {/* Accent line at top */}
      <div
        className={`absolute top-0 left-0 right-0 ${isWorld ? "h-1.5" : "h-1"}`}
        style={{ backgroundColor: metadata?.color || "#00d9ff" }}
      />

      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded-lg"
              style={{ backgroundColor: `${metadata?.color}20` }}
            >
              <Icon className="h-5 w-5" style={{ color: metadata?.color }} />
            </div>
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                {metadata?.displayName || name.toUpperCase()}
                <Badge variant="outline" className="text-xs font-normal">
                  {metadata?.format}
                </Badge>
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                {status.description}
              </p>
            </div>
          </div>
          <Badge
            variant={isRunning ? "default" : "secondary"}
            className={isRunning ? "bg-green-500 hover:bg-green-600" : ""}
          >
            {isRunning ? "RUNNING" : "STOPPED"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Running info */}
        {isRunning && status.pid && (
          <div className="text-xs text-muted-foreground flex gap-4">
            <span>PID: {status.pid}</span>
            {status.started_at && (
              <span>
                Started:{" "}
                {new Date(status.started_at).toLocaleTimeString()}
              </span>
            )}
          </div>
        )}

        {/* Technical details (collapsible) */}
        {metadata?.techDetails && (
          <Collapsible open={techOpen} onOpenChange={setTechOpen}>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between text-muted-foreground hover:text-foreground"
              >
                <span className="flex items-center gap-2">
                  <Info className="h-3 w-3" />
                  Technical Details
                </span>
                {techOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="rounded-md border border-slate-700 bg-slate-900/50 p-3 mt-2 space-y-2">
                {metadata.techDetails.map((detail, idx) => (
                  <div key={idx} className="text-xs">
                    <span className="text-cyan-400 font-medium">{detail.label}:</span>{" "}
                    <span className="text-slate-300">{renderBoldText(detail.value)}</span>
                  </div>
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Config panel (collapsible) */}
        <Collapsible open={configOpen} onOpenChange={setConfigOpen}>
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-between text-muted-foreground hover:text-foreground"
            >
              Configuration
              {configOpen ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ConfigPanel name={name} disabled={isRunning} />
          </CollapsibleContent>
        </Collapsible>

        {/* Log window */}
        <LogWindow logs={logs} name={name} color={metadata?.color || "#00d9ff"} />

        {/* Controls */}
        <div className="flex gap-2 pt-2">
          <Button
            onClick={handleToggle}
            disabled={isLoading}
            variant={isRunning ? "destructive" : "default"}
            className="flex-1"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {isRunning ? "Stopping..." : "Starting..."}
              </>
            ) : isRunning ? (
              "Stop"
            ) : (
              "Start"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
