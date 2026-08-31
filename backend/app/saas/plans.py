"""SaaS plans & limits.

Pricing strategy: deliberately below the typical market rate for AI builders
(most comparable tools run $20–$30/mo). Starter $7/mo, Pro $15/mo. Free tier is
functional so people can try the real product before subscribing.
"""
from __future__ import annotations

from typing import Any

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "tagline": "Try the real product",
        "price_usd": 0,
        "price_yearly_usd": 0,
        "projects": 1,
        "agent_messages_per_day": 25,
        "features": [
            "1 project & canvas",
            "25 agent messages / day",
            "Real-time canvas sync",
            "HTML + React code preview",
            "Standard components",
        ],
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "tagline": "For makers & freelancers",
        "price_usd": 7,
        "price_yearly_usd": 67,
        "projects": 5,
        "agent_messages_per_day": 500,
        "features": [
            "5 projects & canvases",
            "500 agent messages / day",
            "Everything in Free",
            "Code export (HTML / React)",
            "Vector memory & RAG",
            "Python sandbox + HTTP tools",
        ],
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "tagline": "For teams & power users",
        "price_usd": 15,
        "price_yearly_usd": 144,
        "projects": None,  # unlimited
        "agent_messages_per_day": 2000,
        "features": [
            "Unlimited projects",
            "2,000 agent messages / day",
            "Everything in Starter",
            "Priority agent queue",
            "All components & tools",
            "Early access to new features",
        ],
    },
}

DEFAULT_PLAN = "free"


def plan_for(plan_id: str | None) -> dict[str, Any]:
    return PLANS.get(plan_id or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])


def project_limit(plan_id: str) -> int | None:
    """None = unlimited."""
    return PLANS.get(plan_id, PLANS[DEFAULT_PLAN]).get("projects")


def agent_message_limit(plan_id: str) -> int:
    return int(PLANS.get(plan_id, PLANS[DEFAULT_PLAN])["agent_messages_per_day"])
