"""Canonical real-time protocol shared by WebSocket and SSE transports.

Envelope: {"type": str, "data": Any, "request_id": str|None, "room": str}
Backend mirrors: frontend/lib/protocol.ts
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

DEFAULT_ROOM = "studio"

# Client -> Server
CLIENT_CANVAS_UPDATE = "CANVAS_UPDATE"
CLIENT_CANVAS_PATCH = "CANVAS_PATCH"
CLIENT_AGENT_PROMPT = "AGENT_PROMPT"
CLIENT_AGENT_CANCEL = "AGENT_CANCEL"
CLIENT_ROOM_JOIN = "ROOM_JOIN"
CLIENT_PING = "PING"

# Server -> Client
SERVER_INIT_CANVAS = "INIT_CANVAS"
SERVER_CANVAS_SYNC = "CANVAS_SYNC"
SERVER_ROOM_JOINED = "ROOM_JOINED"
SERVER_PONG = "PONG"

SERVER_AGENT_STREAM_START = "AGENT_STREAM_START"
SERVER_AGENT_STREAM_CHUNK = "AGENT_STREAM_CHUNK"
SERVER_AGENT_STREAM_END = "AGENT_STREAM_END"
SERVER_AGENT_DELTA = "AGENT_DELTA"
SERVER_AGENT_TOOL_CALL = "AGENT_TOOL_CALL"
SERVER_AGENT_TOOL_RESULT = "AGENT_TOOL_RESULT"
SERVER_AGENT_DONE = "AGENT_DONE"
SERVER_AGENT_ERROR = "AGENT_ERROR"

CLIENT_TYPES = {
    CLIENT_CANVAS_UPDATE,
    CLIENT_CANVAS_PATCH,
    CLIENT_AGENT_PROMPT,
    CLIENT_AGENT_CANCEL,
    CLIENT_ROOM_JOIN,
    CLIENT_PING,
}


def make_message(
    type_: str,
    data: Any = None,
    *,
    room: str = DEFAULT_ROOM,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": type_,
        "data": data,
        "room": room,
        "request_id": request_id or (uuid4().hex[:12] if request_id is None else None),
    }


def parse_envelope(raw: str | bytes | dict[str, Any]) -> dict[str, Any] | None:
    """Parse and validate an incoming envelope. Returns None when malformed."""
    try:
        if isinstance(raw, (str, bytes)):
            import json

            payload = json.loads(raw)
        else:
            payload = raw
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            return None
        return payload
    except (ValueError, TypeError):
        return None
