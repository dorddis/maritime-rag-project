"use client";

/**
 * Chat Container - Main layout with message history and input
 */

import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatInput } from "./chat-input";
import { ChatMessage } from "./chat-message";
import { useSSEChat } from "@/hooks/use-sse-chat";
import { MessageSquare } from "lucide-react";

export function ChatContainer() {
  const { sendQuery, isStreaming, messages } = useSSEChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = (query: string) => {
    sendQuery(query);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-120px)]">
      {/* Message History */}
      <ScrollArea className="flex-1 pr-4" ref={scrollRef}>
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-4 pb-4">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="pt-4 border-t border-slate-700">
        <ChatInput onSubmit={handleSubmit} isLoading={isStreaming} />
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] text-center">
      <div className="p-4 rounded-full bg-slate-800 mb-4">
        <MessageSquare className="h-8 w-8 text-cyan-400" />
      </div>
      <h2 className="text-xl font-semibold text-slate-200 mb-2">
        Ask about your maritime data
      </h2>
      <p className="text-muted-foreground max-w-md mb-6">
        Use natural language to query ship positions, find patterns, and analyze
        maritime activity.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg">
        <ExampleQuery query="Show me all tankers near Mumbai" />
        <ExampleQuery query="Find ships with suspicious behavior" />
        <ExampleQuery query="Dark ships detected in the last hour" />
        <ExampleQuery query="Cargo vessels faster than 15 knots" />
      </div>
    </div>
  );
}

function ExampleQuery({ query }: { query: string }) {
  const { sendQuery, isStreaming } = useSSEChat();

  return (
    <button
      onClick={() => !isStreaming && sendQuery(query)}
      disabled={isStreaming}
      className="text-left px-4 py-3 rounded-lg border border-slate-700 bg-slate-800/50 hover:bg-slate-800 hover:border-cyan-500/50 transition-colors text-sm text-slate-300 disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {query}
    </button>
  );
}
