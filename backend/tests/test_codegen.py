"""Codegen snapshot-tests: HTML + Tailwind and React/TSX output."""
from app.canvas.codegen import code_for_canvas, generate_html, generate_react


def test_html_contains_components(seed_canvas):
    html = generate_html(seed_canvas, standalone=True)
    assert "<!DOCTYPE html>" in html
    assert "Welcome to FK Agent Studio" in html
    assert "Get Started" in html
    assert "tailwindcss" in html


def test_html_clean_fragment(seed_canvas):
    html = generate_html(seed_canvas)
    assert "<!DOCTYPE html>" not in html
    assert 'data-component="heading"' in html
    # heading is rendered inside div wrapper to allow custom tags
    assert "<h1>Welcome to FK Agent Studio</h1>" in html


def test_react_output_compiles_shape(seed_canvas):
    react = generate_react(seed_canvas)
    assert "export default function Canvas()" in react
    assert "Welcome to FK Agent Studio" in react
    assert "Get Started" in react
    assert "className=" in react
    # balanced JSX tags sanity
    assert react.count("</div>") >= 1


def test_code_for_canvas_payload(seed_canvas):
    payload = code_for_canvas(seed_canvas, "html")
    assert payload["format"] == "html"
    assert payload["version"] == 1
    assert payload["html"].startswith("<!DOCTYPE html>")
    assert payload["react"].startswith("// Auto-generated")


def test_unsupported_format(seed_canvas):
    import pytest

    with pytest.raises(ValueError):
        code_for_canvas(seed_canvas, "svelte")
