"use client";

/**
 * Chat Message - Renders user or assistant message with pipeline visualization
 */

import { User, Bot, AlertCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { PipelineVisualization } from "./pipeline-visualization";
import { ShipResultCard } from "./ship-result-card";
import type { ChatMessage as ChatMessageType } from "@/lib/chat-types";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return <UserMessage content={message.content} />;
  }

  return (
    <AssistantMessage
      content={message.content}
      pipeline={message.pipeline}
      results={message.results}
      isStreaming={message.isStreaming}
      error={message.error}
    />
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3 justify-end">
      <div className="max-w-[80%]">
        <Card className="bg-cyan-600/20 border-cyan-500/30 px-4 py-3">
          <p className="text-sm text-slate-200 whitespace-pre-wrap">{content}</p>
        </Card>
      </div>
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-cyan-500/20 flex items-center justify-center">
        <User className="h-4 w-4 text-cyan-400" />
      </div>
    </div>
  );
}

function AssistantMessage({
  content,
  pipeline,
  results,
  isStreaming,
  error,
}: {
  content: string;
  pipeline?: ChatMessageType["pipeline"];
  results?: ChatMessageType["results"];
  isStreaming?: boolean;
  error?: string;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
        <Bot className="h-4 w-4 text-slate-300" />
      </div>
      <div className="flex-1 space-y-3 min-w-0">
        {/* Pipeline Visualization */}
        {pipeline && <PipelineVisualization pipeline={pipeline} />}

        {/* Error */}
        {error && (
          <Card className="bg-red-500/10 border-red-500/30 px-4 py-3">
            <div className="flex items-center gap-2 text-red-400">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm font-medium">Error</span>
            </div>
            <p className="text-sm text-red-300 mt-1">{error}</p>
          </Card>
        )}

        {/* Answer */}
        {content && !error && (
          <Card className="bg-slate-800/50 border-slate-700 px-4 py-3">
            <div className="text-sm text-slate-200 whitespace-pre-wrap">
              {renderMarkdownBold(content)}
            </div>
          </Card>
        )}

        {/* Results */}
        {results && results.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
              Top Results ({results.length})
            </p>
            <div className="grid gap-2 grid-cols-1 lg:grid-cols-2">
              {results.slice(0, 6).map((result, index) => (
                <ShipResultCard key={result.track_id || result.mmsi || index} result={result} />
              ))}
            </div>
          </div>
        )}

        {/* Streaming indicator */}
        {isStreaming && !content && !error && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <div className="flex gap-1">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-xs">Processing query...</span>
          </div>
        )}
      </div>
    </div>
  );
}

// Simple markdown bold renderer (converts **text** to <strong>)
function renderMarkdownBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="text-cyan-400 font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}
