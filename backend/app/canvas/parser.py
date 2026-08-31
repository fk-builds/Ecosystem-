"""JSON canvas parser — accepts three input shapes and normalizes them to one tree:

1. Canonical tree      {"version": 1, "root": {"id","type","content","styles","children"}}
2. Legacy flat array   [{id, type, content}, ...]  (original Builder Studio format)
3. React Flow export   {"nodes": [{id, type, data}], "edges": [...]}

The parser is lossy-free for the canonical shape, best-effort and fully validated for
the other two. Errors are reported together; no partial state is returned.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import ValidationError

from .models import CanvasMeta, CanvasState, Component
from .registry import COMPONENT_REGISTRY, default_component, is_container, normalize_type

TYPE_ORDER = {t: i for i, t in enumerate(COMPONENT_REGISTRY)}

LEGACY_TO_TYPE: dict[str, str] = {
    "header": "hero",
    "heading": "heading",
    "h1": "heading",
    "h2": "heading",
    "button": "button",
    "cta": "button",
    "text": "text",
    "paragraph": "text",
    "card": "card",
    "image": "image",
    "img": "image",
    "form": "form",
    "input": "input",
    "footer": "footer",
    "divider": "divider",
    "section": "section",
    "hero": "hero",
    "nav": "nav",
    "navbar": "nav",
    "grid": "grid",
}


class ParseError(Exception):
    """Raised when the input cannot be parsed into a valid canvas."""


class ParseResult:
    def __init__(self, canvas: CanvasState | None, errors: list[str], warnings: list[str]):
        self.canvas = canvas
        self.errors = errors
        self.warnings = warnings

    @property
    def ok(self) -> bool:
        return self.canvas is not None


def _new_id(prefix: str = "c") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _coerce_content(raw: Any) -> dict[str, Any]:
    """Legacy flat components used `content: "string"`; normalize to {text: ...}."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return {"text": raw}
    if raw is None:
        return {}
    raise ParseError(f"content must be a dict or string, got {type(raw).__name__}")


def _coerce_component(raw: dict[str, Any], *, strict: bool = False) -> Component:
    if not isinstance(raw, dict):
        raise ParseError(f"component must be an object, got {type(raw).__name__}")

    raw_type = raw.get("type", "")
    if isinstance(raw_type, dict):
        # React Flow: type may carry a data payload; fall back to data.componentType
        raw_type = (raw.get("data") or {}).get("component_type") or raw.get("data", {}).get("type") or ""
    resolved = normalize_type(str(raw_type))
    if resolved is None:
        raise ParseError(f"unknown component type: {raw_type!r}")
    if strict and resolved not in COMPONENT_REGISTRY:
        raise ParseError(f"unknown component type in strict mode: {resolved!r}")

    children_raw = raw.get("children", [])
    if not isinstance(children_raw, list):
        raise ParseError(f"children of {resolved} must be a list")

    return Component(
        id=str(raw.get("id") or _new_id(resolved)),
        type=resolved,
        content=_coerce_content(raw.get("content", {})),
        styles=raw.get("styles", {}) if isinstance(raw.get("styles", {}), dict) else {},
        children=[_coerce_component(c, strict=strict) for c in children_raw],
    )


def _tree_from_flat(items: list[dict[str, Any]], *, strict: bool) -> CanvasState:
    """Legacy flat array -> tree. Non-container types are attached to a page root."""
    components: list[Component] = []
    for i, item in enumerate(items):
        if isinstance(item, str):  # tolerate ["text"] palette-like inputs
            item = {"type": item, "content": {"text": item.title()}}
        if not isinstance(item, dict):
            raise ParseError(f"flat item #{i} must be an object")
        try:
            components.append(_coerce_component(item, strict=strict))
        except ParseError as exc:
            raise ParseError(f"flat item #{i}: {exc}") from exc

    root = Component(
        id="root",
        type="page",
        content={},
        styles=dict(COMPONENT_REGISTRY["page"]["styles"]),
        children=components,
    )
    return CanvasState(version=1, root=root)


def _tree_from_react_flow(payload: dict[str, Any], *, strict: bool) -> CanvasState:
    """{nodes, edges} -> tree. Edges form parent->child; roots attach to `page`."""
    if not isinstance(payload.get("nodes"), list):
        raise ParseError("React Flow input requires a 'nodes' list")

    nodes: list[Component] = []
    for i, node in enumerate(payload["nodes"]):
        if not isinstance(node, dict):
            raise ParseError(f"node #{i} must be an object")
        data = node.get("data") or {}
        flat = {
            "id": node.get("id") or data.get("id") or _new_id(),
            "type": data.get("component_type") or node.get("type") or "text",
            "content": data.get("content") or data.get("props") or {},
            "styles": data.get("styles") or {},
        }
        try:
            nodes.append(_coerce_component(flat, strict=strict))
        except ParseError as exc:
            raise ParseError(f"node #{i}: {exc}") from exc

    children: dict[str, list[str]] = {}
    for edge in payload.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        if edge.get("source") and edge.get("target"):
            children.setdefault(edge["source"], []).append(edge["target"])

    by_id = {n.id: n for n in nodes}
    root = Component(id="root", type="page", content={}, styles=dict(COMPONENT_REGISTRY["page"]["styles"]))
    completed: set[str] = set()

    def attach(parent: Component, node_id: str) -> None:
        if node_id in completed:
            return
        node = by_id.get(node_id)
        if node is None:
            return
        for child_id in children.get(node_id, []):
            attach(node, child_id)
        parent.children.append(node)
        completed.add(node_id)

    for node in nodes:
        if node.id in completed:
            continue
        attach(root, node.id)
    return CanvasState(version=1, root=root)


def parse_canvas(raw: Any, *, strict: bool = False, name: str | None = None) -> ParseResult:
    """Parse any supported shape into a CanvasState.

    Returns ParseResult with `.errors` (fatal, no canvas) or `.warnings` (non-fatal).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if raw is None:
        errors.append("empty canvas input")
        return ParseResult(None, errors, warnings)

    if isinstance(raw, list):
        try:
            canvas = _tree_from_flat(raw, strict=strict)
        except ParseError as exc:
            errors.append(str(exc))
            return ParseResult(None, errors, warnings)
    elif isinstance(raw, dict):
        if "nodes" in raw or "edges" in raw:
            try:
                canvas = _tree_from_react_flow(raw, strict=strict)
            except ParseError as exc:
                errors.append(str(exc))
                return ParseResult(None, errors, warnings)
        elif "root" in raw:
            try:
                root = _coerce_component(raw["root"], strict=strict)
                meta_raw = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
                if isinstance(meta_raw, dict):
                    warn = meta_raw.pop("_warnings", None)
                    if warn:
                        warnings.extend(str(w) for w in warn)
                try:
                    meta = CanvasMeta(**meta_raw)
                except ValidationError as exc:
                    errors.append(f"invalid meta: {exc}")
                    return ParseResult(None, errors, warnings)
                canvas = CanvasState(
                    version=int(raw.get("version", 1)) or 1,
                    id=str(raw.get("id", "studio")),
                    meta=meta,
                    root=root,
                )
                if name:
                    canvas.meta.name = name
            except (ParseError, ValueError, ValidationError) as exc:
                errors.append(f"invalid canvas: {exc}")
                return ParseResult(None, errors, warnings)
        else:
            errors.append("canvas object must contain 'root', 'nodes', or be a list")
            return ParseResult(None, errors, warnings)
    else:
        errors.append(f"unsupported input type: {type(raw).__name__}")
        return ParseResult(None, errors, warnings)

    try:
        warnings.extend(canvas.validate_against_registry())
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"registry validation failed: {exc}")

    # Normalize: dedupe ids, enforce container children, stable ordering.
    _normalize_tree(canvas.root, warnings)
    return ParseResult(canvas, errors, warnings)


def _normalize_tree(comp: Component, warnings: list[str]) -> None:
    seen: set[str] = set()

    def walk(node: Component) -> None:
        if node.id in seen:
            old = node.id
            node.id = _new_id(node.type)
            warnings.append(f"duplicate id '{old}' -> '{node.id}'")
        seen.add(node.id)
        if node.type in COMPONENT_REGISTRY:
            spec = COMPONENT_REGISTRY[node.type]
            if not isinstance(node.content, dict) or not node.content:
                node.content = dict(spec["content"])
            if not node.styles:
                node.styles = dict(spec["styles"])
            if not is_container(node.type) and node.children:
                # leaf types cannot own children; hoist them to the parent
                for child in node.children:
                    warnings.append(f"leaf component '{node.id}' had children; dropped {child.id}")
                node.children = []
        for child in node.children:
            walk(child)

    walk(comp)


def parse_flat_legacy(items: list[dict[str, Any]]) -> CanvasState:
    """Convenience wrapper used by tests / migration scripts."""
    result = parse_canvas(items)
    if not result.ok:
        raise ParseError("; ".join(result.errors))
    return result.canvas  # type: ignore[return-value]


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def assert_safe_id(component_id: str) -> None:
    if not _SAFE_ID.match(component_id):
        raise ParseError(f"invalid component id: {component_id!r}")
