from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Iterable, Mapping

from engine.ingest.pairing import normalize_match_text, pair_question_records


def _candidate_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate["candidate_id"],
        "number": candidate.get("source_number"),
        "section_key": candidate.get("section_key"),
        "stem": candidate.get("stem_text", ""),
        "options": candidate.get("options") or [],
    }


def _normalize_answer(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", "", text)
    return text.rstrip("。．.；;，,")


def _writing_prefix_coverage(candidate: Mapping[str, Any], companion: Mapping[str, Any]) -> float:
    """Return conservative shared-prefix coverage for one English writing prompt.

    Exact student/teacher source pairs often diverge only after the prompt, where
    the student file contains answer space and the teacher file contains a model
    response. A long shared prefix can therefore establish prompt identity without
    treating teacher prose as part of the question.
    """
    student = normalize_match_text(candidate.get("stem_text"))
    teacher = normalize_match_text(companion.get("stem"))
    if not student or not teacher:
        return 0.0

    shared = 0
    for left, right in zip(student, teacher):
        if left != right:
            break
        shared += 1

    shorter = min(len(student), len(teacher))
    if shared < 60 or shorter <= 0:
        return 0.0
    return shared / shorter


_WRITING_GREETING_RE = re.compile(
    r"^\s*((?:dear|hi|hello)\b[^,，\n]{0,80}[,，])",
    re.IGNORECASE,
)


def _writing_instruction_signature(value: object) -> str:
    """Keep source instructions through the first supplied greeting line.

    This intentionally excludes answer-space/model-response continuation. It is
    only used after the stricter common-prefix rule fails.
    """
    lines = [
        line.strip()
        for line in str(value or "").splitlines()
        if line.strip()
    ]
    kept: list[str] = []
    greeting_seen = False
    for line in lines:
        greeting = _WRITING_GREETING_RE.match(line)
        if greeting:
            kept.append(greeting.group(1))
            greeting_seen = True
            break
        kept.append(line)
    if not kept or not greeting_seen:
        return ""
    return "\n".join(kept)


def _writing_instruction_similarity(
    candidate: Mapping[str, Any],
    companion: Mapping[str, Any],
) -> float:
    student = normalize_match_text(
        _writing_instruction_signature(candidate.get("stem_text"))
    )
    teacher = normalize_match_text(
        _writing_instruction_signature(companion.get("stem"))
    )
    if min(len(student), len(teacher)) < 60:
        return 0.0
    return SequenceMatcher(None, student, teacher).ratio()


def _evidence_index(
    evidence: Iterable[Mapping[str, Any]],
) -> dict[tuple[str | None, int], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str | None, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in evidence:
        if item.get("field") != "answer" or item.get("source_number") is None:
            continue
        grouped[(item.get("section_key"), int(item["source_number"]))].append(item)
    return grouped


def _sample_response_index(
    evidence: Iterable[Mapping[str, Any]],
) -> dict[tuple[str | None, int], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str | None, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in evidence:
        if item.get("field") != "source_sample_response" or item.get("source_number") is None:
            continue
        grouped[(item.get("section_key"), int(item["source_number"]))].append(item)
    return grouped


def _answer_decision(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(items)
    variants: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        normalized = _normalize_answer(item.get("value"))
        if normalized:
            variants[normalized].append(item)

    if not variants:
        return {
            "status": "missing",
            "normalized_answer": None,
            "variants": [],
            "evidence_ids": [],
        }
    if len(variants) > 1:
        return {
            "status": "conflict",
            "normalized_answer": None,
            "variants": sorted(variants),
            "evidence_ids": sorted(
                str(item.get("evidence_id") or "")
                for group in variants.values()
                for item in group
            ),
        }

    answer, group = next(iter(variants.items()))
    return {
        "status": "unique",
        "normalized_answer": answer,
        "variants": [answer],
        "evidence_ids": sorted(str(item.get("evidence_id") or "") for item in group),
    }


def reconcile_candidate_and_evidence(
    candidate_bank: Mapping[str, Any],
    evidence_bank: Mapping[str, Any],
    *,
    source_pair_confidence: str = "name_exact",
) -> dict[str, Any]:
    """Create a fail-closed review queue for one already-paired source pair.

    ready_for_verification means enough consistent structure exists for the next
    verification gate. It never means the answer is independently proven correct.
    """
    if candidate_bank.get("subject") != evidence_bank.get("subject"):
        raise ValueError("candidate/evidence subject mismatch")

    candidates = list(candidate_bank.get("candidates") or [])
    prompt_records = list(evidence_bank.get("question_records") or [])
    pairing = pair_question_records(
        [_candidate_record(candidate) for candidate in candidates],
        prompt_records,
    )
    pair_by_student = {item.student_id: item for item in pairing}
    prompt_by_id = {str(item.get("id")): item for item in prompt_records}
    answers = _evidence_index(evidence_bank.get("evidence") or [])
    sample_responses = _sample_response_index(evidence_bank.get("evidence") or [])

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        number = candidate.get("source_number")
        section = candidate.get("section_key")
        pair = pair_by_student.get(candidate_id)

        pair_confidence = pair.confidence if pair else "unmatched"
        pair_reason = pair.reason if pair else "no_prompt_record"
        pair_score = 0.0 if pair is None else float(pair.score)
        companion_id = pair.companion_id if pair else None
        companion = prompt_by_id.get(str(companion_id)) if companion_id else None

        if (
            pair_confidence != "exact"
            and source_pair_confidence == "name_exact"
            and candidate.get("kind") == "composition"
            and candidate.get("section_key") == "writing"
        ):
            writing_prompts = [
                record
                for record in prompt_records
                if record.get("section_key") == "writing"
            ]
            if len(writing_prompts) == 1:
                writing_prompt = writing_prompts[0]
                prefix_coverage = _writing_prefix_coverage(
                    candidate,
                    writing_prompt,
                )
                instruction_similarity = _writing_instruction_similarity(
                    candidate,
                    writing_prompt,
                )
                if 0 < instruction_similarity < 0.98:
                    # When both sources expose a comparable instruction block,
                    # a material difference there outranks generic/prefix
                    # similarity. Keep it deferred rather than silently treating
                    # a missing or added requirement as the same prompt.
                    companion = None
                    companion_id = None
                    pair_confidence = "unmatched"
                    pair_reason = "writing_prompt_source_discrepancy"
                    pair_score = instruction_similarity
                elif prefix_coverage >= 0.80:
                    companion = writing_prompt
                    companion_id = str(companion.get("id") or "")
                    pair_confidence = "high"
                    pair_reason = "name_exact_writing_prompt_prefix"
                    pair_score = prefix_coverage
                elif instruction_similarity >= 0.98:
                    companion = writing_prompt
                    companion_id = str(companion.get("id") or "")
                    pair_confidence = "high"
                    pair_reason = "name_exact_writing_instruction_similarity"
                    pair_score = instruction_similarity

        # A content match binds to the TEACHER question identity, even if renumbered.
        target_number = companion.get("number") if companion is not None else number
        target_section = companion.get("section_key") if companion is not None else section
        answer_items: list[Mapping[str, Any]] = []
        sample_items: list[Mapping[str, Any]] = []
        if target_number is not None:
            answer_items.extend(answers.get((target_section, int(target_number)), []))
            sample_items.extend(sample_responses.get((target_section, int(target_number)), []))
            if not answer_items:
                # Unsectioned answer sheets are usable only without a competing section.
                buckets = [(key, group) for key, group in answers.items()
                           if key[1] == int(target_number)]
                if len(buckets) == 1 and (buckets[0][0][0] is None or target_section is None):
                    answer_items.extend(buckets[0][1])

        answer = _answer_decision(answer_items)
        review_reasons = list(candidate.get("review_reasons") or [])

        binding_strength = "none"
        if pair_confidence == "exact":
            binding_strength = "content_exact"
        elif pair_confidence == "high":
            binding_strength = "content_high"
        elif (answer_items or sample_items) and source_pair_confidence == "name_exact":
            binding_strength = "paired_source_number"
        elif answer_items or sample_items:
            binding_strength = "number_only"

        status = "ready_for_verification"
        if candidate.get("status") != "parsed":
            status = "review_required"
            review_reasons.append("candidate_structure_needs_review")
        if pair_confidence == "ambiguous":
            status = "review_required"
            review_reasons.append("prompt_pair_ambiguous")
        if answer["status"] == "conflict":
            status = "conflict"
            review_reasons.append("answer_evidence_conflict")
        elif answer["status"] == "missing":
            if status != "conflict":
                status = "review_required"
            review_reasons.append("answer_evidence_missing")
        if binding_strength in {"none", "number_only"}:
            if status == "ready_for_verification":
                status = "review_required"
            review_reasons.append("weak_or_missing_evidence_binding")

        rows.append({
            "candidate_id": candidate_id,
            "source_number": number,
            "section_key": section,
            "candidate_status": candidate.get("status"),
            "candidate_kind": candidate.get("kind"),
            "companion_question_id": companion_id,
            "prompt_pair_confidence": pair_confidence,
            "prompt_pair_score": round(pair_score, 6),
            "prompt_pair_reason": pair_reason,
            "binding_strength": binding_strength,
            "answer_status": answer["status"],
            "normalized_answer": answer["normalized_answer"],
            "answer_variants": answer["variants"],
            "evidence_ids": answer["evidence_ids"],
            "source_sample_response_evidence_ids": sorted(
                str(item.get("evidence_id") or "") for item in sample_items
            ),
            "review_status": status,
            "review_reasons": sorted(set(review_reasons)),
            "source_pair_confidence": source_pair_confidence,
            "companion_section_key": None if companion is None else companion.get("section_key"),
            "companion_source_number": None if companion is None else companion.get("number"),
        })

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["review_status"]] += 1

    return {
        "schema_version": 1,
        "subject": candidate_bank.get("subject"),
        "candidate_source_id": candidate_bank.get("source_id"),
        "evidence_source_id": evidence_bank.get("source_id"),
        "source_pair_confidence": source_pair_confidence,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ready_for_verification": counts["ready_for_verification"],
            "review_required": counts["review_required"],
            "conflicts": counts["conflict"],
            "missing_answers": sum(1 for row in rows if row["answer_status"] == "missing"),
        },
    }
