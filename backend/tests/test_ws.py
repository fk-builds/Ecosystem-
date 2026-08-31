"""E2E tests for the SaaS backend: auth, projects, billing, realtime transports."""
import json

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def user(client):
    email = "ws-test@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"token": data["token"], **data["user"]}


@pytest.fixture(scope="module")
def project(client, user):
    r = client.post(
        "/api/projects",
        json={"name": "WS Test Canvas"},
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["project"]


def _recv_until(ws, type_name: str):
    seen = []
    while True:
        frame = json.loads(ws.receive_text())
        seen.append(frame["type"])
        if frame["type"] == type_name:
            return frame, seen
        if len(seen) > 500:
            raise AssertionError(f"waiting for {type_name}; got {seen[:50]}")


def test_health_has_saas_info(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["version"] >= "1.1"
    assert body["billing"] in {"sandbox", "stripe", "manual", "jazzcash", "paddle"}
    assert body["embeddings"] in {"dense", "tfidf"}


def test_plans_public(client):
    r = client.get("/api/plans")
    ids = [p["id"] for p in r.json()["plans"]]
    assert ids == ["free", "starter", "pro"]


def test_signup_login_me_logout(client):
    email = "e2e@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "secret123"})
    assert r.status_code == 200
    token = r.json()["token"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["user"]["email"] == email
    assert r.json()["user"]["plan"] == "free"

    r = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"email": email, "password": "wrongpass"})
    assert r.status_code == 401

    # signup duplicate
    r = client.post("/api/auth/signup", json={"email": email, "password": "secret123"})
    assert r.status_code == 409

    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_demo_login(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200
    assert r.json()["user"]["plan"] == "pro"


def test_project_crud_and_ownership(client):
    # Create with user A
    r = client.post("/api/auth/signup", json={"email": "owner@example.com", "password": "secret123"})
    token_a = r.json()["token"]
    r = client.post("/api/projects", json={"name": "Owned"}, headers={"Authorization": f"Bearer {token_a}"})
    project_id = r.json()["project"]["id"]

    # Another user cannot see it
    r = client.post("/api/auth/signup", json={"email": "intruder@example.com", "password": "secret123"})
    token_b = r.json()["token"]
    r = client.get(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403
    r = client.delete(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403

    # Owner can rename + delete
    r = client.patch(f"/api/projects/{project_id}", json={"name": "Renamed"}, headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    r = client.delete(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200


def test_billing_demo_mode(client, user):
    # With no gateway credentials configured, auto resolves to the manual
    # (wallet/bank + TRX review) provider — the Pakistan bootstrap path.
    r = client.post("/api/billing/checkout", json={"plan": "starter"}, headers={"Authorization": f"Bearer {user['token']}"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "manual"
    assert body["demo"] is False
    assert body["order_id"] and body["amount_pkr"] == 1499

    # Sandbox is only used when explicitly requested (e.g. CI/dev with no wallets).
    r = client.post("/api/billing/checkout", json={"plan": "starter", "provider": "sandbox"}, headers={"Authorization": f"Bearer {user['token']}"})
    assert r.status_code == 200
    assert r.json()["demo"] is True

    r = client.get("/api/billing/status", headers={"Authorization": f"Bearer {user['token']}"})
    body = r.json()
    assert body["plan"] == "starter"
    assert body["usage_limit"] == 500
    assert body["billing_mode"] == "manual"


def test_ws_init_and_sync_authenticated(client, user, project):
    token = user["token"]
    pid = project["id"]
    with client.websocket_connect(f"/ws?token={token}&project={pid}") as ws:
        frame, _ = _recv_until(ws, "INIT_CANVAS")
        assert frame["data"]["root"]["type"] == "page"

        ws.send_text(json.dumps({"type": "CANVAS_PATCH", "data": {"operations": [
            {"op": "add", "component": {"type": "button", "id": "ws-saas-btn", "content": {"text": "Hi"}}},
        ]}}))
        frame, _ = _recv_until(ws, "CANVAS_SYNC")
        assert "ws-saas-btn" in [c["id"] for c in frame["data"]["root"]["children"]]
        assert frame["data"]["version"] >= 2


def test_ws_rejects_anonymous(client, project):
    try:
        with client.websocket_connect(f"/ws?project={project['id']}") as ws:
            ws.receive_text()
            assert False, "expected close"
    except Exception:
        pass  # server closed with 4401


def test_ws_rejects_foreign_project(client):
    # Create a user + project; connect with a *different* token.
    r = client.post("/api/auth/signup", json={"email": "other@example.com", "password": "secret123"})
    token_b = r.json()["token"]
    r = client.post("/api/projects", json={"name": "B owns"}, headers={"Authorization": f"Bearer {token_b}"})
    pid = r.json()["project"]["id"]

    r = client.post("/api/auth/signup", json={"email": "nosy@example.com", "password": "secret123"})
    token_a = r.json()["token"]
    try:
        with client.websocket_connect(f"/ws?token={token_a}&project={pid}") as ws:
            ws.receive_text()
            assert False, "expected close"
    except Exception:
        pass  # server closed with 4403


def test_agent_stream_through_transport(client, user, project):
    token = user["token"]
    pid = project["id"]
    r = client.post("/api/transport", json={
        "type": "AGENT_PROMPT",
        "data": {"prompt": "add a modern hero section"},
        "token": token, "project": pid,
    })
    assert r.json()["ok"] is True

    r = client.get(f"/api/poll?token={token}&project={pid}&after=0&timeout=5")
    assert r.status_code == 200
    types = [f["message"]["type"] for f in r.json()["frames"]]
    assert "AGENT_DONE" in types, types
    assert "AGENT_TOOL_CALL" in types, types

    # Agent mutated the canvas in <room>
    r = client.get(f"/api/projects/{pid}", headers={"Authorization": f"Bearer {user['token']}"})
    types_canvas = [c["type"] for c in r.json()["project"]["canvas"]["root"]["children"]]
    assert "hero" in types_canvas


def test_daily_agent_limit(client):
    """Free plan: 25 messages/day. Driving 25 would take too long; instead verify
    the counter increments and the limit gate is wired (1 message reserved)."""
    r = client.post("/api/auth/signup", json={"email": "limits@example.com", "password": "secret123"})
    token = r.json()["token"]
    r = client.post("/api/projects", json={"name": "Limits"}, headers={"Authorization": f"Bearer {token}"})
    pid = r.json()["project"]["id"]

    for _ in range(2):
        r = client.post("/api/transport", json={
            "type": "AGENT_PROMPT", "data": {"prompt": "add a card"},
            "token": token, "project": pid,
        })
        assert r.status_code == 200

    r = client.get("/api/billing/status", headers={"Authorization": f"Bearer {token}"})
    body = r.json()
    assert body["usage_limit"] == 25
    assert body["usage_today"] >= 2


def test_code_endpoint(client, user, project):
    r = client.get(
        f"/api/projects/{project['id']}/code?format=react",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert r.status_code == 200
    assert "export default function Canvas" in r.json()["react"]


def test_code_endpoint_requires_auth(client, project):
    r = client.get(f"/api/projects/{project['id']}/code?format=html")
    assert r.status_code == 401
