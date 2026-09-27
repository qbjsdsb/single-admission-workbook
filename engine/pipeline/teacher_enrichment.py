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
        if number is None:
            unresolved.append({
                "candidate_id": candidate_id,
                "reason": "missing_source_number",
            })
            continue

        evidence = list(grouped.get((section, int(number)), []))
        if not evidence:
            for (_e_section, e_number), group in grouped.items():
                if e_number == int(number):
                    evidence.extend(group)

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
