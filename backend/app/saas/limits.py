"""Plan limit enforcement: projects per user + daily agent messages."""
from __future__ import annotations

from typing import Any

from .plans import agent_message_limit, project_limit


class LimitError(Exception):
    def __init__(self, message: str, code: str = "limit_exceeded"):
        super().__init__(message)
        self.code = code
        self.message = message


async def assert_project_allowed(user: dict[str, Any], store: Any) -> None:
    limit = project_limit(user.get("plan", "free"))
    if limit is None:
        return
    count = await store.project_count(user["id"])
    if count >= limit:
        raise LimitError(
            f"Your {user.get('plan', 'free')} plan allows {limit} project(s). "
            "Upgrade to add more.",
            code="project_limit",
        )


async def assert_agent_allowed(user: dict[str, Any], store: Any) -> int:
    """Returns the usage count AFTER reserving one message."""
    limit = agent_message_limit(user.get("plan", "free"))
    used = await store.usage_today(user["id"])
    if used >= limit:
        raise LimitError(
            f"You've used all {limit} agent messages for today. "
            "They reset at midnight — or upgrade for more.",
            code="daily_agent_limit",
        )
    return used + 1
