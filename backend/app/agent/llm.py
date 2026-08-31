"""OpenAI-compatible streaming chat client (OpenAI, Azure, Groq, Ollama, LM Studio...).

Streams chat completion chunks as dicts:
  {"type": "delta", "content": str}
  {"type": "tool_call", "id": str, "name": str, "arguments": str}  (arguments may arrive
   in fragments; callers accumulate)
  {"type": "done", "finish_reason": str|None}
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.4):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        stream: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")[:800]
                    raise LLMError(f"LLM HTTP {response.status_code}: {body}")

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        yield {"type": "done", "finish_reason": None}
                        return
                    try:
                        obj = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    finish_reason = choice.get("finish_reason")

                    if delta.get("content"):
                        yield {"type": "delta", "content": delta["content"]}
                    for tc in delta.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        yield {
                            "type": "tool_call",
                            "id": tc.get("id") or "",
                            "index": tc.get("index", 0),
                            "name": fn.get("name") or "",
                            "arguments": fn.get("arguments") or "",
                        }
                    if finish_reason:
                        yield {"type": "done", "finish_reason": finish_reason}
                        return


class LLMError(Exception):
    pass
