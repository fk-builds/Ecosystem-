"""Payment adapter tests: provider selection, Paddle signature, JazzCash hash,
manual review approval flow (E2E through the API)."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.saas.payments import registry as payments
from app.saas.payments.jazzcash_provider import (
    jazzcash_default_fields,
    jazzcash_secure_hash,
    verify_jazzcash_response,
)
from app.saas.payments.paddle_provider import (
    plan_from_paddle_event,
    verify_paddle_signature,
)
from app.saas.payments.sandbox_provider import SandboxProvider
from main import app


def test_auto_pick_falls_back_to_manual(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "payment_provider", "auto")
    monkeypatch.setattr(settings, "paddle_api_key", "")
    monkeypatch.setattr(settings, "jazzcash_merchant_id", "")
    provider = payments.pick_provider(settings)
    assert provider.name == "manual"


def test_auto_pick_paddle_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "payment_provider", "auto")
    monkeypatch.setattr(settings, "paddle_api_key", "test")
    monkeypatch.setattr(settings, "paddle_webhook_secret", "test")
    provider = payments.pick_provider(settings)
    assert provider.name == "paddle"


def test_auto_pick_jazzcash_when_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "payment_provider", "auto")
    monkeypatch.setattr(settings, "paddle_api_key", "")
    monkeypatch.setattr(settings, "jazzcash_merchant_id", "MC123")
    monkeypatch.setattr(settings, "jazzcash_password", "pw")
    monkeypatch.setattr(settings, "jazzcash_integrity_salt", "salt")
    provider = payments.pick_provider(settings)
    assert provider.name == "jazzcash"


def test_paddle_signature_verify():
    secret = "whsec_test"
    payload = json.dumps({"type": "transaction.completed", "data": {"id": "txn_1"}}).encode()
    ts = str(int(time.time()))
    import hashlib
    import hmac as hmac_mod

    sig = hmac_mod.new(secret.encode(), f"{ts}:".encode() + payload, hashlib.sha256).hexdigest()
    assert verify_paddle_signature(payload, f"ts={ts};h1={sig}", secret) is True
    assert verify_paddle_signature(payload, f"ts={ts};h1={'0' * 64}", secret) is False
    # stale timestamp rejected
    old = str(int(time.time()) - 600)
    old_sig = hmac_mod.new(secret.encode(), f"{old}:".encode() + payload, hashlib.sha256).hexdigest()
    assert verify_paddle_signature(payload, f"ts={old};h1={old_sig}", secret) is False


def test_paddle_event_plan_extraction():
    event = {
        "type": "transaction.completed",
        "data": {"status": "completed", "custom_data": {"user_id": "u-1", "plan": "pro", "interval": "month"}},
    }
    assert plan_from_paddle_event(event) == ("u-1", "pro", "month")
    event["data"]["status"] = "pending"
    assert plan_from_paddle_event(event) == (None, None, None)
    assert plan_from_paddle_event({"type": "subscription.canceled", "data": {"custom_data": {"user_id": "u-1", "plan": "pro"}}}) == ("u-1", "free", "month")


def test_jazzcash_hash_deterministic_and_response_verification():
    fields = jazzcash_default_fields(149900, "MC123", "pw", "saltxyz", "https://x/api/payments/jazzcash/callback", "JZ-TEST-1")
    assert "pp_SecureHash" in fields and len(fields["pp_SecureHash"]) == 64
    # Stable for same input
    again = jazzcash_default_fields(149900, "MC123", "pw", "saltxyz", "https://x/api/payments/jazzcash/callback", "JZ-TEST-1")
    assert fields["pp_SecureHash"] == again["pp_SecureHash"]
    # Response verification round-trip
    response = dict(fields)
    response["pp_ResponseCode"] = "000"
    response["pp_SecureHash"] = jazzcash_secure_hash("saltxyz", response)
    assert verify_jazzcash_response(response, "saltxyz") is True
    response["pp_ResponseCode"] = "999"
    assert verify_jazzcash_response(response, "saltxyz") is True  # hash valid, code tells status
    # wrong salt -> invalid
    response["pp_ResponseCode"] = "000"
    assert verify_jazzcash_response(response, "wrong-salt") is False


# ── E2E: manual payment review flow ────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def buyer(client):
    r = client.post("/api/auth/signup", json={"email": "buyer@example.com", "password": "secret123"})
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def owner(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200
    return r.json()


def test_plans_include_pkr(client):
    plans = {p["id"]: p for p in client.get("/api/plans").json()["plans"]}
    assert plans["starter"]["price_pkr_month"] == 1499
    assert plans["pro"]["price_usd"] == 15


def test_manual_checkout_creates_payment(client, buyer):
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "starter", "provider": "manual"},
        headers={"Authorization": f"Bearer {buyer['token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "manual"
    assert body["order_id"]
    assert body["amount_pkr"] == 1499
    assert body["account"]["account_title"] == "" or "account_title" in body["account"]


def test_confirm_then_approve_activates_plan(client, buyer, owner):
    # create + confirm as buyer
    r = client.post(
        "/api/billing/checkout",
        json={"plan": "pro", "provider": "manual"},
        headers={"Authorization": f"Bearer {buyer['token']}"},
    )
    order_id = r.json()["order_id"]
    r = client.post(
        f"/api/billing/payments/{order_id}/confirm",
        json={"txn_ref": "TRX-7728419021"},
        headers={"Authorization": f"Bearer {buyer['token']}"},
    )
    assert r.status_code == 200
    assert r.json()["payment"]["status"] == "pending_review"

    # buyer cannot approve (not admin)
    r = client.post(
        f"/api/billing/payments/{order_id}/approve",
        json={},
        headers={"Authorization": f"Bearer {buyer['token']}"},
    )
    assert r.status_code == 403

    # owner (demo = admin when ADMIN_EMAILS empty) approves
    r = client.post(
        f"/api/billing/payments/{order_id}/approve",
        json={"note": "verified in JazzCash app"},
        headers={"Authorization": f"Bearer {owner['token']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["payment"]["status"] == "approved"

    # buyer's plan is now active
    s = client.get("/api/billing/status", headers={"Authorization": f"Bearer {buyer['token']}"}).json()
    assert s["plan"] == "pro"
    assert s["is_admin"] is False


def test_owner_sees_all_payments(client, owner):
    r = client.get("/api/billing/payments", headers={"Authorization": f"Bearer {owner['token']}"})
    assert r.status_code == 200
    assert len(r.json()["payments"]) >= 2
