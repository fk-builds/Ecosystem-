"""Component type registry: palette used by the UI and by the agent's canvas tools."""
from __future__ import annotations

from typing import Any

# type -> {label, default content, default styles, container?, content_fields}
COMPONENT_REGISTRY: dict[str, dict[str, Any]] = {
    "page": {
        "label": "Page",
        "container": True,
        "content": {},
        "styles": {
            "tailwind": "min-h-screen bg-slate-950 text-slate-100",
            "layout": "flex flex-col",
        },
    },
    "section": {
        "label": "Section",
        "container": True,
        "content": {},
        "styles": {
            "tailwind": "w-full px-6 py-12",
            "layout": "flex flex-col gap-6",
        },
    },
    "nav": {
        "label": "Navbar",
        "container": True,
        "content": {"brand": "My Product", "links": ["Home", "Features", "Pricing"]},
        "styles": {
            "tailwind": "flex items-center justify-between px-6 py-4 border-b border-slate-800",
            "layout": "flex items-center justify-between",
        },
    },
    "hero": {
        "label": "Hero",
        "container": True,
        "content": {
            "heading": "Build with AI",
            "subheading": "Design real-time interfaces, powered by an agent that writes to your canvas.",
            "cta": "Get Started",
        },
        "styles": {
            "tailwind": "flex flex-col items-center text-center gap-6 py-16",
            "layout": "flex flex-col items-center",
        },
    },
    "heading": {
        "label": "Heading",
        "content": {"text": "Section heading", "level": "h1"},
        "styles": {"tailwind": "text-4xl font-bold tracking-tight"},
    },
    "text": {
        "label": "Text",
        "content": {"text": "Write something useful here."},
        "styles": {"tailwind": "text-slate-400 leading-relaxed"},
    },
    "button": {
        "label": "Button",
        "content": {"text": "Get Started", "href": "#"},
        "styles": {"tailwind": "rounded-lg bg-emerald-500 px-5 py-2.5 font-semibold text-slate-950 hover:bg-emerald-400"},
    },
    "image": {
        "label": "Image",
        "content": {"src": "https://picsum.photos/seed/fkbuilder/800/450", "alt": "Preview image"},
        "styles": {"tailwind": "rounded-xl border border-slate-800 w-full"},
    },
    "card": {
        "label": "Card",
        "container": True,
        "content": {"title": "Feature", "text": "A short feature description."},
        "styles": {
            "tailwind": "rounded-xl border border-slate-800 bg-slate-900 p-5",
            "layout": "flex flex-col gap-2",
        },
    },
    "input": {
        "label": "Input",
        "content": {"placeholder": "you@example.com", "label": "Email"},
        "styles": {"tailwind": "rounded-lg border border-slate-700 bg-slate-900 px-4 py-2"},
    },
    "form": {
        "label": "Form",
        "container": True,
        "content": {"action": "#"},
        "styles": {"tailwind": "flex flex-col gap-3 rounded-xl border border-slate-800 p-5"},
    },
    "grid": {
        "label": "Grid",
        "container": True,
        "content": {"columns": 2},
        "styles": {
            "tailwind": "grid grid-cols-1 md:grid-cols-2 gap-4",
            "layout": "grid",
        },
    },
    "divider": {
        "label": "Divider",
        "content": {},
        "styles": {"tailwind": "border-t border-slate-800 my-4"},
    },
    "footer": {
        "label": "Footer",
        "container": True,
        "content": {"text": "© 2025 FK AI Builder"},
        "styles": {"tailwind": "border-t border-slate-800 px-6 py-8 text-sm text-slate-500"},
    },
}

# Agent-facing aliases so natural-language intents map to known types.
TYPE_ALIASES: dict[str, str] = {
    "section": "section",
    "hero": "hero",
    "landing": "hero",
    "header": "hero",
    "nav": "nav",
    "navbar": "nav",
    "heading": "heading",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "title": "heading",
    "text": "text",
    "paragraph": "text",
    "p": "text",
    "button": "button",
    "cta": "button",
    "image": "image",
    "img": "image",
    "picture": "image",
    "card": "card",
    "feature": "card",
    "input": "input",
    "form": "form",
    "grid": "grid",
    "columns": "grid",
    "divider": "divider",
    "hr": "divider",
    "footer": "footer",
}


def normalize_type(type_: str) -> str | None:
    """Resolve a (possibly aliased) component type to a registered type, or None."""
    key = str(type_).strip().lower()
    if key in COMPONENT_REGISTRY:
        return key
    return TYPE_ALIASES.get(key)


def is_container(type_: str) -> bool:
    return bool(COMPONENT_REGISTRY.get(type_, {}).get("container"))


def default_component(type_: str, component_id: str) -> dict[str, Any]:
    """Build a new component dict from registry defaults (deep-copied)."""
    import copy

    spec = COMPONENT_REGISTRY.get(type_)
    if spec is None:
        raise KeyError(f"Unknown component type: {type_}")
    return {
        "id": component_id,
        "type": type_,
        "content": copy.deepcopy(spec["content"]),
        "styles": copy.deepcopy(spec["styles"]),
        "children": [],
    }
