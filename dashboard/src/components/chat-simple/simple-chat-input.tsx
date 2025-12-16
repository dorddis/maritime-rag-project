"use client";

import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useRef, useEffect } from "react";

interface SimpleChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function SimpleChatInput({ onSend, disabled }: SimpleChatInputProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input);
      setInput("");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-4 border-t border-slate-700 bg-slate-900/50">
      <div className="flex gap-2 max-w-[800px] mx-auto">
        <Input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          className="bg-slate-800 border-slate-700 focus-visible:ring-emerald-500"
          disabled={disabled}
        />
        <Button 
          type="submit" 
          disabled={!input.trim() || disabled}
          className="bg-emerald-600 hover:bg-emerald-500 text-white"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </form>
  );
}
