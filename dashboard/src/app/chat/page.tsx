"use client";

/**
 * RAG Chat Page - Natural language queries with pipeline visualization
 */

import Link from "next/link";
import { ArrowLeft, MessageSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatContainer } from "@/components/chat/chat-container";
import { useChatStore } from "@/stores/chat-store";

export default function ChatPage() {
  const clearHistory = useChatStore((state) => state.clearHistory);
  const messageCount = useChatStore((state) => state.messages.length);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto max-w-[1200px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Dashboard
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-cyan-500/20">
                  <MessageSquare className="h-5 w-5 text-cyan-400" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-cyan-400">
                    RAG Chat
                  </h1>
                  <p className="text-xs text-muted-foreground">
                    Query your maritime data with natural language
                  </p>
                </div>
              </div>
            </div>
            {messageCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearHistory}
                className="gap-2 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
                Clear History
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 container mx-auto max-w-[1200px] px-4 py-4">
        <ChatContainer />
      </main>
    </div>
  );
}
