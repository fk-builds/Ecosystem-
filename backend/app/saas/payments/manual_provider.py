"""Manual provider — the Pakistan-first payment path that works TODAY.

The customer pays into the owner's JazzCash / EasyPaisa / bank IBAN, then submits
the transaction reference. The owner (admin) approves it in /billing and the plan
activates. No gateway approval, no fees, works from day one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from ..plans import PLANS
from .base import CheckoutResult


class ManualProvider:
    name = "manual"

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
        plan = PLANS[plan_id]
        amount_pkr = int(plan.get("price_pkr_month", 0) if interval == "month" else plan.get("price_pkr_year", 0))
        order_id = f"ORD-{uuid4().hex[:10].upper()}"
        account = {
            "jazzcash": self.settings.jazzcash_account,
            "easypaisa": self.settings.easypaisa_account,
            "bank_name": self.settings.manual_bank_name,
            "iban": self.settings.manual_iban,
            "account_title": self.settings.manual_account_title,
        }
        instructions = (
            f"Send Rs.{amount_pkr:,} to any account below, then paste the transaction "
            f"reference (TRX id) from your JazzCash/EasyPaisa app or bank SMS."
        )
        await store.create_payment(
            user_id=user["id"],
            plan_id=plan_id,
            interval=interval,
            provider="manual",
            order_id=order_id,
            amount_pkr=amount_pkr,
            currency="PKR",
            status="awaiting_payment",
            account=account,
        )
        return CheckoutResult(
            mode="manual",
            plan=plan_id,
            interval=interval,
            order_id=order_id,
            amount_pkr=amount_pkr,
            instructions=instructions,
            account=account,
        )
