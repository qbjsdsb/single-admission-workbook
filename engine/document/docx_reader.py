from __future__ import annotations

from pathlib import Path
from typing import Mapping

from engine.document.model import DocumentAst, paragraph_block, text_node, unsupported_block
from engine.parse.docx_structure import extract_structure


def _run_styles(properties: Mapping[str, str]) -> list[str]:
    styles: list[str] = []
    if properties.get("b", "false") not in {"false", "0", "none"}:
        styles.append("bold")
    if properties.get("i", "false") not in {"false", "0", "none"}:
        styles.append("italic")
    if properties.get("u", "none") not in {"none", "false", "0"}:
        styles.append("underline")
    if properties.get("em", "none") not in {"none", "false", "0"}:
        styles.append("emphasis_dot")
    return styles


def structure_to_document_ast(structure: Mapping[str, object]) -> DocumentAst:
    blocks: list[dict] = []
    warnings: list[str] = []

    for block in structure.get("blocks") or []:
        locator = str(block.get("locator") or "")
        kind = str(block.get("kind") or "")

        if kind == "p":
            inlines: list[dict] = []
            for run in block.get("runs") or []:
                text = str(run.get("text") or "")
                if text:
                    inlines.append(text_node(text, _run_styles(run.get("properties") or {})))

            for index, omml in enumerate(block.get("math_omml") or []):
                inlines.append({
                    "type": "math_omml",
                    "xml": str(omml),
                    "locator": f"{locator}/math/{index}",
                    "status": "captured_not_normalized",
                })
                warnings.append("math_omml_not_normalized")

            for index, rid in enumerate(block.get("image_relationships") or []):
                if rid:
                    inlines.append({
                        "type": "image_ref",
                        "relationship_id": str(rid),
                        "locator": f"{locator}/image/{index}",
                        "status": "captured_not_normalized",
                    })
                    warnings.append("image_relationship_not_normalized")

            blocks.append(paragraph_block(locator, inlines))
            continue

        if kind == "tbl":
            blocks.append(unsupported_block(
                locator,
                "docx_table",
                raw=str(block.get("xml") or ""),
            ))
            warnings.append("table_not_normalized")
            continue

        blocks.append(unsupported_block(
            locator,
            f"docx_{kind or 'unknown'}",
            raw=str(block.get("xml") or ""),
        ))
        warnings.append(f"{kind or 'unknown'}_not_normalized")

    return DocumentAst(
        source_format="docx",
        blocks=tuple(blocks),
        warnings=tuple(sorted(set(warnings))),
    )


def read_docx_document(path: Path) -> DocumentAst:
    return structure_to_document_ast(extract_structure(path))
