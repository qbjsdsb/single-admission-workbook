from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Mapping

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RICH_TAGS = {
    f"{{{W}}}drawing": "drawing",
    f"{{{W}}}object": "ole_object",
    f"{{{W}}}pict": "vml_drawing",
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath": "math_omml",
    "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara": "math_omml",
}


def _paragraph_text(paragraph: ET.Element) -> str:
    out: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{{{W}}}t":
            out.append(node.text or "")
        elif node.tag == f"{{{W}}}tab":
            out.append("\t")
        elif node.tag in {f"{{{W}}}br", f"{{{W}}}cr"}:
            out.append("\n")
    return "".join(out)


def parse_docx_table_xml(xml: str, locator: str) -> dict[str, Any]:
    """Capture Word table rows/cells and retain raw OOXML for provenance.

    Text and simple grid merges are represented directly. Drawings, embedded
    objects, equations, and nested tables stay explicit review blockers.
    """
    root = ET.fromstring(xml)
    rows: list[dict[str, Any]] = []
    features: set[str] = set()
    for tr in root.findall(f"./{{{W}}}tr"):
        cells: list[dict[str, Any]] = []
        for tc in tr.findall(f"./{{{W}}}tc"):
            tcpr = tc.find(f"./{{{W}}}tcPr")
            grid_span = 1
            vmerge = None
            if tcpr is not None:
                span = tcpr.find(f"./{{{W}}}gridSpan")
                if span is not None:
                    try:
                        grid_span = max(1, int(span.attrib.get(f"{{{W}}}val", "1")))
                    except ValueError:
                        features.add("invalid_grid_span")
                merge = tcpr.find(f"./{{{W}}}vMerge")
                if merge is not None:
                    vmerge = merge.attrib.get(f"{{{W}}}val", "continue")

            paragraphs: list[str] = []
            for child in tc:
                if child.tag == f"{{{W}}}p":
                    paragraphs.append(_paragraph_text(child))
                    for node in child.iter():
                        if node.tag in RICH_TAGS:
                            features.add(RICH_TAGS[node.tag])
                elif child.tag == f"{{{W}}}tbl":
                    features.add("nested_table")
            cells.append({
                "paragraphs": paragraphs,
                "text": "\n".join(paragraphs),
                "grid_span": grid_span,
                "vertical_merge": vmerge,
            })
        rows.append({"cells": cells})

    return {
        "type": "table",
        "locator": locator,
        "rows": rows,
        "unsupported_features": sorted(features),
        "raw_xml": xml,
    }


def normalize_table_block(block: Mapping[str, Any]) -> dict[str, Any] | None:
    if block.get("type") == "table":
        return dict(block)
    if block.get("type") == "unsupported" and block.get("feature") == "docx_table":
        raw = block.get("raw")
        if isinstance(raw, str) and raw:
            try:
                return parse_docx_table_xml(raw, str(block.get("locator") or ""))
            except ET.ParseError:
                return None
    return None


def table_plain_text(table: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for row in table.get("rows") or []:
        cells = [str(cell.get("text") or "").strip() for cell in row.get("cells") or []]
        lines.append(" | ".join(cells))
    return "\n".join(lines).strip()


def table_rich_node(table: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "table",
        "rows": [
            {
                "cells": [
                    {
                        "text": str(cell.get("text") or ""),
                        "grid_span": int(cell.get("grid_span") or 1),
                        **({"vertical_merge": cell["vertical_merge"]}
                           if cell.get("vertical_merge") else {}),
                    }
                    for cell in row.get("cells") or []
                ]
            }
            for row in table.get("rows") or []
        ],
    }
