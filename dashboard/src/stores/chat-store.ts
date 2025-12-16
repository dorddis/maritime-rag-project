/**
 * Zustand store for RAG Chat state management
 */

import { create } from "zustand";
import type {
  ChatMessage,
  PipelineState,
  StepStatus,
  ShipResult,
  RoutingStep,
  SQLStep,
  VectorStep,
  RealtimeStep,
  FusionStep,
} from "@/lib/chat-types";

// Generate unique message ID
function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

interface ChatStore {
  // Messages
  messages: ChatMessage[];
  addUserMessage: (content: string) => string;
  addAssistantMessage: () => string;
  updateAssistantMessage: (id: string, updates: Partial<ChatMessage>) => void;

  // Current streaming state
  currentMessageId: string | null;
  isStreaming: boolean;
  setStreaming: (streaming: boolean) => void;
  setCurrentMessageId: (id: string | null) => void;

  // Pipeline updates
  initializePipeline: (messageId: string) => void;
  updateRoutingStep: (messageId: string, data: Partial<RoutingStep>) => void;
  updateSQLStep: (messageId: string, data: Partial<SQLStep>) => void;
  updateVectorStep: (messageId: string, data: Partial<VectorStep>) => void;
  updateRealtimeStep: (messageId: string, data: Partial<RealtimeStep>) => void;
  updateFusionStep: (messageId: string, data: Partial<FusionStep>) => void;

  // Results
  setResults: (messageId: string, results: ShipResult[]) => void;
  setAnswer: (messageId: string, content: string) => void;
  setError: (messageId: string, error: string) => void;

  // Complete streaming
  completeMessage: (messageId: string) => void;

  // Session management
  clearHistory: () => void;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  // ============ Messages ============
  messages: [],

  addUserMessage: (content: string) => {
    const id = generateId();
    const message: ChatMessage = {
      id,
      role: "user",
      content,
      timestamp: new Date(),
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));

    return id;
  },

  addAssistantMessage: () => {
    const id = generateId();
    const message: ChatMessage = {
      id,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isStreaming: true,
      pipeline: {
        routing: { status: "pending" },
        sql: { status: "pending" },
        vector: { status: "pending" },
        realtime: { status: "pending" },
        fusion: { status: "pending" },
      },
    };

    set((state) => ({
      messages: [...state.messages, message],
      currentMessageId: id,
      isStreaming: true,
    }));

    return id;
  },

  updateAssistantMessage: (id: string, updates: Partial<ChatMessage>) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    }));
  },

  // ============ Streaming State ============
  currentMessageId: null,
  isStreaming: false,

  setStreaming: (streaming: boolean) => {
    set({ isStreaming: streaming });
  },

  setCurrentMessageId: (id: string | null) => {
    set({ currentMessageId: id });
  },

  // ============ Pipeline Updates ============
  initializePipeline: (messageId: string) => {
    const { updateAssistantMessage } = get();
    updateAssistantMessage(messageId, {
      pipeline: {
        routing: { status: "pending" },
        sql: { status: "pending" },
        vector: { status: "pending" },
        realtime: { status: "pending" },
        fusion: { status: "pending" },
      },
    });
  },

  updateRoutingStep: (messageId: string, data: Partial<RoutingStep>) => {
    set((state) => ({
      messages: state.messages.map((msg) => {
        if (msg.id !== messageId) return msg;
        return {
          ...msg,
          pipeline: {
            ...msg.pipeline,
            routing: { ...msg.pipeline?.routing, ...data } as RoutingStep,
          },
        };
      }),
    }));
  },

  updateSQLStep: (messageId: string, data: Partial<SQLStep>) => {
    set((state) => ({
      messages: state.messages.map((msg) => {
        if (msg.id !== messageId) return msg;
        return {
          ...msg,
          pipeline: {
            ...msg.pipeline,
            sql: { ...msg.pipeline?.sql, ...data } as SQLStep,
          },
        };
      }),
    }));
  },

  updateVectorStep: (messageId: string, data: Partial<VectorStep>) => {
    set((state) => ({
      messages: state.messages.map((msg) => {
        if (msg.id !== messageId) return msg;
        return {
          ...msg,
          pipeline: {
            ...msg.pipeline,
            vector: { ...msg.pipeline?.vector, ...data } as VectorStep,
          },
        };
      }),
    }));
  },

  updateRealtimeStep: (messageId: string, data: Partial<RealtimeStep>) => {
    set((state) => ({
      messages: state.messages.map((msg) => {
        if (msg.id !== messageId) return msg;
        return {
          ...msg,
          pipeline: {
            ...msg.pipeline,
            realtime: { ...msg.pipeline?.realtime, ...data } as RealtimeStep,
          },
        };
      }),
    }));
  },

  updateFusionStep: (messageId: string, data: Partial<FusionStep>) => {
    set((state) => ({
      messages: state.messages.map((msg) => {
        if (msg.id !== messageId) return msg;
        return {
          ...msg,
          pipeline: {
            ...msg.pipeline,
            fusion: { ...msg.pipeline?.fusion, ...data } as FusionStep,
          },
        };
      }),
    }));
  },

  // ============ Results ============
  setResults: (messageId: string, results: ShipResult[]) => {
    const { updateAssistantMessage } = get();
    updateAssistantMessage(messageId, { results });
  },

  setAnswer: (messageId: string, content: string) => {
    const { updateAssistantMessage } = get();
    updateAssistantMessage(messageId, { content });
  },

  setError: (messageId: string, error: string) => {
    const { updateAssistantMessage } = get();
    updateAssistantMessage(messageId, { error, isStreaming: false });
  },

  // ============ Complete Streaming ============
  completeMessage: (messageId: string) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId ? { ...msg, isStreaming: false } : msg
      ),
      isStreaming: false,
      currentMessageId: null,
    }));
  },

  // ============ Session Management ============
  clearHistory: () => {
    set({
      messages: [],
      currentMessageId: null,
      isStreaming: false,
    });
  },
}));
