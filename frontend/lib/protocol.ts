/**
 * Canonical real-time protocol — mirrors backend/app/protocol.py.
 * Every frame: { type, data?, request_id?, room? }
 */

export type ServerEventType =
  | "INIT_CANVAS"
  | "CANVAS_SYNC"
  | "ROOM_JOINED"
  | "PONG"
  | "AGENT_STREAM_START"
  | "AGENT_STREAM_CHUNK"
  | "AGENT_STREAM_END"
  | "AGENT_DELTA"
  | "AGENT_TOOL_CALL"
  | "AGENT_TOOL_RESULT"
  | "AGENT_DONE"
  | "AGENT_ERROR";

export type CanvasOp =
  | { op: "add"; component: { type: string; id?: string; content?: Record<string, unknown>; styles?: Record<string, unknown> }; parent_id?: string; index?: number }
  | { op: "update"; id: string; patch: { content?: Record<string, unknown>; styles?: Record<string, unknown>; type?: string } }
  | { op: "remove"; id: string }
  | { op: "delete"; id: string }
  | { op: "move"; id: string; parent_id?: string; index?: number };

export interface ServerMessage<T = unknown> {
  type: ServerEventType;
  data: T;
  room?: string;
  request_id?: string | null;
}

export interface CanvasComponent {
  id: string;
  type: string;
  content: Record<string, unknown>;
  styles: Record<string, unknown>;
  children: CanvasComponent[];
}

export interface CanvasState {
  version: number;
  id: string;
  meta: { name: string; theme?: string; updated_at?: string | null; updated_by?: string | null };
  root: CanvasComponent;
}

export interface ToolTrace {
  call_id: string;
  name: string;
  arguments?: unknown;
  ok?: boolean;
  result?: unknown;
  error?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  toolCalls?: ToolTrace[];
}

export function makeFrame(type: string, data?: unknown) {
  return { type, data };
}

export function eventLabel(type: ServerEventType): string {
  const labels: Record<string, string> = {
    INIT_CANVAS: "Canvas loaded",
    CANVAS_SYNC: "Canvas synced",
    AGENT_STREAM_START: "Agent started",
    AGENT_DELTA: "Token",
    AGENT_TOOL_CALL: "Tool call",
    AGENT_TOOL_RESULT: "Tool result",
    AGENT_DONE: "Agent finished",
    AGENT_ERROR: "Error",
  };
  return labels[type] ?? type;
}
