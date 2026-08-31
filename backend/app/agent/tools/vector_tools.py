"""Vector memory / RAG tools backed by Qdrant (or the offline hash fallback)."""
from __future__ import annotations

from typing import Any

from .registry import Tool, register


async def memory_upsert(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    text = args.get("text", "").strip()
    if not text:
        return {"ok": False, "result": None, "error": "text is required"}
    meta = args.get("metadata") or {}
    meta.setdefault("canvas_id", ctx.canvas_id)
    memory_id = await ctx.memory.upsert(text, meta)
    return {"ok": True, "result": {"memory_id": memory_id, "embedded": True}, "error": None}


async def memory_search(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    query = args.get("query", "").strip()
    if not query:
        return {"ok": False, "result": None, "error": "query is required"}
    top_k = max(1, min(int(args.get("top_k", ctx.settings.vector_memory_top_k)), 20))
    meta: dict[str, Any] = {}
    if args.get("scope_to_canvas", True):
        meta = {"canvas_id": ctx.canvas_id}
    hits = await ctx.memory.search(query, top_k=top_k, meta=meta)
    return {"ok": True, "result": {"hits": hits, "count": len(hits)}, "error": None}


async def memory_list(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 20)), 100))
    meta: dict[str, Any] = {}
    if args.get("scope_to_canvas", True):
        meta = {"canvas_id": ctx.canvas_id}
    items = await ctx.memory.list_items(limit=limit, meta=meta)
    return {"ok": True, "result": {"items": items, "count": len(items)}, "error": None}


def register_vector_tools() -> None:
    register(Tool(
        "memory_upsert",
        "Store a fact, snippet, or document chunk in the agent's vector memory (RAG).",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "metadata": {"type": "object", "description": "e.g. {source: 'prompt', kind: 'note'}"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        memory_upsert,
    ))
    register(Tool(
        "memory_search",
        "Semantic search over agent vector memory. Returns the most similar stored chunks.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"},
                "scope_to_canvas": {"type": "boolean", "description": "Restrict to the current canvas (default true)"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        memory_search,
    ))
    register(Tool(
        "memory_list", "List stored memory items.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer"}, "scope_to_canvas": {"type": "boolean"}},
            "additionalProperties": False,
        },
        memory_list,
    ))


register_vector_tools()
