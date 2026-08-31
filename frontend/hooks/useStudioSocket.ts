"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { applyOpsLocally, findNode } from "@/lib/canvas";
import { getToken } from "@/lib/api";
import type {
  CanvasOp,
  CanvasState,
  ChatMessage,
  ServerMessage,
  ToolTrace,
} from "@/lib/protocol";
import { createTransport, type TransportKind } from "@/lib/transport";

let seq = 0;
const nextId = (prefix: string) => `${prefix}-${++seq}-${Date.now().toString(36)}`;

export interface Studio {
  status: TransportKind;
  ready: boolean;
  canvas: CanvasState | null;
  messages: ChatMessage[];
  streamingText: string;
  toolCalls: ToolTrace[];
  busy: boolean;
  error: string | null;
  sendPrompt: (prompt: string) => void;
  cancelAgent: () => void;
  addComponent: (type: string, parentId: string, content?: Record<string, unknown>) => void;
  updateComponent: (id: string, patch: { content?: Record<string, unknown>; styles?: Record<string, unknown> }) => void;
  removeComponent: (id: string) => void;
  moveComponent: (id: string, direction: -1 | 1) => void;
  resetCanvas: () => void;
  sendFrame: (type: string, data?: unknown) => void;
}

export function useStudioSocket(projectId?: string | null): Studio {
  const [status, setStatus] = useState<TransportKind>("ws");
  const [canvas, setCanvas] = useState<CanvasState | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolTrace[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const transportRef = useRef<ReturnType<typeof createTransport> | null>(null);
  const canvasRef = useRef<CanvasState | null>(null);
  const streamRef = useRef<string>("");
  const streamMsgId = useRef<string | null>(null);
  canvasRef.current = canvas;

  const commitAgentMessage = useCallback((text?: string) => {
    const body = text ?? streamRef.current;
    if (!body) return;
    streamRef.current = "";
    setStreamingText("");
    const msgId = streamMsgId.current ?? nextId("agent");
    streamMsgId.current = null;
    setMessages((prev) => {
      const copy = [...prev].filter((m) => m.id !== msgId);
      copy.push({ id: msgId, role: "agent" as const, text: body });
      return copy.slice(-100);
    });
  }, []);

  useEffect(() => {
    if (!projectId) {
      setReady(false);
      return;
    }
    const token = getToken();
    if (!token) return;
    const transport = createTransport({
      onStatus: setStatus,
      token,
      projectId,
      wsUrl: process.env.NEXT_PUBLIC_WS_URL,
      onMessage: (msg: ServerMessage) => {
        switch (msg.type) {
          case "INIT_CANVAS":
          case "CANVAS_SYNC": {
            setCanvas(msg.data as CanvasState);
            canvasRef.current = msg.data as CanvasState;
            break;
          }
          case "AGENT_STREAM_START": {
            setBusy(true);
            streamRef.current = "";
            setStreamingText("");
            break;
          }
          case "AGENT_DELTA": {
            const chunk = (msg.data as { chunk?: string })?.chunk ?? "";
            streamRef.current += chunk;
            setStreamingText(streamRef.current);
            break;
          }
          case "AGENT_STREAM_CHUNK": {
            // Legacy frame type for backward compatibility
            const chunk = (msg.data as { chunk?: string })?.chunk ?? "";
            streamRef.current += chunk;
            setStreamingText(streamRef.current);
            break;
          }
          case "AGENT_TOOL_CALL": {
            setToolCalls((prev) => [
              ...prev,
              {
                call_id: (msg.data as ToolTrace).call_id,
                name: (msg.data as ToolTrace).name,
                arguments: (msg.data as ToolTrace).arguments,
              },
            ]);
            break;
          }
          case "AGENT_TOOL_RESULT": {
            const trace = msg.data as ToolTrace;
            setToolCalls((prev) => prev.map((t) => (t.call_id === trace.call_id ? { ...t, ...trace } : t)));
            break;
          }
          case "AGENT_DONE": {
            setBusy(false);
            const data = msg.data as { message?: string; tools?: ToolTrace[]; cancelled?: boolean; error?: string };
            if (data.tools?.length) setToolCalls(data.tools);
            commitAgentMessage(data.message);
            if (data.cancelled) setError("Agent request cancelled");
            break;
          }
          case "AGENT_ERROR": {
            setBusy(false);
            const err = (msg.data as { error?: string })?.error ?? "unknown error";
            setError(err);
            commitAgentMessage(`⚠️ ${err}`);
            break;
          }
          case "PONG":
          case "ROOM_JOINED":
          default:
            break;
        }
      },
    });
    transportRef.current = transport;
    setReady(true);
    return () => {
      transport.close();
      transportRef.current = null;
    };
  }, [commitAgentMessage, projectId]);

  const sendFrame = useCallback((type: string, data?: unknown) => {
    transportRef.current?.send(type, data);
  }, []);

  const sendPrompt = useCallback(
    (prompt: string) => {
      if (!prompt.trim() || busy) return;
      setMessages((prev) => [...prev, { id: nextId("user"), role: "user" as const, text: prompt }].slice(-100));
      setToolCalls([]);
      setError(null);
      sendFrame("AGENT_PROMPT", { prompt: prompt.trim() });
    },
    [busy, sendFrame],
  );

  const cancelAgent = useCallback(() => sendFrame("AGENT_CANCEL"), [sendFrame]);

  const addComponent = useCallback(
    (type: string, parentId: string, content?: Record<string, unknown>) => {
      const canvasNow = canvasRef.current;
      if (!canvasNow) return;
      const ops: CanvasOp[] = [
        { op: "add", component: { type, content: content ?? {} }, parent_id: parentId ?? "root" },
      ];
      setCanvas(applyOpsLocally(canvasNow, ops));
      sendFrame("CANVAS_PATCH", { operations: ops });
    },
    [sendFrame],
  );

  const updateComponent = useCallback(
    (id: string, patch: { content?: Record<string, unknown>; styles?: Record<string, unknown> }) => {
      const canvasNow = canvasRef.current;
      if (!canvasNow) return;
      const ops: CanvasOp[] = [{ op: "update", id, patch }];
      setCanvas(applyOpsLocally(canvasNow, ops));
      sendFrame("CANVAS_PATCH", { operations: ops });
    },
    [sendFrame],
  );

  const removeComponent = useCallback(
    (id: string) => {
      const canvasNow = canvasRef.current;
      if (!canvasNow) return;
      const ops: CanvasOp[] = [{ op: "remove", id }];
      setCanvas(applyOpsLocally(canvasNow, ops));
      sendFrame("CANVAS_PATCH", { operations: ops });
    },
    [sendFrame],
  );

  const moveComponent = useCallback(
    (id: string, direction: -1 | 1) => {
      const canvasNow = canvasRef.current;
      if (!canvasNow) return;
      const locate = (node: CanvasState["root"]): { parentId: string; index: number } | null => {
        for (const child of node.children) {
          if (child.id === id) return { parentId: node.id, index: node.children.indexOf(child) };
          const found = locate(child);
          if (found) return found;
        }
        return null;
      };
      const spot = locate(canvasNow.root);
      if (!spot) return;
      const parent = findNode(canvasNow.root, spot.parentId);
      const target = spot.index + direction;
      if (target < 0 || !parent) return;
      if (target > parent.children.length - 1) return;
      const ops: CanvasOp[] = [{ op: "move", id, parent_id: spot.parentId, index: target }];
      setCanvas(applyOpsLocally(canvasNow, ops));
      sendFrame("CANVAS_PATCH", { operations: ops });
    },
    [sendFrame],
  );

  const resetCanvas = useCallback(() => {
    const canvasNow = canvasRef.current;
    if (!canvasNow) return;
    sendFrame("CANVAS_UPDATE", {
      version: 1,
      id: "studio",
      meta: { name: "FK AI Builder", theme: "dark" },
      root: {
        id: "root",
        type: "page",
        content: {},
        styles: { tailwind: "min-h-screen bg-slate-950 text-slate-100" },
        children: [
          { id: "c-nav-1", type: "nav", content: { brand: "FK AI Builder", links: ["Builder", "Dev Hub", "Docs"] }, styles: {}, children: [] },
          {
            id: "c-hero-1",
            type: "hero",
            content: {
              heading: "Welcome to FK Agent Studio",
              subheading: "A real-time design agent and visual canvas in one workspace.",
              cta: "Get Started",
            },
            styles: {},
            children: [],
          },
        ],
      },
    });
  }, [sendFrame]);

  return {
    status,
    canvas,
    messages,
    streamingText,
    toolCalls,
    busy,
    error,
    ready,
    sendPrompt,
    cancelAgent,
    addComponent,
    updateComponent,
    removeComponent,
    moveComponent,
    resetCanvas,
    sendFrame,
  };
}
