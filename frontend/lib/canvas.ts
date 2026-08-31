/**
 * Canvas tree <-> React Flow helpers plus a tiny client-side op mirror so the UI
 * feels instant while awaiting the server's canonical CANVAS_SYNC.
 */
import type { CanvasComponent, CanvasOp, CanvasState } from "./protocol";

export type { CanvasComponent, CanvasState };

export interface FlowNodeData {
  component: CanvasComponent;
  depth: number;
  index: number;
}

export interface FlowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: FlowNodeData;
  parentId?: string;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  animated?: boolean;
}

const ROW_H = 96;
const COL_W = 340;
const NODE_W = 300;

/** Convert a canvas tree into positioned React Flow nodes/edges. */
export function buildFlow(canvas: CanvasState): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];

  const walk = (comp: CanvasComponent, parentId: string | null, depth: number, index: number) => {
    nodes.push({
      id: comp.id,
      type: "studio",
      position: { x: depth * COL_W, y: index * ROW_H },
      data: { component: comp, depth, index },
      parentId: parentId ?? undefined,
    });
    comp.children.forEach((child, i) => {
      edges.push({ id: `${comp.id}->${child.id}`, source: comp.id, target: child.id, type: "smoothstep" });
      walk(child, comp.id, depth + 1, i);
    });
  };
  walk(canvas.root, null, 0, 0);
  return { nodes, edges };
}

/** Flatten a tree for palette/search convenience. */
export function flattenTree(root: CanvasComponent): CanvasComponent[] {
  const out: CanvasComponent[] = [];
  const walk = (c: CanvasComponent) => {
    out.push(c);
    c.children.forEach(walk);
  };
  walk(root);
  return out;
}

/** Find a component by id. */
export function findNode(root: CanvasComponent, id: string): CanvasComponent | undefined {
  if (root.id === id) return root;
  for (const child of root.children) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return undefined;
}

/** Parent container of a component (undefined for root). */
export function findParent(root: CanvasComponent, id: string): CanvasComponent | undefined {
  for (const child of root.children) {
    if (child.id === id) return root;
    const found = findParent(child, id);
    if (found) return found;
  }
  return undefined;
}

/** Best-effort client-side mirror of the backend op layer (reconciled by sync). */
export function applyOpsLocally(canvas: CanvasState, ops: CanvasOp[]): CanvasState {
  const next = structuredClone(canvas);
  let failed = false;
  for (const op of ops) {
    try {
      applyOpLocally(next, op);
    } catch {
      failed = true;
      break;
    }
  }
  return failed ? canvas : { ...next, version: next.version + 1 };
}

function applyOpLocally(canvas: CanvasState, op: CanvasOp) {
  switch (op.op) {
    case "add": {
      const parentId = op.parent_id ?? "root";
      const parent = findNode(canvas.root, parentId);
      if (!parent) throw new Error("parent missing");
      const comp: CanvasComponent = {
        id: op.component.id ?? `${op.component.type}-${Math.random().toString(36).slice(2, 8)}`,
        type: op.component.type,
        content: op.component.content ?? {},
        styles: op.component.styles ?? {},
        children: [],
      };
      if (op.index != null) parent.children.splice(op.index, 0, comp);
      else parent.children.push(comp);
      break;
    }
    case "update": {
      const node = findNode(canvas.root, op.id);
      if (!node) throw new Error("missing");
      if (op.patch.content) node.content = { ...node.content, ...op.patch.content };
      if (op.patch.styles) node.styles = { ...node.styles, ...op.patch.styles };
      if (op.patch.type) node.type = op.patch.type;
      break;
    }
    case "remove":
    case "delete": {
      const parent = findParent(canvas.root, op.id);
      if (!parent) throw new Error("missing parent");
      parent.children = parent.children.filter((c) => c.id !== op.id);
      break;
    }
    case "move": {
      const parent = findParent(canvas.root, op.id);
      const node = findNode(canvas.root, op.id);
      if (!parent || !node) throw new Error("missing");
      parent.children = parent.children.filter((c) => c.id !== op.id);
      const dest = findNode(canvas.root, op.parent_id ?? "root");
      if (!dest) throw new Error("dest missing");
      if (op.index != null) dest.children.splice(op.index, 0, node);
      else dest.children.push(node);
      break;
    }
  }
}

/** Type label map used across the UI. */
export const TYPE_LABELS: Record<string, string> = {
  page: "Page",
  section: "Section",
  nav: "Navbar",
  hero: "Hero",
  heading: "Heading",
  text: "Text",
  button: "Button",
  image: "Image",
  card: "Card",
  input: "Input",
  form: "Form",
  grid: "Grid",
  divider: "Divider",
  footer: "Footer",
};

export const CONTAINER_TYPES = new Set(["page", "section", "nav", "hero", "card", "form", "grid", "footer"]);

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

export { NODE_W };
