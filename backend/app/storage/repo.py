"""Canvas persistence.

MemoryRepository: in-process default (perfect for demos/tests).
PostgresRepository: Supabase-compatible PostgreSQL via asyncpg when DATABASE_URL is set.
Both expose the same interface; WsHub chooses at startup.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from ..canvas.models import CanvasState
from ..canvas.parser import parse_canvas

logger = logging.getLogger(__name__)


class CanvasRepository(Protocol):
    async def get(self, canvas_id: str) -> CanvasState | None: ...
    async def save(self, canvas: CanvasState) -> None: ...
    async def list_ids(self) -> list[str]: ...


# ── In-memory ──────────────────────────────────────────────────────────

class MemoryRepository:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    async def get(self, canvas_id: str) -> CanvasState | None:
        raw = self._store.get(canvas_id)
        if raw is None:
            return None
        parsed = parse_canvas(raw)
        return parsed.canvas if parsed.ok else None

    async def save(self, canvas: CanvasState) -> None:
        self._store[canvas.id] = canvas.to_dict()

    async def list_ids(self) -> list[str]:
        return list(self._store.keys())


# ── PostgreSQL / Supabase ──────────────────────────────────────────────

class PostgresRepository:
    """Persists canvases to a `canvases` table (see storage/schema.sql)."""

    def __init__(self, dsn: str, pool_size: int = 5) -> None:
        self._dsn = dsn
        self._pool_size = pool_size
        self._pool: Any = None

    async def connect(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=1,
            max_size=self._pool_size,
            command_timeout=30,
        )
        logger.info("PostgresRepository connected")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def get(self, canvas_id: str) -> CanvasState | None:
        if not self._pool:
            return None
        row = await self._pool.fetchrow(
            "SELECT state FROM canvases WHERE id = $1", canvas_id
        )
        if row is None:
            return None
        parsed = parse_canvas(json.loads(row["state"]))
        return parsed.canvas if parsed.ok else None

    async def save(self, canvas: CanvasState) -> None:
        if not self._pool:
            return
        payload = json.dumps(canvas.to_dict())
        await self._pool.execute(
            """
            INSERT INTO canvases (id, version, state, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (id) DO UPDATE
            SET version = EXCLUDED.version,
                state = EXCLUDED.state,
                updated_at = now()
            """,
            canvas.id,
            canvas.version,
            payload,
        )
        await self._pool.execute(
            """
            INSERT INTO canvas_versions (canvas_id, version, state, created_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT DO NOTHING
            """,
            canvas.id,
            canvas.version,
            payload,
        )

    async def list_ids(self) -> list[str]:
        if not self._pool:
            return []
        rows = await self._pool.fetch("SELECT id FROM canvases ORDER BY updated_at DESC")
        return [r["id"] for r in rows]


def build_repository(dsn: str | None = None, pool_size: int = 5) -> CanvasRepository:
    if dsn:
        return PostgresRepository(dsn, pool_size=pool_size)
    logger.info("DATABASE_URL not set — using in-memory canvas repository")
    return MemoryRepository()
