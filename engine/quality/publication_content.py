from __future__ import annotations

from collections import Counter
import hashlib
import re
from typing import Any, Iterable, Mapping

VISUAL_CUE_RE = re.compile(
    r"(?:下图|上图|右图|左图|见图|如图|图中|图示|图表|下表|上表|表中|右表|左表)"
)

FORBIDDEN_ANALYSIS_FRAGMENTS = (
    "本题为时事政治/知识识记填空",
    "根据题干所考查的概念、原理和材料信息进行判断",
    "先概括材料主体、措施与结果",
    "本题为开放写作。先逐项圈出题干中的内容要求",
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


def _analysis_text(question: Mapping[str, Any]) -> str:
    analysis = question.get("analysis")
    text = _plain_text(analysis) if isinstance(analysis, list) else str(analysis or "")
    return re.sub(r"\s+", " ", text).strip()


def validate_publication_content(questions: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    materialized = list(questions)
    analysis_rows: list[tuple[str, str]] = []

    for question in materialized:
        qid = str(question.get("id") or "<unknown>")
        errors.extend(validate_question_content(question, location=qid))
        text = _analysis_text(question)
        if text:
            analysis_rows.append((qid, text))

        for index, child in enumerate(question.get("children") or [], start=1):
            child_id = str(child.get("id") or f"child-{index}")
            location = f"{qid}/{child_id}"
            errors.extend(
                validate_question_content(
                    child,
                    location=location,
                )
            )
            child_text = _analysis_text(child)
            if child_text:
                analysis_rows.append((location, child_text))

    composition_rows = [
        (qid, _analysis_text(question))
        for question in materialized
        if question.get("kind") == "composition"
        for qid in [str(question.get("id") or "<unknown>")]
        if _analysis_text(question)
    ]
    composition_counts = Counter(
        text for _, text in composition_rows if len(text) >= 40
    )
    for text, count in composition_counts.items():
        if count < 2:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        errors.append(
            "composition teacher analysis repeated "
            f"{count} times (analysis_sha256={digest})"
        )
    # Exact repeated prose across many distinct questions is a reliable signal
    # that a generic filler/template has leaked into the teacher edition. Use a
    # deliberately high threshold so ordinary concept overlap is not blocked.
    counts = Counter(text for _, text in analysis_rows if len(text) >= 24)
    for text, count in counts.items():
        if count < 8:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        errors.append(
            "teacher analysis boilerplate repeated "
            f"{count} times (analysis_sha256={digest})"
        )

    return errors
