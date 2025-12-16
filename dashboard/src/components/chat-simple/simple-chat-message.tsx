"use client";

import { User, Bot, AlertTriangle, Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ShipResultCard } from "@/components/chat/ship-result-card"; // Reuse existing card
import type { SimpleChatMessage } from "@/stores/simple-chat-store";
import { Badge } from "@/components/ui/badge";

export function SimpleChatMessageItem({ message }: { message: SimpleChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="bg-emerald-600/20 text-emerald-100 rounded-lg px-4 py-2 max-w-[80%] border border-emerald-500/30">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 mb-6">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
        <Bot className="h-4 w-4 text-slate-300" />
      </div>
      
      <div className="flex-1 space-y-4 min-w-0">
        {/* Error */}
        {message.error && (
          <Card className="bg-red-500/10 border-red-500/30 px-4 py-3 text-red-300">
            <div className="flex items-center gap-2 mb-1 text-red-400 font-medium">
              <AlertTriangle className="h-4 w-4" />
              Error
            </div>
            {message.error}
          </Card>
        )}

        {/* Text Answer */}
        {message.content && (
          <div className="prose prose-invert prose-sm max-w-none text-slate-200 whitespace-pre-wrap leading-relaxed">
            {message.content}
          </div>
        )}

        {/* Ship Results Grid */}
        {message.results && message.results.length > 0 && (
          <div className="space-y-2 mt-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider font-semibold">
              <Search className="h-3 w-3" />
              Found {message.results.length} Results
            </div>
            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-2">
              {message.results.slice(0, 6).map((result, i) => (
                <ShipResultCard key={result.track_id || i} result={result} />
              ))}
            </div>
          </div>
        )}

        {/* Loading Indicator */}
        {message.isStreaming && !message.content && !message.error && (
          <div className="flex gap-1 h-6 items-center">
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-bounce" />
          </div>
        )}
      </div>
    </div>
  );
}
