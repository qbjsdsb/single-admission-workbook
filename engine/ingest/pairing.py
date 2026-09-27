from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from typing import Iterable, Mapping

ANSWER_ROLES = {"teacher", "solution", "answer"}


@dataclass(frozen=True)
class PairCandidate:
    pair_key: str
    student_path: str
    companion_path: str
    companion_role: str
    confidence: str = "name_exact"


@dataclass(frozen=True)
class QuestionPairCandidate:
    student_id: str
    companion_id: str | None
    confidence: str
    score: float
    reason: str


def exact_pair_candidates(items: Iterable[Mapping[str, object]]) -> list[PairCandidate]:
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for item in items:
        groups[str(item["pair_key"])].append(item)

    out: list[PairCandidate] = []
    for key, group in groups.items():
        students = [x for x in group if x.get("role") == "student"]
        companions = [x for x in group if x.get("role") in ANSWER_ROLES]
        for student in students:
            for companion in companions:
                if student.get("subject") != companion.get("subject"):
                    continue
                out.append(PairCandidate(
                    pair_key=key,
                    student_path=str(student["path"]),
                    companion_path=str(companion["path"]),
                    companion_role=str(companion["role"]),
                ))
    return sorted(out, key=lambda x: (x.student_path, x.companion_path))


def _flatten(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "".join(_flatten(v) for v in value)
    if isinstance(value, tuple):
        return "".join(_flatten(v) for v in value)
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text") or "")
        if "tex" in value:
            return str(value.get("tex") or "")
        if "children" in value:
            return _flatten(value.get("children"))
        if "content" in value:
            return _flatten(value.get("content"))
        return "".join(_flatten(value.get(k)) for k in sorted(value))
    return str(value)


def normalize_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", _flatten(value)).lower()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def question_record_fingerprint(record: Mapping[str, object]) -> str:
    payload = {
        "section": normalize_match_text(record.get("section_key")),
        "stem": normalize_match_text(record.get("stem")),
        "options": [
            normalize_match_text(option)
            for option in (record.get("options") or [])
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _record_similarity(a: Mapping[str, object], b: Mapping[str, object]) -> float:
    stem_a = normalize_match_text(a.get("stem"))
    stem_b = normalize_match_text(b.get("stem"))
    stem_score = SequenceMatcher(None, stem_a, stem_b).ratio() if stem_a and stem_b else 0.0

    options_a = normalize_match_text(a.get("options"))
    options_b = normalize_match_text(b.get("options"))
    option_score = (
        SequenceMatcher(None, options_a, options_b).ratio()
        if options_a and options_b else 0.0
    )
    section_bonus = 0.10 if a.get("section_key") and a.get("section_key") == b.get("section_key") else 0.0
    number_bonus = 0.05 if a.get("number") is not None and a.get("number") == b.get("number") else 0.0
    return min(1.0, 0.65 * stem_score + 0.20 * option_score + section_bonus + number_bonus)


def pair_question_records(
    student_records: Iterable[Mapping[str, object]],
    companion_records: Iterable[Mapping[str, object]],
    *,
    min_score: float = 0.88,
    ambiguity_margin: float = 0.04,
) -> list[QuestionPairCandidate]:
    """Pair questions by content, not question number alone.

    Exact structural fingerprints win. Fuzzy matches must clear a conservative
    threshold and must not have another near-equal candidate. Ambiguity remains
    explicit and must be reviewed.
    """
    students = list(student_records)
    companions = list(companion_records)
    unused = set(range(len(companions)))
    results: list[QuestionPairCandidate] = []

    exact: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(companions):
        exact[question_record_fingerprint(record)].append(index)

    for student in students:
        sid = str(student.get("id") or student.get("number") or "")
        fingerprint = question_record_fingerprint(student)
        exact_candidates = [i for i in exact.get(fingerprint, []) if i in unused]
        if len(exact_candidates) == 1:
            index = exact_candidates[0]
            unused.remove(index)
            results.append(QuestionPairCandidate(
                sid,
                str(companions[index].get("id") or companions[index].get("number") or ""),
                "exact",
                1.0,
                "content_fingerprint",
            ))
            continue
        if len(exact_candidates) > 1:
            results.append(QuestionPairCandidate(
                sid, None, "ambiguous", 1.0, "duplicate_exact_candidates"
            ))
            continue

        scored = sorted(
            (
                (_record_similarity(student, companions[index]), index)
                for index in unused
            ),
            reverse=True,
        )
        if not scored or scored[0][0] < min_score:
            results.append(QuestionPairCandidate(
                sid, None, "unmatched", scored[0][0] if scored else 0.0, "below_threshold"
            ))
            continue

        best_score, best_index = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best_score - second_score < ambiguity_margin:
            results.append(QuestionPairCandidate(
                sid, None, "ambiguous", best_score, "near_equal_candidates"
            ))
            continue

        unused.remove(best_index)
        results.append(QuestionPairCandidate(
            sid,
            str(companions[best_index].get("id") or companions[best_index].get("number") or ""),
            "high",
            best_score,
            "content_similarity",
        ))

    return results
