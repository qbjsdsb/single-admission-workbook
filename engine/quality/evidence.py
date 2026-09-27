from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, Mapping


@dataclass(frozen=True)
class EvidenceDecision:
    question_id: str
    status: str
    normalized_value: str | None
    source_ids: tuple[str, ...]
    variants: tuple[str, ...]


def normalize_answer(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", "", text)
    # Cosmetic terminal punctuation must not manufacture a conflict.
    text = text.rstrip("。．.；;，,")
    return text.upper()


def evaluate_answer_evidence(
    question_id: str, evidence: Iterable[Mapping[str, object]]
) -> EvidenceDecision:
    relevant = [e for e in evidence if e.get("question_id") == question_id]
    groups: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for item in relevant:
        value = normalize_answer(item.get("value"))
        if value:
            groups[value].append(item)

    if not groups:
        return EvidenceDecision(question_id, "missing", None, (), ())
    if len(groups) > 1:
        variants = tuple(sorted(groups))
        sources = tuple(sorted(str(e.get("source_id", "")) for e in relevant))
        return EvidenceDecision(question_id, "conflict", None, sources, variants)

    value, group = next(iter(groups.items()))
    verified = [e for e in group if e.get("status") == "verified"]
    status = "agreed" if len(verified) >= 2 else "single"
    sources = tuple(sorted(str(e.get("source_id", "")) for e in group))
    return EvidenceDecision(question_id, status, value, sources, (value,))


def validate_release_evidence(
    question_ids: Iterable[str],
    evidence: Iterable[Mapping[str, object]],
    *,
    require_verified: bool = True,
) -> list[str]:
    grouped = defaultdict(list)
    for item in evidence:
        grouped[item.get('question_id')].append(item)
    errors: list[str] = []
    for question_id in question_ids:
        evidence = grouped[question_id]
        decision = evaluate_answer_evidence(question_id, evidence)
        if decision.status == "missing":
            errors.append(f"{question_id}: missing answer evidence")
        elif decision.status == "conflict":
            errors.append(
                f"{question_id}: conflicting answer evidence {', '.join(decision.variants)}"
            )
        elif require_verified:
            relevant = [
                e for e in evidence
                if e.get("question_id") == question_id
                and normalize_answer(e.get("value")) == decision.normalized_value
            ]
            if not any(e.get("status") == "verified" for e in relevant):
                errors.append(f"{question_id}: answer evidence is not verified")
    return errors
