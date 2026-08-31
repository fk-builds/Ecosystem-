"use client";

import { useEffect, useState } from "react";
import { typeLabel } from "@/lib/canvas";
import type { CanvasComponent } from "@/lib/protocol";

interface Props {
  selected?: CanvasComponent;
  onUpdate: (patch: { content?: Record<string, unknown>; styles?: Record<string, unknown> }) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

const CONTENT_FIELDS: Record<string, { key: string; label: string; kind?: "text" | "area" }[]> = {
  hero: [
    { key: "heading", label: "Heading" },
    { key: "subheading", label: "Subheading", kind: "area" },
    { key: "cta", label: "CTA label" },
  ],
  heading: [{ key: "text", label: "Text" }],
  text: [{ key: "text", label: "Text", kind: "area" }],
  button: [
    { key: "text", label: "Label" },
    { key: "href", label: "Href" },
  ],
  card: [
    { key: "title", label: "Title" },
    { key: "text", label: "Description", kind: "area" },
  ],
  input: [
    { key: "label", label: "Label" },
    { key: "placeholder", label: "Placeholder" },
  ],
  nav: [{ key: "brand", label: "Brand" }],
  footer: [{ key: "text", label: "Text" }],
  image: [
    { key: "src", label: "Image URL" },
    { key: "alt", label: "Alt text" },
  ],
};

export default function PropertyInspector({ selected, onUpdate, onRemove, onMoveUp, onMoveDown }: Props) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [tailwind, setTailwind] = useState("");
  const [tailwindDirty, setTailwindDirty] = useState(false);

  useEffect(() => {
    const fields = CONTENT_FIELDS[selected?.type ?? ""] ?? [];
    const next: Record<string, string> = {};
    for (const f of fields) {
      const v = (selected?.content ?? {})[f.key];
      next[f.key] = typeof v === "string" ? v : v == null ? "" : String(v);
    }
    setDraft(next);
    setTailwind(selected ? String(selected.styles?.tailwind ?? "") : "");
    setDirty(false);
    setTailwindDirty(false);
  }, [selected?.id, selected?.type, selected && JSON.stringify(selected.content)]);

  if (!selected) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center text-sm text-slate-500">
        <span className="text-2xl">⌖</span>
        Select a component on the canvas to edit its props and Tailwind classes.
      </div>
    );
  }

  const fields = CONTENT_FIELDS[selected.type] ?? [];

  const apply = () => {
    const content: Record<string, unknown> = { ...draft };
    for (const f of fields) {
      const v = draft[f.key] ?? "";
      if (v === "") delete content[f.key];
      else content[f.key] = v;
    }
    const patch: { content?: Record<string, unknown>; styles?: Record<string, unknown> } = {};
    if (dirty) patch.content = content;
    if (tailwindDirty) patch.styles = { ...(selected.styles ?? {}), tailwind };
    if (Object.keys(patch).length) onUpdate(patch);
    setDirty(false);
    setTailwindDirty(false);
  };

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{typeLabel(selected.type)}</h3>
          <code className="text-[11px] text-slate-500">{selected.id}</code>
        </div>
        <div className="flex gap-1">
          <button onClick={onMoveUp} title="Move up" className="rounded border border-studio-border px-2 py-1 text-xs text-slate-300 hover:text-emerald-300">↑</button>
          <button onClick={onMoveDown} title="Move down" className="rounded border border-studio-border px-2 py-1 text-xs text-slate-300 hover:text-emerald-300">↓</button>
          <button onClick={onRemove} title="Delete" className="rounded border border-rose-500/40 px-2 py-1 text-xs text-rose-400 hover:bg-rose-500/10">✕</button>
        </div>
      </div>

      {fields.length > 0 && (
        <div className="space-y-3">
          {fields.map((f) => (
            <label key={f.key} className="block">
              <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-500">{f.label}</span>
              {f.kind === "area" ? (
                <textarea
                  rows={3}
                  value={draft[f.key] ?? ""}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, [f.key]: e.target.value }));
                    setDirty(true);
                  }}
                  className="w-full rounded-lg border border-studio-border bg-studio-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-emerald-400"
                />
              ) : (
                <input
                  value={draft[f.key] ?? ""}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, [f.key]: e.target.value }));
                    setDirty(true);
                  }}
                  className="w-full rounded-lg border border-studio-border bg-studio-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-emerald-400"
                />
              )}
            </label>
          ))}
        </div>
      )}

      <label className="mt-4 block">
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-500">Tailwind classes</span>
        <textarea
          rows={3}
          value={tailwind}
          onChange={(e) => {
            setTailwind(e.target.value);
            setTailwindDirty(true);
          }}
          className="w-full rounded-lg border border-studio-border bg-studio-bg px-3 py-2 font-mono text-xs text-slate-200 outline-none focus:border-emerald-400"
        />
      </label>

      <button
        onClick={apply}
        disabled={!dirty && !tailwindDirty}
        className="mt-4 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Apply changes
      </button>
      <p className="mt-2 text-[11px] text-slate-500">Changes sync to every connected client in real time.</p>
    </div>
  );
}
