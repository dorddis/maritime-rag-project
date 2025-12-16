"use client";

/**
 * Simplified Chat Page - Focuses on Q&A and Results
 */

import Link from "next/link";
import { ArrowLeft, MessageSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SimpleChatContainer } from "@/components/chat-simple/simple-chat-container";
import { useSimpleChatStore } from "@/stores/simple-chat-store";

export default function SimpleChatPage() {
  const clearHistory = useSimpleChatStore((state) => state.clearHistory);
  const messageCount = useSimpleChatStore((state) => state.messages.length);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="container mx-auto max-w-[1000px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Dashboard
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-emerald-500/20">
                  <MessageSquare className="h-5 w-5 text-emerald-400" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-emerald-400">
                    Maritime Assistant
                  </h1>
                  <p className="text-xs text-muted-foreground">
                    Ask questions about your fleet
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
                Clear
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 container mx-auto max-w-[1000px] px-4 py-4 flex flex-col">
        <SimpleChatContainer />
      </main>
    </div>
  );
}
