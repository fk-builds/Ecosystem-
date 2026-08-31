"""Sandboxed execution + allowlisted HTTP fetch tools.

Security posture (defense in depth):
  - Python runs with a restricted builtins namespace (no imports, no file/network
    access) inside a worker thread with a hard timeout. For production, run
    executors in gVisor/Firecracker or an external sandbox (ARCHITECTURE.md M4).
  - HTTP tool only allows hosts in `HTTP_TOOL_ALLOWLIST` (default all), caps
    response size and timeout.
"""
from __future__ import annotations

import asyncio
import textwrap
from typing import Any
from urllib.parse import urlsplit

from .registry import Tool, register

_ALLOWED_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool, "chr": chr,
    "dict": dict, "divmod": divmod, "enumerate": enumerate, "filter": filter,
    "float": float, "format": format, "hash": hash, "hex": hex, "int": int,
    "isinstance": isinstance, "issubclass": issubclass, "iter": iter, "len": len,
    "list": list, "map": map, "max": max, "min": min, "next": next, "object": object,
    "oct": oct, "ord": ord, "pow": pow, "range": range, "repr": repr,
    "reversed": reversed, "round": round, "set": set, "slice": slice,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "type": type,
    "zip": zip, "print": print, "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError, "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError, "ArithmeticError": ArithmeticError,
}


def _restricted_namespace() -> dict[str, Any]:
    return {"__builtins__": _ALLOWED_BUILTINS, "__name__": "sandbox"}


def _run_restricted(code: str) -> str:
    """Execute `code` with restricted builtins and capture stdout."""
    import io
    from contextlib import redirect_stdout

    ns = _restricted_namespace()
    wrapped = textwrap.indent(code, "    ")
    output = io.StringIO()
    with redirect_stdout(output):
        exec(compile(f"def __main__():\n{wrapped}\n__main__()", "<sandbox>", "exec"), ns, ns)
    return output.getvalue().rstrip() or "<no output>"


async def run_python(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    if not ctx.settings.exec_python_enabled:
        return {"ok": False, "result": None, "error": "python execution is disabled by the server"}
    code = args.get("code", "")
    if not code.strip():
        return {"ok": False, "result": None, "error": "code is required"}
    if len(code) > 16_000:
        return {"ok": False, "result": None, "error": "code exceeds 16000 chars"}

    loop = asyncio.get_running_loop()
    timeout = ctx.settings.exec_python_timeout_s
    try:
        output = await asyncio.wait_for(loop.run_in_executor(None, _run_restricted, code), timeout=timeout)
        return {"ok": True, "result": {"status": "ok", "output": output}, "error": None}
    except asyncio.TimeoutError:
        return {"ok": False, "result": None, "error": f"execution timed out after {timeout}s"}
    except Exception as exc:  # noqa: BLE001 - surface sandbox errors safely
        return {"ok": False, "result": None, "error": f"execution error: {type(exc).__name__}: {exc}"}


async def http_fetch(args: dict[str, Any], ctx: Any) -> dict[str, Any]:
    import httpx

    url = args.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "result": None, "error": "url must be http(s)"}

    host = urlsplit(url).hostname or ""
    allowlist = ctx.settings.http_allowlist
    if allowlist is not None and host not in allowlist:
        return {"ok": False, "result": None, "error": f"host '{host}' is not in the server allowlist"}

    try:
        async with httpx.AsyncClient(timeout=ctx.settings.http_tool_timeout_s, follow_redirects=True) as client:
            response = await client.get(url)
            body = response.text[: ctx.settings.http_tool_max_bytes]
            return {
                "ok": True,
                "result": {
                    "status": response.status_code,
                    "url": str(response.url),
                    "content_type": response.headers.get("content-type", ""),
                    "body": body,
                },
                "error": None,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "result": None, "error": f"http error: {type(exc).__name__}: {exc}"}


def register_exec_tools() -> None:
    register(Tool(
        "execute_python",
        "Execute a small Python snippet in a restricted sandbox (no imports/network). "
        "Useful for content transforms, math, and quick data manipulation.",
        {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python code to run"}},
            "required": ["code"],
            "additionalProperties": False,
        },
        run_python,
    ))
    register(Tool(
        "http_fetch",
        "Fetch a URL's content (used to ground responses with live data).",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
        http_fetch,
    ))


register_exec_tools()
