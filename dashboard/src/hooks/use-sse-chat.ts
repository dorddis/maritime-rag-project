/**
 * SSE Chat Hook - Handles Server-Sent Events for RAG pipeline streaming
 */

import { useCallback, useRef } from "react";
import { useChatStore } from "@/stores/chat-store";
import type {
  ChatRequest,
  SSEEventType,
  RoutingEventData,
  SQLCompleteEventData,
  VectorCompleteEventData,
  RealtimeEventData,
  FusionEventData,
  AnswerEventData,
  DoneEventData,
  QueryType,
} from "@/lib/chat-types";

// API base URL
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

// SSE event line parser
function parseSSELine(line: string): { event?: string; data?: string } {
  if (line.startsWith("event:")) {
    return { event: line.slice(6).trim() };
  }
  if (line.startsWith("data:")) {
    return { data: line.slice(5).trim() };
  }
  return {};
}

// Parse SSE text into events
function parseSSEText(text: string): Array<{ event: string; data: unknown }> {
  const events: Array<{ event: string; data: unknown }> = [];
  const blocks = text.split("\n\n").filter((block) => block.trim());

  for (const block of blocks) {
    const lines = block.split("\n");
    let currentEvent = "message";
    let currentData = "";

    for (const line of lines) {
      const { event, data } = parseSSELine(line);
      if (event) currentEvent = event;
      if (data) currentData = data;
    }

    if (currentData) {
      try {
        events.push({
          event: currentEvent,
          data: JSON.parse(currentData),
        });
      } catch (e) {
        console.warn("Failed to parse SSE data:", currentData);
      }
    }
  }

  return events;
}

export function useSSEChat() {
  const store = useChatStore();
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendQuery = useCallback(
    async (query: string, options?: Partial<ChatRequest>) => {
      // Cancel any existing request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      // Create new abort controller
      abortControllerRef.current = new AbortController();

      // Add user message
      store.addUserMessage(query);

      // Add assistant message placeholder
      const assistantMsgId = store.addAssistantMessage();

      try {
        // Make POST request for SSE stream
        const response = await fetch(`${API_BASE}/api/rag/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            query,
            include_realtime: options?.include_realtime ?? true,
            max_results: options?.max_results ?? 10,
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("No response body");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        // Read stream
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          // Decode chunk and add to buffer
          buffer += decoder.decode(value, { stream: true });

          // Parse complete events from buffer
          const events = parseSSEText(buffer);

          // Clear processed content from buffer
          const lastDoubleNewline = buffer.lastIndexOf("\n\n");
          if (lastDoubleNewline !== -1) {
            buffer = buffer.slice(lastDoubleNewline + 2);
          }

          // Process events
          for (const { event, data } of events) {
            handleSSEEvent(assistantMsgId, event as SSEEventType, data);
          }
        }

        // Complete message
        store.completeMessage(assistantMsgId);
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          console.log("Request aborted");
          return;
        }

        console.error("SSE Chat error:", error);
        store.setError(
          assistantMsgId,
          (error as Error).message || "Failed to get response"
        );
      }
    },
    [store]
  );

  const handleSSEEvent = useCallback(
    (messageId: string, event: SSEEventType, data: unknown) => {
      switch (event) {
        case "routing": {
          const routingData = data as RoutingEventData;
          if (routingData.status === "start") {
            store.updateRoutingStep(messageId, { status: "running" });
          } else if (routingData.status === "complete") {
            store.updateRoutingStep(messageId, {
              status: "complete",
              queryType: routingData.query_type as QueryType,
              confidence: routingData.confidence,
              reasoning: routingData.reasoning,
              extractedFilters: routingData.extracted_filters,
              timeRange: routingData.time_range,
              semanticQuery: routingData.semantic_query,
              executionTimeMs: routingData.execution_time_ms,
            });

            // Mark steps as skipped based on query type
            const queryType = routingData.query_type;
            if (queryType === "semantic") {
              store.updateSQLStep(messageId, { status: "skipped" });
            } else if (queryType === "structured" || queryType === "temporal") {
              store.updateVectorStep(messageId, { status: "skipped" });
            }
          }
          break;
        }

        case "sql_start": {
          store.updateSQLStep(messageId, { status: "running" });
          break;
        }

        case "sql_complete": {
          const sqlData = data as SQLCompleteEventData;
          store.updateSQLStep(messageId, {
            status: sqlData.status === "error" ? "error" : "complete",
            sql: sqlData.sql,
            rowCount: sqlData.row_count,
            totalResults: sqlData.total_results,
            results: sqlData.results,
            explanation: sqlData.explanation,
            executionTimeMs: sqlData.execution_time_ms,
            error: sqlData.error,
          });
          break;
        }

        case "vector_start": {
          const vectorStartData = data as { query: string };
          store.updateVectorStep(messageId, {
            status: "running",
            query: vectorStartData.query,
          });
          break;
        }

        case "vector_complete": {
          const vectorData = data as VectorCompleteEventData;
          store.updateVectorStep(messageId, {
            status: vectorData.status === "error" ? "error" : "complete",
            query: vectorData.query,
            resultCount: vectorData.result_count,
            topSimilarities: vectorData.top_similarities,
            sources: vectorData.sources,
            results: vectorData.results,
            executionTimeMs: vectorData.execution_time_ms,
            error: vectorData.error,
          });
          break;
        }

        case "realtime": {
          const realtimeData = data as RealtimeEventData;
          store.updateRealtimeStep(messageId, {
            status: realtimeData.status === "error" ? "error" : "complete",
            trackCount: realtimeData.track_count,
            filtersApplied: realtimeData.filters_applied,
            results: realtimeData.results,
            executionTimeMs: realtimeData.execution_time_ms,
            error: realtimeData.error,
          });
          break;
        }

        case "fusion": {
          const fusionData = data as FusionEventData;
          store.updateFusionStep(messageId, {
            status: "complete",
            method: fusionData.method,
            rrfK: fusionData.rrf_k,
            weights: fusionData.weights,
            totalResults: fusionData.total_results,
            breakdown: fusionData.breakdown,
            results: fusionData.results,
            executionTimeMs: fusionData.execution_time_ms,
          });

          // Also set results on the message
          if (fusionData.results) {
            store.setResults(messageId, fusionData.results);
          }
          break;
        }

        case "answer": {
          const answerData = data as AnswerEventData;
          store.setAnswer(messageId, answerData.content);
          break;
        }

        case "error": {
          const errorData = data as { error: string };
          store.setError(messageId, errorData.error);
          break;
        }

        case "done": {
          const doneData = data as DoneEventData;
          console.log("Pipeline complete:", doneData);
          // Message will be completed in the main loop
          break;
        }
      }
    },
    [store]
  );

  const cancelQuery = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    store.setStreaming(false);
  }, [store]);

  return {
    sendQuery,
    cancelQuery,
    isStreaming: store.isStreaming,
    messages: store.messages,
    clearHistory: store.clearHistory,
  };
}
