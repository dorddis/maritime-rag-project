"use client";

/**
 * Chat Input - Query input with send button
 */

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSubmit: (query: string) => void;
  isLoading: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSubmit, isLoading, disabled }: ChatInputProps) {
  const [query, setQuery] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 150)}px`;
    }
  }, [query]);

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = () => {
    const trimmedQuery = query.trim();
    if (trimmedQuery && !isLoading && !disabled) {
      onSubmit(trimmedQuery);
      setQuery("");
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter to send, Shift+Enter for newline
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex gap-3 items-end">
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about ships, positions, patterns..."
          disabled={isLoading || disabled}
          rows={1}
          className="w-full resize-none rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <div className="absolute right-3 bottom-3 text-xs text-muted-foreground">
          {isLoading ? (
            "Processing..."
          ) : (
            <span>
              Press <kbd className="px-1 py-0.5 rounded bg-slate-700 text-[10px]">Enter</kbd> to send
            </span>
          )}
        </div>
      </div>
      <Button
        onClick={handleSubmit}
        disabled={!query.trim() || isLoading || disabled}
        className="h-12 px-4 bg-cyan-600 hover:bg-cyan-700"
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}
