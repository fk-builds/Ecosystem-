"""Agent engine: LLM tool-calling loop + offline fallback.

The engine is transport-agnostic. The WebSocket/SSE layer supplies an `emit`
callback; the engine emits protocol events:
  AGENT_STREAM_START / AGENT_DELTA / AGENT_STREAM_END
  AGENT_TOOL_CALL / AGENT_TOOL_RESULT
  AGENT_DONE / AGENT_ERROR

Tool execution goes through ToolRegistry; canvas tools broadcast CANVAS_SYNC
through the room so all clients see agent edits instantly.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..canvas.models import CanvasState
from .llm import LLMClient, LLMError
from .local_agent import detect_intent, stream_local_response, summarize_ops
from .prompts import build_system_prompt
from .tools.registry import ToolContext, get_tool, import_tools, openai_tools

logger = logging.getLogger(__name__)

Emit = Callable[[str, Any], Awaitable[None]]


@dataclass
class AgentContext:
    """Injected runtime for tool executors."""

    canvas: CanvasState
    canvas_id: str
    repo: Any
    memory: Any
    settings: Any
    broadcast: Callable[[str, Any], Awaitable[None]]
    llm_client: LLMClient | None = None


@dataclass
class AgentRun:
    request_id: str
    context: AgentContext
    emit: Emit
    cancel_event: Any = field(default=None)
    history: list[dict[str, Any]] = field(default_factory=list)


class AgentEngine:
    def __init__(self, settings: Any, llm_client: LLMClient | None = None):
        self.settings = settings
        self.llm_client = llm_client
        import_tools()

    # ── Public API ───────────────────────────────────────────────────

    async def run(self, run: AgentRun, prompt: str) -> dict[str, Any]:
        """Run one agent turn. Returns a summary dict (also emitted as AGENT_DONE)."""
        if self.llm_client is not None:
            return await self._run_llm(run, prompt)

        # Offline deterministic path — still uses the real tool registry.
        ops = detect_intent(prompt, run.context.canvas)
        tool_trace: list[dict[str, Any]] = []
        if ops:
            tool_trace = await self._execute_tools(run, [{"name": "canvas_apply_ops", "arguments": {"operations": ops}}])
            # Remember the session's decision in real vector memory (RAG).
            try:
                await run.context.memory.upsert(
                    f"User asked: {prompt}. Applied: {summarize_ops(ops)}",
                    {"source": "agent", "kind": "action"},
                )
            except Exception:  # noqa: BLE001 - memory must never break the turn
                pass

        await run.emit("AGENT_STREAM_START", None)
        async for event in stream_local_response(prompt, ops, summarize_ops(ops)):
            if event.get("type") == "delta":
                await run.emit("AGENT_DELTA", {"chunk": event["content"]})
            elif event.get("type") == "done":
                break
        await run.emit("AGENT_STREAM_END", None)

        summary = {
            "mode": "local",
            "message": "Applied your request to the canvas.",
            "tools": tool_trace,
            "cancelled": False,
        }
        await run.emit("AGENT_DONE", summary)
        return summary

    # ── LLM tool loop ────────────────────────────────────────────────

    async def _run_llm(self, run: AgentRun, prompt: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt(run.context.canvas)}]
        messages.append({"role": "user", "content": prompt})

        tool_trace: list[dict[str, Any]] = []
        final_text = ""
        try:
            await run.emit("AGENT_STREAM_START", None)
            for _round in range(self.settings.agent_max_tool_rounds):
                if self._cancelled(run):
                    break

                tool_calls: dict[int, dict[str, str]] = {}
                round_text = ""
                done_reason: str | None = None
                try:
                    async for event in self.llm_client.stream_chat(messages, tools=openai_tools()):
                        if self._cancelled(run):
                            break
                        etype = event.get("type")
                        if etype == "delta":
                            chunk = event["content"]
                            round_text += chunk
                            await run.emit("AGENT_DELTA", {"chunk": chunk})
                        elif etype == "tool_call":
                            idx = int(event.get("index", 0))
                            slot = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            if event.get("id"):
                                slot["id"] = event["id"]
                            if event.get("name"):
                                slot["name"] += event["name"]
                            slot["arguments"] += event.get("arguments", "")
                        elif etype == "done":
                            done_reason = event.get("finish_reason")
                            break
                except LLMError as exc:
                    await run.emit("AGENT_ERROR", {"error": str(exc)})
                    return {"mode": "llm", "message": "", "tools": tool_trace, "cancelled": False, "error": str(exc)}
                except Exception as exc:  # noqa: BLE001
                    logger.exception("LLM stream failed")
                    await run.emit("AGENT_ERROR", {"error": f"LLM stream failed: {type(exc).__name__}"})
                    return {"mode": "llm", "message": "", "tools": tool_trace, "cancelled": False, "error": str(exc)}

                if round_text:
                    final_text += round_text

                assistant_msg: dict[str, Any] = {"role": "assistant", "content": round_text or None}
                if tool_calls:
                    calls_payload = []
                    for idx in sorted(tool_calls):
                        slot = tool_calls[idx]
                        calls_payload.append({
                            "id": slot["id"] or f"call_{idx}",
                            "type": "function",
                            "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"},
                        })
                    assistant_msg["tool_calls"] = calls_payload
                messages.append(assistant_msg)

                if not tool_calls:
                    break

                tool_trace.extend(await self._execute_tools(run, [
                    {
                        "name": tc["function"]["name"],
                        "arguments": _safe_json(tc["function"]["arguments"]),
                        "call_id": tc["id"],
                    }
                    for tc in calls_payload
                ]))

                # Feed tool results back to the model as `tool` messages.
                for result in tool_trace[-len(calls_payload):]:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result.get("call_id") or "",
                        "content": json.dumps({"ok": result.get("ok"), "result": result.get("result"), "error": result.get("error")})[:8000],
                    })

                if done_reason == "tool_calls":
                    continue
            else:
                logger.warning("Reached max tool rounds (%s)", self.settings.agent_max_tool_rounds)

            cancelled = self._cancelled(run)
            summary = {"mode": "llm", "message": final_text, "tools": tool_trace, "cancelled": cancelled}
            await run.emit("AGENT_STREAM_END", None)
            await run.emit("AGENT_DONE", summary)
            return summary
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent turn failed")
            await run.emit("AGENT_ERROR", {"error": f"agent error: {type(exc).__name__}: {exc}"})
            return {"mode": "llm", "message": "", "tools": tool_trace, "cancelled": False, "error": str(exc)}

    # ── Tool execution ───────────────────────────────────────────────

    async def _execute_tools(self, run: AgentRun, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for spec in specs:
            if self._cancelled(run):
                break
            name = spec.get("name", "")
            args = spec.get("arguments") or {}
            call_id = spec.get("call_id") or f"call_{len(trace)}"

            await run.emit("AGENT_TOOL_CALL", {"id": call_id, "name": name, "arguments": args})
            tool = get_tool(name)
            if tool is None:
                result = {"ok": False, "result": None, "error": f"unknown tool '{name}'"}
            else:
                try:
                    result = await tool.handler(args, run.context)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tool %s failed", name)
                    result = {"ok": False, "result": None, "error": f"{type(exc).__name__}: {exc}"}

            entry = {"call_id": call_id, "name": name, **result}
            trace.append(entry)
            await run.emit("AGENT_TOOL_RESULT", entry)

            if not result.get("ok"):
                # Surface tool failure to the model: still continue the loop so the LLM
                # can recover, unless the canvas is corrupted.
                continue
        return trace

    @staticmethod
    def _cancelled(run: AgentRun) -> bool:
        return bool(run.cancel_event and run.cancel_event.is_set())


def _safe_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}
