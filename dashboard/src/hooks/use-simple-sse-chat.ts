"use client";

import { useCallback, useRef } from "react";
import { useSimpleChatStore } from "@/stores/simple-chat-store";
import type { SSEEventType, AnswerEventData, FusionEventData, ErrorEventData } from "@/lib/chat-types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

// Helper to parse SSE
function parseSSEText(text: string): Array<{ event: string; data: any }> {
  const events: Array<{ event: string; data: any }> = [];
  const blocks = text.split("\n\n").filter((block) => block.trim());

  for (const block of blocks) {
    const lines = block.split("\n");
    let currentEvent = "message";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event:")) currentEvent = line.slice(6).trim();
      if (line.startsWith("data:")) currentData = line.slice(5).trim();
    }

    if (currentData) {
      try {
        events.push({ event: currentEvent, data: JSON.parse(currentData) });
      } catch (e) {
        console.warn("Failed to parse SSE data:", currentData);
      }
    }
  }
  return events;
}

export function useSimpleSSEChat() {
  const store = useSimpleChatStore();
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendQuery = useCallback(
    async (query: string) => {
      // Cancel previous
      if (abortControllerRef.current) abortControllerRef.current.abort();
      abortControllerRef.current = new AbortController();

      store.addUserMessage(query);
      const assistantMsgId = store.addAssistantMessage();

      try {
        const response = await fetch(`${API_BASE}/api/rag/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({ query }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = parseSSEText(buffer);
          
          // Clear processed buffer
          const lastDoubleNewline = buffer.lastIndexOf("\n\n");
          if (lastDoubleNewline !== -1) buffer = buffer.slice(lastDoubleNewline + 2);

          for (const { event, data } of events) {
            if (event === "answer") {
              store.setAnswer(assistantMsgId, (data as AnswerEventData).content);
            } else if (event === "fusion") {
              // Capture fusion results (ship cards)
              const fusionData = data as FusionEventData;
              if (fusionData.results && fusionData.results.length > 0) {
                store.setResults(assistantMsgId, fusionData.results);
              }
            } else if (event === "error") {
              store.setError(assistantMsgId, (data as ErrorEventData).error);
            }
          }
        }
        store.completeMessage(assistantMsgId);
      } catch (error: any) {
        if (error.name === "AbortError") return;
        store.setError(assistantMsgId, error.message || "Failed to get response");
      }
    },
    [store]
  );

  return {
    sendQuery,
    messages: store.messages,
    isStreaming: store.isStreaming,
    clearHistory: store.clearHistory,
  };
}
