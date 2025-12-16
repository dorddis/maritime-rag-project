"use client";

/**
 * Terminal-style log window for an ingester
 */

import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface LogWindowProps {
  logs: string[];
  name: string;
  color: string;
}

export function LogWindow({ logs, name, color }: LogWindowProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const colorLog = (line: string): { text: string; className: string } => {
    if (line.includes("[ERROR]") || line.includes("Error")) {
      return { text: line, className: "text-destructive" };
    }
    if (line.includes("[WARN]") || line.includes("Warning")) {
      return { text: line, className: "text-yellow-400" };
    }
    if (line.includes("Started") || line.includes("Connected")) {
      return { text: line, className: "text-green-400" };
    }
    return { text: line, className: "text-muted-foreground" };
  };

  return (
    <div className="mt-3">
      <div className="text-xs text-muted-foreground mb-1 flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        Logs
      </div>
      <ScrollArea
        ref={scrollRef}
        className="h-32 w-full rounded-md border bg-black/40 p-2 font-mono text-xs"
      >
        {logs.length === 0 ? (
          <div className="text-muted-foreground/50 italic">
            No logs yet. Start the ingester to see output.
          </div>
        ) : (
          logs.map((line, i) => {
            const { text, className } = colorLog(line);
            return (
              <div key={`${name}-${i}`} className={className}>
                {text}
              </div>
            );
          })
        )}
      </ScrollArea>
    </div>
  );
}
