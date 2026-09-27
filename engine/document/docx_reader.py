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


def _asset_fields(assets: Mapping[str, Mapping[str, object]], rid: str | None) -> dict:
    if not rid:
        return {}
    record = assets.get(rid) or {}
    return {
        "relationship_id": rid,
        **({"asset_sha256": record.get("sha256")} if record.get("sha256") else {}),
        **({"asset_target": record.get("target")} if record.get("target") else {}),
        **({"asset_extension": record.get("extension")} if record.get("extension") else {}),
        **({"asset_bytes": record.get("bytes")} if record.get("bytes") is not None else {}),
    }


def structure_to_document_ast(structure: Mapping[str, object]) -> DocumentAst:
    blocks: list[dict] = []
    warnings: list[str] = []
    assets = structure.get("assets") or {}

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

            ole_preview_ids = {
                str(obj.get("preview_relationship_id"))
                for obj in (block.get("ole_objects") or [])
                if obj.get("preview_relationship_id")
            }

            for drawing in block.get("drawings") or []:
                rid = drawing.get("relationship_id")
                if not rid:
                    continue
                node = {
                    "type": "image_ref",
                    "locator": f"{locator}/drawing/{drawing.get('index', 0)}",
                    "status": "captured_not_normalized",
                    "source": "drawingml",
                    **_asset_fields(assets, str(rid)),
                }
                if drawing.get("cx_emu") is not None:
                    node["cx_emu"] = int(drawing["cx_emu"])
                if drawing.get("cy_emu") is not None:
                    node["cy_emu"] = int(drawing["cy_emu"])
                if drawing.get("name"):
                    node["name"] = str(drawing["name"])
                inlines.append(node)
                warnings.append("image_relationship_not_normalized")

            for index, obj in enumerate(block.get("ole_objects") or []):
                object_rid = obj.get("relationship_id")
                preview_rid = obj.get("preview_relationship_id")
                prog_id = str(obj.get("prog_id") or "")
                inlines.append({
                    "type": "ole_object_ref",
                    "locator": f"{locator}/ole/{index}",
                    "status": "captured_not_normalized",
                    "feature": "equation_ole" if obj.get("is_equation") else "ole_object",
                    "prog_id": prog_id,
                    **_asset_fields(assets, str(object_rid) if object_rid else None),
                    **({
                        "preview_relationship_id": str(preview_rid),
                        "preview_asset_sha256": (assets.get(str(preview_rid)) or {}).get("sha256"),
                        "preview_asset_target": (assets.get(str(preview_rid)) or {}).get("target"),
                        "preview_asset_extension": (assets.get(str(preview_rid)) or {}).get("extension"),
                    } if preview_rid else {}),
                    **({"shape_style": str(obj["shape_style"])} if obj.get("shape_style") else {}),
                })
                warnings.append(
                    "equation_ole_not_normalized" if obj.get("is_equation")
                    else "ole_object_not_normalized"
                )

            for index, rid in enumerate(block.get("vml_image_relationships") or []):
                rid = str(rid)
                if rid in ole_preview_ids:
                    continue
                inlines.append({
                    "type": "image_ref",
                    "locator": f"{locator}/vml-image/{index}",
                    "status": "captured_not_normalized",
                    "source": "vml",
                    **_asset_fields(assets, rid),
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
