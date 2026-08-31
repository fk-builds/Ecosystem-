"use client";

import { useCallback, useMemo, useRef, type DragEvent, type MouseEvent } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import { CONTAINER_TYPES, NODE_W, typeLabel, type CanvasComponent, type FlowNode } from "@/lib/canvas";
import type { FlowEdge } from "@/lib/canvas";

interface Props {
  nodes: FlowNode[];
  edges: FlowEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onPaletteDrop: (type: string, parentId: string) => void;
}

type StudioNodeData = CanvasComponent;

function StudioNode({ data, selected }: { data: StudioNodeData; selected: boolean }) {
  const comp = data;
  const container = CONTAINER_TYPES.has(comp.type);
  const text = previewText(comp);
  return (
    <div
      data-node-id={comp.id}
      className={`w-[300px] rounded-xl border bg-[#0e1526] p-3 shadow-lg transition ${
        selected ? "border-emerald-400 shadow-emerald-500/20" : "border-[#1c2740] hover:border-[#2b3a5e]"
      }`}
      style={{ width: NODE_W }}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="rounded bg-studio-bg px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
          {typeLabel(comp.type)}
        </span>
        {container && <span className="text-[10px] text-slate-500">container · {comp.children.length}</span>}
      </div>
      {text ? <p className="line-clamp-2 text-xs text-slate-300">{text}</p> : <p className="text-xs text-slate-600">(empty)</p>}
      <code className="mt-1.5 block truncate text-[10px] text-slate-600">{comp.id}</code>
    </div>
  );
}

function previewText(comp: CanvasComponent): string {
  const c = comp.content as Record<string, unknown>;
  return String(c.heading ?? c.text ?? c.title ?? c.brand ?? c.cta ?? c.placeholder ?? "");
}

const nodeTypes = { studio: StudioNode };

export default function BuilderCanvas({ nodes, edges, selectedId, onSelect, onPaletteDrop }: Props) {
  const wrapper = useRef<HTMLDivElement>(null);

  const flowNodes: Node[] = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        type: "studio",
        position: n.position,
        data: n.data.component,
        selected: n.id === selectedId,
      })),
    [nodes, selectedId],
  );

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/fk-component");
      if (!type) return;
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-node-id]");
      const parentId = target?.getAttribute("data-node-id") ?? "root";
      onPaletteDrop(type, parentId);
    },
    [onPaletteDrop],
  );

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const onNodeClick = useCallback((_: MouseEvent, node: Node) => onSelect(node.id), [onSelect]);
  const onPaneClick = useCallback(() => onSelect(null), [onSelect]);

  return (
    <div ref={wrapper} className="h-full w-full" onDrop={onDrop} onDragOver={onDragOver}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={flowNodes}
          edges={edges as Edge[]}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          fitView
          minZoom={0.3}
          maxZoom={1.6}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1c2740" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={() => "#0e1526"}
            nodeStrokeColor={() => "#2b3a5e"}
            maskColor="rgba(10, 15, 26, 0.7)"
          />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
