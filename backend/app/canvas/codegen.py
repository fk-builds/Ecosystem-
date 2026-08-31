"""On-the-fly code generator.

Given a canvas JSON tree emit:
  - HTML + Tailwind CSS (self-contained, iframe-previewable)
  - React/TSX component (typed props, data model)

Generation is pure and deterministic — no I/O, safe to call on every mutation.
"""
from __future__ import annotations

import html as html_mod
from typing import Any

from .models import CanvasState
from .registry import COMPONENT_REGISTRY

TAG_BY_TYPE: dict[str, str] = {
    "page": "div",
    "section": "section",
    "nav": "nav",
    "hero": "section",
    "heading": "h1",
    "text": "p",
    "button": "a",
    "image": "img",
    "card": "div",
    "input": "input",
    "form": "form",
    "grid": "div",
    "divider": "hr",
    "footer": "footer",
}

SELF_CLOSING = {"image", "input", "divider"}


def _esc(value: Any) -> str:
    return html_mod.escape(str(value), quote=True)


def _tag_for(comp: dict[str, Any]) -> str:
    tag = TAG_BY_TYPE.get(comp["type"])
    if tag:
        return tag
    if comp["type"] == "heading":
        level = str(comp.get("content", {}).get("level", "h1")).lower()
        return level if level in {"h1", "h2", "h3", "h4", "h5", "h6"} else "h1"
    return "div"


def _class_attr(comp: dict[str, Any], extra: str = "") -> str:
    parts = [comp.get("styles", {}).get("tailwind", "")]
    if extra:
        parts.append(extra)
    return " ".join(p for p in parts if p)


def _render_html_component(comp: dict[str, Any], depth: int = 0) -> str:
    tag = _tag_for(comp)
    ctype = comp["type"]
    content = comp.get("content", {})
    children_html = "\n".join(_render_html_component(c, depth + 1) for c in comp.get("children", []))

    inner: list[str] = []
    if ctype == "hero":
        if content.get("heading"):
            inner.append(f'<h1 class="text-5xl font-extrabold tracking-tight">{_esc(content["heading"])}</h1>')
        if content.get("subheading"):
            inner.append(f'<p class="max-w-xl text-lg text-slate-400">{_esc(content["subheading"])}</p>')
        if content.get("cta"):
            inner.append(
                f'<a href="#" class="mt-2 rounded-lg bg-emerald-500 px-6 py-3 font-semibold text-slate-950 hover:bg-emerald-400">{_esc(content["cta"])}</a>'
            )
    elif ctype == "nav":
        brand = content.get("brand", "My Product")
        inner.append(f'<span class="text-lg font-bold">{_esc(brand)}</span>')
        links = content.get("links", [])
        if isinstance(links, list):
            items = "".join(f'<a href="#" class="text-sm text-slate-400 hover:text-white">{_esc(l)}</a>' for l in links)
        else:
            items = ""
        inner.append(f'<nav class="flex gap-6">{items}</nav>')
    elif ctype == "heading":
        level = str(content.get("level", "h1")).lower()
        if level not in {"h1", "h2", "h3"}:
            level = "h1"
        inner.append(f'<{level}>{_esc(content.get("text", ""))}</{level}>')
        tag = "div"  # heading already rendered
    elif ctype == "text":
        inner.append(_esc(content.get("text", "")))
    elif ctype == "button":
        inner.append(_esc(content.get("text", "Button")))
    elif ctype == "card":
        if content.get("title"):
            inner.append(f'<h3 class="text-lg font-semibold">{_esc(content["title"])}</h3>')
        if content.get("text"):
            inner.append(f'<p class="text-sm text-slate-400">{_esc(content["text"])}</p>')
    elif ctype == "input":
        if content.get("label"):
            inner.append(f'<label class="text-xs text-slate-400 uppercase">{_esc(content["label"])}</label>')
    elif ctype == "form":
        inner.append('<div class="flex flex-col gap-3">')
        inner.append('<label class="text-xs text-slate-400">Email</label>')
        inner.append('<input type="email" placeholder="you@example.com" class="rounded-lg border border-slate-700 bg-slate-950 px-4 py-2" />')
        inner.append('<button type="submit" class="rounded-lg bg-emerald-500 px-4 py-2 font-semibold text-slate-950">Submit</button>')
        inner.append("</div>")
    elif ctype == "footer":
        inner.append(_esc(content.get("text", "")))
    else:
        inner.append(children_html)

    if not inner and not SELF_CLOSING.__contains__(ctype):
        inner.append(children_html)

    classes = _class_attr(comp)
    if ctype == "grid" and "grid-cols" not in classes:
        columns = max(1, min(int(content.get("columns", 2) or 2), 4))
        classes = f"{classes} md:grid-cols-{columns}".strip()

    id_attr = f' id="{_esc(comp["id"])}"' if comp.get("id") else ""
    type_attr = f' data-component="{_esc(ctype)}"'

    if ctype in SELF_CLOSING:
        return f'<{tag}{id_attr}{type_attr} class="{_esc(classes)}" />'

    body = "\n".join(inner)
    indent = "  " * depth
    return f'<{tag}{id_attr}{type_attr} class="{_esc(classes)}">\n{indent}  {body}\n{indent}</{tag}>'


def generate_html(canvas: CanvasState, *, standalone: bool = False) -> str:
    """Generate Tailwind HTML for a canvas. `standalone` wraps it in a preview page."""
    body = _render_html_component(canvas.root.to_dict())
    if not standalone:
        return body
    meta = canvas.meta
    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(meta.name)}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>body{{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}}</style>
</head>
<body class="bg-slate-950 text-slate-100 antialiased">
{body}
</body>
</html>
"""


# ── React / TSX generator ─────────────────────────────────────────────

REACT_IMPORTS = """import type { CSSProperties, ReactNode } from "react";

export interface CanvasComponentProps {
  id?: string;
  data: Record<string, unknown>;
  styles?: Record<string, string | number>;
  children?: ReactNode;
}
"""

_JSX_ESCAPES = str.maketrans(
    {
        "{": "{\"{\"}",
        "}": "{\"}\"}",
        "<": "{'<'}",  # handled separately below
    }
)


def _jsx_text(value: Any) -> str:
    s = str(value)
    s = s.replace("&", "&amp;").replace("<", "{'<'}").replace(">", "{'>'}")
    s = s.replace("{", "{\"{\"}").replace("}", "{\"}\"}")
    return s


def _jsx_attr(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _jsx_component(comp: dict[str, Any], depth: int) -> str:
    """Emit a static TSX component from the canvas tree (literal content)."""
    indent = "  " * depth
    ctype = comp["type"]
    content = comp.get("content", {})
    cls = comp.get("styles", {}).get("tailwind", "")
    children = "\n".join(_jsx_component(c, depth + 1) for c in comp.get("children", []))
    id_attr = f' id="{_jsx_attr(comp["id"])}"' if comp.get("id") else ""
    class_attr = f' className="{_jsx_attr(cls)}"' if cls else ""

    if ctype == "page":
        return f'{indent}<div{id_attr}{class_attr}>\n{children}\n{indent}</div>'

    if ctype == "hero":
        parts: list[str] = []
        if content.get("heading"):
            parts.append(f'{indent}  <h1 className="text-5xl font-extrabold tracking-tight">{_jsx_text(content["heading"])}</h1>')
        if content.get("subheading"):
            parts.append(f'{indent}  <p className="max-w-xl text-lg text-slate-400">{_jsx_text(content["subheading"])}</p>')
        if content.get("cta"):
            parts.append(f'{indent}  <a href="#" className="mt-2 rounded-lg bg-emerald-500 px-6 py-3 font-semibold text-slate-950 hover:bg-emerald-400">{_jsx_text(content["cta"])}</a>')
        parts.append(children)
        body = "\n".join(p for p in parts if p)
        return f'{indent}<section{id_attr}{class_attr}>\n{body}\n{indent}</section>'

    if ctype == "heading":
        level = str(content.get("level", "h1")).lower()
        level = level if level in {"h1", "h2", "h3"} else "h1"
        return f'{indent}<{level}{id_attr}{class_attr}>{_jsx_text(content.get("text", ""))}</{level}>'

    if ctype == "text":
        return f'{indent}<p{id_attr}{class_attr}>{_jsx_text(content.get("text", ""))}</p>'

    if ctype == "button":
        href = _jsx_attr(content.get("href", "#"))
        return f'{indent}<a href="{href}"{id_attr}{class_attr}>{_jsx_text(content.get("text", "Button"))}</a>'

    if ctype == "image":
        src = _jsx_attr(content.get("src", ""))
        alt = _jsx_attr(content.get("alt", ""))
        return f'{indent}<img src="{src}" alt="{alt}"{id_attr}{class_attr} />'

    if ctype == "input":
        label = ""
        if content.get("label"):
            label = f'\n{indent}  <label className="text-xs text-slate-400 uppercase">{_jsx_text(content["label"])}</label>'
        placeholder = _jsx_attr(content.get("placeholder", ""))
        return f'{indent}<div>{label}\n{indent}  <input type="text" placeholder="{placeholder}"{class_attr} />\n{indent}</div>'

    if ctype == "card":
        parts = []
        if content.get("title"):
            parts.append(f'{indent}  <h3 className="text-lg font-semibold">{_jsx_text(content["title"])}</h3>')
        if content.get("text"):
            parts.append(f'{indent}  <p className="text-sm text-slate-400">{_jsx_text(content["text"])}</p>')
        parts.append(children)
        body = "\n".join(p for p in parts if p)
        return f'{indent}<div{id_attr}{class_attr}>\n{body}\n{indent}</div>'

    if ctype == "nav":
        links = ""
        raw_links = content.get("links", [])
        if isinstance(raw_links, list) and raw_links:
            items = "\n".join(
                f'{indent}    <a href="#" className="text-sm text-slate-400 hover:text-white">{_jsx_text(l)}</a>'
                for l in raw_links
            )
            links = f'\n{indent}  <div className="flex gap-6">\n{items}\n{indent}  </div>'
        return (
            f'{indent}<nav{id_attr}{class_attr}>\n'
            f'{indent}  <span className="text-lg font-bold">{_jsx_text(content.get("brand", "My Product"))}</span>'
            f'{links}\n{indent}</nav>'
        )

    if ctype == "form":
        return (
            f'{indent}<form{id_attr}{class_attr}>\n'
            f'{indent}  <label className="text-xs text-slate-400 uppercase">Email</label>\n'
            f'{indent}  <input type="email" placeholder="you@example.com" className="rounded-lg border border-slate-700 bg-slate-950 px-4 py-2" />\n'
            f'{indent}  <button type="submit" className="rounded-lg bg-emerald-500 px-4 py-2 font-semibold text-slate-950">Submit</button>\n'
            f'{indent}</form>'
        )

    if ctype == "grid":
        columns = max(1, min(int(content.get("columns", 2) or 2), 4))
        if "md:grid-cols-" not in cls:
            cls = f"{cls} md:grid-cols-{columns}".strip()
        return f'{indent}<div{id_attr} className="{_jsx_attr(cls)}">\n{children}\n{indent}</div>'

    if ctype == "divider":
        return f'{indent}<hr{id_attr}{class_attr} />'

    if ctype == "footer":
        return f'{indent}<footer{id_attr}{class_attr}>{_jsx_text(content.get("text", ""))}</footer>'

    if ctype == "section":
        return f'{indent}<section{id_attr}{class_attr}>\n{children}\n{indent}</section>'

    return f'{indent}<div{id_attr}{class_attr}>\n{children}\n{indent}</div>'


def generate_react(canvas: CanvasState) -> str:
    """Generate a typed React + Tailwind component from the canvas tree."""
    root = canvas.root.to_dict()
    body = _jsx_component(root, 0)
    return f"""// Auto-generated by FK AI Builder — {canvas.meta.name}
// Edit visually in Builder Studio; this file is regenerated on every change.

{REACT_IMPORTS}

export default function Canvas() {{
  return (
{body}
  );
}}
"""


def code_for_canvas(canvas: CanvasState, fmt: str = "html") -> dict[str, Any]:
    """Public codegen endpoint payload."""
    fmt = fmt.lower()
    if fmt not in {"html", "react", "tsx"}:
        raise ValueError(f"unsupported format '{fmt}' (use html|react|tsx)")
    return {
        "format": "html" if fmt == "html" else "react",
        "html": generate_html(canvas, standalone=True),
        "react": generate_react(canvas),
        "version": canvas.version,
    }
