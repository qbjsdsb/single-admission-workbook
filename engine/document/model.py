from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


DOCUMENT_AST_VERSION = 1


@dataclass(frozen=True)
class DocumentAst:
    source_format: str
    blocks: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": DOCUMENT_AST_VERSION,
            "source_format": self.source_format,
            "blocks": list(self.blocks),
            "warnings": list(self.warnings),
        }


def text_node(text: str, styles: Iterable[str] = ()) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    styles = tuple(dict.fromkeys(styles))
    if styles:
        node["styles"] = list(styles)
    return node


def paragraph_block(
    locator: str,
    inlines: Iterable[dict[str, Any]],
    *,
    page: int | None = None,
    bbox: Iterable[float] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "paragraph",
        "locator": locator,
        "inlines": list(inlines),
    }
    if page is not None:
        block["page"] = page
    if bbox is not None:
        block["bbox"] = [float(x) for x in bbox]
    return block


def unsupported_block(
    locator: str,
    feature: str,
    *,
    raw: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "unsupported",
        "locator": locator,
        "feature": feature,
    }
    if raw is not None:
        block["raw"] = raw
    if page is not None:
        block["page"] = page
    return block
