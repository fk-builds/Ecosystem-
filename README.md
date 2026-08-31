# FK AI Builder — Agent Dev Hub × Builder Studio

A unified, real-time full-stack platform that combines an **AI Agent workspace**
(Agent Dev Hub) with a **drag-and-drop visual canvas builder** (Builder Studio).

- **Frontend** — Next.js (App Router) + Tailwind + React Flow
- **Backend** — FastAPI: WebSockets + SSE + sequence-numbered long-poll, async tool executor
- **State** — canonical JSON canvas tree; server-authoritative, versioned, synced to every client
- **Agent** — OpenAI-compatible tool-calling loop (works with OpenAI/Azure/Groq/Ollama/LM Studio)
  plus a zero-key **offline local agent** so the whole loop runs in the demo
- **Persistence** — PostgreSQL/Supabase (optional) via asyncpg; in-memory by default
- **Memory / RAG** — Qdrant (optional) with a deterministic in-memory hash fallback

```
┌────────────────────────── Browser ───────────────────────────┐
│  Next.js app (port 3000)                                     │
│  BuilderCanvas (React Flow) │ DevHub (chat) │ Inspector/Code │
│            ▲  WebSocket (upgrade) │ long-poll + POST (fallback)
└────────────┼──────────────────────────────────────────────────┘
             │  /api rewrites (dev) or direct (deploy)
┌────────────▼──────────────────────────────────────────────────┐
│  FastAPI (port 8000)                                         │
│  WS /ws · SSE /api/events · long-poll /api/poll · /api/transport
│  WsHub → CanvasState (tree) → ops(atomic) → codegen          │
│  AgentEngine → LLM stream → ToolRegistry                     │
│    canvas.* · codegen.* · memory.* (Qdrant) · exec.* (sandbox)│
│  Repo: Memory | Postgres/Supabase                            │
└──────────────────────────────────────────────────────────────┘
```

## Quickstart

```bash
# 1) Optional infra: PostgreSQL (Supabase-compatible) + Qdrant
docker compose up -d

# 2) Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 3) Frontend
cd ../frontend
npm install
npm run dev
```

Open http://localhost:3000 — you land on the marketing page. Log in or hit
**✨ Try the demo account (Pro)** (`demo@fk.ai` / `demo1234`), open a project,
and you'll see the canvas + Dev Hub with a live connection badge
(`Live · WebSocket` when the browser can upgrade, otherwise `Live · long-poll` —
both fully real-time).

> When the backend is deployed separately from the frontend (or behind a gateway
> that doesn't proxy WebSockets), set `NEXT_PUBLIC_WS_URL=wss://api.example.com/ws`
> so the browser can upgrade to the WebSocket path; otherwise it stays on the
> equally real-time long-poll transport.

> No API key required. With `AGENT_API_KEY` unset the backend uses a deterministic
> local intent agent; set `AGENT_API_KEY` (+ optional `AGENT_BASE_URL`, `AGENT_MODEL`)
> to switch to a real model. Point it at Ollama/LM Studio/Groq for free options.

## SaaS plans (below market, by design)

| Plan | Price | Projects | Agent msgs/day |
|---|---|---|---|
| Free | $0 | 1 | 25 |
| Starter | **$7/mo** ($67/yr) | 5 | 500 |
| Pro | **$15/mo** ($144/yr) | unlimited | 2,000 |

Comparable AI builder tools charge $20–30/mo. **Payments work from Pakistan**:
Stripe is unavailable for PK businesses (SBP PSEFT licensing), so the billing
layer uses a provider registry — `auto` picks **paddle** (international MoR,
payouts to PK via Payoneer) → **jazzcash** (hosted PKR gateway) → **manual**
(JazzCash/EasyPaisa/IBAN + TRX-id review, works today with zero approvals) →
**sandbox**. Limits are enforced on the server, never the client. See
`docs/PAKISTAN-PAYMENTS.md` for the exact signup lists (Paddle + Payoneer,
JazzCash merchant, or just fill the manual wallet fields in `.env`).

## Things to try

- Drag **Hero** from the palette onto the canvas, or click it to add
- Ask the Dev Hub: `add a modern hero section with heading 'Ship Fast'`
- `add a features grid with 3 cards`
- `change the heading to Goodbye world`
- `remove the button`
- Select any node → edit props/Tailwind classes in the Inspector → watch **all
  clients** sync; the **Code** tab regenerates HTML + React on every change
- Open two browser windows — edits and agent mutations appear in both instantly

## Configuration (`.env` / env vars)

See `.env.example` for everything (LLM endpoint/keys, `DATABASE_URL`, `QDRANT_URL`,
tool timeouts, allowlists). Nothing secret is committed.

## API

| Route | Purpose |
|---|---|
| `GET /api/health` | liveness + mode summary |
| `GET /api/plans` | public plan catalog |
| `POST /api/auth/signup\|login\|demo\|logout`, `GET /api/auth/me` | session auth |
| `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}` | user projects |
| `GET /api/projects/{id}/code?format=html\|react` | generated code payload |
| `GET /api/billing/status`, `POST /api/billing/checkout\|cancel` | plans & provider checkout |
| `GET /api/billing/payments`, `POST /api/billing/payments/{id}/confirm\|approve\|reject` | manual payment review |
| `POST /api/payments/paddle/webhook`, `POST /api/payments/jazzcash/callback` | provider webhooks |
| `WS /ws?token=&project=` | real-time socket (per-project room) |
| `GET /api/events?token=&project=` | SSE stream (direct/prod deployments) |
| `GET /api/poll?token=&project=&after=<seq>` | proxy-safe long-poll (lossless) |
| `POST /api/transport` | uplink for poll/SSE clients (token+project in body) |

Protocol frames (`INIT_CANVAS`, `CANVAS_SYNC`, `CANVAS_PATCH`, `AGENT_PROMPT`,
`AGENT_STREAM_START/_DELTA/_END`, `AGENT_TOOL_CALL/_RESULT`, `AGENT_DONE`,
`AGENT_ERROR`) are defined in `backend/app/protocol.py` and mirrored in
`frontend/lib/protocol.ts`.

## Tests

```bash
cd backend && source .venv/bin/activate && python -m pytest -q
# 31 tests: parser (canonical/legacy/RF), atomic ops, codegen, WS/SSE/poll E2E
```

See `ARCHITECTURE.md` for the full directory map, data model, and milestone plan.
