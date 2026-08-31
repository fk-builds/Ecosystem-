"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import ToolCallFeed from "@/components/ToolCallFeed";
import type { ChatMessage, ToolTrace } from "@/lib/protocol";

interface Props {
  messages: ChatMessage[];
  streamingText: string;
  toolCalls: ToolTrace[];
  busy: boolean;
  onSend: (prompt: string) => void;
  onCancel: () => void;
  onInsert: (content: string) => void;
}

const SUGGESTIONS = [
  "Add a modern hero section",
  "Add a features grid with 3 cards",
  "Change the heading to Ship Faster",
  "Remove the button",
];

export default function DevHub({ messages, streamingText, toolCalls, busy, onSend, onCancel, onInsert }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, streamingText, toolCalls.length]);

  const submit = () => {
    if (!input.trim() || busy) return;
    onSend(input);
    setInput("");
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") submit();
  };

  return (
    <div className="flex h-[46%] min-h-[220px] flex-col border-t border-studio-border">
      <div className="flex items-center justify-between border-b border-studio-border px-4 py-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
          <span className={`h-2 w-2 rounded-full ${busy ? "streaming-cursor bg-emerald-400" : "bg-slate-600"}`} />
          Agent Dev Hub
        </h2>
        {busy && (
          <button onClick={onCancel} className="rounded border border-rose-500/40 px-2 py-0.5 text-[11px] text-rose-300 hover:bg-rose-500/10">
            Stop
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !busy && (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">
              Ask the agent to build on your canvas — it streams responses token-by-token and edits the builder live.
            </p>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => onSend(s)}
                className="block w-full rounded-lg border border-studio-border bg-studio-panel px-3 py-2 text-left text-xs text-slate-300 transition hover:border-emerald-400/40 hover:text-emerald-300"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`max-w-[88%] ${m.role === "user" ? "ml-auto" : ""}`}>
            <div
              className={`rounded-xl px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-blue-600/90 text-white"
                  : "border border-studio-border bg-studio-panel text-slate-200"
              }`}
            >
              {m.text}
            </div>
            {m.toolCalls && m.toolCalls.length > 0 && <ToolCallFeed calls={m.toolCalls} />}
          </div>
        ))}

        {busy && (
          <div className="max-w-[88%]">
            <div className="rounded-xl border border-emerald-400/30 bg-studio-panel px-3 py-2 text-sm text-emerald-200">
              {streamingText || <span className="streaming-cursor">▋</span>}
            </div>
            {toolCalls.length > 0 && (
              <button
                onClick={() => onInsert(streamingText)}
                className="mt-1 text-[11px] text-slate-500 hover:text-emerald-300"
              >
                + Keep transcript as text on canvas
              </button>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-studio-border p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Ask agent to build components…"
            className="min-w-0 flex-1 rounded-lg border border-studio-border bg-studio-bg px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600 focus:border-emerald-400"
          />
          <button
            onClick={submit}
            disabled={busy || !input.trim()}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
