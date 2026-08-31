"""Provider selection + factory."""
from __future__ import annotations

from typing import Any

from .base import CheckoutResult, PaymentProvider

AVAILABLE = ("auto", "sandbox", "manual", "paddle", "jazzcash", "stripe")


def pick_provider(settings: Any, requested: str = "") -> PaymentProvider:
    """Auto-selection priority: paddle (intl) > jazzcash (local) > manual > sandbox."""
    wanted = (requested or settings.payment_provider or "auto").lower()
    if wanted == "stripe" and settings.stripe_secret_key:
        from .stripe_provider import StripeProvider

        return StripeProvider(settings)
    if wanted in {"", "auto"}:
        if settings.paddle_api_key and settings.paddle_webhook_secret:
            from .paddle_provider import PaddleProvider

            return PaddleProvider(settings)
        if settings.jazzcash_all_configured:
            from .jazzcash_provider import JazzCashProvider

            return JazzCashProvider(settings)
        from .manual_provider import ManualProvider

        return ManualProvider(settings)
    if wanted == "paddle":
        if not settings.paddle_api_key:
            raise ValueError("paddle provider selected but PADDLE_API_KEY is not set")
        from .paddle_provider import PaddleProvider

        return PaddleProvider(settings)
    if wanted == "jazzcash":
        if not settings.jazzcash_all_configured:
            raise ValueError("jazzcash provider selected but JAZZCASH_* env vars are missing")
        from .jazzcash_provider import JazzCashProvider

        return JazzCashProvider(settings)
    if wanted == "manual":
        from .manual_provider import ManualProvider

        return ManualProvider(settings)
    if wanted == "sandbox":
        from .sandbox_provider import SandboxProvider

        return SandboxProvider(settings)
    raise ValueError(f"unknown payment provider: {wanted!r}")


def provider_status(settings: Any) -> dict[str, Any]:
    """What's configured — surfaced by /api/billing/status and the UI."""
    try:
        active = pick_provider(settings).name
    except ValueError:
        active = "sandbox"
    return {
        "mode": settings.payment_provider or "auto",
        "paddle": bool(settings.paddle_api_key and settings.paddle_webhook_secret),
        "jazzcash": bool(settings.jazzcash_all_configured),
        "manual": bool(settings.manual_account_title),
        "stripe": bool(settings.stripe_secret_key),
        "active": active,
    }
