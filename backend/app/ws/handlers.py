"""WS/SSE/long-poll shared message dispatch: canvas ops, agent prompts, heartbeat.

All transports call these handlers, so behavior is identical. `WsHub` manages a
per-project `RoomState` (canonical canvas + active agent runs), while
`ConnectionManager` fans frames out per room with a sequence buffer.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .. import protocol
from ..agent.engine import AgentContext, AgentEngine, AgentRun
from ..canvas.models import CanvasState
from ..canvas.operations import apply_operations
from ..canvas.parser import parse_canvas
from ..saas import limits
from ..saas.limits import LimitError
from .manager import Connection, ConnectionManager

logger = logging.getLogger(__name__)


@dataclass
class RoomState:
    project_id: str
    user_id: str
    canvas: CanvasState
    memory: Any
    active_runs: dict[str, asyncio.Event] = field(default_factory=dict)


class ProjectRepo:
    """Adapter so canvas tools can persist through the SaaS store."""

    def __init__(self, hub: "WsHub", project_id: str):
        self.hub = hub
        self.project_id = project_id

    async def save(self, canvas: CanvasState) -> None:
        await self.hub.store.save_canvas(self.project_id, canvas.to_dict())

    async def get(self, _: str) -> CanvasState | None:
        return None


class WsHub:
    """Real-time hub: rooms per project, shared agent engine, memory, store."""

    def __init__(
        self,
        manager: ConnectionManager,
        store: Any,
        memory: Any,
        settings: Any,
        engine_factory: Any,
        llm_client: Any = None,
    ) -> None:
        self.manager = manager
        self.store = store
        self.memory = memory
        self.settings = settings
        self.engine_factory = engine_factory
        self.llm_client = llm_client
        self.rooms: dict[str, RoomState] = {}

    # ── rooms ───────────────────────────────────────────────────────

    def get_room(self, project_id: str) -> RoomState | None:
        return self.rooms.get(project_id)

    async def ensure_room(self, project_id: str, user_id: str, canvas: CanvasState) -> RoomState:
        room = self.rooms.get(project_id)
        if room is None:
            room = RoomState(project_id=project_id, user_id=user_id, canvas=canvas, memory=self.memory)
            self.rooms[project_id] = room
            # Seed the long-poll buffer so the first poll receives canonical state.
            self.manager.seed(protocol.make_message(protocol.SERVER_INIT_CANVAS, canvas.to_dict()), room=project_id)
        return room

    def drop_room(self, project_id: str) -> None:
        self.rooms.pop(project_id, None)

    # ── outbound ────────────────────────────────────────────────────

    async def broadcast(self, type_: str, data: Any, room: str, request_id: str | None = None) -> None:
        await self.manager.broadcast(
            protocol.make_message(type_, data, room=room, request_id=request_id), room=room
        )

    async def send_canvas(self, conn: Connection, room_id: str) -> None:
        room = self.get_room(room_id)
        if room is None:
            self.manager.send(conn, protocol.make_message(protocol.SERVER_AGENT_ERROR, {"error": "room not found"}, room=room_id))
            return
        self.manager.send(conn, protocol.make_message(protocol.SERVER_INIT_CANVAS, room.canvas.to_dict(), room=room_id))

    # ── client dispatch ─────────────────────────────────────────────

    async def handle(self, conn: Connection, payload: dict[str, Any]) -> None:
        type_ = payload.get("type", "")
        data = payload.get("data")
        request_id = payload.get("request_id")
        room_id = payload.get("room") or conn.room

        if type_ == protocol.CLIENT_PING:
            self.manager.send(conn, protocol.make_message(protocol.SERVER_PONG, {"ts": data}, room=room_id, request_id=request_id))
            return
        if type_ == protocol.CLIENT_ROOM_JOIN:
            self.manager.send(conn, protocol.make_message(protocol.SERVER_ROOM_JOINED, {"room": room_id}, room=room_id, request_id=request_id))
            await self.send_canvas(conn, room_id)
            return
        if type_ == protocol.CLIENT_CANVAS_UPDATE:
            await self.replace_canvas(room_id, data, request_id)
            return
        if type_ == protocol.CLIENT_CANVAS_PATCH:
            await self.patch_canvas(room_id, data, request_id)
            return
        if type_ == protocol.CLIENT_AGENT_CANCEL:
            self._cancel_runs(room_id)
            return
        if type_ == protocol.CLIENT_AGENT_PROMPT:
            await self.run_agent(room_id, conn.user, data, request_id)
            return

        self.manager.send(
            conn,
            protocol.make_message(protocol.SERVER_AGENT_ERROR, {"error": f"unknown message type '{type_}'"}, room=room_id, request_id=request_id),
        )

    # ── canvas ops ──────────────────────────────────────────────────

    async def patch_canvas(self, room_id: str, data: Any, request_id: str | None = None) -> None:
        room = self.get_room(room_id)
        if room is None:
            return
        if not isinstance(data, dict) or "operations" not in data:
            await self.manager.broadcast(
                protocol.make_message(protocol.SERVER_AGENT_ERROR, {"error": "CANVAS_PATCH requires {operations: [...]}"}, room=room_id, request_id=request_id)
            )
            return
        result = apply_operations(room.canvas, data["operations"])
        if not result.ok:
            await self.manager.broadcast(
                protocol.make_message(protocol.SERVER_AGENT_ERROR, {"error": result.error or "invalid operations"}, room=room_id, request_id=request_id)
            )
            return
        room.canvas = result.canvas
        await self.store.save_canvas(room_id, room.canvas.to_dict())
        await self.broadcast("CANVAS_SYNC", room.canvas.to_dict(), room_id, request_id)

    async def replace_canvas(self, room_id: str, data: Any, request_id: str | None = None) -> None:
        room = self.get_room(room_id)
        if room is None:
            return
        parsed = parse_canvas(data, name=self.settings.canvas_default_name)
        if not parsed.ok or parsed.canvas is None:
            await self.manager.broadcast(
                protocol.make_message(protocol.SERVER_AGENT_ERROR, {"error": "; ".join(parsed.errors)}, room=room_id, request_id=request_id)
            )
            return
        parsed.canvas.version = max(parsed.canvas.version, room.canvas.version + 1)
        room.canvas = parsed.canvas
        await self.store.save_canvas(room_id, room.canvas.to_dict())
        await self.broadcast("CANVAS_SYNC", room.canvas.to_dict(), room_id, request_id)

    # ── agent ───────────────────────────────────────────────────────

    async def run_agent(self, room_id: str, user: dict[str, Any] | None, data: Any, request_id: str | None = None) -> None:
        room = self.get_room(room_id)
        if room is None:
            return
        prompt = (data if isinstance(data, str) else (data or {}).get("prompt", "")).strip()
        if not prompt:
            await self.broadcast("AGENT_ERROR", {"error": "empty prompt"}, room_id, request_id)
            return

        # Plan limits: reserve one daily agent message for this user.
        if user:
            try:
                await limits.assert_agent_allowed(user, self.store)
                await self.store.increment_usage(user["id"])
            except LimitError as exc:
                await self.broadcast("AGENT_ERROR", {"error": exc.message}, room_id, request_id)
                return

        request_id = request_id or f"req-{id(prompt)}"
        if request_id in room.active_runs:
            await self.broadcast("AGENT_ERROR", {"error": "another agent request is already running here"}, room_id, request_id)
            return

        cancel_event = asyncio.Event()
        room.active_runs[request_id] = cancel_event

        repo = ProjectRepo(self, room_id)

        async def broadcast(type_: str, data: Any) -> None:
            await self.broadcast(type_, data, room_id, request_id)

        context = AgentContext(
            canvas=room.canvas,
            canvas_id=room_id,
            repo=repo,
            memory=room.memory,
            settings=self.settings,
            broadcast=broadcast,
        )
        engine: AgentEngine = self.engine_factory(llm_client=self.llm_client)

        async def emit(type_: str, data: Any) -> None:
            await self.broadcast(type_, data, room_id, request_id)

        run = AgentRun(request_id=request_id, context=context, emit=emit, cancel_event=cancel_event)
        try:
            await engine.run(run, prompt)
            room.canvas = context.canvas  # tools mutated via context
            await self.store.save_canvas(room_id, room.canvas.to_dict())
        except Exception:  # noqa: BLE001
            logger.exception("agent turn crashed (room=%s)", room_id)
            await emit("AGENT_ERROR", {"error": "agent crashed unexpectedly"})
        finally:
            room.active_runs.pop(request_id, None)

    def _cancel_runs(self, room_id: str) -> None:
        room = self.get_room(room_id)
        if room:
            for event in room.active_runs.values():
                event.set()
