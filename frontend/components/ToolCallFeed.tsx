"use client";

import { useState } from "react";
import type { ToolTrace } from "@/lib/protocol";

export default function ToolCallFeed({ calls }: { calls: ToolTrace[] }) {
  const [open, setOpen] = useState<string | null>(null);

  if (!calls.length) return null;

  return (
    <div className="mt-1.5 space-y-1">
      {calls.map((call) => {
        const expanded = open === call.call_id;
        const summary = summarize(call);
        return (
          <button
            key={call.call_id}
            onClick={() => setOpen(expanded ? null : call.call_id)}
            className="block w-full rounded-lg border border-studio-border bg-studio-bg px-2.5 py-1.5 text-left text-[11px] transition hover:border-emerald-400/30"
          >
            <span className="flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${call.ok === false ? "bg-rose-500" : "bg-emerald-400"}`} />
              <span className="font-mono text-emerald-300">{call.name}</span>
              <span className="ml-auto text-slate-500">{call.ok === false ? "failed" : "ok"}</span>
            </span>
            {expanded && (
              <pre className="mt-1.5 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-[#0a0f1a] p-2 text-[10px] text-slate-400">
                {JSON.stringify(call, null, 2)}
              </pre>
            )}
            {summary && !expanded && <span className="mt-0.5 block text-slate-600">{summary}</span>}
          </button>
        );
      })}
    </div>
  );
}

function summarize(call: ToolTrace): string {
  if (!call.result) return call.error ?? "";
  const result = call.result as Record<string, unknown> | string;
  if (typeof result === "string") return result.slice(0, 90);
  if (result.version != null) return `canvas → version ${result.version}`;
  if (Array.isArray(result.hits)) return `memory → ${(result.hits as unknown[]).length} hits`;
  if (Array.isArray(result.commits)) return `${(result.commits as unknown[]).length} commit(s)`;
  return "";
}
