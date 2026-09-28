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


def _asset_inline(
    assets: Mapping[str, Mapping[str, object]],
    rid: str,
    locator: str,
    source: str,
) -> dict:
    record = assets.get(rid) or {}
    if record.get("mathml_status") == "inline_text":
        node = {
            "type": "mathml_inline_text",
            "text": str(record.get("mathml_inline_text") or ""),
            "locator": locator,
            "status": "normalized_from_embedded_mathml",
            "mathml_xml": str(record.get("mathml_xml") or ""),
        }
        if record.get("sha256"):
            node["source_asset_sha256"] = record["sha256"]
        if record.get("target"):
            node["source_asset_target"] = record["target"]
        if record.get("extension"):
            node["source_asset_extension"] = record["extension"]
        return node
    node = {
        "type": "image_ref",
        "locator": locator,
        "status": "captured_not_normalized",
        "source": source,
        **_asset_fields(assets, rid),
    }
    if record.get("mathml_status"):
        node["mathml_status"] = str(record["mathml_status"])
    if record.get("mathml_xml"):
        node["mathml_xml"] = str(record["mathml_xml"])
    return node


def _ole_inline(assets: Mapping[str, Mapping[str, object]], obj: Mapping[str, object], locator: str, index: int) -> dict:
    object_rid = obj.get("relationship_id")
    preview_rid = obj.get("preview_relationship_id")
    prog_id = str(obj.get("prog_id") or "")
    return {
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
    }


def structure_to_document_ast(structure: Mapping[str, object]) -> DocumentAst:
    blocks: list[dict] = []
    warnings: list[str] = [str(x) for x in (structure.get('warnings') or [])]
    assets = structure.get("assets") or {}

    for block in structure.get("blocks") or []:
        locator = str(block.get("locator") or "")
        kind = str(block.get("kind") or "")

        if kind == "p":
            inlines: list[dict] = []
            marker = str(block.get("numbering_marker") or "")
            if marker:
                inlines.append(text_node(marker + " "))
            ordered_content = block.get("inline_content")
            if ordered_content is None:
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

            if ordered_content is not None:
                for item in ordered_content:
                    kind = item.get("kind")
                    if kind == "text":
                        value = str(item.get("text") or "")
                        if value:
                            inlines.append(text_node(value, _run_styles(item.get("properties") or {})))
                    elif kind == "drawing":
                        rid = item.get("relationship_id")
                        if not rid:
                            continue
                        node = _asset_inline(
                            assets, str(rid),
                            f"{locator}/drawing/{item.get('index', 0)}", "drawingml",
                        )
                        if node["type"] == "image_ref":
                            for key in ("cx_emu", "cy_emu"):
                                if item.get(key) is not None:
                                    node[key] = int(item[key])
                            if item.get("name"):
                                node["name"] = str(item["name"])
                            warnings.append("image_relationship_not_normalized")
                            if node.get("mathml_status"):
                                warnings.append("mathml_wmf_not_normalized")
                        inlines.append(node)
                    elif kind == "ole_object":
                        node = _ole_inline(assets, item, locator, int(item.get("index", 0)))
                        inlines.append(node)
                        warnings.append(
                            "equation_ole_not_normalized" if item.get("is_equation")
                            else "ole_object_not_normalized"
                        )
                    elif kind == "math_omml":
                        inlines.append({
                            "type": "math_omml",
                            "xml": str(item.get("xml") or ""),
                            "locator": f"{locator}/math/{len([x for x in inlines if x.get('type') == 'math_omml'])}",
                            "status": "captured_not_normalized",
                        })
                        warnings.append("math_omml_not_normalized")
                    elif kind == "vml_image":
                        rid = str(item.get("relationship_id") or "")
                        if not rid or rid in ole_preview_ids:
                            continue
                        node = _asset_inline(
                            assets, rid,
                            f"{locator}/vml-image/{len([x for x in inlines if x.get('source') == 'vml'])}",
                            "vml",
                        )
                        if node["type"] == "image_ref":
                            warnings.append("image_relationship_not_normalized")
                            if node.get("mathml_status"):
                                warnings.append("mathml_wmf_not_normalized")
                        inlines.append(node)
                blocks.append(paragraph_block(locator, inlines))
                continue

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
                inlines.append(_ole_inline(assets, obj, locator, index))
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
