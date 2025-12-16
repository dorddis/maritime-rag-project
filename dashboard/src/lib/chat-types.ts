/**
 * TypeScript interfaces for RAG Chat Interface
 */

// ============ Message Types ============

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  pipeline?: PipelineState;
  results?: ShipResult[];
  isStreaming?: boolean;
  error?: string;
}

// ============ Pipeline State Types ============

export type StepStatus = "pending" | "running" | "complete" | "error" | "skipped";

export type QueryType = "structured" | "semantic" | "hybrid" | "temporal";

export interface PipelineState {
  routing?: RoutingStep;
  sql?: SQLStep;
  vector?: VectorStep;
  realtime?: RealtimeStep;
  fusion?: FusionStep;
}

export interface RoutingStep {
  status: StepStatus;
  queryType?: QueryType;
  confidence?: number;
  reasoning?: string;
  extractedFilters?: Record<string, unknown>;
  timeRange?: { type: string; value: string };
  semanticQuery?: string;
  executionTimeMs?: number;
}

export interface SQLStep {
  status: StepStatus;
  sql?: string;
  rowCount?: number;
  totalResults?: number;
  results?: Record<string, unknown>[];
  explanation?: string;
  executionTimeMs?: number;
  error?: string;
}

export interface VectorStep {
  status: StepStatus;
  query?: string;
  resultCount?: number;
  topSimilarities?: number[];
  sources?: string[];
  results?: Record<string, unknown>[];
  executionTimeMs?: number;
  error?: string;
}

export interface RealtimeStep {
  status: StepStatus;
  trackCount?: number;
  filtersApplied?: Record<string, unknown>;
  results?: Record<string, unknown>[];
  executionTimeMs?: number;
  error?: string;
}

export interface FusionStep {
  status: StepStatus;
  method?: string;
  rrfK?: number;
  weights?: Record<string, number>;
  totalResults?: number;
  breakdown?: {
    structured: number;
    semantic: number;
    realtime: number;
  };
  results?: ShipResult[];
  executionTimeMs?: number;
}

// ============ Ship Result Types ============

export interface ShipResult {
  // Core identifiers
  id?: string;
  track_id?: string;
  mmsi?: string;
  ship_name?: string;

  // Position
  latitude: number;
  longitude: number;

  // Movement
  speed_knots?: number;
  course?: number;

  // Classification
  vessel_type?: string;
  status?: string;

  // Dark ship indicators
  is_dark_ship?: boolean;
  dark_ship_confidence?: number;
  alert_reason?: string;

  // Sensor info
  contributing_sensors?: string[];

  // Fusion metadata
  fusion_score?: number;
  source?: "structured" | "semantic" | "realtime";
  similarity?: number;

  // Timestamps
  updated_at?: string;
}

// ============ SSE Event Types ============

export type SSEEventType =
  | "routing"
  | "sql_start"
  | "sql_complete"
  | "vector_start"
  | "vector_complete"
  | "realtime"
  | "fusion"
  | "answer"
  | "error"
  | "done";

export interface SSEEvent {
  event: SSEEventType;
  data: SSEEventData;
}

export type SSEEventData =
  | RoutingEventData
  | SQLStartEventData
  | SQLCompleteEventData
  | VectorStartEventData
  | VectorCompleteEventData
  | RealtimeEventData
  | FusionEventData
  | AnswerEventData
  | ErrorEventData
  | DoneEventData;

export interface RoutingEventData {
  status: "start" | "complete";
  timestamp?: string;
  query_type?: QueryType;
  confidence?: number;
  reasoning?: string;
  extracted_filters?: Record<string, unknown>;
  time_range?: { type: string; value: string };
  semantic_query?: string;
  execution_time_ms?: number;
}

export interface SQLStartEventData {
  status: "start";
  timestamp: string;
}

export interface SQLCompleteEventData {
  status: "complete" | "error";
  sql?: string;
  row_count?: number;
  total_results?: number;
  results?: Record<string, unknown>[];
  explanation?: string;
  execution_time_ms?: number;
  error?: string;
}

export interface VectorStartEventData {
  status: "start";
  query: string;
  timestamp: string;
}

export interface VectorCompleteEventData {
  status: "complete" | "error";
  query?: string;
  result_count?: number;
  top_similarities?: number[];
  sources?: string[];
  results?: Record<string, unknown>[];
  execution_time_ms?: number;
  error?: string;
}

export interface RealtimeEventData {
  status: "complete" | "error";
  track_count?: number;
  filters_applied?: Record<string, unknown>;
  results?: Record<string, unknown>[];
  execution_time_ms?: number;
  error?: string;
}

export interface FusionEventData {
  status: "complete";
  method: string;
  rrf_k?: number;
  weights?: Record<string, number>;
  total_results: number;
  breakdown: {
    structured: number;
    semantic: number;
    realtime: number;
  };
  results: ShipResult[];
  execution_time_ms: number;
}

export interface AnswerEventData {
  status: "complete";
  content: string;
  execution_time_ms: number;
}

export interface ErrorEventData {
  status: "error";
  error: string;
  timestamp: string;
}

export interface DoneEventData {
  status: "complete";
  total_time_ms: number;
  step_times: Record<string, number>;
  result_count: number;
}

// ============ API Types ============

export interface ChatRequest {
  query: string;
  include_realtime?: boolean;
  max_results?: number;
}

export interface ChatResponse {
  query: string;
  query_type: QueryType;
  route: Record<string, unknown>;
  structured_results: Record<string, unknown>[];
  semantic_results: Record<string, unknown>[];
  realtime_results: Record<string, unknown>[];
  fused_results: ShipResult[];
  explanation: string;
  answer: string;
  execution_time_ms: number;
}

// ============ UI Helper Types ============

export interface PipelineStepConfig {
  id: keyof PipelineState;
  name: string;
  icon: string;
  description: string;
}

export const PIPELINE_STEPS: PipelineStepConfig[] = [
  {
    id: "routing",
    name: "Query Analysis",
    icon: "Route",
    description: "Classifying query type and extracting filters",
  },
  {
    id: "sql",
    name: "SQL Query",
    icon: "Database",
    description: "Generating and executing database query",
  },
  {
    id: "vector",
    name: "Vector Search",
    icon: "Search",
    description: "Semantic similarity search",
  },
  {
    id: "realtime",
    name: "Real-time Data",
    icon: "Radio",
    description: "Fetching live tracking data",
  },
  {
    id: "fusion",
    name: "Result Fusion",
    icon: "Layers",
    description: "Combining and ranking results",
  },
];

// Query type display info
export const QUERY_TYPE_INFO: Record<
  QueryType,
  { label: string; color: string; description: string }
> = {
  structured: {
    label: "STRUCTURED",
    color: "#00d9ff",
    description: "Database query with exact filters",
  },
  semantic: {
    label: "SEMANTIC",
    color: "#a855f7",
    description: "Semantic similarity search",
  },
  hybrid: {
    label: "HYBRID",
    color: "#feca57",
    description: "Combined database and semantic search",
  },
  temporal: {
    label: "TEMPORAL",
    color: "#1dd1a1",
    description: "Time-based query",
  },
};
