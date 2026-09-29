from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

VISUAL_CUE_RE = re.compile(
    r"(?:下图|上图|右图|左图|见图|如图|图中|图示|图表|下表|上表|表中|右表|左表)"
)

FORBIDDEN_ANALYSIS_FRAGMENTS = (
    "本题为时事政治/知识识记填空",
    "根据题干所考查的概念、原理和材料信息进行判断",
    "先概括材料主体、措施与结果",
)


def _iter_rich(nodes: object) -> Iterable[Mapping[str, Any]]:
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        yield node
        children = node.get("children")
        if isinstance(children, list):
            yield from _iter_rich(children)


def _plain_text(nodes: object) -> str:
    parts: list[str] = []
    for node in _iter_rich(nodes):
        if node.get("type") == "text":
            parts.append(str(node.get("text") or ""))
    return "".join(parts)


def _has_node(nodes: object, *types: str) -> bool:
    wanted = set(types)
    return any(node.get("type") in wanted for node in _iter_rich(nodes))


def validate_question_content(question: Mapping[str, Any], *, location: str | None = None) -> list[str]:
    """Publication-level semantic/fidelity guards.

    These checks are intentionally fail-closed. They do not attempt to repair or
    infer missing source content. A blocked item must return to source extraction
    or editorial review.
    """
    qid = str(location or question.get("id") or "<unknown>")
    errors: list[str] = []
    stem = question.get("stem") or []
    stem_text = _plain_text(stem)

    if VISUAL_CUE_RE.search(stem_text) and not _has_node(stem, "image", "table"):
        errors.append(f"{qid}: visual cue present but source visual/table is missing")

    if question.get("kind") == "fill_blank" and not _has_node(stem, "blank"):
        errors.append(f"{qid}: fill_blank must preserve explicit blank rich node")

    analysis = question.get("analysis")
    analysis_text = _plain_text(analysis) if isinstance(analysis, list) else str(analysis or "")
    for fragment in FORBIDDEN_ANALYSIS_FRAGMENTS:
        if fragment in analysis_text:
            errors.append(f"{qid}: placeholder/template teacher analysis is not publishable")
            break

    return errors


def validate_publication_content(questions: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    for question in questions:
        qid = str(question.get("id") or "<unknown>")
        errors.extend(validate_question_content(question, location=qid))
        for index, child in enumerate(question.get("children") or [], start=1):
            child_id = str(child.get("id") or f"child-{index}")
            errors.extend(
                validate_question_content(
                    child,
                    location=f"{qid}/{child_id}",
                )
            )
    return errors
