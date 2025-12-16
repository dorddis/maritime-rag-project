/**
 * Zustand store for Simple Chat state management
 */

import { create } from "zustand";
import type { ShipResult, MessageRole } from "@/lib/chat-types";

// Generate unique message ID
function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

export interface SimpleChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  results?: ShipResult[];
  isStreaming?: boolean;
  error?: string;
}

interface SimpleChatStore {
  // Messages
  messages: SimpleChatMessage[];
  addUserMessage: (content: string) => string;
  addAssistantMessage: () => string;
  
  // Updates
  setAnswer: (messageId: string, content: string) => void;
  setResults: (messageId: string, results: ShipResult[]) => void;
  setError: (messageId: string, error: string) => void;
  completeMessage: (messageId: string) => void;

  // State
  isStreaming: boolean;
  setStreaming: (streaming: boolean) => void;
  clearHistory: () => void;
}

export const useSimpleChatStore = create<SimpleChatStore>((set, get) => ({
  messages: [],
  isStreaming: false,

  setStreaming: (streaming: boolean) => set({ isStreaming: streaming }),

  addUserMessage: (content: string) => {
    const id = generateId();
    set((state) => ({
      messages: [
        ...state.messages,
        { id, role: "user", content, timestamp: new Date() },
      ],
    }));
    return id;
  },

  addAssistantMessage: () => {
    const id = generateId();
    set((state) => ({
      isStreaming: true,
      messages: [
        ...state.messages,
        {
          id,
          role: "assistant",
          content: "",
          timestamp: new Date(),
          isStreaming: true,
        },
      ],
    }));
    return id;
  },

  setAnswer: (id: string, content: string) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, content } : msg
      ),
    }));
  },

  setResults: (id: string, results: ShipResult[]) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, results } : msg
      ),
    }));
  },

  setError: (id: string, error: string) => {
    set((state) => ({
      isStreaming: false,
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, error, isStreaming: false } : msg
      ),
    }));
  },

  completeMessage: (id: string) => {
    set((state) => ({
      isStreaming: false,
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, isStreaming: false } : msg
      ),
    }));
  },

  clearHistory: () => set({ messages: [], isStreaming: false }),
}));
