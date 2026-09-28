from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Any, Iterable, Mapping


def _evidence_by_number(
    evidence_bank: Mapping[str, Any],
) -> dict[tuple[str | None, int], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str | None, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in evidence_bank.get("evidence") or []:
        if item.get("source_number") is None:
            continue
        grouped[(item.get("section_key"), int(item["source_number"]))].append(item)
    return grouped


def _join_field(items: Iterable[Mapping[str, Any]], field: str) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item.get("field") != field:
            continue
        value = str(item.get("value") or "").strip()
        if value and value not in seen:
            seen.add(value)
            chunks.append(value)
    return "\n".join(chunks)


def build_teacher_enrichment(
    pairing_review: Mapping[str, Any],
    evidence_bank: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach teacher-only prose only when candidate/evidence binding is trustworthy."""
    if pairing_review.get("evidence_source_id") != evidence_bank.get("source_id"):
        raise ValueError("pairing review and evidence bank source mismatch")
    if pairing_review.get("subject") != evidence_bank.get("subject"):
        raise ValueError("pairing review and evidence bank subject mismatch")

    grouped = _evidence_by_number(evidence_bank)
    evidence_by_id = {item.get("evidence_id"): item
                      for item in evidence_bank.get("evidence") or []}
    items: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []

    for row in pairing_review.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "")
        number = row.get("source_number")
        section = row.get("section_key")

        if row.get("review_status") == "conflict":
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "pairing_or_answer_conflict",
            })
            continue
        if row.get("binding_strength") not in {
            "content_exact", "content_high", "paired_source_number"
        }:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "weak_evidence_binding",
            })
            continue
        # Reuse the exact answer evidence binding established by reconciliation.
        # Student question numbers are not safe after teacher-side renumbering.
        bound = [evidence_by_id[eid] for eid in row.get("evidence_ids") or []
                 if eid in evidence_by_id and evidence_by_id[eid].get("field") == "answer"]
        identities = {(item.get("section_key"), item.get("source_number")) for item in bound}
        sample_bound = [
            evidence_by_id[eid]
            for eid in row.get("source_sample_response_evidence_ids") or []
            if eid in evidence_by_id
            and evidence_by_id[eid].get("field") == "source_sample_response"
        ]
        if len(identities) == 1 and next(iter(identities))[1] is not None:
            identity = next(iter(identities))
        elif (
            row.get("candidate_kind") == "composition"
            and row.get("section_key") == "writing"
            and row.get("source_pair_confidence") == "name_exact"
            and row.get("candidate_status") == "parsed"
            and row.get("binding_strength")
            in {"content_exact", "content_high", "paired_source_number"}
            and sample_bound
        ):
            sample_identities = {
                (item.get("section_key"), item.get("source_number"))
                for item in sample_bound
            }
            if len(sample_identities) != 1:
                unresolved.append({
                    "candidate_id": candidate_id,
                    "reason": "missing_or_ambiguous_sample_response_binding",
                })
                continue
            identity = next(iter(sample_identities))
            if row.get("companion_source_number") is not None:
                expected_identity = (
                    row.get("companion_section_key") or row.get("section_key"),
                    row.get("companion_source_number"),
                )
            else:
                expected_identity = (
                    row.get("section_key"),
                    row.get("source_number"),
                )
            if expected_identity[1] is None or identity != expected_identity:
                unresolved.append({
                    "candidate_id": candidate_id,
                    "reason": "sample_response_source_number_mismatch",
                })
                continue
        else:
            unresolved.append({"candidate_id": candidate_id,
                               "reason": "missing_or_ambiguous_answer_binding"})
            continue
        evidence = list(grouped.get(identity, []))

        analysis = _join_field(evidence, "analysis")
        notes = _join_field(evidence, "teacher_notes")
        sample_items = [
            item for item in evidence
            if item.get("field") == "source_sample_response"
        ]
        sample_response = "\n".join(
            str(item.get("value") or "").strip()
            for item in sample_items
            if str(item.get("value") or "").strip()
        )
        if sample_response:
            source_sha256 = str(evidence_bank.get("source_sha256") or "")
            if not source_sha256:
                unresolved.append({
                    "candidate_id": candidate_id,
                    "reason": "sample_response_source_hash_missing",
                })
                continue
            paragraph_hashes = []
            for sample_item in sample_items:
                value = str(sample_item.get("value") or "").strip()
                digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                if sample_item.get("value_sha256") != digest:
                    raise ValueError(
                        f"{candidate_id}: sample response evidence hash mismatch"
                    )
                paragraph_hashes.append(digest)
            sample_provenance = {
                "evidence_source_id": str(evidence_bank["source_id"]),
                "source_sha256": source_sha256,
                "evidence_ids": [str(item["evidence_id"]) for item in sample_items],
                "locators": [str(item["locator"]) for item in sample_items],
                "paragraph_sha256": paragraph_hashes,
                "response_sha256": hashlib.sha256(
                    sample_response.encode("utf-8")
                ).hexdigest(),
            }

        if not analysis and not notes and not sample_response:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "no_teacher_prose_evidence",
            })
            continue

        item: dict[str, Any] = {"candidate_id": candidate_id}
        if analysis:
            item["analysis"] = analysis
        if notes:
            item["teacher_notes"] = notes
        if sample_response:
            item["source_sample_response"] = sample_response
            item["source_sample_response_provenance"] = sample_provenance
        items.append(item)

    return {
        "schema_version": 1,
        "candidate_source_id": pairing_review.get("candidate_source_id"),
        "evidence_source_id": evidence_bank.get("source_id"),
        "items": items,
        "unresolved": unresolved,
        "summary": {
            "enriched": len(items),
            "unresolved": len(unresolved),
        },
    }



def apply_reviewed_analysis_supplements(
    teacher_enrichment: Mapping[str, Any] | None,
    supplement_manifest: Mapping[str, Any],
    *,
    known_candidate_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Merge only explicitly approved non-source analysis into teacher prose.

    Source-derived teacher analysis always wins. A supplement may fill a missing
    analysis but can never overwrite a different source-provided analysis.
    Draft/deferred/rejected supplement rows remain outside the publication input.
    """
    source_id = str(supplement_manifest.get("candidate_source_id") or "")
    if not source_id:
        raise ValueError("analysis supplement missing candidate_source_id")

    if teacher_enrichment is None:
        base = {
            "schema_version": 1,
            "candidate_source_id": source_id,
            "items": [],
        }
    else:
        if str(teacher_enrichment.get("candidate_source_id") or "") != source_id:
            raise ValueError("analysis supplement source mismatch")
        base = {
            "schema_version": 1,
            "candidate_source_id": source_id,
            "items": [dict(item) for item in teacher_enrichment.get("items") or []],
        }

    by_id: dict[str, dict[str, Any]] = {}
    for item in base["items"]:
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id or candidate_id in by_id:
            raise ValueError("teacher enrichment contains missing/duplicate candidate_id")
        by_id[candidate_id] = item

    seen: set[str] = set()
    for item in supplement_manifest.get("items") or []:
        candidate_id = str(item.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError("analysis supplement item missing candidate_id")
        if candidate_id in seen:
            raise ValueError(f"duplicate analysis supplement candidate: {candidate_id}")
        seen.add(candidate_id)

        if known_candidate_ids is not None and candidate_id not in known_candidate_ids:
            raise ValueError(f"analysis supplement references unknown candidate {candidate_id}")

        if item.get("decision") != "approve":
            continue

        analysis = str(item.get("analysis") or "").strip()
        review_note = str(item.get("review_note") or "").strip()
        if not analysis or not review_note:
            raise ValueError(f"{candidate_id}: approved supplement needs analysis and review_note")

        existing = by_id.get(candidate_id)
        if existing is not None and existing.get("analysis"):
            existing_analysis = str(existing["analysis"]).strip()
            if existing_analysis != analysis:
                raise ValueError(
                    f"{candidate_id}: supplement cannot overwrite source teacher analysis"
                )
            continue

        target = existing if existing is not None else {"candidate_id": candidate_id}
        target["analysis"] = analysis
        by_id[candidate_id] = target

    return {
        "schema_version": 1,
        "candidate_source_id": source_id,
        "items": [by_id[candidate_id] for candidate_id in sorted(by_id)],
    }
