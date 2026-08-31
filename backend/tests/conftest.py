"""Shared fixtures for backend tests."""
import os
import sys
from pathlib import Path

# Force in-memory SaaS store before `main` is imported.
os.environ.setdefault("SAAS_DATA_DIR", ":memory:")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.canvas.parser import parse_canvas


@pytest.fixture
def seed_canvas():
    """Default seed: hero + button (mirrors the original starter modules)."""
    parsed = parse_canvas(
        {
            "version": 1,
            "id": "studio",
            "meta": {"name": "Test Canvas"},
            "root": {
                "id": "root",
                "type": "page",
                "content": {},
                "styles": {"tailwind": "min-h-screen bg-slate-950 text-slate-100"},
                "children": [
                    {"id": "c1", "type": "heading", "content": {"text": "Welcome to FK Agent Studio", "level": "h1"}},
                    {"id": "c2", "type": "button", "content": {"text": "Get Started"}},
                ],
            },
        }
    )
    assert parsed.ok, parsed.errors
    return parsed.canvas
