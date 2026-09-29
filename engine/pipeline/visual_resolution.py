from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping


VISUAL_CUE_RE = re.compile(
    r"(?:下图|上图|右图|左图|见图|如图|图中|图示|下表|上表|表中|右表|左表)"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_single_visual_candidate(item: Mapping[str, Any]) -> tuple[bool, str]:
    refs = list(item.get("asset_refs") or [])
    if len(refs) != 1:
        return False, "requires_exactly_one_source_visual"

    stem_text = str(item.get("stem_text") or "")
    if not VISUAL_CUE_RE.search(stem_text):
        return False, "source_stem_has_no_explicit_visual_cue"

    ref = refs[0]
    locator = str(ref.get("locator") or "")
    paragraph_locator = locator.split("/drawing/", 1)[0].split("/vml-image/", 1)[0]
    if paragraph_locator not in set(str(x) for x in item.get("locators") or []):
        return False, "visual_locator_not_bound_to_question"

    rich = item.get("stem_rich")
    if rich:
        allowed = {"text", "blank"}
        if any(str(node.get("type") or "") not in allowed for node in rich):
            return False, "existing_rich_stem_requires_manual_visual_placement"

    extension = str(ref.get("asset_extension") or "").lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        return False, "visual_format_requires_conversion_or_review"

    if not str(ref.get("asset_sha256") or ""):
        return False, "source_visual_hash_missing"

    return True, ""


def resolve_safe_single_visuals(
    scored_verified_bank: Mapping[str, Any],
    asset_manifest: Mapping[str, Any],
    *,
    asset_dir: Path,
) -> dict[str, Any]:
    """Resolve only a narrow, auditable class of source visuals.

    Safe automatic placement is limited to one raster image explicitly referenced
    by the question stem (for example "下图"). The image must be bound to one of
    the question's source paragraph locators and its exported bytes must match the
    source asset hash. Everything else remains unresolved and therefore continues
    to be blocked by Canonical promotion.
    """
    assets = asset_manifest.get("assets") or {}
    resolved_items: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for original in scored_verified_bank.get("assigned") or []:
        item = dict(original)
        refs = list(item.get("asset_refs") or [])
        if not refs:
            resolved_items.append(item)
            continue

        safe, reason = _safe_single_visual_candidate(item)
        if not safe:
            resolved_items.append(item)
            audit_rows.append({
                "candidate_id": str(item.get("candidate_id") or ""),
                "status": "deferred",
                "reason": reason,
            })
            continue

        ref = refs[0]
        relationship_id = str(ref.get("relationship_id") or "")
        manifest_asset = assets.get(relationship_id)
        if not isinstance(manifest_asset, Mapping):
            resolved_items.append(item)
            audit_rows.append({
                "candidate_id": str(item.get("candidate_id") or ""),
                "status": "deferred",
                "reason": "relationship_missing_from_asset_manifest",
            })
            continue

        expected_hash = str(ref.get("asset_sha256") or "")
        if str(manifest_asset.get("sha256") or "") != expected_hash:
            resolved_items.append(item)
            audit_rows.append({
                "candidate_id": str(item.get("candidate_id") or ""),
                "status": "deferred",
                "reason": "asset_manifest_hash_mismatch",
            })
            continue

        if manifest_asset.get("export_status") != "exported":
            resolved_items.append(item)
            audit_rows.append({
                "candidate_id": str(item.get("candidate_id") or ""),
                "status": "deferred",
                "reason": "source_visual_not_exported",
            })
            continue

        export_name = str(manifest_asset.get("export_name") or "")
        if not export_name:
            resolved_items.append(item)
            audit_rows.append({
                "candidate_id": str(item.get("candidate_id") or ""),
                "status": "deferred",
                "reason": "exported_visual_filename_missing",
            })
            continue

        path = (asset_dir / export_name).resolve()
        if not path.is_file() or _file_sha256(path) != expected_hash:
            resolved_items.append(item)
            audit_rows.append({
                "candidate_id": str(item.get("candidate_id") or ""),
                "status": "deferred",
                "reason": "exported_visual_bytes_do_not_match_source",
            })
            continue

        stem_rich = [
            dict(node)
            for node in (
                item.get("stem_rich")
                or [{"type": "text", "text": str(item.get("stem_text") or "")}]
            )
        ]
        stem_rich.append({
            "type": "image",
            "asset": str(path),
            "alt": "题目原图",
        })
        item["stem_rich"] = stem_rich
        item.pop("asset_refs", None)
        resolved_items.append(item)
        audit_rows.append({
            "candidate_id": str(item.get("candidate_id") or ""),
            "status": "resolved",
            "method": "single_explicit_visual_source_order_v1",
            "relationship_id": relationship_id,
            "asset_sha256": expected_hash,
            "asset_extension": str(ref.get("asset_extension") or ""),
        })

    output_bank = dict(scored_verified_bank)
    output_bank["assigned"] = resolved_items
    return {
        "bank": output_bank,
        "audit": {
            "schema_version": 1,
            "source_name": str(asset_manifest.get("source_name") or ""),
            "source_sha256": str(asset_manifest.get("source_sha256") or ""),
            "resolved": sum(1 for row in audit_rows if row["status"] == "resolved"),
            "deferred": sum(1 for row in audit_rows if row["status"] == "deferred"),
            "rows": audit_rows,
        },
    }
