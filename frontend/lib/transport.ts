/**
 * Real-time transport that works everywhere.
 *
 *  1. Probe WebSocket /ws?token=...&project=... (best when a gateway supports
 *     upgrade). Zero-latency push.
 *  2. Fallback: sequence-numbered long-poll /api/poll?token=...&project=... —
 *     immune to proxies that buffer/compress infinite SSE streams. Uplink is
 *     POST /api/transport with token+project.
 *
 * Both transports deliver the same protocol frames.
 */
import type { ServerMessage } from "./protocol";

export type TransportKind = "ws" | "poll" | "offline";

export interface Transport {
  kind: TransportKind;
  send: (type: string, data?: unknown) => void;
  close: () => void;
}

export interface TransportOptions {
  onMessage: (msg: ServerMessage) => void;
  onStatus: (kind: TransportKind) => void;
  token: string;
  projectId: string;
  wsUrl?: string;
}

const WS_PROBE_TIMEOUT_MS = 2200;
const POLL_FAIL_RETRY_MS = 1500;

function qs(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

export function createTransport(opts: TransportOptions): Transport {
  let closed = false;
  let ws: WebSocket | null = null;
  let pollTimer: number | null = null;
  let usingWs = false;
  let after = 0;

  const startPolling = () => {
    if (closed || pollTimer !== null) return;
    opts.onStatus("poll");

    const loop = async () => {
      if (closed) return;
      try {
        const query = qs({ token: opts.token, project: opts.projectId, after: String(after) });
        const res = await fetch(`/api/poll?${query}`);
        if (!res.ok) {
          if (res.status === 401) opts.onStatus("offline");
          throw new Error(`HTTP ${res.status}`);
        }
        const payload = (await res.json()) as { frames: { seq: number; message: ServerMessage }[]; after: number };
        for (const frame of payload.frames) {
          after = Math.max(after, frame.seq);
          opts.onMessage(frame.message);
        }
        pollTimer = window.setTimeout(loop, 40);
      } catch {
        opts.onStatus("offline");
        pollTimer = window.setTimeout(loop, POLL_FAIL_RETRY_MS);
      }
    };
    pollTimer = window.setTimeout(loop, 0);
  };

  const probeWebSocket = () => {
    const base = opts.wsUrl ?? wsUrlFromLocation();
    const separator = base.includes("?") ? "&" : "?";
    const url = `${base}${separator}${qs({ token: opts.token, project: opts.projectId })}`;
    try {
      ws = new WebSocket(url);
    } catch {
      startPolling();
      return;
    }
    const timer = window.setTimeout(() => {
      if (ws && ws.readyState !== WebSocket.OPEN) {
        ws?.close();
        ws = null;
        startPolling();
      }
    }, WS_PROBE_TIMEOUT_MS);

    ws.onopen = () => {
      window.clearTimeout(timer);
      usingWs = true;
      opts.onStatus("ws");
    };
    ws.onmessage = (e) => {
      if (!usingWs) return;
      try {
        opts.onMessage(JSON.parse(e.data as string) as ServerMessage);
      } catch {
        /* ignore malformed */
      }
    };
    ws.onerror = () => {
      window.clearTimeout(timer);
      if (ws && ws.readyState !== WebSocket.OPEN) {
        ws.close();
        ws = null;
        startPolling();
      }
    };
    ws.onclose = () => {
      window.clearTimeout(timer);
      if (!closed) {
        usingWs = false;
        startPolling();
      }
    };
  };

  const send = (type: string, data?: unknown) => {
    if (ws && usingWs && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, data }));
      return;
    }
    void fetch("/api/transport", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, data, token: opts.token, project: opts.projectId }),
    }).catch(() => opts.onStatus("offline"));
  };

  probeWebSocket();

  return {
    kind: "poll",
    send,
    close: () => {
      closed = true;
      if (pollTimer !== null) window.clearTimeout(pollTimer);
      ws?.close();
    },
  };
}

function wsUrlFromLocation(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}
