from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Mapping


NUMBER = r"([0-9]+(?:\.[0-9]+)?)"
FULL_SCORE_IN_TEXT = re.compile(r"(?:满分|总分|共计|满|共)\s*[。．.:：]?\s*" + NUMBER + r"\s*分(?!钟)")
COUNT_RE = re.compile(r"共\s*(\d+)\s*(?:小题|题)")
PER_RE = re.compile(r"(?:每小题|每题)\s*" + NUMBER + r"\s*分")
FULL_RE = re.compile(r"(?:满分|总分|共计|满)\s*[。．.:：]?\s*" + NUMBER + r"\s*分(?!钟)")
FULL_ALT_RE = re.compile(r"共\s*" + NUMBER + r"\s*分(?!钟)")
PAREN_SCORE_RE = re.compile(r"[（(]\s*" + NUMBER + r"\s*分\s*[）)]")


@dataclass(frozen=True)
class SectionScoreEvidence:
    section_key: str
    heading: str
    candidate_count: int
    declared_count: int | None
    per_question_score: float | None
    full_score: float | None
    per_question_source: str | None
    full_score_source: str | None
    status: str
    reasons: tuple[str, ...]


def _number(match: re.Match[str] | None) -> float | None:
    if match is None:
        return None
    return float(match.group(1))


def parse_section_score(
    section: Mapping[str, Any],
) -> SectionScoreEvidence:
    heading = str(section.get("heading") or "")
    candidate_count = int(section.get("candidate_count") or 0)

    count_match = COUNT_RE.search(heading)
    declared_count = int(count_match.group(1)) if count_match else None

    per_match = PER_RE.search(heading)
    per_question_score = _number(per_match)
    per_question_source = "explicit" if per_question_score is not None else None

    full_match = FULL_RE.search(heading) or FULL_ALT_RE.search(heading)
    if full_match is None and section.get("section_key") == "writing":
        # Some source editions print a one-task writing score as just "(10分)".
        # Treat that as explicit only in the writing section, never on an
        # arbitrary multiple-question heading.
        full_match = PAREN_SCORE_RE.search(heading)
    full_score = _number(full_match)
    full_score_source = "explicit" if full_score is not None else None

    reasons: list[str] = []

    if declared_count is not None and candidate_count and declared_count != candidate_count:
        reasons.append(
            f"declared_count_{declared_count}_!=_parsed_count_{candidate_count}"
        )

    if (
        declared_count
        and per_question_score is not None
        and full_score is None
    ):
        full_score = declared_count * per_question_score
        full_score_source = "derived_from_count_times_per_question"

    if (
        declared_count
        and per_question_score is not None
        and full_score is not None
    ):
        expected = declared_count * per_question_score
        if not math.isclose(expected, full_score, rel_tol=1e-9, abs_tol=1e-9):
            reasons.append(
                f"declared_score_math_{expected:g}_!=_full_score_{full_score:g}"
            )

    if reasons:
        status = "conflict"
    elif per_question_score is not None or (
        candidate_count == 1 and full_score is not None
    ):
        status = "usable"
    else:
        status = "incomplete"

    return SectionScoreEvidence(
        section_key=str(section.get("section_key") or ""),
        heading=heading,
        candidate_count=candidate_count,
        declared_count=declared_count,
        per_question_score=per_question_score,
        full_score=full_score,
        per_question_source=per_question_source,
        full_score_source=full_score_source,
        status=status,
        reasons=tuple(reasons),
    )


def build_score_evidence(candidate_bank: Mapping[str, Any]) -> dict[str, Any]:
    source_sections = list(candidate_bank.get("sections") or [])
    sections = [parse_section_score(section) for section in source_sections]

    records = []
    for source_section, section in zip(source_sections, sections):
        heading = str(source_section.get("heading") or "")
        record = {
            "section_key": section.section_key,
            "heading": section.heading,
            "heading_source": "inferred" if source_section.get("inferred") else "source",
            "heading_text_sha256": hashlib.sha256(
                heading.encode("utf-8")
            ).hexdigest(),
            "candidate_count": section.candidate_count,
            "declared_count": section.declared_count,
            "per_question_score": section.per_question_score,
            "full_score": section.full_score,
            "per_question_source": section.per_question_source,
            "full_score_source": section.full_score_source,
            "status": section.status,
            "reasons": list(section.reasons),
        }
        if source_section.get("heading_locator"):
            record["heading_locator"] = str(source_section["heading_locator"])
        records.append(record)

    counts = {"usable": 0, "incomplete": 0, "conflict": 0}
    for record in records:
        counts[record["status"]] += 1

    return {
        "schema_version": 1,
        "subject": candidate_bank.get("subject"),
        "candidate_source_id": candidate_bank.get("source_id"),
        "sections": records,
        "summary": {
            "total_sections": len(records),
            **counts,
        },
    }


CN_SMALL_NUMBERS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _section_count_from_total_text(text: str) -> int | None:
    match = re.search(r"([0-9]+|[一二两三四五六七八九十]+)\s*大题", text)
    if not match:
        return None
    value = match.group(1)
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = CN_SMALL_NUMBERS.get(left, 1) * 10 if left else 10
        return tens + CN_SMALL_NUMBERS.get(right, 0)
    return CN_SMALL_NUMBERS.get(value)


def apply_exam_total_residual_resolution(
    candidate_bank: Mapping[str, Any],
    score_evidence: Mapping[str, Any],
    resolution: Mapping[str, Any],
    *,
    source_text_by_locator: Mapping[str, str],
) -> dict[str, Any]:
    """Apply one audited residual score derived from an explicit scoped total.

    The total must explicitly name its score and number of sections; every other
    section in that scope must have an explicit, usable source score. The target
    per-question score is only accepted when the residual divides evenly across
    its source question count. Raw text remains with the private source AST; the
    emitted score evidence keeps only source locators, hashes, and arithmetic.
    """
    source_id = candidate_bank.get("source_id")
    if source_id != score_evidence.get("candidate_source_id"):
        raise ValueError("candidate bank and score evidence source mismatch")
    if source_id != resolution.get("candidate_source_id"):
        raise ValueError("score resolution source mismatch")

    target_key = str(resolution.get("target_section_key") or "")
    total_evidence = resolution.get("total_evidence") or {}
    total_locator = str(total_evidence.get("locator") or "")
    total_text = source_text_by_locator.get(total_locator)
    if not total_text:
        raise ValueError("total score evidence locator missing from source AST")
    total_hash = hashlib.sha256(total_text.encode("utf-8")).hexdigest()
    if total_hash != total_evidence.get("text_sha256"):
        raise ValueError("total score evidence hash mismatch")
    score_match = FULL_SCORE_IN_TEXT.search(total_text)
    if score_match is None:
        raise ValueError("total score evidence has no explicit total score")
    total_score = float(score_match.group(1))

    declared_sections = _section_count_from_total_text(total_text)
    scope_keys = [str(x) for x in resolution.get("scope_section_keys") or []]
    if (
        not target_key
        or target_key not in scope_keys
        or len(scope_keys) != len(set(scope_keys))
        or declared_sections is None
        or declared_sections != len(scope_keys)
    ):
        raise ValueError("total score scope does not match declared section count")

    candidate_sections = {
        str(section.get("section_key") or ""): section
        for section in candidate_bank.get("sections") or []
    }
    evidence_sections = {
        str(section.get("section_key") or ""): section
        for section in score_evidence.get("sections") or []
    }
    if any(key not in candidate_sections or key not in evidence_sections for key in scope_keys):
        raise ValueError("score resolution references a section outside the candidate bank")

    target_candidates = int(candidate_sections[target_key].get("candidate_count") or 0)
    if target_candidates <= 0:
        raise ValueError("target section has no parsed questions")
    target_score_row = evidence_sections[target_key]
    if target_score_row.get("status") != "incomplete":
        raise ValueError("target section score is not an incomplete gap")
    if (
        int(target_score_row.get("candidate_count") or 0) != target_candidates
        or target_score_row.get("heading") != candidate_sections[target_key].get("heading")
        or target_score_row.get("heading_text_sha256")
        != hashlib.sha256(
            str(candidate_sections[target_key].get("heading") or "").encode("utf-8")
        ).hexdigest()
    ):
        raise ValueError("target score evidence is stale for the candidate bank")

    other_scores: list[dict[str, Any]] = []
    known_total = 0.0
    for key in scope_keys:
        if key == target_key:
            continue
        source_section = candidate_sections[key]
        score_section = evidence_sections[key]
        if (
            score_section.get("status") != "usable"
            or score_section.get("full_score_source") != "explicit"
            or source_section.get("inferred")
            or score_section.get("heading_source") != "source"
        ):
            raise ValueError(f"other scoped section lacks explicit usable score: {key}")
        if int(score_section.get("candidate_count") or 0) != int(
            source_section.get("candidate_count") or 0
        ):
            raise ValueError(f"other scoped section score evidence is stale: {key}")
        locator = str(score_section.get("heading_locator") or "")
        text = source_text_by_locator.get(locator)
        if not locator or not text:
            raise ValueError(f"explicit score heading locator missing from source AST: {key}")
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if (
            text != score_section.get("heading")
            or text_hash != score_section.get("heading_text_sha256")
        ):
            raise ValueError(f"explicit score heading source mismatch: {key}")
        value = float(score_section["full_score"])
        known_total += value
        other_scores.append({
            "section_key": key,
            "score": value,
            "source_locator": locator,
            "source_text_sha256": text_hash,
        })

    residual = total_score - known_total
    if residual <= 0 or not math.isfinite(residual / target_candidates):
        raise ValueError("explicit total does not leave a positive per-question score")
    per_question = residual / target_candidates

    record = dict(score_evidence)
    updated_sections = []
    for section in record.get("sections") or []:
        if section.get("section_key") != target_key:
            updated_sections.append(section)
            continue
        updated = dict(section)
        resolution_method = str(
            resolution.get("method") or "explicit_volume_total_residual"
        )
        if resolution_method not in {
            "explicit_volume_total_residual",
            "automatic_explicit_volume_total_residual",
        }:
            raise ValueError("unsupported score residual resolution method")
        residual_resolution = {
            "method": resolution_method,
            "total_score": total_score,
            "total_locator": total_locator,
            "total_text_sha256": total_hash,
            "scope_section_keys": scope_keys,
            "other_section_scores": other_scores,
            "target_question_count": target_candidates,
            "residual_score": residual,
            "per_question_score": per_question,
        }
        if resolution_method == "explicit_volume_total_residual":
            residual_resolution.update({
                "reviewer": str(resolution.get("reviewer") or ""),
                "reviewed_at": str(resolution.get("reviewed_at") or ""),
                "review_note": str(resolution.get("review_note") or ""),
            })
            if (
                not residual_resolution["reviewer"]
                or not residual_resolution["reviewed_at"]
            ):
                raise ValueError("score resolution requires a reviewer and review date")
        else:
            rule_version = str(resolution.get("rule_version") or "")
            if not rule_version:
                raise ValueError("automatic score resolution requires rule_version")
            residual_resolution["rule_version"] = rule_version

        updated.update({
            "per_question_score": per_question,
            "full_score": residual,
            "per_question_source": "derived_from_exam_total_residual",
            "full_score_source": "derived_from_exam_total_residual",
            "status": "usable",
            "reasons": [],
            "residual_resolution": residual_resolution,
        })
        updated_sections.append(updated)

    counts = {"usable": 0, "incomplete": 0, "conflict": 0}
    for section in updated_sections:
        counts[str(section["status"])] += 1
    record["sections"] = updated_sections
    record["summary"] = {"total_sections": len(updated_sections), **counts}
    return record


def auto_apply_first_volume_residual_resolution(
    candidate_bank: Mapping[str, Any],
    score_evidence: Mapping[str, Any],
    *,
    source_text_by_locator: Mapping[str, str],
) -> dict[str, Any]:
    """Resolve one inferred first-volume score gap from explicit source totals.

    The fast path is deliberately narrow: the source must explicitly print a
    first-volume total and major-section count, the first N parsed sections must
    match that scope, exactly one scoped score row may be incomplete, and that
    row must come from an inferred heading. Every sibling score is still checked
    against its source locator/hash by apply_exam_total_residual_resolution.
    """
    sections = list(candidate_bank.get("sections") or [])
    score_rows = list(score_evidence.get("sections") or [])
    score_by_key = {
        str(row.get("section_key") or ""): row
        for row in score_rows
    }
    for locator, text in sorted(source_text_by_locator.items()):
        if "第一卷" not in text:
            continue
        declared_sections = _section_count_from_total_text(text)
        if declared_sections is None or FULL_SCORE_IN_TEXT.search(text) is None:
            continue
        if declared_sections <= 0 or declared_sections > len(sections):
            continue
        scope_keys = [
            str(section.get("section_key") or "")
            for section in sections[:declared_sections]
        ]
        scoped_rows = [score_by_key.get(key) for key in scope_keys]
        if any(row is None for row in scoped_rows):
            continue
        incomplete = [
            row
            for row in scoped_rows
            if row is not None and row.get("status") == "incomplete"
        ]
        if len(incomplete) != 1:
            continue
        target = incomplete[0]
        if target.get("heading_source") != "inferred":
            continue
        total_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return apply_exam_total_residual_resolution(
            candidate_bank,
            score_evidence,
            {
                "method": "automatic_explicit_volume_total_residual",
                "rule_version": "first_volume_residual_v1",
                "candidate_source_id": candidate_bank.get("source_id"),
                "target_section_key": target.get("section_key"),
                "scope_section_keys": scope_keys,
                "total_evidence": {
                    "locator": locator,
                    "text_sha256": total_hash,
                },
            },
            source_text_by_locator=source_text_by_locator,
        )
    return dict(score_evidence)


def apply_corroborated_series_section_score(
    candidate_bank: Mapping[str, Any],
    score_evidence: Mapping[str, Any],
    resolution: Mapping[str, Any],
    *,
    reference_score_evidence_by_source: Mapping[str, Mapping[str, Any]],
    reference_text_by_source_locator: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Fill one missing section score from repeated same-series source evidence.

    This is not presented as score text printed in the target source. It requires
    at least three independent source documents from the same corpus with the same
    section key, candidate count and explicit per-question score. Each reference
    heading is re-bound to its source locator/hash. Disagreement fails closed.
    """
    source_id = str(candidate_bank.get("source_id") or "")
    if source_id != str(score_evidence.get("candidate_source_id") or ""):
        raise ValueError("candidate bank and score evidence source mismatch")
    if source_id != str(resolution.get("candidate_source_id") or ""):
        raise ValueError("series score resolution source mismatch")

    target_key = str(resolution.get("target_section_key") or "")
    candidate_sections = {
        str(section.get("section_key") or ""): section
        for section in candidate_bank.get("sections") or []
    }
    evidence_sections = {
        str(section.get("section_key") or ""): section
        for section in score_evidence.get("sections") or []
    }
    target_source = candidate_sections.get(target_key)
    target = evidence_sections.get(target_key)
    if target_source is None or target is None:
        raise ValueError("series score resolution target section missing")
    if target.get("status") != "incomplete":
        raise ValueError("series score resolution target is not an incomplete gap")

    target_count = int(target_source.get("candidate_count") or 0)
    if target_count <= 0 or int(target.get("candidate_count") or 0) != target_count:
        raise ValueError("series score resolution target count is stale")

    reference_ids = [str(value) for value in resolution.get("reference_source_ids") or []]
    if len(reference_ids) < 3 or len(reference_ids) != len(set(reference_ids)):
        raise ValueError("series score resolution requires at least three unique references")
    if source_id in reference_ids:
        raise ValueError("target source cannot be its own series reference")

    references: list[dict[str, Any]] = []
    values: set[tuple[float, float]] = set()
    for reference_id in reference_ids:
        reference_bank = reference_score_evidence_by_source.get(reference_id)
        if reference_bank is None:
            raise ValueError(f"series score reference missing: {reference_id}")
        if str(reference_bank.get("candidate_source_id") or "") != reference_id:
            raise ValueError(f"series score reference identity mismatch: {reference_id}")
        if reference_bank.get("subject") != score_evidence.get("subject"):
            raise ValueError(f"series score reference subject mismatch: {reference_id}")

        reference_section = next(
            (
                section
                for section in reference_bank.get("sections") or []
                if str(section.get("section_key") or "") == target_key
            ),
            None,
        )
        if reference_section is None:
            raise ValueError(f"series score reference lacks target section: {reference_id}")
        if (
            reference_section.get("status") != "usable"
            or reference_section.get("heading_source") != "source"
            or reference_section.get("per_question_source") != "explicit"
            or reference_section.get("full_score_source")
            not in {"explicit", "derived_from_count_times_per_question"}
        ):
            raise ValueError(f"series score reference is not explicit enough: {reference_id}")
        if int(reference_section.get("candidate_count") or 0) != target_count:
            raise ValueError(f"series score reference count mismatch: {reference_id}")

        per_question = reference_section.get("per_question_score")
        full_score = reference_section.get("full_score")
        if per_question is None or full_score is None:
            raise ValueError(f"series score reference value missing: {reference_id}")

        locator = str(reference_section.get("heading_locator") or "")
        source_text = (reference_text_by_source_locator.get(reference_id) or {}).get(locator)
        if not locator or not source_text:
            raise ValueError(f"series score reference locator missing: {reference_id}")
        text_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if (
            source_text != reference_section.get("heading")
            or text_hash != reference_section.get("heading_text_sha256")
        ):
            raise ValueError(f"series score reference source mismatch: {reference_id}")

        value = (float(per_question), float(full_score))
        values.add(value)
        references.append({
            "source_id": reference_id,
            "section_key": target_key,
            "candidate_count": target_count,
            "heading_locator": locator,
            "heading_text_sha256": text_hash,
            "per_question_score": value[0],
            "full_score": value[1],
        })

    if len(values) != 1:
        raise ValueError("series score references disagree")
    per_question, full_score = next(iter(values))
    if not math.isclose(
        per_question * target_count,
        full_score,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError("series score reference arithmetic does not match target count")

    record = dict(score_evidence)
    updated_sections: list[dict[str, Any]] = []
    for section in record.get("sections") or []:
        if str(section.get("section_key") or "") != target_key:
            updated_sections.append(section)
            continue
        updated = dict(section)
        updated.update({
            "per_question_score": per_question,
            "full_score": full_score,
            "per_question_source": "corroborated_series_section_score",
            "full_score_source": "corroborated_series_section_score",
            "status": "usable",
            "reasons": [],
            "series_resolution": {
                "method": "corroborated_series_section_score",
                "rule_version": "same_series_explicit_section_v1",
                "reference_count": len(references),
                "references": references,
            },
        })
        updated_sections.append(updated)

    counts = {"usable": 0, "incomplete": 0, "conflict": 0}
    for section in updated_sections:
        counts[str(section["status"])] += 1
    record["sections"] = updated_sections
    record["summary"] = {"total_sections": len(updated_sections), **counts}
    return record


def apply_score_evidence(
    verified_candidate_bank: Mapping[str, Any],
    score_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach only unambiguous score evidence to verified candidates.

    A section-level full score is usable as the question score only when the section
    contains exactly one parsed candidate. Otherwise an explicit/derived per-question
    score is required.
    """
    if verified_candidate_bank.get("candidate_source_id") != score_evidence.get("candidate_source_id"):
        raise ValueError("verified candidate bank and score evidence source mismatch")
    if verified_candidate_bank.get("subject") != score_evidence.get("subject"):
        raise ValueError("verified candidate bank and score evidence subject mismatch")

    score_by_section = {
        str(item["section_key"]): item
        for item in score_evidence.get("sections") or []
    }

    assigned: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for candidate in verified_candidate_bank.get("verified") or []:
        section = score_by_section.get(str(candidate.get("section_key") or ""))
        if section is None:
            unresolved.append({
                "candidate_id": candidate["candidate_id"],
                "reason": "missing_section_score_evidence",
            })
            continue
        if section.get("status") == "conflict":
            unresolved.append({
                "candidate_id": candidate["candidate_id"],
                "reason": "section_score_conflict",
            })
            continue

        score = section.get("per_question_score")
        score_source = section.get("per_question_source")
        if score is None and int(section.get("candidate_count") or 0) == 1:
            score = section.get("full_score")
            score_source = section.get("full_score_source")

        if score is None:
            unresolved.append({
                "candidate_id": candidate["candidate_id"],
                "reason": "score_incomplete",
            })
            continue

        assigned.append({
            **candidate,
            "score": float(score),
            "score_source": score_source,
        })

    return {
        "schema_version": 1,
        "subject": verified_candidate_bank.get("subject"),
        "candidate_source_id": verified_candidate_bank.get("candidate_source_id"),
        "assigned": assigned,
        "unresolved": unresolved,
        "summary": {
            "assigned": len(assigned),
            "unresolved": len(unresolved),
        },
    }
