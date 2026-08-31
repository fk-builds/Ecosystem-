"""Sandbox: instant activation. Dev/demo only — no real money moves."""
from __future__ import annotations

from typing import Any

from .base import CheckoutResult


class SandboxProvider:
    name = "sandbox"

    def __init__(self, settings: Any):
        self.settings = settings

    async def create_checkout(
        self,
        *,
        user: dict[str, Any],
        plan_id: str,
        interval: str,
        store: Any,
        base_url: str,
    ) -> CheckoutResult:
        await store.set_plan(user["id"], plan_id, period_end=None, status="active")
        return CheckoutResult(mode="sandbox", plan=plan_id, interval=interval)
