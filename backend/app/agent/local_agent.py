"""Deterministic fallback agent (zero API keys).

When no LLM is configured (AGENT_API_KEY empty), this intent parser makes the
full loop demoable offline: it detects tool intents from the prompt, streams a
natural-language response, and executes canvas mutations through the same
ToolRegistry as the real LLM path.

Supported intents (all optional):
  - "add a modern hero section"                    -> canvas_add hero
  - "add a heading that says Hello there"          -> canvas_add heading(text)
  - "add a card with title X and text Y"           -> canvas_add card
  - "remove the button" / "remove the last hero"   -> canvas_delete (by type)
  - "change the heading to Goodbye" / "update text to ..." -> canvas_update
"""
from __future__ import annotations

import re
from typing import Any, AsyncIterator

from ..canvas.registry import COMPONENT_REGISTRY, normalize_type

_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "hero": ("hero", "landing", "header"),
    "nav": ("nav", "navbar", "navigation"),
    "heading": ("heading", "title", "h1", "h2", "h3"),
    "text": ("text", "paragraph", "description"),
    "button": ("button", "cta", "call to action"),
    "card": ("card", "feature", "features"),
    "image": ("image", "picture"),
    "form": ("form", "contact form"),
    "input": ("input", "email input"),
    "grid": ("grid", "columns"),
    "divider": ("divider", "separator", "hr"),
    "footer": ("footer"),
    "section": ("section", "content section"),
}

_DEFAULT_CONTENT: dict[str, dict[str, Any]] = {
    "hero": {"heading": "Build with AI", "subheading": "Design real-time interfaces, powered by an agent that writes to your canvas.", "cta": "Get Started"},
    "nav": {"brand": "My Product", "links": ["Home", "Features", "Pricing"]},
    "heading": {"text": "Section heading", "level": "h1"},
    "text": {"text": "A concise description of what this section offers."},
    "button": {"text": "Get Started", "href": "#"},
    "card": {"title": "Feature", "text": "A short feature description."},
    "image": {"src": "https://picsum.photos/seed/fkbuilder/800/450", "alt": "Preview image"},
    "form": {"action": "#"},
    "input": {"placeholder": "you@example.com", "label": "Email"},
    "grid": {"columns": 2},
    "divider": {},
    "footer": {"text": "© 2025 FK AI Builder"},
    "section": {},
}

_REMOVE_RE = re.compile(r"\b(remove|delete|drop)\b", re.IGNORECASE)
_UPDATE_RE = re.compile(
    r"\b(change|update|set|rewrite)\b\s+(?:the\s+)?(heading|title|text|paragraph|description|button|hero|card)\b"
    r"(?:\s*.*?\b(?:to|say(?:ing)?|as)\s+[\"']?([^\"']+?)[\"']?)?$",
    re.IGNORECASE,
)
_ADD_RE = re.compile(r"\b(add|create|insert|build|make|include)\b", re.IGNORECASE)


def detect_intent(prompt: str, canvas: Any) -> list[dict[str, Any]]:
    """Return ops for the prompt, or [] when nothing matches."""
    lowered = prompt.lower()

    # 1. Remove
    if _REMOVE_RE.search(lowered):
        target_type = _first_matching_type(lowered)
        if target_type:
            target = _find_by_type(canvas, target_type)
            if target:
                return [{"op": "remove", "id": target.id}]

    # 2. Update: "change the heading to Goodbye"
    update = _UPDATE_RE.search(prompt)
    if update:
        type_label = _RESOLVE_UPDATE.get(update.group(2), update.group(2))
        target = _find_by_type(canvas, type_label)
        if target:
            text = (update.group(3) or "").strip().rstrip(".")
            if text:
                patch_content: dict[str, Any] = {}
                if target.type in {"heading", "text", "button"}:
                    patch_content["text"] = text
                elif target.type == "hero":
                    patch_content["heading"] = text
                elif target.type == "card":
                    patch_content["title"] = text
                if patch_content:
                    return [{"op": "update", "id": target.id, "patch": {"content": patch_content}}]

    # 3. Add: "add a modern hero section ..."
    if _ADD_RE.search(lowered):
        type_match = _first_matching_type(lowered)
        if type_match:
            content = _content_from_prompt(prompt, type_match)
            return [{"op": "add", "component": {"type": type_match, "content": content}}]

    return []


_RESOLVE_UPDATE = {"title": "heading", "paragraph": "text", "description": "text"}


_STRUCTURAL = {"grid", "section", "form", "nav", "hero", "footer"}


def _first_matching_type(lowered: str) -> str | None:
    """Earliest appearing type keyword wins; structural composers get a priority
    boost so "features grid" -> grid rather than card (from "features").

    "add a modern hero section with heading 'X'" -> hero (heading is content, not
    the primary component); "add a heading that says X" -> heading.
    """
    best: tuple[int, int, int, str] | None = None  # (position, -length, structural-rank, type)
    for comp_type, words in _TYPE_WORDS.items():
        for word in words:
            if word in lowered and len(word) >= 3:
                pos = lowered.index(word)
                candidate = (pos, -len(word), 0 if comp_type in _STRUCTURAL else 1, comp_type)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
    return best[3] if best else None


def _content_from_prompt(prompt: str, comp_type: str) -> dict[str, Any]:
    lowered = prompt.lower()
    content = dict(_DEFAULT_CONTENT.get(comp_type, {}))

    # "says/that says/saying '...'" or quoted phrase (match on the original to
    # preserve the user's casing).
    quote = None
    m = re.search(r"[\"']([^\"']{3,90})[\"']", prompt)
    if m:
        quote = m.group(1).strip()
    if not quote:
        m = re.search(r"(?:that says|saying|reads|titled|called)\s+[\"']?([^\"',]+)[\"']?", prompt)
        if m:
            quote = m.group(1).strip().rstrip(".")
    if not quote:
        m = re.search(r"(?:with|heading)\s+(?:text\s+)?[\"']?([^\"',]+?)[\"']?(?:\s+(?:and|with|saying|subheading))?$", prompt)
        if m and len(m.group(1).strip()) > 2:
            quote = m.group(1).strip().rstrip(".")

    if quote:
        if comp_type == "hero":
            content["heading"] = quote
        elif comp_type in {"heading", "text", "button"}:
            content["text"] = quote
        elif comp_type == "card":
            content["title"] = quote
        elif comp_type == "nav":
            content["brand"] = quote
        elif comp_type == "footer":
            content["text"] = quote

    # "with X cards" / "3 columns" becomes grid/card content hints
    if comp_type == "grid":
        m = re.search(r"(\d+)\s+(?:columns|cols)", lowered)
        if m:
            content["columns"] = max(1, min(int(m.group(1)), 4))

    return content


def _find_by_type(canvas: Any, type_label: str) -> Any | None:
    wanted = normalize_type(type_label)
    if wanted is None:
        return None

    def walk(comp: Any) -> Any | None:
        if comp.type == wanted:
            return comp
        for child in comp.children:
            found = walk(child)
            if found:
                return found
        return None

    return walk(canvas.root)


async def stream_local_response(prompt: str, ops: list[dict[str, Any]], summary: str) -> AsyncIterator[dict[str, Any]]:
    """Stream a scripted response (used when no LLM is configured)."""
    if ops:
        text = (
            f"Got it — I'll {summary} on the canvas. "
            "The update is live, and every connected client is synced in real time. "
            "What would you like to refine next?"
        )
    else:
        text = (
            f"I can help with: \"{prompt.strip()}\". "
            "Try asking me to add a modern hero section, add a features grid, "
            "change the heading to something new, remove the button, or generate the React code."
        )
    for word in text.split(" "):
        yield {"type": "delta", "content": word + " "}
    yield {"type": "done", "finish_reason": "stop"}


def summarize_ops(ops: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for op in ops:
        kind = op.get("op")
        if kind == "add":
            comp = op.get("component", {})
            parts.append(f"add a {comp.get('type', 'component')} component")
        elif kind == "update":
            parts.append(f"update the {op.get('id')} component")
        elif kind in {"remove", "delete"}:
            parts.append(f"remove the {op.get('id')} component")
        elif kind == "move":
            parts.append(f"move the {op.get('id')} component")
    return ", ".join(parts) or "apply those changes"
