"""Paddle Billing provider (merchant-of-record) — real Stripe alternative for
international customers. Payouts reach Pakistan via Payoneer/wire.

Setup (see docs/PAKISTAN-PAYMENTS.md):
  1. Create a Paddle seller account, verify, set payout = Payoneer.
  2. In Paddle dashboard create 4 prices (Starter/Pro × monthly/yearly, USD) and
     paste the price ids into PADDLE_PRICE_* env vars.
  3. Add webhook endpoint https://<your-domain>/api/payments/paddle/webhook with
     events: transaction.completed, subscription.canceled; paste the webhook
     secret into PADDLE_WEBHOOK_SECRET.
"""
from __future__ import annotations

import hmac
import json
import time
from typing import Any

import httpx

from .base import CheckoutResult

PADDLE_API = "https://api.paddle.com"


class PaddleProvider:
    name = "paddle"

    def __init__(self, settings: Any):
        self.settings = settings

    def _price_id(self, plan_id: str, interval: str) -> str:
        key = f"paddle_price_{plan_id}_{interval}"
        price_id = getattr(self.settings, key, "") or ""
        if not price_id:
            raise ValueError(
                f"missing price id: configure {key.upper()} in Paddle dashboard "
                f"(plan={plan_id}, interval={interval})"
            )
        return price_id

    async def create_checkout(
        self,
        *,
        user: dict[str, Any],
        plan_id: str,
        interval: str,
        store: Any,
        base_url: str,
    ) -> CheckoutResult:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{PADDLE_API}/checkout/sessions",
                headers={"Authorization": f"Bearer {self.settings.paddle_api_key}"},
                json={
                    "items": [{"price_id": self._price_id(plan_id, interval)}],
                    "custom_data": {"user_id": user["id"], "plan": plan_id, "interval": interval},
                    "customer_email": user["email"],
                    "success_url": f"{base_url}/billing?status=success",
                    "cancel_url": f"{base_url}/billing?status=cancelled",
                },
            )
            if response.status_code >= 400:
                raise RuntimeError(f"paddle checkout failed ({response.status_code}): {response.text[:400]}")
            data = response.json().get("data", {})
        checkout_id = data.get("id", "")
        url = data.get("url") or f"https://checkout.paddle.com/{checkout_id}"
        return CheckoutResult(mode="paddle", plan=plan_id, interval=interval, order_id=checkout_id, url=url)


def verify_paddle_signature(raw: bytes, header: str, secret: str) -> bool:
    """Verify `Paddle-Signature: ts=<ts>;h1=<hex>` (HMAC-SHA256, 5-min skew)."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(";") if "=" in item)
        timestamp, signature = parts.get("ts", ""), parts.get("h1", "")
        if not timestamp or not signature:
            return False
        if abs(time.time() - float(timestamp)) > 300:
            return False
        expected = hmac.new(secret.encode(), f"{timestamp}:".encode() + raw, hashlib_sha256()).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:  # noqa: BLE001
        return False


def hashlib_sha256() -> Any:
    import hashlib

    return hashlib.sha256


def plan_from_paddle_event(event: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (user_id, plan, interval) from a Paddle webhook event."""
    event_type = event.get("type", "")
    data = event.get("data", {}) or {}
    custom = data.get("custom_data") or {}
    user_id = custom.get("user_id")
    plan = custom.get("plan")
    interval = custom.get("interval", "month")

    if event_type == "transaction.completed":
        status = data.get("status")
        if status != "completed":
            return None, None, None
        return user_id, plan, interval
    if event_type == "subscription.canceled":
        return user_id, "free", interval
    if event_type in {"subscription.updated", "subscription.past_due"}:
        status = data.get("status")
        return user_id, ("free" if status in {"canceled", "past_due", "paused"} else plan), interval
    return None, None, None


def event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("data", {}) or {}
