from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class UnsupportedRichContent(ValueError):
    pass


@dataclass(frozen=True)
class AdaptedParagraph:
    locator: str
    nodes: tuple[dict, ...]


def _styled_text_node(text: str, properties: Mapping[str, str]) -> dict:
    node: dict = {"type": "text", "text": text}
    wrappers: list[str] = []
    if properties.get("b", "false") not in {"false", "0", "none"}:
        wrappers.append("bold")
    if properties.get("i", "false") not in {"false", "0", "none"}:
        wrappers.append("italic")
    if properties.get("u", "none") not in {"none", "false", "0"}:
        wrappers.append("underline")
    if properties.get("em", "none") not in {"none", "false", "0"}:
        wrappers.append("emphasis_dot")
    for kind in wrappers:
        node = {"type": kind, "children": [node]}
    return node


def adapt_paragraph_block(block: Mapping[str, object]) -> AdaptedParagraph:
    """Convert only content we can preserve exactly; fail closed on rich unknowns."""
    if block.get("kind") != "p":
        raise UnsupportedRichContent(
            f"{block.get('locator', '?')}: non-paragraph block requires dedicated adapter"
        )
    if block.get("math_omml"):
        raise UnsupportedRichContent(
            f"{block.get('locator', '?')}: OMML conversion not verified"
        )
    if any(block.get("image_relationships") or []):
        raise UnsupportedRichContent(
            f"{block.get('locator', '?')}: image placement conversion not verified"
        )

    nodes: list[dict] = []
    for run in block.get("runs") or []:
        text = str(run.get("text") or "")
        if not text:
            continue
        nodes.append(_styled_text_node(text, run.get("properties") or {}))
    return AdaptedParagraph(str(block.get("locator") or ""), tuple(nodes))
