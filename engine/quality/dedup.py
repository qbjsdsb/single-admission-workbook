from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from typing import Iterable, Mapping


@dataclass(frozen=True)
class DuplicateCluster:
    fingerprint: str
    question_ids: tuple[str, ...]


@dataclass(frozen=True)
class NearDuplicate:
    left_id: str
    right_id: str
    similarity: float


def _normalize(value):
    if isinstance(value, str):
        text = unicodedata.normalize("NFKC", value)
        return re.sub(r"\s+", " ", text).strip()
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(value[k]) for k in sorted(value)}
    return value


def canonical_content_payload(question: Mapping[str, object]) -> dict:
    """Fields that define the actual exercise, excluding answer/explanation/source metadata."""
    return _normalize({
        "subject": question.get("subject"),
        "kind": question.get("kind"),
        "stem": question.get("stem"),
        "options": question.get("options"),
        "parts": question.get("parts"),
    })


def content_fingerprint(question: Mapping[str, object]) -> str:
    payload = json.dumps(
        canonical_content_payload(question),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def exact_duplicate_clusters(
    questions: Iterable[Mapping[str, object]],
) -> list[DuplicateCluster]:
    groups: dict[str, list[str]] = defaultdict(list)
    for q in questions:
        groups[content_fingerprint(q)].append(str(q.get("id") or ""))
    return [
        DuplicateCluster(fp, tuple(sorted(ids)))
        for fp, ids in sorted(groups.items())
        if len(ids) > 1
    ]


def _plain(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_plain(v) for v in value)
    if isinstance(value, dict):
        for key in ("text", "tex", "children", "content", "stem"):
            if key in value:
                return _plain(value[key])
        return "".join(_plain(value[k]) for k in sorted(value))
    return str(value or "")


def near_duplicate_candidates(
    questions: Iterable[Mapping[str, object]], threshold: float = 0.94
) -> list[NearDuplicate]:
    """Advisory only: never auto-merge near duplicates."""
    items = list(questions)
    out: list[NearDuplicate] = []
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            if left.get("subject") != right.get("subject"):
                continue
            a = re.sub(r"\W+", "", unicodedata.normalize("NFKC", _plain(left.get("stem"))).lower())
            b = re.sub(r"\W+", "", unicodedata.normalize("NFKC", _plain(right.get("stem"))).lower())
            if not a or not b:
                continue
            score = SequenceMatcher(None, a, b).ratio()
            if score >= threshold and content_fingerprint(left) != content_fingerprint(right):
                out.append(NearDuplicate(
                    str(left.get("id") or ""),
                    str(right.get("id") or ""),
                    round(score, 6),
                ))
    return sorted(out, key=lambda x: (-x.similarity, x.left_id, x.right_id))
