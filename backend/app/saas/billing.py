"""Billing: Stripe Checkout (production) + instant demo mode (no keys needed).

Demo mode: POST /api/billing/checkout activates the plan immediately (period_end
= now + 30 days) and returns {"demo": true}. With STRIPE_SECRET_KEY set, a real
Checkout Session is created and returned; the webhook endpoint keeps the plan in
sync. All plan math stays server-side (never trust the client).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .plans import PLANS

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"


def _period_end(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def create_checkout(
    *,
    user_id: str,
    user_email: str,
    plan_id: str,
    secret_key: str,
    base_url: str,
    interval: str = "month",
) -> dict[str, Any]:
    """Create a real Stripe subscription Checkout Session.

    `client_reference_id` = our user id so the webhook can reliably map the
    subscription back to the account (no email guessing).
    """
    plan = PLANS[plan_id]
    unit = int(plan["price_usd"] * 100)
    if interval == "year":
        unit = int((plan.get("price_yearly_usd") or plan["price_usd"] * 12 * 0.8) * 100)
    if unit <= 0:
        raise ValueError("cannot checkout a free plan")

    success = f"{base_url}/billing?status=success"
    cancel = f"{base_url}/billing?status=cancelled"
    form = {
        "mode": "subscription",
        "success_url": success,
        "cancel_url": cancel,
        "customer_email": user_email,
        "client_reference_id": user_id,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(unit),
        "line_items[0][price_data][product_data][name]": f"FK AI Builder — {plan['name']}",
        "line_items[0][price_data][recurring][interval]": interval,
        "subscription_data[metadata][plan]": plan_id,
        "subscription_data[metadata][interval]": interval,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{STRIPE_API}/checkout/sessions",
            data=form,
            headers={"Authorization": f"Bearer {secret_key}"},
        )
    if response.status_code >= 400:
        logger.error("stripe checkout failed: %s", response.text[:500])
        raise RuntimeError(f"stripe checkout failed ({response.status_code})")
    data = response.json()
    return {"url": data.get("url"), "demo": False, "plan": plan_id}


def verify_stripe_webhook(payload: bytes, signature_header: str, secret: str) -> dict[str, Any] | None:
    """Verify and parse a Stripe webhook (HMAC per Stripe docs, stdlib-only)."""
    try:
        parts = dict(
            item.split("=", 1) for item in signature_header.split(",") if "=" in item
        )
        timestamp = parts.get("t", "")
        signatures = parts.get("v1", "").split(",") if "v1" in parts else []
        signed = f"{timestamp}.{payload.decode()}"
        expected = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            return None
        # Reject old timestamps (5 min skew) to prevent replay.
        if abs(time.time() - float(timestamp)) > 300:
            return None
        return json.loads(payload)
    except Exception:  # noqa: BLE001
        return None


def plan_from_webhook(event: dict[str, Any]) -> str | None:
    """Map a Stripe event to 'free' | 'starter' | 'pro'."""
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        return (obj.get("metadata") or {}).get("plan")
    if event_type.startswith("customer.subscription."):
        metadata = (obj.get("metadata") or {})
        plan = metadata.get("plan")
        if obj.get("status") in {"canceled", "unpaid", "incomplete_expired"}:
            return "free"
        return plan
    return None


async def demo_activate(user_id: str, plan_id: str, store: Any, days: int = 30) -> dict[str, Any]:
    """Demo-mode activation (also used by Stripe webhook persistence)."""
    if plan_id not in PLANS or plan_id == "free":
        await store.set_plan(user_id, "free", status="active")
    else:
        await store.set_plan(user_id, plan_id, period_end=_period_end(days), status="active")
    user = await store.get_user(user_id)
    return {"demo": True, "plan": user["plan"] if user else plan_id, "period_end": user.get("period_end") if user else None}
