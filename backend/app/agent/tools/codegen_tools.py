"""Code generation tools: turn the current canvas tree into HTML / React on demand."""
from __future__ import annotations

from typing import Any

from ...canvas.codegen import code_for_canvas
from .registry import Tool, register


async def generate_code(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    fmt = args.get("format", "html")
    try:
        payload = code_for_canvas(ctx.canvas, fmt)
    except ValueError as exc:
        return {"ok": False, "result": None, "error": str(exc)}
    return {"ok": True, "result": payload, "error": None}


def register_codegen_tools() -> None:
    register(Tool(
        "code_generate",
        "Generate clean Tailwind HTML or React (TSX) source from the current canvas.",
        {
            "type": "object",
            "properties": {"format": {"type": "string", "enum": ["html", "react"]}},
            "additionalProperties": False,
        },
        generate_code,
    ))


register_codegen_tools()
