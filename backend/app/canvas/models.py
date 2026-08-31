"""Canonical JSON canvas tree model (the dynamic state tree)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .registry import COMPONENT_REGISTRY, is_container


class Component(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    type: str
    content: dict[str, Any] = Field(default_factory=dict)
    styles: dict[str, Any] = Field(default_factory=dict)
    children: list["Component"] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "styles": self.styles,
        }
        if self.children:
            data["children"] = [c.to_dict() for c in self.children]
        return data


class CanvasMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "Untitled Canvas"
    theme: str = "dark"
    updated_at: str | None = None
    updated_by: str | None = None


class CanvasState(BaseModel):
    """Single source of truth for a canvas. `version` drives client reconciliation."""

    model_config = ConfigDict(extra="ignore")

    version: int = 1
    id: str = "studio"
    meta: CanvasMeta = Field(default_factory=CanvasMeta)
    root: Component

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "meta": self.meta.model_dump(),
            "root": self.root.to_dict(),
        }

    def validate_against_registry(self, strict: bool = False) -> list[str]:
        """Structural checks against the component registry. Returns non-fatal warnings."""
        warnings: list[str] = []

        def walk(comp: Component) -> None:
            if comp.type not in COMPONENT_REGISTRY:
                warnings.append(f"Unknown component type '{comp.type}' ({comp.id})")
            elif is_container(comp.type) and not comp.children and comp.type != "page":
                warnings.append(f"Container '{comp.type}' ({comp.id}) has no children")
            for child in comp.children:
                walk(child)

        walk(self.root)
        return warnings
