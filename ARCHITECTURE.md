# FK AI Builder — Unified Architecture

Unifies **Agent Dev Hub** (AI agent workspace) and **Builder Studio** (visual canvas builder)
into one real-time full-stack platform. Next.js (App Router) + React Flow on the frontend,
FastAPI (WebSocket + SSE) on the backend, PostgreSQL (Supabase) for app state and
Qdrant/Pinecone for agent vector memory & RAG.

```
fk-ai-builder/
├── README.md                      # Quickstart, env vars, run commands
├── ARCHITECTURE.md                # This document
├── docker-compose.yml             # Postgres (Supabase-compatible) + Qdrant
├── .env.example                   # All environment variables
│
├── backend/                       # FastAPI — real-time engine + SaaS API
│   ├── requirements.txt
│   ├── main.py                    # App factory, auth, projects, billing, WS/SSE/long-poll
│   ├── config.py                  # Typed settings (pydantic-settings, 12-factor)
│   ├── protocol.py                # Canonical message contract
│   ├── saas/
│   │   ├── plans.py               # Free $0 / Starter $7 / Pro $15 + limits
│   │   ├── auth.py                # Session tokens + Supabase HS256 JWT + pbkdf2 hashing
│   │   ├── store.py               # Users/projects/usage/billing (memory or file-backed)
│   │   ├── billing.py             # Stripe Checkout + webhook verify + demo mode
│   │   └── limits.py              # Project + daily agent-message enforcement
│   ├── ws/
│   │   ├── manager.py             # Rooms, per-conn queues, sequence buffer, long-poll
│   │   └── handlers.py            # Per-project dispatch: ops, agent prompts, limits
│   ├── canvas/
│   │   ├── models.py              # CanvasState / Component / Style schema (JSON tree)
│   │   ├── registry.py            # Component types + defaults + aliases
│   │   ├── parser.py              # Parser (tree / legacy flat / React-Flow shapes)
│   │   ├── operations.py          # Atomic add/update/move/remove/replace
│   │   └── codegen.py             # HTML+Tailwind and React (TSX) generators
│   ├── storage/
│   │   ├── repo.py                # Memory + Postgres(Supabase) canvas repository
│   │   ├── vector.py              # Qdrant + offline hash-embedding memory
│   │   └── schema.sql             # Postgres DDL
│   ├── agent/
│   │   ├── engine.py              # Tool-calling loop (stream tokens + execute tools)
│   │   ├── llm.py                 # OpenAI-compatible streaming client
│   │   ├── local_agent.py         # Zero-key intent fallback (offline demo)
│   │   ├── prompts.py             # System prompt
│   │   └── tools/                 # canvas / codegen / vector / exec tool registry
│   └── tests/                     # 38 tests: parser, ops, codegen, SaaS, WS/SSE/poll E2E
│
└── frontend/                      # Next.js App Router — SaaS web app
    ├── next.config.mjs            # dev rewrites: /api -> FastAPI
    ├── app/
    │   ├── page.tsx               # Landing page
    │   ├── auth/page.tsx          # Login / signup / demo
    │   ├── dashboard/page.tsx     # Projects + usage stats
    │   ├── billing/page.tsx       # Plans, Stripe/demo checkout, cancel
    │   ├── pricing/page.tsx       # Public pricing (below-market plans)
    │   ├── app/[projectId]/page.tsx  # The unified workspace (canvas + DevHub)
    │   └── layout.tsx / globals.css
    ├── lib/
    │   ├── api.ts                 # Typed REST client (token auth)
    │   ├── protocol.ts            # Shared message types
    │   ├── canvas.ts              # Canvas -> React Flow + optimistic ops
    │   └── transport.ts           # WS probe -> lossless long-poll fallback
    ├── hooks/
    │   ├── useAuth.ts             # Session handling
    │   └── useStudioSocket.ts     # Per-project realtime connection
    └── components/
        ├── StudioShell.tsx        # Auth-gated shell
        ├── Header.tsx / Toolbar.tsx / BuilderCanvas.tsx
        ├── PropertyInspector.tsx / DevHub.tsx / ToolCallFeed.tsx
        └── CodePreview.tsx
```

## Real-time message contract (canonical envelope)

Every frame: `{ "type": string, "data": any, "request_id": string|null, "room": string }`

| Direction | Type | Purpose |
|---|---|---|
| C→S | `CANVAS_UPDATE` | Replace full canvas (manual edits, import, reset) |
| C→S | `CANVAS_PATCH` | Apply an op list (`add/update/move/remove`) — atomic |
| C→S | `AGENT_PROMPT` | Ask the agent; response streams back over the same transport |
| C→S | `AGENT_CANCEL` | Stop the running agent request |
| S→C | `INIT_CANVAS` | Canonical state on join (+ version) |
| S→C | `CANVAS_SYNC` | Authoritative new state after any mutation |
| S→C | `AGENT_STREAM_START / _CHUNK / _END` | Legacy-compatible token stream |
| S→C | `AGENT_DELTA` | Modern token delta (also used by SSE) |
| S→C | `AGENT_TOOL_CALL / AGENT_TOOL_RESULT` | Tool execution trace |
| S→C | `AGENT_DONE` | Final message, tools used, mutation summary |
| S→C | `AGENT_ERROR` | Failure with safe error string |
| S→C | `ROOM_JOINED / PONG` | Lifecycle |

## Data model (JSON canvas tree)

```json
{
  "version": 7,
  "meta": { "name": "My Landing Page", "theme": "dark" },
  "root": {
    "id": "root",
    "type": "page",
    "content": {},
    "styles": { "tailwind": "min-h-screen bg-slate-950 text-white", "layout": "flex flex-col" },
    "children": [
      { "id": "c-hero-1", "type": "hero", "content": { "heading": "...", "subheading": "...", "cta": "Get Started" },
        "styles": { "tailwind": "..." }, "children": [] }
    ]
  }
}
```

- Server holds the **single source of truth**; clients send deltas (`CANVAS_PATCH`) and
  the server broadcasts the canonical `CANVAS_SYNC` — optimistic UI is reconciled by `version`.
- Parser accepts three shapes: the canonical tree, the **legacy flat array**
  `[{id,type,content}]` (from the original modules), and React Flow export
  `{nodes, edges}` — all normalized to the same tree, with validation errors.
- Codegen is a pure function of the tree: tailwind HTML and a typed React/TSX component
  are regenerated on every mutation (and on-demand via `GET /api/canvas/{id}/code`).

## Tool-calling loop

```
user prompt
   │
   ▼
[AgentEngine] ──stream deltas──▶ client (typing effect)
   │  (OpenAI-compatible tool schema OR LocalAgent intent parser)
   ▼
tool_call? ──▶ ToolRegistry.execute(name, args)
                 ├─ canvas.*     (mutates canonical state, broadcasts CANVAS_SYNC)
                 ├─ codegen.*    (pure render)
                 ├─ vector.*     (Qdrant memory / RAG)
                 └─ exec.*       (sandboxed python, allowlisted HTTP)
   │
   └── results appended as `tool` messages → loop until finish_reason=stop
```

## Execution plan — milestones

**M0 — Foundations (done in this PR)**
- Monorepo layout, docker-compose (Postgres + Qdrant), env template.
- FastAPI app factory, typed settings, health endpoint, CORS policy.
- Canonical JSON canvas schema + parser + operations + codegen with unit tests.

**M1 — Real-time core (done in this PR)**
- WebSocket server: rooms, per-connection queues, broadcast, heartbeat, reconnect.
- REST + SSE fallback transport (`/api/events`, `/api/transport`) so clients degrade gracefully.
- Canvas repository: memory default, Postgres/Supabase when `DATABASE_URL` is set, version history.

**M2 — Agent tool-calling layer (done in this PR)**
- `AgentEngine`: OpenAI-compatible streaming with native tool-call accumulation.
- Local fallback agent (works with zero API keys) so the whole loop is demoable offline.
- Tools: canvas mutate, codegen, vector memory (Qdrant + offline fallback), python sandbox, HTTP.
- Tool trace events and cancellation.

**M3 — Unified UI (done in this PR)**
- Next.js App Router workspace: BuilderCanvas (React Flow, DnD palette, inspector) + DevHub (chat) + CodePreview.
- Bi-directional sync: canvas→agent context, agent→canvas mutations, cross-client broadcast.

**M3.5 — SaaS web app (done in this PR)**
- Auth: signup/login/demo with pbkdf2 session tokens; Supabase HS256 JWT accepted when configured.
- Multi-project workspaces: every user owns projects; realtime rooms are per-project and
  access-controlled (WS close codes 4401/4403, REST 401/403).
- Plans & billing: Free ($0), Starter ($7/mo, $67/yr), Pro ($15/mo, $144/yr) — deliberately
  below market ($20–30/mo for comparable AI builders). Stripe Checkout in production,
  instant demo activation without keys. Daily agent-message + project limits enforced server-side.
- Pages: landing, pricing, auth, dashboard, billing, project workspace.

**M4 — Hardening (next sprint)**
- SaaS persistence on PostgreSQL/Supabase (users/projects/usage tables; store interface ready).
- Stripe customer-id mapping at checkout; real embeddings + RAG chunking with citations.
- Sandbox hardening (gVisor/Firecracker), tool budgets, observability (OpenTelemetry).
- Playwright E2E, CI, Docker images, deploy (Render/Fly + managed Supabase/Qdrant).

## Key production decisions

- **Transport**: WebSocket primary; SSE (`/api/events` — for direct/prod deployments) and a
  sequence-numbered long-poll (`/api/poll` + `POST /api/transport`) fallback. All three share
  the same protocol and handlers, so a reverse proxy, compression middleware, or restrictive
  network never breaks sync. Long-poll frames are buffered server-side per room with a global
  sequence number — a client resumes at `after=<seq>` and can never miss a frame.
- **State**: versioned canonical state server-side; clients are renderers of the latest
  version. Ops are validated atomically — a bad op is rejected without partial mutation.
- **LLM**: any OpenAI-compatible endpoint (OpenAI, Azure, Groq, Ollama, LM Studio) via
  `AGENT_BASE_URL`/`AGENT_API_KEY`; deterministic local agent when no key is configured.
- **Vector memory**: Qdrant when configured; deterministic hash-embedding fallback in
  memory for offline dev — same tool interface, zero downtime.
- **Secrets**: nothing in the repo; all config via env, `.env.example` documents each var.
- **SaaS**: plans are per-user state on the server (never trusted from the client); billing
  math lives in `saas/plans.py`; daily usage counters gate agent calls at the hub — clients
  get a friendly `AGENT_ERROR` with the limit message, and a 403 with `detail` on REST.
