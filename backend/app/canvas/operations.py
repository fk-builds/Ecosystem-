"""Pure, atomic canvas operations.

Every mutation goes through `apply_operations`, which deep-copies the state and
validates the whole op list before committing. A single invalid op rejects the
entire batch — no partial mutation, so clients can safely retry.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import CanvasState, Component
from .parser import ParseError, _coerce_component, assert_safe_id
from .registry import default_component, is_container, normalize_type


class OpError(Exception):
    pass


def _safe_id(component_id: str) -> str:
    try:
        assert_safe_id(component_id)
    except ParseError as exc:
        raise OpError(str(exc)) from exc
    return component_id


@dataclass
class OpResult:
    canvas: CanvasState
    commits: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def find(comp: Component, comp_id: str) -> Component | None:
    """Find a component by id anywhere in the tree."""
    if comp.id == comp_id:
        return comp
    for child in comp.children:
        found = find(child, comp_id)
        if found:
            return found
    return None


def parent_children_of(comp: Component, comp_id: str) -> list[Component] | None:
    """Return the children list that directly holds comp_id, or None if comp_id is the root."""
    for child in comp.children:
        if child.id == comp_id:
            return comp.children
        found = parent_children_of(child, comp_id)
        if found is not None:
            return found
    return None


def contains(comp: Component, comp_id: str) -> bool:
    """True when comp_id exists anywhere inside comp (including comp itself)."""
    if comp.id == comp_id:
        return True
    return any(contains(child, comp_id) for child in comp.children)


def _short_id(raw: dict[str, Any], version: int) -> str:
    digest = hashlib.sha1(f"{version}|{raw}".encode()).hexdigest()[:6]
    return digest


def _materialize(resolved: str, raw: dict[str, Any], comp_id: str) -> Component:
    """Build a component, filling in registry defaults for anything not supplied."""
    base = default_component(resolved, comp_id)

    content_raw = raw.get("content", {})
    if isinstance(content_raw, str):
        content = {**base["content"], "text": content_raw}
    elif isinstance(content_raw, dict):
        content = {**base["content"], **content_raw}
    else:
        content = base["content"]

    styles_raw = raw.get("styles", {})
    styles = {**base["styles"], **(styles_raw if isinstance(styles_raw, dict) else {})}

    children = []
    for child in raw.get("children", []) or []:
        if isinstance(child, dict) and child.get("type"):
            child_resolved = normalize_type(str(child["type"]))
            if child_resolved is None:
                raise OpError(f"unknown child type '{child['type']}'")
            child_id = child.get("id") or f"{child_resolved}-{_short_id(child, comp_id)}"
            children.append(_materialize(child_resolved, child, child_id))
        else:
            raise OpError("children must be component objects")

    return Component(
        id=comp_id,
        type=resolved,
        content=content,
        styles=styles,
        children=children,
    )


def apply_operations(canvas: CanvasState, operations: list[dict[str, Any]]) -> OpResult:
    """Apply an op list atomically. Returns a new CanvasState (never mutates input)."""
    if not isinstance(operations, list) or not operations:
        return OpResult(canvas, [], None)
    try:
        working = _clone(canvas)
        commits: list[dict[str, Any]] = []
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                raise OpError(f"op #{i} must be an object")
            commits.append(_apply_op(working, op))
        working.version = (canvas.version or 0) + 1
        working.meta.updated_at = datetime.now(timezone.utc).isoformat()
        return OpResult(working, commits, None)
    except OpError as exc:
        # Atomic: never return a partially-modified state.
        return OpResult(canvas, [], str(exc))


def _clone(canvas: CanvasState) -> CanvasState:
    return copy.deepcopy(canvas)


def _apply_op(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    kind = str(op.get("op", "")).lower()
    handler = _HANDLERS.get(kind)
    if handler is None:
        raise OpError(f"unknown op '{kind}'")
    return handler(canvas, op)


def _op_add(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    raw = op.get("component") or {}
    parent_id = str(op.get("parent_id", "root"))
    index = op.get("index")

    if isinstance(raw, str):  # agent ergonomics: {"op":"add","component":"hero"}
        raw = {"type": raw}
    if not isinstance(raw, dict) or not raw.get("type"):
        raise OpError("add op requires component.type")

    resolved = normalize_type(str(raw["type"]))
    if resolved is None:
        raise OpError(f"unknown component type '{raw['type']}'")

    comp_id = str(raw.get("id") or op.get("id") or f"{resolved}-{_short_id(raw, canvas.version)}")
    _safe_id(comp_id)
    if find(canvas.root, comp_id) is not None:
        raise OpError(f"component id '{comp_id}' already exists")

    new_comp = _materialize(resolved, raw, comp_id)
    _validate_parent(canvas.root, parent_id, new_comp.id)

    parent = find(canvas.root, parent_id)
    assert parent is not None
    if index is None:
        parent.children.append(new_comp)
    else:
        parent.children.insert(max(0, min(int(index), len(parent.children))), new_comp)
    return {"op": "add", "id": new_comp.id, "parent_id": parent_id, "index": index}


def _validate_parent(comp: Component, parent_id: str, new_id: str) -> None:
    parent = find(comp, parent_id)
    if parent is None:
        raise OpError(f"parent '{parent_id}' not found")
    if not is_container(parent.type):
        raise OpError(f"component '{parent_id}' of type '{parent.type}' cannot hold children")
    if new_id == parent_id:
        raise OpError("a component cannot be its own parent")


def _op_update(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    comp_id = str(op.get("id", ""))
    _safe_id(comp_id)
    comp = find(canvas.root, comp_id)
    if comp is None:
        raise OpError(f"component '{comp_id}' not found")

    patch = op.get("patch") or {}
    if not isinstance(patch, dict):
        raise OpError("update op requires a patch object")
    merge = bool(op.get("merge", True))

    if "content" in patch:
        merged = dict(comp.content) if merge else {}
        if isinstance(patch["content"], dict):
            merged.update(patch["content"])
        elif isinstance(patch["content"], str):
            merged["text"] = patch["content"]
        comp.content = merged
    if "styles" in patch:
        merged = dict(comp.styles) if merge else {}
        if isinstance(patch["styles"], dict):
            merged.update(patch["styles"])
        comp.styles = merged
    if "type" in patch:
        resolved = normalize_type(str(patch["type"]))
        if resolved is None:
            raise OpError(f"cannot change type to unknown '{patch['type']}'")
        comp.type = resolved
    return {"op": "update", "id": comp_id}


def _op_remove(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    comp_id = str(op.get("id", ""))
    _safe_id(comp_id)
    if canvas.root.id == comp_id:
        raise OpError("cannot remove the page root")
    comp = find(canvas.root, comp_id)
    siblings = parent_children_of(canvas.root, comp_id)
    if comp is None or siblings is None:
        raise OpError(f"component '{comp_id}' not found")
    siblings.remove(comp)
    return {"op": "remove", "id": comp_id}


def _op_move(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    comp_id = str(op.get("id", ""))
    parent_id = str(op.get("parent_id", "root"))
    index = op.get("index")
    _safe_id(comp_id)

    if canvas.root.id == comp_id:
        raise OpError("cannot move the page root")
    comp = find(canvas.root, comp_id)
    siblings = parent_children_of(canvas.root, comp_id)
    if comp is None or siblings is None:
        raise OpError(f"component '{comp_id}' not found")
    _validate_parent(canvas.root, parent_id, comp_id)

    # Reject moving a component into its own subtree (would create a cycle).
    destination = find(canvas.root, parent_id)
    assert destination is not None
    if contains(destination, comp_id):
        raise OpError("cannot move a component into its own subtree")

    siblings.remove(comp)
    if index is None:
        destination.children.append(comp)
    else:
        destination.children.insert(max(0, min(int(index), len(destination.children))), comp)
    return {"op": "move", "id": comp_id, "parent_id": parent_id, "index": index}


def _op_replace(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    comp_id = str(op.get("id", ""))
    _safe_id(comp_id)
    comp = find(canvas.root, comp_id)
    parent_children = parent_children_of(canvas.root, comp_id)
    if comp is None or parent_children is None:
        raise OpError(f"component '{comp_id}' not found")
    replacement = _materialize(normalize_type(str((op.get("component") or {}).get("type", "text"))), op.get("component") or {}, comp_id)
    parent_children[parent_children.index(comp)] = replacement
    return {"op": "replace", "id": comp_id, "type": replacement.type}


def _op_set_meta(canvas: CanvasState, op: dict[str, Any]) -> dict[str, Any]:
    patch = op.get("patch") or {}
    if not isinstance(patch, dict):
        raise OpError("set_meta requires a patch object")
    for key, value in patch.items():
        if hasattr(canvas.meta, key):
            setattr(canvas.meta, key, value)
    return {"op": "set_meta", "id": "meta"}


_HANDLERS = {
    "add": _op_add,
    "update": _op_update,
    "remove": _op_remove,
    "delete": _op_remove,
    "move": _op_move,
    "replace": _op_replace,
    "set_meta": _op_set_meta,
}


def apply_ops_or_raise(canvas: CanvasState, operations: list[dict[str, Any]]) -> CanvasState:
    result = apply_operations(canvas, operations)
    if not result.ok:
        raise OpError(result.error or "unknown error")
    return result.canvas
