"""User/project/usage/billing store.

- MemoryStore: in-process (tests, `SAAS_DATA_DIR=:memory:`)
- FileStore: JSON file-backed (demo mode — survives restarts)
- PostgreSQL/Supabase: see ARCHITECTURE.md M4 (schema in storage/schema.sql);
  this store interface is what the SQL implementation would satisfy.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from .auth import hash_password, verify_password

logger = logging.getLogger(__name__)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return date.today().isoformat()


class StoreError(Exception):
    pass


class MemoryStore:
    """Interface: users, sessions, projects, usage, billing."""

    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._projects: dict[str, dict[str, Any]] = {}
        self._usage: dict[str, dict[str, int]] = {}
        self._lock = asyncio.Lock()

    # ── users ──────────────────────────────────────────────────────

    async def create_user(self, email: str, password: str | None, plan: str = "free") -> dict[str, Any]:
        email = email.strip().lower()
        async with self._lock:
            if self.find_user_by_email(email):
                raise StoreError("email already registered")
            user = {
                "id": f"u-{uuid4().hex[:12]}",
                "email": email,
                "password_hash": hash_password(password) if password else None,
                "plan": plan,
                "plan_status": "active" if plan != "free" else "free",
                "period_end": None,
                "created_at": utcnow(),
            }
            self._users[user["id"]] = user
            return dict(user)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return dict(self._users[user_id]) if user_id in self._users else None

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        email = email.strip().lower()
        for user in self._users.values():
            if user["email"].lower() == email:
                return dict(user)
        return None

    async def check_login(self, email: str, password: str) -> dict[str, Any] | None:
        user = self.find_user_by_email(email)
        if not user or not user.get("password_hash"):
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        return user

    async def set_plan(self, user_id: str, plan: str, *, period_end: str | None = None, status: str = "active") -> None:
        async with self._lock:
            user = self._users.get(user_id)
            if not user:
                raise StoreError("user not found")
            user["plan"] = plan
            user["plan_status"] = status
            user["period_end"] = period_end
            if plan == "free":
                user["period_end"] = None

    # ── sessions ───────────────────────────────────────────────────

    async def create_session(self, user_id: str, token: str) -> None:
        async with self._lock:
            self._sessions[token] = {"user_id": user_id, "created_at": utcnow()}

    async def user_for_token(self, token: str) -> dict[str, Any] | None:
        async with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            user = self._users.get(session["user_id"])
            return dict(user) if user else None

    async def delete_session(self, token: str) -> None:
        async with self._lock:
            self._sessions.pop(token, None)

    # ── projects ───────────────────────────────────────────────────

    async def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            items = [p for p in self._projects.values() if p["user_id"] == user_id]
            items.sort(key=lambda p: p["updated_at"], reverse=True)
            return [dict(p) for p in items]

    async def create_project(self, user_id: str, name: str, canvas: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            project = {
                "id": f"p-{uuid4().hex[:12]}",
                "user_id": user_id,
                "name": name.strip() or "Untitled Canvas",
                "canvas": canvas,
                "created_at": utcnow(),
                "updated_at": utcnow(),
            }
            self._projects[project["id"]] = project
            return dict(project)

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        async with self._lock:
            project = self._projects.get(project_id)
            return dict(project) if project else None

    async def save_canvas(self, project_id: str, canvas: dict[str, Any]) -> None:
        async with self._lock:
            project = self._projects.get(project_id)
            if not project:
                raise StoreError("project not found")
            project["canvas"] = canvas
            project["version"] = canvas.get("version", 0)
            project["updated_at"] = utcnow()

    async def delete_project(self, project_id: str) -> bool:
        async with self._lock:
            return self._projects.pop(project_id, None) is not None

    async def project_count(self, user_id: str) -> int:
        async with self._lock:
            return sum(1 for p in self._projects.values() if p["user_id"] == user_id)

    # ── usage ──────────────────────────────────────────────────────

    async def usage_today(self, user_id: str) -> int:
        async with self._lock:
            return self._usage.get(user_id, {}).get(today(), 0)

    async def increment_usage(self, user_id: str) -> int:
        async with self._lock:
            day = today()
            bucket = self._usage.setdefault(user_id, {})
            bucket[day] = bucket.get(day, 0) + 1
            return bucket[day]

    # ── persistence (FileStore only) ───────────────────────────────

    async def close(self) -> None:  # noqa: D401 - noop for memory
        pass


class FileStore(MemoryStore):
    """MemoryStore + JSON file persistence (demo/drop-in dev)."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def load_async(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._users = data.get("users", {})
                self._sessions = data.get("sessions", {})
                self._projects = data.get("projects", {})
                self._usage = data.get("usage", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not load %s: %s", self._path, exc)

    async def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            tmp = f"{self._path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "users": self._users,
                        "sessions": self._sessions,
                        "projects": self._projects,
                        "usage": self._usage,
                    },
                    fh,
                    indent=1,
                )
            os.replace(tmp, self._path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not persist %s: %s", self._path, exc)

    # Override mutating ops to persist after writes. The base methods hold the
    # lock; to avoid re-entrancy we persist right after each awaited mutation.
    async def create_user(self, email: str, password: str | None, plan: str = "free") -> dict[str, Any]:
        user = await super().create_user(email, password, plan)
        await self._persist()
        return user

    async def set_plan(self, user_id: str, plan: str, *, period_end: str | None = None, status: str = "active") -> None:
        await super().set_plan(user_id, plan, period_end=period_end, status=status)
        await self._persist()

    async def create_session(self, user_id: str, token: str) -> None:
        await super().create_session(user_id, token)
        await self._persist()

    async def delete_session(self, token: str) -> None:
        await super().delete_session(token)
        await self._persist()

    async def create_project(self, user_id: str, name: str, canvas: dict[str, Any]) -> dict[str, Any]:
        project = await super().create_project(user_id, name, canvas)
        await self._persist()
        return project

    async def save_canvas(self, project_id: str, canvas: dict[str, Any]) -> None:
        await super().save_canvas(project_id, canvas)
        await self._persist()

    async def delete_project(self, project_id: str) -> bool:
        ok = await super().delete_project(project_id)
        await self._persist()
        return ok

    async def increment_usage(self, user_id: str) -> int:
        count = await super().increment_usage(user_id)
        await self._persist()
        return count
