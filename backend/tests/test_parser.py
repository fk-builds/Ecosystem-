"""Canvas parser tests: canonical, legacy flat, React Flow, normalization, errors."""
import pytest

from app.canvas.parser import ParseError, parse_canvas, parse_flat_legacy


def test_parse_canonical_roundtrip():
    raw = {
        "version": 2,
        "meta": {"name": "Landing"},
        "root": {
            "id": "root", "type": "page", "content": {},
            "children": [
                {"id": "a", "type": "heading", "content": {"text": "Hi", "level": "h1"}},
                {"id": "b", "type": "section", "content": {}, "children": [
                    {"id": "c", "type": "text", "content": {"text": "Body"}},
                ]},
            ],
        },
    }
    parsed = parse_canvas(raw)
    assert parsed.ok and parsed.canvas is not None
    canvas = parsed.canvas
    assert canvas.version == 2
    assert canvas.meta.name == "Landing"
    assert [c.id for c in canvas.root.children] == ["a", "b"]
    assert canvas.root.children[1].children[0].type == "text"
    assert canvas.to_dict()["root"]["type"] == "page"
    assert parsed.warnings == []


def test_parse_legacy_flat_array():
    """Original Builder Studio format: [{id, type, content: str}]."""
    legacy = [
        {"id": "c1", "type": "header", "content": "Welcome to FK Agent Studio"},
        {"id": "c2", "type": "button", "content": "Get Started"},
    ]
    canvas = parse_flat_legacy(legacy)
    first, second = canvas.root.children
    assert first.type == "hero"  # legacy "header" maps to hero
    assert first.content == {"text": "Welcome to FK Agent Studio"}
    assert second.type == "button"


def test_parse_react_flow_shape():
    payload = {
        "nodes": [
            {"id": "n1", "type": "custom", "data": {"component_type": "hero", "content": {"heading": "RF"}}},
            {"id": "n2", "type": "custom", "data": {"component_type": "text", "content": {"text": "desc"}}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    parsed = parse_canvas(payload)
    assert parsed.ok and parsed.canvas is not None
    assert parsed.canvas.root.children[0].type == "hero"
    assert parsed.canvas.root.children[0].children[0].type == "text"


def test_unknown_type_rejected():
    parsed = parse_canvas({"root": {"id": "r", "type": "wat", "content": {}}})
    assert not parsed.ok
    assert any("unknown component type" in e for e in parsed.errors)


def test_duplicate_ids_normalized():
    parsed = parse_canvas(
        {
            "root": {
                "id": "root", "type": "page", "content": {},
                "children": [
                    {"id": "dup", "type": "text", "content": {"text": "one"}},
                    {"id": "dup", "type": "text", "content": {"text": "two"}},
                ],
            }
        }
    )
    assert parsed.ok and parsed.canvas is not None
    ids = [c.id for c in parsed.canvas.root.children]
    assert len(set(ids)) == 2
    assert any("duplicate id" in w for w in parsed.warnings)


def test_leaf_children_hoisted_to_parent():
    parsed = parse_canvas(
        {
            "root": {
                "id": "root", "type": "page", "content": {},
                "children": [
                    {"id": "leaf", "type": "button", "content": {"text": "x"}, "children": [
                        {"id": "kid", "type": "text", "content": {"text": "y"}},
                    ]},
                ],
            }
        }
    )
    assert parsed.ok and parsed.canvas is not None
    leaf = parsed.canvas.root.children[0]
    assert leaf.type == "button" and leaf.children == []
    assert any("dropped" in w for w in parsed.warnings)


def test_garbage_inputs():
    for bad in [None, 42, "nope", {"foo": 1}]:
        parsed = parse_canvas(bad)
        assert not parsed.ok, bad


def test_ids_are_optional_and_generated():
    """Ids may be omitted; parser generates safe ones."""
    parsed = parse_canvas({"root": {"id": "root", "type": "page", "content": {}, "children": [
        {"type": "text", "content": {"text": "no id"}},
    ]}})
    assert parsed.ok and parsed.canvas is not None
    assert parsed.canvas.root.children[0].id.startswith("text-")
