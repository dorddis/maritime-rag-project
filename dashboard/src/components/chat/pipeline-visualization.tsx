"use client";

/**
 * Pipeline Visualization - Shows all pipeline steps for a RAG query
 */

import { Card } from "@/components/ui/card";
import { PipelineStep } from "./pipeline-step";
import type { PipelineState } from "@/lib/chat-types";
import {
  Route,
  Database,
  Search,
  Radio,
  Layers,
} from "lucide-react";

interface PipelineVisualizationProps {
  pipeline: PipelineState;
}

export function PipelineVisualization({ pipeline }: PipelineVisualizationProps) {
  const { routing, sql, vector, realtime, fusion } = pipeline;

  // Check if any step has started
  const hasAnyStep = routing || sql || vector || realtime || fusion;
  if (!hasAnyStep) return null;

  return (
    <Card className="bg-slate-800/30 border-slate-700 p-3">
      <div className="space-y-1">
        {/* Query Analysis */}
        {routing && (
          <PipelineStep
            name="Query Analysis"
            icon={Route}
            status={routing.status}
            executionTimeMs={routing.executionTimeMs}
          >
            <RoutingContent routing={routing} />
          </PipelineStep>
        )}

        {/* SQL Query */}
        {sql && sql.status !== "skipped" && (
          <PipelineStep
            name="SQL Query"
            icon={Database}
            status={sql.status}
            executionTimeMs={sql.executionTimeMs}
          >
            <SQLContent sql={sql} />
          </PipelineStep>
        )}

        {/* Vector Search */}
        {vector && vector.status !== "skipped" && (
          <PipelineStep
            name="Vector Search"
            icon={Search}
            status={vector.status}
            executionTimeMs={vector.executionTimeMs}
          >
            <VectorContent vector={vector} />
          </PipelineStep>
        )}

        {/* Real-time Data */}
        {realtime && (
          <PipelineStep
            name="Real-time Data"
            icon={Radio}
            status={realtime.status}
            executionTimeMs={realtime.executionTimeMs}
          >
            <RealtimeContent realtime={realtime} />
          </PipelineStep>
        )}

        {/* Result Fusion */}
        {fusion && (
          <PipelineStep
            name="Result Fusion"
            icon={Layers}
            status={fusion.status}
            executionTimeMs={fusion.executionTimeMs}
          >
            <FusionContent fusion={fusion} />
          </PipelineStep>
        )}
      </div>
    </Card>
  );
}

// ============ Step Content Components ============

import { Badge } from "@/components/ui/badge";
import type {
  RoutingStep,
  SQLStep,
  VectorStep,
  RealtimeStep,
  FusionStep,
} from "@/lib/chat-types";
import { QUERY_TYPE_INFO } from "@/lib/chat-types";

function RoutingContent({ routing }: { routing: RoutingStep }) {
  if (routing.status !== "complete") return null;

  const queryType = routing.queryType;
  const typeInfo = queryType ? QUERY_TYPE_INFO[queryType] : null;

  return (
    <div className="space-y-2">
      {/* Query Type */}
      {queryType && typeInfo && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Type:</span>
          <Badge
            style={{ backgroundColor: `${typeInfo.color}20`, color: typeInfo.color, borderColor: `${typeInfo.color}50` }}
            variant="outline"
            className="text-xs font-medium"
          >
            {typeInfo.label}
          </Badge>
          <span className="text-xs text-muted-foreground">{typeInfo.description}</span>
        </div>
      )}

      {/* Confidence */}
      {routing.confidence !== undefined && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Confidence:</span>
          <div className="flex-1 h-1.5 bg-slate-700 rounded-full max-w-32">
            <div
              className="h-full rounded-full bg-cyan-500"
              style={{ width: `${routing.confidence * 100}%` }}
            />
          </div>
          <span className="text-xs text-slate-400">{(routing.confidence * 100).toFixed(0)}%</span>
        </div>
      )}

      {/* Reasoning */}
      {routing.reasoning && (
        <div>
          <span className="text-xs text-muted-foreground">Reasoning: </span>
          <span className="text-xs text-slate-300">{routing.reasoning}</span>
        </div>
      )}

      {/* Extracted Filters */}
      {routing.extractedFilters && Object.keys(routing.extractedFilters).length > 0 && (
        <div className="flex flex-wrap gap-1">
          <span className="text-xs text-muted-foreground">Filters:</span>
          {Object.entries(routing.extractedFilters).map(([key, value]) => (
            <Badge key={key} variant="secondary" className="text-xs">
              {key}: {String(value)}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function SQLContent({ sql }: { sql: SQLStep }) {
  if (sql.status === "pending" || sql.status === "running") return null;

  return (
    <div className="space-y-2">
      {/* SQL Query */}
      {sql.sql && (
        <div>
          <span className="text-xs text-muted-foreground block mb-1">Query:</span>
          <pre className="text-xs bg-slate-900 p-2 rounded overflow-x-auto text-cyan-300 font-mono">
            {sql.sql}
          </pre>
        </div>
      )}

      {/* Results */}
      {sql.status === "complete" && (
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>Rows: <span className="text-slate-300">{sql.rowCount ?? sql.totalResults ?? 0}</span></span>
        </div>
      )}

      {/* Error */}
      {sql.error && (
        <div className="text-xs text-red-400">Error: {sql.error}</div>
      )}
    </div>
  );
}

function VectorContent({ vector }: { vector: VectorStep }) {
  if (vector.status === "pending" || vector.status === "running") return null;

  return (
    <div className="space-y-2">
      {/* Search Query */}
      {vector.query && (
        <div>
          <span className="text-xs text-muted-foreground">Search query: </span>
          <span className="text-xs text-slate-300">&quot;{vector.query}&quot;</span>
        </div>
      )}

      {/* Results */}
      {vector.status === "complete" && (
        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span>Results: <span className="text-slate-300">{vector.resultCount ?? 0}</span></span>
          {vector.sources && vector.sources.length > 0 && (
            <span>Sources: <span className="text-slate-300">{vector.sources.join(", ")}</span></span>
          )}
        </div>
      )}

      {/* Top Similarities */}
      {vector.topSimilarities && vector.topSimilarities.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Top similarities:</span>
          {vector.topSimilarities.slice(0, 3).map((sim, i) => (
            <Badge key={i} variant="outline" className="text-xs">
              {(sim * 100).toFixed(0)}%
            </Badge>
          ))}
        </div>
      )}

      {/* Error */}
      {vector.error && (
        <div className="text-xs text-red-400">Error: {vector.error}</div>
      )}
    </div>
  );
}

function RealtimeContent({ realtime }: { realtime: RealtimeStep }) {
  if (realtime.status === "pending" || realtime.status === "running") return null;

  return (
    <div className="space-y-2">
      {/* Track Count */}
      {realtime.status === "complete" && (
        <div className="text-xs text-muted-foreground">
          Live tracks: <span className="text-slate-300">{realtime.trackCount ?? 0}</span>
        </div>
      )}

      {/* Filters Applied */}
      {realtime.filtersApplied && Object.keys(realtime.filtersApplied).length > 0 && (
        <div className="flex flex-wrap gap-1">
          <span className="text-xs text-muted-foreground">Filters:</span>
          {Object.entries(realtime.filtersApplied).map(([key, value]) => (
            <Badge key={key} variant="secondary" className="text-xs">
              {key}: {String(value)}
            </Badge>
          ))}
        </div>
      )}

      {/* Error */}
      {realtime.error && (
        <div className="text-xs text-red-400">Error: {realtime.error}</div>
      )}
    </div>
  );
}

function FusionContent({ fusion }: { fusion: FusionStep }) {
  if (fusion.status === "pending" || fusion.status === "running") return null;

  return (
    <div className="space-y-2">
      {/* Method */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Method:</span>
        <Badge variant="outline" className="text-xs">
          {fusion.method || "RRF"}
        </Badge>
        {fusion.rrfK && (
          <span className="text-muted-foreground">(k={fusion.rrfK})</span>
        )}
      </div>

      {/* Breakdown */}
      {fusion.breakdown && (
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <span>Structured: <span className="text-slate-300">{fusion.breakdown.structured}</span></span>
          <span>Semantic: <span className="text-slate-300">{fusion.breakdown.semantic}</span></span>
          <span>Realtime: <span className="text-slate-300">{fusion.breakdown.realtime}</span></span>
        </div>
      )}

      {/* Total */}
      {fusion.totalResults !== undefined && (
        <div className="text-xs">
          <span className="text-muted-foreground">Total fused results: </span>
          <span className="text-cyan-400 font-medium">{fusion.totalResults}</span>
        </div>
      )}
    </div>
  );
}
