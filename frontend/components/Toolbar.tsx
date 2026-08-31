"use client";

import type { DragEvent } from "react";
import { typeLabel } from "@/lib/canvas";

const PALETTE = [
  { type: "section", icon: "▦" },
  { type: "hero", icon: "🚀" },
  { type: "heading", icon: "H" },
  { type: "text", icon: "¶" },
  { type: "button", icon: "⌁" },
  { type: "card", icon: "▤" },
  { type: "image", icon: "▣" },
  { type: "form", icon: "✉" },
  { type: "grid", icon: "⊞" },
  { type: "nav", icon: "☰" },
  { type: "divider", icon: "―" },
  { type: "footer", icon: "⏝" },
];

export const PALETTE_TYPES = PALETTE.map((p) => p.type);

export default function Toolbar({ onAdd }: { onAdd: (type: string) => void }) {
  const onDragStart = (e: DragEvent, type: string) => {
    e.dataTransfer.setData("application/fk-component", type);
    e.dataTransfer.effectAllowed = "copy";
  };

  return (
    <aside className="flex w-40 shrink-0 flex-col border-r border-studio-border bg-studio-panel">
      <div className="border-b border-studio-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Components
      </div>
      <div className="flex flex-col gap-1 overflow-y-auto p-2">
        {PALETTE.map(({ type, icon }) => (
          <button
            key={type}
            draggable
            onDragStart={(e) => onDragStart(e, type)}
            onClick={() => onAdd(type)}
            title={`Drag to canvas or click to add "${typeLabel(type)}"`}
            className="group flex cursor-grab items-center gap-2 rounded-md border border-transparent px-2 py-1.5 text-left text-sm text-slate-300 transition hover:border-studio-border hover:bg-studio-bg hover:text-emerald-300 active:cursor-grabbing"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded bg-studio-bg text-xs text-slate-500 group-hover:text-emerald-400">
              {icon}
            </span>
            {typeLabel(type)}
          </button>
        ))}
      </div>
      <div className="mt-auto border-t border-studio-border p-3 text-[11px] leading-relaxed text-slate-500">
        Drag onto a container to nest.
      </div>
    </aside>
  );
}
