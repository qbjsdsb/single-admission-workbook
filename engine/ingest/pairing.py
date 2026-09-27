from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping

ANSWER_ROLES = {"teacher", "solution", "answer"}

@dataclass(frozen=True)
class PairCandidate:
    pair_key: str
    student_path: str
    companion_path: str
    companion_role: str
    confidence: str = "name_exact"

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
