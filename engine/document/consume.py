from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LocatedParagraph:
    locator: str
    text: str
    inlines: tuple[dict, ...]
    page: int | None = None


@dataclass(frozen=True)
class DocumentTextView:
    paragraphs: tuple[LocatedParagraph, ...]
    blockers: tuple[str, ...]


class DocumentNormalizationRequired(ValueError):
    def __init__(self, blockers):
        self.blockers = tuple(blockers)
        super().__init__(
            "document contains content that is not safe for question segmentation: "
            + "; ".join(self.blockers)
        )


def segmentation_view(document: Mapping[str, object]) -> DocumentTextView:
    paragraphs: list[LocatedParagraph] = []
    blockers: list[str] = []

    if document.get("version") != 1:
        blockers.append(f"unsupported_document_ast_version:{document.get('version')}")

    for block in document.get("blocks") or []:
        block_type = block.get("type")
        locator = str(block.get("locator") or "?")

        if block_type == "unsupported":
            blockers.append(f"{locator}:{block.get('feature', 'unsupported')}")
            continue
        if block_type != "paragraph":
            blockers.append(f"{locator}:unknown_block_type:{block_type}")
            continue

        text_parts: list[str] = []
        inlines = tuple(block.get("inlines") or [])
        for inline in inlines:
            kind = inline.get("type")
            if kind == "text":
                text_parts.append(str(inline.get("text") or ""))
            elif kind == "math_omml":
                blockers.append(f"{inline.get('locator', locator)}:math_omml")
            elif kind == "image_ref":
                blockers.append(f"{inline.get('locator', locator)}:image_ref")
            else:
                blockers.append(f"{locator}:unknown_inline_type:{kind}")

        text = "".join(text_parts).strip()
        if text:
            paragraphs.append(LocatedParagraph(
                locator=locator,
                text=text,
                inlines=inlines,
                page=block.get("page"),
            ))

    return DocumentTextView(
        paragraphs=tuple(paragraphs),
        blockers=tuple(sorted(set(blockers))),
    )


def safe_segmentation_paragraphs(document: Mapping[str, object]) -> tuple[LocatedParagraph, ...]:
    view = segmentation_view(document)
    if view.blockers:
        raise DocumentNormalizationRequired(view.blockers)
    return view.paragraphs
