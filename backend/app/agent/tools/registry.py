"""Tool registry: name -> (schema, async executor).

Every tool returns `{"ok": bool, "result": Any, "error": str|None}`.
The executor context carries the room's canvas state, repo, memory, and sinks
for broadcasting canvas sync / events during tool execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from ...canvas.models import CanvasState


class ToolContext(Protocol):
    canvas: CanvasState
    canvas_id: str
    repo: Any
    memory: Any
    broadcast: Callable[[str, Any], Awaitable[None]]
    settings: Any


ToolExecutor = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]


class Tool:
    def __init__(self, name: str, description: str, schema: dict[str, Any], handler: ToolExecutor):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler

    def openai_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.schema}}


def register(tool: Tool) -> None:
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def tool_list() -> list[Tool]:
    return list(_TOOLS.values())


def openai_tools() -> list[dict[str, Any]]:
    return [t.openai_schema() for t in _TOOLS.values()]


_TOOLS: dict[str, Tool] = {}


def import_tools() -> None:
    """Idempotent import of all tool modules (registers into _TOOLS)."""
    from . import canvas_tools, codegen_tools, exec_tools, vector_tools  # noqa: F401
