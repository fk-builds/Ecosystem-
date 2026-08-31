"""Stripe provider — kept for the future (e.g. overseas entity via US/UK company,
or once Stripe opens in Pakistan). Not selectable unless STRIPE_SECRET_KEY is set."""
from __future__ import annotations

from typing import Any

from ..billing import create_checkout as stripe_create_checkout
from .base import CheckoutResult


class StripeProvider:
    name = "stripe"

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
        result = await stripe_create_checkout(
            user_id=user["id"],
            user_email=user["email"],
            plan_id=plan_id,
            secret_key=self.settings.stripe_secret_key,
            base_url=base_url,
            interval=interval,
        )
        return CheckoutResult(mode="stripe", plan=plan_id, interval=interval, url=result.get("url"))
