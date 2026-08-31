"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { StudioShell } from "@/components/StudioShell";
import Header from "@/components/Header";
import Toolbar from "@/components/Toolbar";
import BuilderCanvas from "@/components/BuilderCanvas";
import DevHub from "@/components/DevHub";
import CodePreview from "@/components/CodePreview";
import PropertyInspector from "@/components/PropertyInspector";
import { useStudioSocket } from "@/hooks/useStudioSocket";
import { buildFlow, type CanvasComponent as ComponentNode } from "@/lib/canvas";

type Panel = "inspector" | "code";

export default function ProjectWorkspace() {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <StudioShell>
      <Workspace projectId={projectId} />
    </StudioShell>
  );
}

function Workspace({ projectId }: { projectId: string }) {
  const studio = useStudioSocket(projectId);
  const [panel, setPanel] = useState<Panel>("inspector");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"canvas" | "preview">("canvas");

  const flow = useMemo(() => (studio.canvas ? buildFlow(studio.canvas) : { nodes: [], edges: [] }), [studio.canvas]);

  const selected: ComponentNode | undefined = useMemo(() => {
    if (!selectedId || !studio.canvas) return undefined;
    const lookup = (node: ComponentNode): ComponentNode | undefined => {
      if (node.id === selectedId) return node;
      for (const child of node.children ?? []) {
        const found = lookup(child);
        if (found) return found;
      }
      return undefined;
    };
    return lookup(studio.canvas.root);
  }, [selectedId, studio.canvas]);

  const handlePaletteDrop = (type: string, parentId: string) => {
    studio.addComponent(type, parentId);
  };

  return (
    <div className="flex h-screen flex-col">
      <Header
        projectId={projectId}
        canvasName={studio.canvas?.meta.name ?? "Loading…"}
        version={studio.canvas?.version ?? 0}
        status={studio.status}
        ready={studio.ready}
        onReset={() => studio.resetCanvas()}
      />

      <div className="flex min-h-0 flex-1">
        <Toolbar onAdd={(type) => (selectedId ? studio.addComponent(type, selectedId) : studio.addComponent(type, "root"))} />

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-1 border-b border-studio-border px-4 py-2">
            <button
              onClick={() => setTab("canvas")}
              className={`rounded-md px-3 py-1 text-sm ${tab === "canvas" ? "bg-studio-accentSoft text-emerald-300" : "text-slate-400 hover:text-slate-200"}`}
            >
              Canvas
            </button>
            <button
              onClick={() => setTab("preview")}
              className={`rounded-md px-3 py-1 text-sm ${tab === "preview" ? "bg-studio-accentSoft text-emerald-300" : "text-slate-400 hover:text-slate-200"}`}
            >
              Live Preview
            </button>
            <span className="ml-auto text-xs text-slate-500">version {studio.canvas?.version ?? 0}</span>
          </div>

          {tab === "canvas" ? (
            <div className="min-h-0 flex-1">
              <BuilderCanvas
                nodes={flow.nodes}
                edges={flow.edges}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onPaletteDrop={handlePaletteDrop}
              />
            </div>
          ) : (
            <div className="min-h-0 flex-1 bg-slate-900">
              <CodePreview canvas={studio.canvas} projectId={projectId} />
            </div>
          )}
        </main>

        <aside className="flex w-[420px] min-w-[360px] flex-col border-l border-studio-border">
          <div className="flex border-b border-studio-border">
            <button
              onClick={() => setPanel("inspector")}
              className={`flex-1 px-4 py-2 text-sm ${panel === "inspector" ? "border-b-2 border-emerald-400 text-emerald-300" : "text-slate-400"}`}
            >
              Inspector
            </button>
            <button
              onClick={() => setPanel("code")}
              className={`flex-1 px-4 py-2 text-sm ${panel === "code" ? "border-b-2 border-emerald-400 text-emerald-300" : "text-slate-400"}`}
            >
              Code
            </button>
          </div>
          {panel === "inspector" ? (
            <PropertyInspector
              selected={selected}
              onUpdate={(patch) => selected && studio.updateComponent(selected.id, patch)}
              onRemove={() => {
                if (selected) studio.removeComponent(selected.id);
                setSelectedId(null);
              }}
              onMoveUp={() => selected && studio.moveComponent(selected.id, -1)}
              onMoveDown={() => selected && studio.moveComponent(selected.id, 1)}
            />
          ) : (
            <CodePreview canvas={studio.canvas} projectId={projectId} compact />
          )}

          <DevHub
            messages={studio.messages}
            streamingText={studio.streamingText}
            toolCalls={studio.toolCalls}
            busy={studio.busy}
            onSend={studio.sendPrompt}
            onCancel={studio.cancelAgent}
            onInsert={(content) => {
              if (!content) return;
              studio.addComponent("text", "root", { text: content });
            }}
          />
        </aside>
      </div>
    </div>
  );
}
