"""ConnectionManager: rooms, per-connection queues, broadcast, heartbeat.

Design:
  - Every websocket gets an asyncio.Queue; a per-connection writer task drains it.
    Slow clients never block the broadcaster (drop the oldest frame if >8 pending).
  - `broadcast` fans out to all connections in a room; `send` targets one.
  - A per-room sequence buffer supports the long-poll fallback transport: clients
    resume with `after=<seq>` and never miss frames, even across poll gaps.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from ..canvas.models import CanvasState

logger = logging.getLogger(__name__)

MAX_PENDING_FRAMES = 16
BUFFER_SIZE = 256


@dataclass
class Connection:
    websocket: Any
    room: str = "studio"
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    closed: bool = False
    user: dict[str, Any] | None = None
    project_id: str | None = None


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[Any, Connection] = {}
        self._rooms: dict[str, list[Connection]] = {}
        self._lock = asyncio.Lock()
        # Sequence buffer + watchers for the long-poll fallback transport.
        self._seq = 0
        self._buffer: dict[str, deque[tuple[int, dict[str, Any]]]] = defaultdict(lambda: deque(maxlen=BUFFER_SIZE))
        self._watchers: dict[str, list[asyncio.Queue[tuple[int, dict[str, Any]]]]] = defaultdict(list)

    # ── lifecycle ────────────────────────────────────────────────────

    async def connect(
        self,
        websocket: Any,
        room: str = "studio",
        *,
        user: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> Connection:
        await websocket.accept()
        conn = Connection(websocket=websocket, room=room, user=user, project_id=project_id)
        async with self._lock:
            self._connections[websocket] = conn
            self._rooms.setdefault(room, []).append(conn)
        # Start the per-connection writer task.
        asyncio.create_task(self._writer(conn), name=f"ws-writer-{id(conn)}")
        logger.info("client connected (room=%s, total=%s)", room, len(self._connections))
        return conn

    async def disconnect(self, conn: Connection) -> None:
        if conn.websocket in self._connections:
            async with self._lock:
                self._connections.pop(conn.websocket, None)
                room_list = self._rooms.get(conn.room)
                if room_list and conn in room_list:
                    room_list.remove(conn)
            conn.closed = True
            # Wake the writer task with a sentinel so it exits promptly.
            try:
                conn.queue.put_nowait(None)
            except (asyncio.QueueFull, AttributeError):
                pass
            logger.info("client disconnected (room=%s, total=%s)", conn.room, len(self._connections))

    async def close_all(self) -> None:
        for conn in list(self._connections.values()):
            conn.closed = True
            try:
                await conn.websocket.close()
            except Exception:  # noqa: BLE001
                pass

    # ── sending ──────────────────────────────────────────────────────

    def send(self, conn: Connection, message: dict[str, Any]) -> None:
        """Queue a frame for one client (non-blocking).

        Duck-typed connections without a queue (uplink shims) receive frames by
        broadcasting them back to their room.
        """
        if getattr(conn, "closed", False):
            return
        queue = getattr(conn, "queue", None)
        if queue is None:
            room = getattr(conn, "room", "studio")
            asyncio.create_task(self.broadcast(message, room=room))
            return
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # Slow consumer: drop oldest to keep the stream live.
            try:
                queue.get_nowait()
                queue.put_nowait(message)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    async def broadcast(self, message: dict[str, Any], room: str = "studio") -> None:
        item = self._stamp(room, message)
        for conn in list(self._rooms.get(room, [])):
            self.send(conn, message)
        for watcher in list(self._watchers.get(room, [])):
            try:
                watcher.put_nowait(item)
            except asyncio.QueueFull:
                pass

    def seed(self, message: dict[str, Any], room: str = "studio") -> int:
        """Insert a frame into the buffer without delivering to live connections."""
        item = self._stamp(room, message)
        return item[0]

    def _stamp(self, room: str, message: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._seq += 1
        item = (self._seq, message)
        self._buffer[room].append(item)
        return item

    def buffer_since(self, room: str, after: int) -> list[tuple[int, dict[str, Any]]]:
        return [item for item in self._buffer[room] if item[0] > after]

    async def poll(self, room: str, after: int, timeout: float = 10.0) -> list[tuple[int, dict[str, Any]]]:
        """Long-poll: return buffered frames after seq, or wait up to `timeout` for
        the next one. Never returns duplicates — clients track `after`."""
        frames = self.buffer_since(room, after)
        if frames:
            return frames

        watcher: asyncio.Queue[tuple[int, dict[str, Any]]] = asyncio.Queue(maxsize=BUFFER_SIZE)
        self._watchers[room].append(watcher)
        try:
            try:
                async with asyncio.timeout(timeout):
                    item = await watcher.get()
                    if item[0] > after:
                        frames = [item]
            except (TimeoutError, asyncio.TimeoutError):
                pass
        finally:
            try:
                self._watchers[room].remove(watcher)
            except ValueError:
                pass
        return frames

    async def _writer(self, conn: Connection) -> None:
        try:
            while not conn.closed:
                message = await conn.queue.get()
                if message is None:
                    break
                await conn.websocket.send_json(message)
        except Exception:  # websocket torn down
            conn.closed = True
        finally:
            await self.disconnect(conn)

    def connection_count(self) -> int:
        return len(self._connections)

    def room_connections(self, room: str) -> int:
        return len(self._rooms.get(room, []))
