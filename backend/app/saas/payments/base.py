"""Payment provider abstraction for Pakistan-friendly billing.

Providers (selected via PAYMENT_PROVIDER env / auto):
  sandbox  — instant activation (dev / no keys)
  manual   — JazzCash wallet / EasyPaisa / IBAN transfer + transaction-id review.
             Works TODAY with zero gateway approval. Owner approves the payment.
  paddle   — Paddle Billing (merchant-of-record). International cards/USD.
             Payouts to Pakistan via Payoneer. Real Stripe alternative.
  jazzcash — JazzCash merchant gateway (PKR, wallet + cards). Requires a
             merchant account (approval takes days). Falls back to manual when
             credentials are absent.
  stripe   — kept for the future (overseas entity) — see docs.

Every provider returns a CheckoutResult; the webhook/approval path always ends in
the same `store.set_plan(...)` activation so billing state is provider-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class CheckoutResult:
    mode: str
    plan: str
    interval: str
    order_id: str | None = None
    amount_pkr: int | None = None
    amount_usd: int | None = None
    url: str | None = None
    redirect_params: dict[str, str] = field(default_factory=dict)
    instructions: str | None = None
    account: dict[str, str] = field(default_factory=dict)


class PaymentProvider(Protocol):
    name: str

    async def create_checkout(
        self,
        *,
        user: dict[str, Any],
        plan_id: str,
        interval: str,
        store: Any,
        base_url: str,
    ) -> CheckoutResult: ...
