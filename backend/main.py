"""FK AI Builder — FastAPI production server (WebSocket + SSE + long-poll + SaaS).

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Auth: Bearer session token (or ?token= for WS/poll). Supabase JWT accepted when
SUPABASE_JWT_SECRET is set. Demo seed account: demo@fk.ai / demo1234 (Pro plan).
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import protocol
from app.agent.engine import AgentEngine
from app.agent.llm import LLMClient
from app.canvas.codegen import code_for_canvas
from app.canvas.models import CanvasState
from app.canvas.parser import parse_canvas
from app.config import get_settings
from app.saas import auth as saas_auth
from app.saas import billing, limits
from app.saas.store import FileStore
from app.saas.limits import LimitError
from app.saas.payments import registry as payments
from app.saas.payments.jazzcash_provider import (
    jazzcash_callback_result,
    encode_form,
)
from app.saas.payments.paddle_provider import (
    event_payload,
    plan_from_paddle_event,
    verify_paddle_signature,
)
from app.saas.plans import DEFAULT_PLAN, PLANS
from app.saas.store import FileStore, MemoryStore, StoreError
from app.storage.vector import DenseEmbedder, build_memory
from app.ws.handlers import WsHub
from app.ws.manager import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fk-ai-builder")

settings = get_settings()


async def _build_llm_client(settings: Any) -> tuple[LLMClient | None, str]:
    """Prefer a configured OpenAI-compatible endpoint; else a local Ollama server
    (real free LLM, no key) when reachable; else the deterministic offline agent."""
    if settings.llm_configured:
        return LLMClient(settings.agent_base_url, settings.agent_api_key, settings.agent_model, settings.agent_temperature), "openai-compatible"

    candidates = [settings.ollama_base_url] if settings.ollama_base_url else ["http://localhost:11434/v1"]
    import httpx

    for base in candidates:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{base.rstrip('/')}/models")
                if response.status_code != 200:
                    continue
                models = [m.get("id") for m in response.json().get("data", []) if m.get("id")]
            if not models:
                continue
            model = settings.agent_model if settings.agent_model in models else models[0]
            logger.info("using local Ollama model: %s (%s)", model, base)
            return LLMClient(base, "", model, settings.agent_temperature), f"ollama:{model}"
        except Exception:  # noqa: BLE001 - offline box, fall through
            continue
    return None, "offline-local-agent"


def _build_embedder(settings: Any) -> DenseEmbedder | None:
    """Real embeddings when an LLM endpoint/key is configured; None = TF-IDF."""
    if settings.llm_configured:
        return DenseEmbedder(settings.agent_base_url, settings.agent_api_key, settings.embedding_model)
    if settings.ollama_base_url:
        return DenseEmbedder(settings.ollama_base_url, "", settings.embedding_model)
    return None


def default_canvas(name: str = "Welcome Canvas") -> CanvasState:
    parsed = parse_canvas(
        {
            "version": 1,
            "id": "studio",
            "meta": {"name": name, "theme": "dark"},
            "root": {
                "id": "root",
                "type": "page",
                "content": {},
                "styles": {"tailwind": "min-h-screen bg-slate-950 text-slate-100", "layout": "flex flex-col"},
                "children": [
                    {"id": "c-nav-1", "type": "nav", "content": {"brand": "FK AI Builder", "links": ["Builder", "Dev Hub", "Docs"]}},
                    {
                        "id": "c-hero-1",
                        "type": "hero",
                        "content": {
                            "heading": "Welcome to FK Agent Studio",
                            "subheading": "A real-time design agent and visual canvas in one workspace.",
                            "cta": "Get Started",
                        },
                    },
                    {"id": "c-cta-1", "type": "button", "content": {"text": "Get Started", "href": "#"}},
                ],
            },
        }
    )
    assert parsed.ok, "; ".join(parsed.errors)
    return parsed.canvas  # type: ignore[return-value]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # SaaS store: file-backed (persists across restarts) or memory (tests).
    if settings.saas_data_dir == ":memory:":
        store: Any = MemoryStore()
    else:
        store = FileStore(f"{settings.saas_data_dir}/saas.json")
        store.load_async()

    # Seed the demo account (works in every mode; harmless in production).
    if not store.find_user_by_email(settings.demo_email):
        try:
            await store.create_user(settings.demo_email, settings.demo_password, plan="pro")
            demo = store.find_user_by_email(settings.demo_email)
            if demo:
                await store.set_plan(demo["id"], "pro")
                project = await store.create_project(
                    demo["id"], "My First Canvas", default_canvas("My First Canvas").to_dict()
                )
                logger.info("seeded demo user/project: %s/%s", demo["email"], project["id"])
        except StoreError:
            pass

    llm_client, llm_mode = await _build_llm_client(settings)
    embedder = _build_embedder(settings)
    memory = build_memory(
        settings.qdrant_url,
        settings.qdrant_collection,
        settings.qdrant_api_key,
        embedder=embedder,
    )
    manager = ConnectionManager()
    hub = WsHub(manager, store, memory, settings, lambda llm_client=None: AgentEngine(settings, llm_client=llm_client), llm_client=llm_client)

    app.state.store = store
    app.state.memory = memory
    app.state.manager = manager
    app.state.hub = hub
    app.state.llm_mode = llm_mode
    app.state.embedder_ready = embedder is not None
    logger.info(
        "started | llm=%s | auth=%s | billing=%s | vector=%s",
        llm_mode,
        "supabase-jwt" if settings.supabase_jwt_secret else "session-tokens",
        _active_payment_provider(settings),
        "qdrant+dense" if settings.qdrant_url and embedder else "qdrant+offline" if settings.qdrant_url else "tfidf",
    )
    try:
        yield
    finally:
        await manager.close_all()
        if hasattr(memory, "close"):
            await memory.close()  # type: ignore[attr-defined]


app = FastAPI(title="FK AI Builder", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── auth helpers ─────────────────────────────────────────────────────

def _token_from(request: Any = None, headers: dict[str, str] | None = None, query: dict[str, Any] | None = None) -> str | None:
    if headers is not None:
        auth = headers.get("authorization") or headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    if query is not None:
        token = query.get("token")
        if isinstance(token, str) and token:
            return token
    if request is not None:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    return None


async def resolve_user(token: str | None, store: Any) -> dict[str, Any] | None:
    if not token:
        return None
    user = await store.user_for_token(token)
    if user:
        return user
    if settings.supabase_jwt_secret:
        claims = saas_auth.supabase_verify_jwt(token, settings.supabase_jwt_secret)
        if claims and claims.get("sub"):
            email = claims.get("email") or f"{claims['sub']}@supabase.local"
            user = store.find_user_by_email(email)
            if not user:
                try:
                    user = await store.create_user(email, None, plan=DEFAULT_PLAN)
                    user["id"] = claims["sub"] if not user or user["email"] != email else user["id"]
                except StoreError:
                    user = None
            return user
    return None


async def require_user(request: Request, store: Any) -> dict[str, Any]:
    token = _token_from(request=request)
    user = await resolve_user(token, store)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


async def require_project(project_id: str, user: dict[str, Any], store: Any) -> dict[str, Any]:
    project = await store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if project["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="you do not own this project")
    return project


# ── health & plans ───────────────────────────────────────────────────

def _active_payment_provider(settings: Any) -> str:
    try:
        return payments.provider_status(settings)["active"]
    except Exception:  # noqa: BLE001
        return "sandbox"


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "fk-ai-builder",
        "version": "1.1.0",
        "llm_mode": getattr(app.state, "llm_mode", "offline-local-agent"),
        "auth": "supabase-jwt" if settings.supabase_jwt_secret else "session-tokens",
        "billing": _active_payment_provider(settings),
        "embeddings": "dense" if getattr(app.state, "embedder_ready", False) else "tfidf",
        "connections": app.state.manager.connection_count(),
        "rooms": len(app.state.hub.rooms),
    }


@app.get("/api/plans")
async def plans() -> dict[str, Any]:
    return {"plans": [PLANS[k] for k in ("free", "starter", "pro")]}


# ── auth routes ──────────────────────────────────────────────────────

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=200)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "plan": user.get("plan", "free"),
        "plan_status": user.get("plan_status", "free"),
        "period_end": user.get("period_end"),
        "created_at": user.get("created_at"),
    }


async def _issue_token(store: Any, user: dict[str, Any]) -> str:
    token = saas_auth.new_session_token()
    await store.create_session(user["id"], token)
    return token


@app.post("/api/auth/signup")
async def signup(body: Credentials) -> dict[str, Any]:
    try:
        user = await app.state.store.create_user(body.email, body.password, plan=DEFAULT_PLAN)
    except StoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    token = await _issue_token(app.state.store, user)
    return {"token": token, "user": _public_user(user)}


@app.post("/api/auth/login")
async def login(body: Credentials) -> dict[str, Any]:
    user = await app.state.store.check_login(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = await _issue_token(app.state.store, user)
    return {"token": token, "user": _public_user(user)}


@app.post("/api/auth/demo")
async def demo_login() -> dict[str, Any]:
    user = app.state.store.find_user_by_email(settings.demo_email)
    if not user:
        raise HTTPException(status_code=404, detail="demo account unavailable")
    token = await _issue_token(app.state.store, user)
    return {"token": token, "user": _public_user(user)}


@app.post("/api/auth/logout")
async def logout(request: Request) -> dict[str, Any]:
    token = _token_from(request=request)
    if token:
        await app.state.store.delete_session(token)
    return {"ok": True}


@app.get("/api/auth/me")
async def me(request: Request) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    return {"user": _public_user(user)}


# ── projects ─────────────────────────────────────────────────────────

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.get("/api/projects")
async def list_projects(request: Request) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    projects = await app.state.store.list_projects(user["id"])
    return {
        "projects": [
            {
                "id": p["id"],
                "name": p["name"],
                "version": (p.get("canvas") or {}).get("version", 0),
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
            }
            for p in projects
        ]
    }


@app.post("/api/projects")
async def create_project(request: Request, body: ProjectIn) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    try:
        await limits.assert_project_allowed(user, app.state.store)
    except LimitError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    project = await app.state.store.create_project(user["id"], body.name, default_canvas(body.name).to_dict())
    return {"project": {"id": project["id"], "name": project["name"], "version": 1}}


@app.get("/api/projects/{project_id}")
async def get_project(request: Request, project_id: str) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    project = await require_project(project_id, user, app.state.store)
    return {"project": {k: v for k, v in project.items()}}


@app.patch("/api/projects/{project_id}")
async def rename_project(request: Request, project_id: str, body: ProjectIn) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    project = await require_project(project_id, user, app.state.store)
    project["name"] = body.name
    await app.state.store.save_canvas(project_id, project["canvas"])
    return {"ok": True}


@app.delete("/api/projects/{project_id}")
async def delete_project(request: Request, project_id: str) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    await require_project(project_id, user, app.state.store)
    await app.state.store.delete_project(project_id)
    app.state.hub.drop_room(project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/code")
async def get_project_code(request: Request, project_id: str, format: str = Query("html", pattern="^(html|react|tsx)$")) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    project = await require_project(project_id, user, app.state.store)
    parsed = parse_canvas(project["canvas"])
    if not parsed.ok or parsed.canvas is None:
        raise HTTPException(status_code=422, detail="; ".join(parsed.errors))
    try:
        return code_for_canvas(parsed.canvas, format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── billing ──────────────────────────────────────────────────────────

class CheckoutIn(BaseModel):
    plan: str
    interval: str = "month"
    provider: str = ""  # auto|sandbox|manual|paddle|jazzcash|stripe


@app.get("/api/billing/status")
async def billing_status(request: Request) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    from app.saas.plans import agent_message_limit

    used = await app.state.store.usage_today(user["id"])
    provider = payments.provider_status(settings)
    return {
        "plan": user.get("plan", "free"),
        "plan_status": user.get("plan_status", "free"),
        "period_end": user.get("period_end"),
        "usage_today": used,
        "usage_limit": agent_message_limit(user.get("plan", "free")),
        "projects": await app.state.store.project_count(user["id"]),
        "billing_mode": provider["active"],
        "billing_providers": provider,
        "is_admin": settings.is_admin(user.get("email")),
        "payment_contacts": {
            "jazzcash": settings.jazzcash_account or "",
            "easypaisa": settings.easypaisa_account or "",
            "bank_name": settings.manual_bank_name or "",
            "iban": settings.manual_iban or "",
            "account_title": settings.manual_account_title or "",
        },
    }


@app.post("/api/billing/checkout")
async def checkout(request: Request, body: CheckoutIn) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail="unknown plan")
    if body.plan == "free":
        raise HTTPException(status_code=400, detail="free plan cannot be checked out")

    provider = payments.pick_provider(settings, body.provider)
    try:
        result = await provider.create_checkout(
            user=user,
            plan_id=body.plan,
            interval=body.interval,
            store=app.state.store,
            base_url=settings.public_base_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("checkout failed (%s)", provider.name)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "mode": result.mode,
        "plan": result.plan,
        "interval": result.interval,
        "order_id": result.order_id,
        "amount_pkr": result.amount_pkr,
        "amount_usd": result.amount_usd,
        "url": result.url,
        "redirect_params": result.redirect_params,
        "instructions": result.instructions,
        "account": result.account,
        "demo": result.mode == "sandbox",
    }


@app.get("/api/billing/payments")
async def list_payments(request: Request) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    if settings.is_admin(user.get("email")):
        payments_list = await app.state.store.list_payments()
    else:
        payments_list = await app.state.store.list_payments(user_id=user["id"])
    return {"payments": payments_list}


class PaymentConfirmIn(BaseModel):
    txn_ref: str = Field(min_length=4, max_length=120)
    note: str = ""


async def _resolve_payment(store: FileStore, ref: str) -> dict[str, Any] | None:
    """Resolve a payment by its id OR provider order id."""
    payment = await store.get_payment(ref)
    if payment:
        return payment
    for item in await store.list_payments():
        if item["order_id"] == ref:
            return item
    return None


@app.post("/api/billing/payments/{payment_id}/confirm")
async def confirm_payment(request: Request, payment_id: str, body: PaymentConfirmIn) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    payment = await _resolve_payment(app.state.store, payment_id)
    if not payment or payment["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="payment not found")
    if payment["status"] not in {"awaiting_payment", "pending_review"}:
        raise HTTPException(status_code=409, detail=f"payment already {payment['status']}")
    updated = await app.state.store.update_payment(
        payment["id"], status="pending_review", txn_ref=body.txn_ref.strip(), note=body.note.strip()
    )
    return {"ok": True, "payment": updated}


class PaymentAdminIn(BaseModel):
    note: str = ""


@app.post("/api/billing/payments/{payment_id}/approve")
async def approve_payment(request: Request, payment_id: str, body: PaymentAdminIn | None = None) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    if not settings.is_admin(user.get("email")):
        raise HTTPException(status_code=403, detail="admin only")
    payment = await _resolve_payment(app.state.store, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="payment not found")
    if payment["status"] not in {"pending_review", "awaiting_payment"}:
        raise HTTPException(status_code=409, detail=f"payment already {payment['status']}")
    await billing.demo_activate(payment["user_id"], payment["plan_id"], app.state.store)
    updated = await app.state.store.update_payment(
        payment["id"], status="approved", note=(body.note if body else payment.get("note", "")) or payment.get("note", "")
    )
    return {"ok": True, "payment": updated}


@app.post("/api/billing/payments/{payment_id}/reject")
async def reject_payment(request: Request, payment_id: str, body: PaymentAdminIn | None = None) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    if not settings.is_admin(user.get("email")):
        raise HTTPException(status_code=403, detail="admin only")
    payment = await _resolve_payment(app.state.store, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="payment not found")
    updated = await app.state.store.update_payment(
        payment["id"], status="rejected", note=(body.note if body else "") or payment.get("note", "")
    )
    return {"ok": True, "payment": updated}


# ── provider webhooks / callbacks ───────────────────────────────────

@app.post("/api/payments/paddle/webhook")
async def paddle_webhook(request: Request) -> JSONResponse:
    """Paddle Billing webhook: verified signature -> activate/downgrade plan."""
    if not settings.paddle_webhook_secret:
        return JSONResponse({"ok": True, "skipped": "paddle webhook not configured"})
    payload = await request.body()
    signature = request.headers.get("paddle-signature", "")
    if not verify_paddle_signature(payload, signature, settings.paddle_webhook_secret):
        return JSONResponse({"error": "invalid signature"}, status_code=400)
    event = json.loads(payload)
    user_id, plan, interval = plan_from_paddle_event(event)
    if user_id and plan and plan in PLANS:
        if plan == "free":
            await app.state.store.set_plan(user_id, "free", status="canceled")
        else:
            await billing.demo_activate(user_id, plan, app.state.store)
        logger.info("paddle webhook %s -> user %s (%s)", event.get("type"), user_id, plan)
    return JSONResponse({"ok": True})


@app.post("/api/payments/jazzcash/callback")
async def jazzcash_callback(request: Request) -> Any:
    """JazzCash posts form fields back here after the customer pays."""
    form = await request.form()
    fields = {k: str(v) for k, v in form.items()}
    result = jazzcash_callback_result(fields, settings.jazzcash_integrity_salt)
    if result["ok"] and result["order_id"]:
        payment = await _resolve_payment(app.state.store, result["order_id"])
        if payment and payment["status"] in {"awaiting_payment", "pending_review"}:
            await billing.demo_activate(payment["user_id"], payment["plan_id"], app.state.store)
            await app.state.store.update_payment(
                payment["id"],
                status="approved",
                txn_ref=fields.get("pp_TxnRefNo", "") or payment.get("txn_ref", ""),
                note="auto-approved via JazzCash callback",
            )
            return RedirectResponse(f"{settings.public_base_url}/billing?status=success&provider=jazzcash")
    return RedirectResponse(f"{settings.public_base_url}/billing?status=failed&provider=jazzcash")


@app.post("/api/billing/cancel")
async def cancel_subscription(request: Request) -> dict[str, Any]:
    user = await require_user(request, app.state.store)
    current = user.get("plan", "free")
    if current == "free":
        return {"ok": True, "plan": "free"}
    await app.state.store.set_plan(user["id"], "free", status="canceled")
    return {"ok": True, "plan": "free"}


@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    if not settings.stripe_webhook_secret:
        return JSONResponse({"ok": True, "skipped": "webhook not configured"})
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    event = billing.verify_stripe_webhook(payload, signature, settings.stripe_webhook_secret)
    if event is None:
        return JSONResponse({"error": "invalid signature"}, status_code=400)
    plan = billing.plan_from_webhook(event)
    if plan and plan in PLANS:
        target = None
        session = event.get("data", {}).get("object", {})
        # Real customer mapping: client_reference_id = our user id, set at checkout.
        ref = session.get("client_reference_id")
        if ref:
            found = await app.state.store.get_user(ref)
            target = found["id"] if found else None
        email = session.get("customer_email") or session.get("customer_details", {}).get("email")
        if not target and email:
            found = app.state.store.find_user_by_email(email or "")
            target = found["id"] if found else None
        if target:
            await billing.demo_activate(target, plan, app.state.store)
            logger.info("webhook %s -> user %s (%s)", event.get("type"), target, plan)
    return JSONResponse({"ok": True})


# ── WebSocket ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    hub: WsHub = app.state.hub
    store = app.state.store
    token = websocket.query_params.get("token") or _token_from(headers=dict(websocket.headers))
    project_id = websocket.query_params.get("project", "")

    user = await resolve_user(token, store)
    if not user:
        await websocket.close(code=4401, reason="authentication required")
        return
    project = await store.get_project(project_id)
    if not project or project["user_id"] != user["id"]:
        await websocket.close(code=4403, reason="project not found or not owned")
        return

    parsed = parse_canvas(project["canvas"])
    if not parsed.ok or parsed.canvas is None:
        await websocket.close(code=4400, reason="invalid project canvas")
        return
    room = await hub.ensure_room(project_id, user["id"], parsed.canvas)

    conn = await hub.manager.connect(
        websocket, project_id, user=user, project_id=project_id
    )
    await hub.send_canvas(conn, project_id)
    hub.manager.send(conn, protocol.make_message(protocol.SERVER_ROOM_JOINED, {"room": project_id}, room=project_id))
    try:
        while True:
            raw = await websocket.receive_text()
            payload = protocol.parse_envelope(raw)
            if payload is None:
                hub.manager.send(conn, protocol.make_message(protocol.SERVER_AGENT_ERROR, {"error": "malformed message"}, room=project_id))
                continue
            await hub.handle(conn, payload)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.manager.disconnect(conn)


# ── SSE + long-poll + POST fallbacks ────────────────────────────────

class _SSEConnection:
    def __init__(self, queue: asyncio.Queue[dict[str, Any]]):
        self.queue = queue
        self.closed = False

    async def accept(self) -> None:  # noqa: D401
        ...

    async def send_json(self, message: dict[str, Any]) -> None:
        await self.queue.put(message)

    async def close(self) -> None:
        self.closed = True


def sse_frame(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/events")
async def sse_events(token: str = Query(""), project: str = Query("")) -> StreamingResponse:
    user = await resolve_user(token, app.state.store)
    stored = await app.state.store.get_project(project)
    if not user or not stored or stored["user_id"] != user["id"]:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    parsed = parse_canvas(stored["canvas"])
    if not parsed.ok or parsed.canvas is None:
        return JSONResponse({"error": "invalid canvas"}, status_code=422)
    room = await app.state.hub.ensure_room(project, user["id"], parsed.canvas)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    shim = _SSEConnection(queue)
    conn = await app.state.hub.manager.connect(shim, project, user=user, project_id=project)
    await app.state.hub.send_canvas(conn, project)

    async def gen():
        try:
            yield sse_frame("connected", {"message": "stream open"})
            while True:
                message = await queue.get()
                yield sse_frame(message["type"], message)
        finally:
            await app.state.hub.manager.disconnect(conn)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/poll")
async def poll_events(
    token: str = Query(""),
    project: str = Query(""),
    after: int = Query(0, ge=0),
    timeout: float = Query(10.0, ge=0.5, le=30.0),
) -> dict[str, Any]:
    """Proxy-safe long-poll fallback (lossless via per-room sequence buffer)."""
    user = await resolve_user(token, app.state.store)
    stored = await app.state.store.get_project(project)
    if not user or not stored or stored["user_id"] != user["id"]:
        raise HTTPException(status_code=401, detail="unauthorized")

    parsed = parse_canvas(stored["canvas"])
    if parsed.ok and parsed.canvas is not None:
        await app.state.hub.ensure_room(project, user["id"], parsed.canvas)
    frames = await app.state.hub.manager.poll(project, after, timeout)
    last = after
    payload = []
    for seq, message in frames:
        last = seq
        payload.append({"seq": seq, "message": message})
    return {"frames": payload, "after": last}


class PostEnvelope(BaseModel):
    type: str
    data: Any = None
    request_id: str | None = None
    token: str = ""
    project: str = ""


@app.post("/api/transport")
async def post_transport(envelope: PostEnvelope) -> dict[str, Any]:
    """Uplink for poll/SSE clients: same dispatch as the WebSocket."""
    hub: WsHub = app.state.hub
    user = await resolve_user(envelope.token, app.state.store)
    if not user or not envelope.project:
        raise HTTPException(status_code=401, detail="authentication required")
    stored = await app.state.store.get_project(envelope.project)
    if not stored or stored["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="project not owned")
    if envelope.type not in protocol.CLIENT_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown type '{envelope.type}'")

    parsed = parse_canvas(stored["canvas"])
    if parsed.ok and parsed.canvas is not None:
        await hub.ensure_room(envelope.project, user["id"], parsed.canvas)

    async def _uplink_accept() -> None:  # noqa: D401 - broadcast-only connection
        ...

    async def _uplink_send(message: dict[str, Any]) -> None:
        await hub.manager.broadcast(message, room=envelope.project)

    uplink = type(
        "_Uplink",
        (),
        {
            "closed": False,
            "room": envelope.project,
            "user": user,
            "project_id": envelope.project,
            "accept": staticmethod(_uplink_accept),
            "send_json": staticmethod(_uplink_send),
        },
    )()

    await hub.handle(uplink, {**envelope.model_dump(), "room": envelope.project})  # type: ignore[arg-type]
    return {"ok": True, "enqueued": envelope.type}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
