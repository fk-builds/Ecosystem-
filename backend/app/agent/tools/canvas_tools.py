"""Canvas mutation tools — the two-way Agent <-> Builder bridge."""
from __future__ import annotations

from typing import Any

from ...canvas.operations import apply_operations
from ...canvas.registry import COMPONENT_REGISTRY
from .registry import Tool, register


async def _apply(ctx: Any, ops: list[dict[str, Any]]) -> dict[str, Any]:
    result = apply_operations(ctx.canvas, ops)
    if not result.ok:
        return {"ok": False, "result": None, "error": result.error}
    ctx.canvas = result.canvas
    await ctx.repo.save(ctx.canvas)
    await ctx.broadcast("CANVAS_SYNC", ctx.canvas.to_dict())
    return {"ok": True, "result": {"version": ctx.canvas.version, "commits": result.commits}, "error": None}


async def get_canvas(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"ok": True, "result": ctx.canvas.to_dict(), "error": None}


async def list_types(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "result": {t: {"label": s["label"], "container": bool(s.get("container"))} for t, s in COMPONENT_REGISTRY.items()},
        "error": None,
    }


async def add_component(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ops = [{
        "op": "add",
        "component": args.get("component") or {"type": args.get("type", "text")},
        "parent_id": args.get("parent_id", "root"),
        "index": args.get("index"),
    }]
    return await _apply(ctx, ops)


async def update_component(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ops = [{"op": "update", "id": args.get("id", ""), "patch": args.get("patch") or {}}]
    return await _apply(ctx, ops)


async def delete_component(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ops = [{"op": "remove", "id": args.get("id", "")}]
    return await _apply(ctx, ops)


async def move_component(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ops = [{"op": "move", "id": args.get("id", ""), "parent_id": args.get("parent_id", "root"), "index": args.get("index")}]
    return await _apply(ctx, ops)


async def apply_ops(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ops = args.get("operations") or args.get("ops")
    if not isinstance(ops, list) or not ops:
        return {"ok": False, "result": None, "error": "operations must be a non-empty list"}
    return await _apply(ctx, ops)


def register_canvas_tools() -> None:
    register(Tool(
        "canvas_get", "Return the current JSON canvas state tree.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        get_canvas,
    ))
    register(Tool(
        "canvas_list_types", "List available component types with their labels.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        list_types,
    ))
    register(Tool(
        "canvas_add",
        "Add a component to the canvas. Use a known type (hero, section, heading, text, button, "
        "card, image, input, form, grid, nav, divider, footer). Pass parent_id to nest.",
        {
            "type": "object",
            "properties": {
                "component": {
                    "type": "object",
                    "description": "Component object with type, content, styles",
                    "properties": {
                        "type": {"type": "string"},
                        "content": {"type": "object"},
                        "styles": {"type": "object"},
                    },
                },
                "type": {"type": "string", "description": "Shorthand for component.type"},
                "parent_id": {"type": "string", "description": "Container id to nest under (default root)"},
                "index": {"type": "integer", "description": "Insertion index among siblings"},
            },
            "additionalProperties": False,
        },
        add_component,
    ))
    register(Tool(
        "canvas_update",
        "Patch component content/styles by id.",
        {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "patch": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "object", "description": "Merged into existing content"},
                        "styles": {"type": "object", "description": "Merged into existing styles, e.g. {tailwind: '...'}"},
                        "type": {"type": "string"},
                    },
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        update_component,
    ))
    register(Tool(
        "canvas_delete", "Remove a component (and its children) by id.",
        {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
        delete_component,
    ))
    register(Tool(
        "canvas_move", "Move a component to another container / index.",
        {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "parent_id": {"type": "string"},
                "index": {"type": "integer"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        move_component,
    ))
    register(Tool(
        "canvas_apply_ops", "Apply a list of atomic ops in one batch (add/update/remove/move).",
        {
            "type": "object",
            "properties": {
                "operations": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["operations"],
            "additionalProperties": False,
        },
        apply_ops,
    ))


register_canvas_tools()
