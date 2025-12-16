"use client";

import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SimpleChatMessageItem } from "./simple-chat-message";
import { SimpleChatInput } from "./simple-chat-input";
import { useSimpleSSEChat } from "@/hooks/use-simple-sse-chat";

export function SimpleChatContainer() {
  const { messages, sendQuery, isStreaming } = useSimpleSSEChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] bg-slate-900/50 rounded-xl border border-slate-800 overflow-hidden shadow-2xl">
      <ScrollArea className="flex-1 p-4">
        <div className="max-w-[800px] mx-auto space-y-6 pb-4">
          {messages.length === 0 ? (
            <div className="text-center text-muted-foreground mt-20 space-y-2">
              <h3 className="text-lg font-medium text-slate-300">Welcome to Maritime Chat</h3>
              <p>Try asking questions like:</p>
              <ul className="text-sm space-y-1 mt-4 text-emerald-400/80">
                <li>"Where are the tankers near Mumbai?"</li>
                <li>"Show me ships faster than 15 knots"</li>
                <li>"Any suspicious dark ships?"</li>
              </ul>
            </div>
          ) : (
            messages.map((msg) => (
              <SimpleChatMessageItem key={msg.id} message={msg} />
            ))
          )}
          <div ref={scrollRef} />
        </div>
      </ScrollArea>

      <SimpleChatInput onSend={sendQuery} disabled={isStreaming} />
    </div>
  );
}
