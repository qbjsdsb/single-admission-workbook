from __future__ import annotations

from collections import defaultdict
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
        if len(identities) != 1 or next(iter(identities))[1] is None:
            unresolved.append({"candidate_id": candidate_id,
                               "reason": "missing_or_ambiguous_answer_binding"})
            continue
        identity = next(iter(identities))
        evidence = list(grouped.get(identity, []))

        analysis = _join_field(evidence, "analysis")
        notes = _join_field(evidence, "teacher_notes")
        if not analysis and not notes:
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
