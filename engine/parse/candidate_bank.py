from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from engine.parse.exam_split import QUESTION_RE, detect_section
from engine.parse.options import parse_options


@dataclass(frozen=True)
class ParagraphEvidence:
    locator: str
    text: str


def _stable_id(*parts: object) -> str:
    payload = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _paragraph_text(block: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    if block.get("type") != "paragraph":
        return None, [f"unsupported_block:{block.get('feature') or block.get('type')}"]

    text_parts: list[str] = []
    blockers: list[str] = []
    for inline in block.get("inlines") or []:
        kind = inline.get("type")
        if kind == "text":
            text_parts.append(str(inline.get("text") or ""))
        else:
            blockers.append(f"unsupported_inline:{kind}")
    # A paragraph can contain several instances of the same unsupported rich
    # feature (for example, two images). Keep the blocker evidence unique so
    # it satisfies the candidate-bank contract without hiding any new type.
    return "".join(text_parts).strip(), list(dict.fromkeys(blockers))


def safe_paragraphs(document: Mapping[str, Any]) -> tuple[list[ParagraphEvidence], list[dict[str, Any]]]:
    paragraphs: list[ParagraphEvidence] = []
    blockers: list[dict[str, Any]] = []
    for block in document.get("blocks") or []:
        locator = str(block.get("locator") or "")
        text, reasons = _paragraph_text(block)
        if reasons:
            blockers.append({"locator": locator, "reasons": reasons})
            continue
        if text:
            paragraphs.append(ParagraphEvidence(locator, text))
    return paragraphs, blockers


def _strip_question_prefix(text: str) -> tuple[int | None, str]:
    match = QUESTION_RE.match(text)
    if not match:
        return None, text.strip()
    return int(match.group(1)), match.group(2).strip()


def _question_slices(paragraphs: list[ParagraphEvidence]) -> list[tuple[int, list[ParagraphEvidence]]]:
    starts: list[tuple[int, int]] = []
    for index, paragraph in enumerate(paragraphs):
        match = QUESTION_RE.match(paragraph.text)
        if match:
            starts.append((index, int(match.group(1))))

    out: list[tuple[int, list[ParagraphEvidence]]] = []
    for pos, (start, number) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(paragraphs)
        out.append((number, paragraphs[start:end]))
    return out


def _longest_consecutive_question_run(
    paragraphs: list[ParagraphEvidence],
    *,
    minimum_questions: int = 5,
) -> list[ParagraphEvidence]:
    """Find a likely unheaded question section without consuming notice items.

    Real papers can omit the first "single choice" heading. We only infer a
    section when there is a long 1,2,3,... run. Short notice lists such as
    "1. fill in your name / 2. use a pencil" are therefore ignored.
    """
    numbered = []
    for index, paragraph in enumerate(paragraphs):
        match = QUESTION_RE.match(paragraph.text)
        if match:
            numbered.append((index, int(match.group(1))))

    best: list[tuple[int, int]] = []
    current: list[tuple[int, int]] = []
    for item in numbered:
        index, number = item
        if number == 1:
            if len(current) > len(best):
                best = current
            current = [item]
        elif current and number == current[-1][1] + 1:
            current.append(item)
        else:
            if len(current) > len(best):
                best = current
            current = []
    if len(current) > len(best):
        best = current

    if len(best) < minimum_questions:
        return []
    return paragraphs[best[0][0]:]


def _simple_candidate(
    *,
    source_id: str,
    subject: str,
    section_key: str,
    kind: str,
    number: int | None,
    paragraphs: list[ParagraphEvidence],
) -> dict[str, Any]:
    texts = [p.text for p in paragraphs]
    first_number, first_rest = _strip_question_prefix(texts[0]) if texts else (None, "")
    if number is None:
        number = first_number
    normalized = [first_rest] + texts[1:] if texts else []

    options_result = parse_options(normalized) if kind == "single_choice" else None
    status = "parsed"
    review_reasons: list[str] = []
    options: list[dict[str, str]] = []

    if kind == "single_choice":
        if options_result is None or options_result.status != "ok":
            status = "needs_review"
            review_reasons.append(
                "option_parse_" + (options_result.status if options_result else "missing")
            )
            stem_text = "\n".join(normalized).strip()
        else:
            stem_text = "\n".join(options_result.stem_paragraphs).strip()
            options = [
                {"label": label, "text": value}
                for label, value in options_result.options
            ]
    else:
        stem_text = "\n".join(normalized).strip()

    locator_key = _stable_id(*(p.locator for p in paragraphs))
    candidate_id = (
        f"{source_id}:q:{number}:{locator_key[:8]}"
        if number is not None
        else f"{source_id}:item:{_stable_id(section_key, locator_key, stem_text)}"
    )
    record: dict[str, Any] = {
        "candidate_id": candidate_id,
        "source_id": source_id,
        "subject": subject,
        "source_number": number,
        "section_key": section_key,
        "kind": kind,
        "stem_text": stem_text,
        "locators": [p.locator for p in paragraphs],
        "status": status,
        "review_reasons": review_reasons,
    }
    if options:
        record["options"] = options
    return record


def _extract_cloze_group(
    source_id: str,
    subject: str,
    section_key: str,
    paragraphs: list[ParagraphEvidence],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    first_question = next(
        (i for i, p in enumerate(paragraphs) if QUESTION_RE.match(p.text)),
        len(paragraphs),
    )
    shared = paragraphs[:first_question]
    question_part = paragraphs[first_question:]
    group_id = f"{source_id}:group:{_stable_id(section_key, *(p.locator for p in shared))}"
    candidates: list[dict[str, Any]] = []

    for number, slice_ in _question_slices(question_part):
        record = _simple_candidate(
            source_id=source_id,
            subject=subject,
            section_key=section_key,
            kind="single_choice",
            number=number,
            paragraphs=slice_,
        )
        record["group_id"] = group_id
        candidates.append(record)

    groups = [{
        "group_id": group_id,
        "kind": "cloze_group",
        "section_key": section_key,
        "label": None,
        "shared_material_text": "\n".join(p.text for p in shared).strip(),
        "locators": [p.locator for p in shared],
        "child_candidate_ids": [q["candidate_id"] for q in candidates],
    }]
    return candidates, groups


def _extract_reading_groups(
    source_id: str,
    subject: str,
    section_key: str,
    paragraphs: list[ParagraphEvidence],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    boundaries: list[tuple[int, str]] = []
    for index, paragraph in enumerate(paragraphs):
        label = paragraph.text.strip()
        if re.fullmatch(r"[A-Z]", label):
            boundaries.append((index, label))

    if not boundaries:
        candidates, groups = _extract_cloze_group(
            source_id, subject, section_key, paragraphs
        )
        for group in groups:
            group["kind"] = "reading_group"
        return candidates, groups

    candidates: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []

    for pos, (start, label) in enumerate(boundaries):
        end = boundaries[pos + 1][0] if pos + 1 < len(boundaries) else len(paragraphs)
        body = paragraphs[start + 1:end]
        first_question = next(
            (i for i, p in enumerate(body) if QUESTION_RE.match(p.text)),
            len(body),
        )
        shared = body[:first_question]
        question_part = body[first_question:]
        group_id = f"{source_id}:reading:{label}:{_stable_id(*(p.locator for p in shared))}"

        local_candidates: list[dict[str, Any]] = []
        for number, slice_ in _question_slices(question_part):
            record = _simple_candidate(
                source_id=source_id,
                subject=subject,
                section_key=section_key,
                kind="single_choice",
                number=number,
                paragraphs=slice_,
            )
            record["group_id"] = group_id
            local_candidates.append(record)
            candidates.append(record)

        groups.append({
            "group_id": group_id,
            "kind": "reading_group",
            "section_key": section_key,
            "label": label,
            "shared_material_text": "\n".join(p.text for p in shared).strip(),
            "locators": [p.locator for p in shared],
            "child_candidate_ids": [q["candidate_id"] for q in local_candidates],
        })

    return candidates, groups


def extract_candidate_bank(
    document: Mapping[str, Any],
    *,
    subject: str,
    source_id: str,
) -> dict[str, Any]:
    if subject not in {"english", "politics"}:
        raise ValueError("candidate-bank v0.1 currently supports only english/politics fast lane")

    paragraphs, blockers = safe_paragraphs(document)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    pre_section: list[ParagraphEvidence] = []

    for paragraph in paragraphs:
        detected = detect_section(subject, paragraph.text)
        if detected:
            section_key, kind = detected
            current = {
                "section_key": section_key,
                "kind": kind,
                "heading": paragraph.text,
                "heading_locator": paragraph.locator,
                "paragraphs": [],
                "inferred": False,
            }
            sections.append(current)
        elif current is not None:
            current["paragraphs"].append(paragraph)
        else:
            pre_section.append(paragraph)

    # Some real papers begin questions directly and only label section II onward.
    # Recover a long 1..N run, but keep it review-gated because the heading was absent.
    if not any(section["section_key"] == "single_choice" for section in sections):
        inferred_body = _longest_consecutive_question_run(pre_section)
        if inferred_body:
            sections.insert(0, {
                "section_key": "single_choice",
                "kind": "single_choice",
                "heading": "[inferred missing single-choice heading]",
                "heading_locator": inferred_body[0].locator,
                "paragraphs": inferred_body,
                "inferred": True,
            })

    candidates: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    section_summaries: list[dict[str, Any]] = []

    for section in sections:
        body: list[ParagraphEvidence] = section["paragraphs"]
        kind = section["kind"]
        section_key = section["section_key"]

        before = len(candidates)
        if kind == "composition":
            if body:
                candidates.append(_simple_candidate(
                    source_id=source_id,
                    subject=subject,
                    section_key=section_key,
                    kind="composition",
                    number=None,
                    paragraphs=body,
                ))
        elif kind == "cloze_group":
            new_candidates, new_groups = _extract_cloze_group(
                source_id, subject, section_key, body
            )
            candidates.extend(new_candidates)
            groups.extend(new_groups)
        elif kind == "reading_group":
            new_candidates, new_groups = _extract_reading_groups(
                source_id, subject, section_key, body
            )
            candidates.extend(new_candidates)
            groups.extend(new_groups)
        else:
            for number, slice_ in _question_slices(body):
                candidates.append(_simple_candidate(
                    source_id=source_id,
                    subject=subject,
                    section_key=section_key,
                    kind=kind,
                    number=number,
                    paragraphs=slice_,
                ))

        if section.get("inferred"):
            for candidate in candidates[before:]:
                if candidate["status"] == "parsed":
                    candidate["status"] = "needs_review"
                if "section_heading_missing_inferred_single_choice" not in candidate["review_reasons"]:
                    candidate["review_reasons"].append(
                        "section_heading_missing_inferred_single_choice"
                    )

        section_summaries.append({
            "section_key": section_key,
            "kind": kind,
            "heading": section["heading"],
            "heading_locator": section["heading_locator"],
            "candidate_count": len(candidates) - before,
            "inferred": bool(section.get("inferred")),
        })

    status_counts: dict[str, int] = {}
    for candidate in candidates:
        status_counts[candidate["status"]] = status_counts.get(candidate["status"], 0) + 1

    return {
        "schema_version": 1,
        "source_id": source_id,
        "subject": subject,
        "sections": section_summaries,
        "candidates": candidates,
        "groups": groups,
        "blockers": blockers,
        "summary": {
            "candidate_count": len(candidates),
            "group_count": len(groups),
            "blocker_count": len(blockers),
            "status_counts": status_counts,
        },
    }


def dumps_candidate_bank(bank: Mapping[str, Any]) -> str:
    return json.dumps(bank, ensure_ascii=False, indent=2, sort_keys=False)
