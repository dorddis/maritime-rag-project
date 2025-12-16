"use client";

/**
 * Pipeline Step - Single collapsible step in the pipeline visualization
 */

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronUp, Loader2, Check, AlertCircle, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { StepStatus } from "@/lib/chat-types";
import type { LucideIcon } from "lucide-react";

interface PipelineStepProps {
  name: string;
  icon: LucideIcon;
  status: StepStatus;
  executionTimeMs?: number;
  children: ReactNode;
}

export function PipelineStep({
  name,
  icon: Icon,
  status,
  executionTimeMs,
  children,
}: PipelineStepProps) {
  // Auto-expand completed steps, collapse pending/running
  const [isOpen, setIsOpen] = useState(status === "complete" || status === "error");

  // Update open state when status changes to complete
  const shouldAutoOpen = status === "complete" || status === "error";

  return (
    <Collapsible open={isOpen || shouldAutoOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-between h-auto py-2 px-2 hover:bg-slate-700/50"
        >
          <span className="flex items-center gap-2">
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-sm text-slate-300">{name}</span>
          </span>
          <span className="flex items-center gap-2">
            <StatusIndicator status={status} />
            {executionTimeMs !== undefined && status === "complete" && (
              <span className="text-xs text-muted-foreground">
                {executionTimeMs.toFixed(0)}ms
              </span>
            )}
            {isOpen || shouldAutoOpen ? (
              <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </span>
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="rounded-md border border-slate-700 bg-slate-900/50 p-3 mt-1 ml-5">
          {children}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function StatusIndicator({ status }: { status: StepStatus }) {
  switch (status) {
    case "pending":
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 text-slate-500 border-slate-600">
          Pending
        </Badge>
      );
    case "running":
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 text-cyan-400 border-cyan-500/50 bg-cyan-500/10">
          <Loader2 className="h-2.5 w-2.5 mr-1 animate-spin" />
          Running
        </Badge>
      );
    case "complete":
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 text-green-400 border-green-500/50 bg-green-500/10">
          <Check className="h-2.5 w-2.5 mr-1" />
          Complete
        </Badge>
      );
    case "error":
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 text-red-400 border-red-500/50 bg-red-500/10">
          <AlertCircle className="h-2.5 w-2.5 mr-1" />
          Error
        </Badge>
      );
    case "skipped":
      return (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-5 text-slate-500 border-slate-600">
          <SkipForward className="h-2.5 w-2.5 mr-1" />
          Skipped
        </Badge>
      );
    default:
      return null;
  }
}
