from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Any, Mapping

from engine.parse.exam_split import QUESTION_RE, detect_section
from engine.parse.options import parse_options


@dataclass(frozen=True)
class ParagraphEvidence:
    locator: str
    text: str


def _normalize_choice(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).strip()
    return value.upper()


def _stable_id(*parts: object) -> str:
    payload = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _safe_paragraphs(document: Mapping[str, Any]) -> tuple[list[ParagraphEvidence], list[dict[str, Any]]]:
    paragraphs: list[ParagraphEvidence] = []
    blockers: list[dict[str, Any]] = []
    for block in document.get("blocks") or []:
        locator = str(block.get("locator") or "")
        if block.get("type") != "paragraph":
            blockers.append({
                "locator": locator,
                "reasons": [f"unsupported_block:{block.get('feature') or block.get('type')}"],
            })
            continue
        text_parts: list[str] = []
        unsupported: list[str] = []
        for inline in block.get("inlines") or []:
            if inline.get("type") == "text":
                text_parts.append(str(inline.get("text") or ""))
            else:
                unsupported.append(f"unsupported_inline:{inline.get('type')}")
        text = "".join(text_parts).strip()
        if unsupported:
            blockers.append({"locator": locator, "reasons": unsupported})
        if text:
            paragraphs.append(ParagraphEvidence(locator, text))
    return paragraphs, blockers


EXPLICIT_NUMBERED_ANSWER = re.compile(
    r"^\s*(\d{1,3})\s*[.．、]?\s*答案\s*[:：]?\s*(.+?)\s*$"
)
PLAIN_ANSWER = re.compile(r"^\s*答案\s*[:：]?\s*(.+?)\s*$")
ANALYSIS = re.compile(r"^\s*解析\s*[:：]?\s*(.+?)\s*$")
CORE = re.compile(r"^\s*题干核心\s*[:：]?\s*(.+?)\s*$")

# Supports "1.A 2.B ..." and "26.甲27.乙" while stopping at the next numbered item.
COMPACT_ITEM = re.compile(
    r"(\d{1,3})\s*[.．、]\s*(.+?)(?=(?:\s*\d{1,3}\s*[.．、])|$)"
)


def _compact_items(text: str) -> list[tuple[int, str]]:
    hits = [
        (int(match.group(1)), match.group(2).strip())
        for match in COMPACT_ITEM.finditer(text)
        if match.group(2).strip()
    ]
    return hits if len(hits) >= 2 else []


def _question_prompt_record(
    source_id: str,
    subject: str,
    section_key: str | None,
    number: int,
    paragraphs: list[ParagraphEvidence],
) -> dict[str, Any] | None:
    if not paragraphs:
        return None
    first = QUESTION_RE.match(paragraphs[0].text)
    if not first:
        return None

    body: list[str] = [first.group(2).strip()]
    for paragraph in paragraphs[1:]:
        text = paragraph.text.strip()
        if (
            PLAIN_ANSWER.match(text)
            or ANALYSIS.match(text)
            or CORE.match(text)
            or EXPLICIT_NUMBERED_ANSWER.match(text)
        ):
            break
        body.append(text)

    parsed = parse_options(body)
    stem_text = "\n".join(parsed.stem_paragraphs if parsed.status == "ok" else body).strip()
    record: dict[str, Any] = {
        "id": f"{source_id}:prompt:{number}:{_stable_id(*(p.locator for p in paragraphs))[:8]}",
        "number": number,
        "section_key": section_key,
        "stem": stem_text,
        "locators": [p.locator for p in paragraphs],
        "match_status": "content_available",
    }
    if parsed.status == "ok":
        record["options"] = [
            {"label": label, "text": value}
            for label, value in parsed.options
        ]
    else:
        record["option_status"] = parsed.status
    return record


def extract_evidence_bank(
    document: Mapping[str, Any],
    *,
    subject: str,
    source_id: str,
) -> dict[str, Any]:
    if subject not in {"english", "politics"}:
        raise ValueError("evidence-bank v0.1 currently supports only english/politics fast lane")

    paragraphs, blockers = _safe_paragraphs(document)
    evidence: list[dict[str, Any]] = []
    question_records: list[dict[str, Any]] = []

    current_section: str | None = None
    current_number: int | None = None
    current_question_paragraphs: list[ParagraphEvidence] = []
    seen_prompt_keys: set[tuple[str | None, int]] = set()

    def emit(
        *,
        number: int,
        field: str,
        value: str,
        locator: str,
        mode: str,
    ) -> None:
        normalized = value.strip()
        if not normalized:
            return
        evidence.append({
            "evidence_id": f"{source_id}:{field}:{number}:{_stable_id(locator, normalized)}",
            "source_id": source_id,
            "subject": subject,
            "source_number": number,
            "section_key": current_section,
            "field": field,
            "value": normalized,
            "locator": locator,
            "extraction_mode": mode,
            "status": "extracted",
        })

    def flush_prompt() -> None:
        nonlocal current_question_paragraphs
        if current_number is None or not current_question_paragraphs:
            current_question_paragraphs = []
            return
        key = (current_section, current_number)
        if key not in seen_prompt_keys:
            record = _question_prompt_record(
                source_id, subject, current_section, current_number, current_question_paragraphs
            )
            if record:
                question_records.append(record)
                seen_prompt_keys.add(key)
        current_question_paragraphs = []

    for paragraph in paragraphs:
        text = paragraph.text.strip()
        section = detect_section(subject, text)
        if section:
            flush_prompt()
            current_section = section[0]
            current_number = None
            continue

        numbered_answer = EXPLICIT_NUMBERED_ANSWER.match(text)
        if numbered_answer:
            flush_prompt()
            current_number = int(numbered_answer.group(1))
            emit(
                number=current_number,
                field="answer",
                value=_normalize_choice(numbered_answer.group(2)),
                locator=paragraph.locator,
                mode="explicit_numbered",
            )
            continue

        compact = _compact_items(text)
        if compact:
            # A compact row is evidence only; it does not establish prompt identity.
            for number, value in compact:
                emit(
                    number=number,
                    field="answer",
                    value=_normalize_choice(value),
                    locator=paragraph.locator,
                    mode="compact_summary",
                )
            continue

        answer = PLAIN_ANSWER.match(text)
        if answer and current_number is not None:
            emit(
                number=current_number,
                field="answer",
                value=_normalize_choice(answer.group(1)),
                locator=paragraph.locator,
                mode="explicit_current",
            )
            continue

        analysis = ANALYSIS.match(text)
        if analysis and current_number is not None:
            emit(
                number=current_number,
                field="analysis",
                value=analysis.group(1),
                locator=paragraph.locator,
                mode="explicit_current",
            )
            continue

        core = CORE.match(text)
        if core and current_number is not None:
            emit(
                number=current_number,
                field="teacher_notes",
                value=core.group(1),
                locator=paragraph.locator,
                mode="explicit_current",
            )
            continue

        question = QUESTION_RE.match(text)
        if question:
            flush_prompt()
            current_number = int(question.group(1))
            current_question_paragraphs = [paragraph]

            # In answer-only fill/material sections a numbered row can itself be the answer.
            if current_section in {"fill_blank", "material_answer"}:
                remainder = question.group(2).strip()
                if remainder:
                    emit(
                        number=current_number,
                        field="answer",
                        value=remainder,
                        locator=paragraph.locator,
                        mode="numbered_answer_row",
                    )
            continue

        if current_question_paragraphs:
            current_question_paragraphs.append(paragraph)

    flush_prompt()

    # Same source + question + field can appear in a summary and again in detailed records.
    # Preserve both as evidence; exact duplicate records are compacted by identity.
    unique: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    for item in evidence:
        key = (
            int(item["source_number"]),
            str(item["field"]),
            str(item["value"]),
            str(item["locator"]),
        )
        unique[key] = item
    evidence = list(unique.values())

    counts: dict[str, int] = {}
    for item in evidence:
        counts[item["field"]] = counts.get(item["field"], 0) + 1

    return {
        "schema_version": 1,
        "source_id": source_id,
        "subject": subject,
        "question_records": question_records,
        "evidence": evidence,
        "blockers": blockers,
        "summary": {
            "question_record_count": len(question_records),
            "evidence_count": len(evidence),
            "blocker_count": len(blockers),
            "field_counts": counts,
        },
    }
