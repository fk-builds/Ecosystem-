"use client";

import { useEffect, useState } from "react";
import type { CanvasState } from "@/lib/protocol";

interface CodePayload {
  format: string;
  html: string;
  react: string;
  version: number;
}

interface Props {
  canvas: CanvasState | null;
  projectId?: string;
  compact?: boolean;
}

export default function CodePreview({ canvas, projectId, compact }: Props) {
  const [payload, setPayload] = useState<CodePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"html" | "react">("html");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!canvas || !projectId) return;
    setLoading(true);
    fetch(`/api/projects/${projectId}/code?format=html`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: CodePayload) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, canvas?.version]);

  const code = payload ? (mode === "html" ? payload.html : payload.react) : "";

  const copy = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const download = () => {
    if (!code) return;
    const blob = new Blob([code], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = mode === "html" ? "canvas.html" : "Canvas.tsx";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (compact) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-studio-border px-3 py-2">
          {(["html", "react"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded px-2 py-0.5 text-[11px] ${mode === m ? "bg-studio-accentSoft text-emerald-300" : "text-slate-500"}`}
            >
              {m.toUpperCase()}
            </button>
          ))}
          <span className="ml-auto text-[10px] text-slate-600">v{payload?.version ?? "—"}</span>
          <button onClick={copy} className="text-[11px] text-slate-400 hover:text-emerald-300">{copied ? "✓" : "Copy"}</button>
        </div>
        <pre className="min-h-0 flex-1 overflow-auto p-3 font-mono text-[10.5px] leading-relaxed text-slate-300">
          {loading ? "generating…" : code}
        </pre>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-studio-border bg-studio-panel px-4 py-2">
        <div className="flex gap-1" aria-hidden>
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
        </div>
        <span className="ml-2 text-xs text-slate-400">Generated output — regenerates on every canvas change</span>
        <div className="ml-auto flex items-center gap-2">
          {(["html", "react"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded px-2 py-0.5 text-[11px] ${mode === m ? "bg-studio-accentSoft text-emerald-300" : "text-slate-500"}`}
            >
              {m.toUpperCase()}
            </button>
          ))}
          <button onClick={copy} className="rounded border border-studio-border px-2 py-0.5 text-[11px] text-slate-300 hover:text-emerald-300">
            {copied ? "Copied ✓" : "Copy"}
          </button>
          <button onClick={download} className="rounded border border-studio-border px-2 py-0.5 text-[11px] text-slate-300 hover:text-emerald-300">
            ↓ .{mode === "html" ? "html" : "tsx"}
          </button>
        </div>
      </div>

      {mode === "html" && payload ? (
        <iframe title="Live preview" className="min-h-0 flex-1 bg-white" srcDoc={payload.html} />
      ) : (
        <pre className="min-h-0 flex-1 overflow-auto p-4 font-mono text-xs leading-relaxed text-slate-300">
          {loading ? "generating…" : code || "No canvas yet."}
        </pre>
      )}
    </div>
  );
}
