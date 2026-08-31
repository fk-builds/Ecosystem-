"use client";

import Link from "next/link";
import type { TransportKind } from "@/lib/transport";

const STATUS_STYLES: Record<TransportKind, { dot: string; label: string }> = {
  ws: { dot: "bg-emerald-400", label: "Live · WebSocket" },
  poll: { dot: "bg-amber-400", label: "Live · long-poll" },
  offline: { dot: "bg-rose-500", label: "Reconnecting…" },
};

export default function Header({
  projectId,
  canvasName,
  version,
  status,
  ready,
  onReset,
}: {
  projectId: string;
  canvasName: string;
  version: number;
  status: TransportKind;
  ready: boolean;
  onReset: () => void;
}) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.offline;
  return (
    <header className="flex items-center gap-4 border-b border-studio-border bg-studio-panel px-5 py-3">
      <Link href="/dashboard" className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-500 text-sm font-black text-slate-950">
          FK
        </div>
        <div>
          <h1 className="text-sm font-semibold leading-tight">{canvasName}</h1>
          <p className="text-[11px] text-slate-500">Agent Dev Hub + Builder Studio</p>
        </div>
      </Link>

      <div className="ml-auto flex items-center gap-3 text-xs">
        <span className="flex items-center gap-1.5 rounded-full border border-studio-border bg-studio-bg px-2.5 py-1 text-slate-400">
          <span className={`h-2 w-2 rounded-full ${ready ? s.dot : "bg-slate-600"}`} />
          {ready ? s.label : "Connecting…"}
        </span>
        <span className="rounded-full border border-studio-border bg-studio-bg px-2.5 py-1 text-slate-400">
          v{version} · {projectId}
        </span>
        <button
          onClick={() => {
            if (window.confirm("Reset this canvas to the default sample?")) onReset();
          }}
          className="rounded-md border border-studio-border px-3 py-1 text-slate-400 transition hover:border-rose-500/50 hover:text-rose-300"
        >
          Reset
        </button>
        <Link href="/dashboard" className="rounded-md border border-studio-border px-3 py-1 text-slate-400 transition hover:text-emerald-300">
          Projects
        </Link>
      </div>
    </header>
  );
}
