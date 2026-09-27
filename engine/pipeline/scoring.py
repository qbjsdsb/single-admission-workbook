from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping


NUMBER = r"([0-9]+(?:\.[0-9]+)?)"
COUNT_RE = re.compile(r"共\s*(\d+)\s*(?:小题|题)")
PER_RE = re.compile(r"(?:每小题|每题)\s*" + NUMBER + r"\s*分")
FULL_RE = re.compile(r"(?:满分|总分|共计)\s*" + NUMBER + r"\s*分")
FULL_ALT_RE = re.compile(r"共\s*" + NUMBER + r"\s*分")


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
    full_score = _number(full_match)
    full_score_source = "explicit" if full_score is not None else None

    reasons: list[str] = []

    if declared_count is not None and candidate_count and declared_count != candidate_count:
        reasons.append(
            f"declared_count_{declared_count}_!=_parsed_count_{candidate_count}"
        )

    if (
        declared_count
        and full_score is not None
        and per_question_score is None
        and declared_count > 0
    ):
        per_question_score = full_score / declared_count
        per_question_source = "derived_from_full_score"

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
    sections = [
        parse_section_score(section)
        for section in candidate_bank.get("sections") or []
    ]

    records = []
    for section in sections:
        records.append({
            "section_key": section.section_key,
            "heading": section.heading,
            "candidate_count": section.candidate_count,
            "declared_count": section.declared_count,
            "per_question_score": section.per_question_score,
            "full_score": section.full_score,
            "per_question_source": section.per_question_source,
            "full_score_source": section.full_score_source,
            "status": section.status,
            "reasons": list(section.reasons),
        })

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


def apply_score_evidence(
    verified_candidate_bank: Mapping[str, Any],
    score_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach only unambiguous score evidence to verified candidates.

    A section-level full score is usable as the question score only when the section
    contains exactly one parsed candidate. Otherwise an explicit/derived per-question
    score is required.
    """
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
