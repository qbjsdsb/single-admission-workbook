from __future__ import annotations

from collections import defaultdict
import unicodedata
import re
from typing import Any, Iterable, Mapping


def _normalize_answer(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", "", text)
    return text.rstrip("。．.；;，,")


def aggregate_pairing_reviews(
    reviews: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge multiple companion-source reviews for the same candidate bank.

    The aggregate is still pre-verification. It is used to prioritize human/content
    review and to surface independent-source agreement or conflict.
    """
    reviews = list(reviews)
    if not reviews:
        raise ValueError("at least one pairing review is required")

    candidate_source_ids = {str(r.get("candidate_source_id") or "") for r in reviews}
    subjects = {str(r.get("subject") or "") for r in reviews}
    if len(candidate_source_ids) != 1 or "" in candidate_source_ids:
        raise ValueError("reviews must refer to one candidate source")
    if len(subjects) != 1 or "" in subjects:
        raise ValueError("reviews must refer to one subject")

    grouped: dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for review in reviews:
        evidence_source_id = str(review.get("evidence_source_id") or "")
        for row in review.get("rows") or []:
            grouped[str(row["candidate_id"])].append((evidence_source_id, row))

    rows: list[dict[str, Any]] = []
    for candidate_id, source_rows in sorted(grouped.items()):
        answer_groups: dict[str, set[str]] = defaultdict(set)
        all_sources: set[str] = set()
        strong_sources: set[str] = set()
        reasons: set[str] = set()
        machine_conflict = False

        for evidence_source_id, row in source_rows:
            all_sources.add(evidence_source_id)
            reasons.update(row.get("review_reasons") or [])
            if row.get("answer_status") == "conflict" or row.get("review_status") == "conflict":
                machine_conflict = True
            normalized = row.get("normalized_answer")
            if normalized:
                answer_groups[_normalize_answer(normalized)].add(evidence_source_id)
            if (
                normalized
                and row.get("binding_strength")
                in {"content_exact", "content_high", "paired_source_number"}
            ):
                strong_sources.add(evidence_source_id)

        variants = sorted(answer_groups)
        if machine_conflict or len(variants) > 1:
            status = "conflict"
            normalized_answer = None
        elif len(variants) == 1:
            normalized_answer = variants[0]
            agreeing_sources = answer_groups[normalized_answer]
            if len(agreeing_sources & strong_sources) >= 2:
                status = "machine_corroborated"
            elif len(agreeing_sources & strong_sources) == 1:
                status = "single_source_consistent"
            else:
                status = "review_required"
        else:
            status = "review_required"
            normalized_answer = None

        rows.append({
            "candidate_id": candidate_id,
            "aggregate_status": status,
            "normalized_answer": normalized_answer,
            "answer_variants": variants,
            "evidence_source_ids": sorted(all_sources),
            "strong_evidence_source_ids": sorted(strong_sources),
            "review_reasons": sorted(reasons),
        })

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["aggregate_status"]] += 1

    return {
        "schema_version": 1,
        "subject": next(iter(subjects)),
        "candidate_source_id": next(iter(candidate_source_ids)),
        "rows": rows,
        "summary": {
            "total": len(rows),
            "machine_corroborated": counts["machine_corroborated"],
            "single_source_consistent": counts["single_source_consistent"],
            "review_required": counts["review_required"],
            "conflicts": counts["conflict"],
        },
    }


def build_verified_candidate_bank(
    candidate_bank: Mapping[str, Any],
    aggregate_review: Mapping[str, Any],
    verification_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Promote explicitly approved candidates into a verified private bank.

    This is still not the publication Canonical Question Bank: chapter assignment,
    scores, rich-content fidelity and editorial checks may still be pending.
    """
    if candidate_bank.get("source_id") != aggregate_review.get("candidate_source_id"):
        raise ValueError("candidate bank and aggregate review source mismatch")
    if candidate_bank.get("subject") != aggregate_review.get("subject"):
        raise ValueError("candidate bank and aggregate review subject mismatch")

    candidates = {
        str(item["candidate_id"]): item
        for item in candidate_bank.get("candidates") or []
    }
    aggregates = {
        str(item["candidate_id"]): item
        for item in aggregate_review.get("rows") or []
    }
    decisions = {
        str(item["candidate_id"]): item
        for item in verification_manifest.get("decisions") or []
    }

    verified: list[dict[str, Any]] = []
    rejected: list[str] = []
    deferred: list[str] = []

    for candidate_id, decision in decisions.items():
        candidate = candidates.get(candidate_id)
        aggregate = aggregates.get(candidate_id)
        if candidate is None:
            raise ValueError(f"verification references unknown candidate {candidate_id}")
        if aggregate is None:
            raise ValueError(f"verification has no aggregate review for {candidate_id}")

        action = decision.get("decision")
        if action == "reject":
            rejected.append(candidate_id)
            continue
        if action == "defer":
            deferred.append(candidate_id)
            continue
        if action != "approve":
            raise ValueError(f"unsupported verification decision for {candidate_id}: {action}")

        if candidate.get("status") != "parsed" and decision.get("method") != "human_review":
            raise ValueError(
                f"{candidate_id}: ambiguous candidate requires human_review approval"
            )
        if aggregate.get("aggregate_status") == "conflict" and decision.get("method") != "human_review":
            raise ValueError(
                f"{candidate_id}: conflicting machine evidence requires human_review"
            )

        aggregate_answer = aggregate.get("normalized_answer")
        verified_answer = decision.get("verified_answer")
        if verified_answer is None:
            verified_answer = aggregate_answer
        verified_answer = _normalize_answer(verified_answer)
        if not verified_answer:
            raise ValueError(f"{candidate_id}: approved candidate needs a verified answer")

        if aggregate_answer and verified_answer != _normalize_answer(aggregate_answer):
            if not str(decision.get("override_reason") or "").strip():
                raise ValueError(
                    f"{candidate_id}: answer override requires override_reason"
                )

        verified.append({
            "candidate_id": candidate_id,
            "source_id": candidate.get("source_id"),
            "subject": candidate.get("subject"),
            "source_number": candidate.get("source_number"),
            "section_key": candidate.get("section_key"),
            "kind": candidate.get("kind"),
            "stem_text": candidate.get("stem_text"),
            "options": candidate.get("options") or [],
            "group_id": candidate.get("group_id"),
            "locators": candidate.get("locators") or [],
            "verified_answer": verified_answer,
            "verification_method": decision.get("method"),
            "verification_note": str(decision.get("note") or ""),
            "override_reason": str(decision.get("override_reason") or ""),
            "machine_aggregate_status": aggregate.get("aggregate_status"),
            "machine_answer": aggregate_answer,
        })

    return {
        "schema_version": 1,
        "subject": candidate_bank.get("subject"),
        "candidate_source_id": candidate_bank.get("source_id"),
        "verified": verified,
        "rejected_candidate_ids": sorted(rejected),
        "deferred_candidate_ids": sorted(deferred),
        "summary": {
            "verified": len(verified),
            "rejected": len(rejected),
            "deferred": len(deferred),
        },
    }
