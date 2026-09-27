from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

# Some source files contain missing punctuation after question numbers (e.g. "12 Actually...").
# Allow either punctuation or at least one whitespace after a 1-3 digit question number.
QUESTION_RE = re.compile(r"^\s*(\d{1,3})(?:\s*[.．、]\s*|\s+)(.+?)\s*$")

SECTION_LEAD = (
    r"^\\s*(?:(?:[0-9]+|[IVXLC]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[一二三四五六七八九十]+)"
    r"\\s*[.．、:：]?\\s*)?"
)

SECTION_PATTERNS = {
    "english": [
        (re.compile(SECTION_LEAD + r"(?:单项选择(?:题)?|选择题)", re.IGNORECASE), "single_choice", "single_choice"),
        (re.compile(SECTION_LEAD + r"完形填空", re.IGNORECASE), "cloze", "cloze_group"),
        (re.compile(SECTION_LEAD + r"阅读理解", re.IGNORECASE), "reading", "reading_group"),
        (re.compile(SECTION_LEAD + r"单词拼写", re.IGNORECASE), "word_spelling", "fill_blank"),
        (re.compile(SECTION_LEAD + r"(?:书面表达|写作)", re.IGNORECASE), "writing", "composition"),
    ],
    "politics": [
        (re.compile(SECTION_LEAD + r"(?:单选题|单项选择(?:题)?|选择题)"), "single_choice", "single_choice"),
        (re.compile(SECTION_LEAD + r"填空题"), "fill_blank", "fill_blank"),
        (re.compile(SECTION_LEAD + r"(?:问答题|材料题)"), "material_answer", "material_question"),
    ],
}

@dataclass(frozen=True)
class CandidateBlock:
    number: int | None
    section_key: str | None
    kind: str | None
    paragraphs: tuple[str, ...]

@dataclass(frozen=True)
class SectionBlock:
    section_key: str
    kind: str
    heading: str
    paragraphs: tuple[str, ...]

@dataclass(frozen=True)
class GroupBlock:
    label: str | None
    shared_material: tuple[str, ...]
    questions: tuple[CandidateBlock, ...]

def detect_section(subject: str, text: str):
    for pattern, key, kind in SECTION_PATTERNS.get(subject, []):
        if pattern.search(text):
            return key, kind
    return None

def split_sections(paragraphs: Iterable[str], subject: str) -> list[SectionBlock]:
    out: list[SectionBlock] = []
    key: str | None = None
    kind: str | None = None
    heading = ""
    body: list[str] = []

    def flush():
        nonlocal body
        if key is not None and kind is not None:
            out.append(SectionBlock(key, kind, heading, tuple(body)))
        body = []

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue
        section = detect_section(subject, text)
        if section:
            flush()
            key, kind = section
            heading = text
        elif key is not None:
            body.append(text)

    flush()
    return out

def split_numbered_questions(
    paragraphs: Iterable[str],
    subject: str,
    *,
    section_key: str | None = None,
    kind: str | None = None,
) -> list[CandidateBlock]:
    current_section = section_key
    current_kind = kind
    current_number: int | None = None
    current_paragraphs: list[str] = []
    out: list[CandidateBlock] = []

    def flush():
        nonlocal current_number, current_paragraphs
        if current_number is not None:
            out.append(CandidateBlock(
                number=current_number,
                section_key=current_section,
                kind=current_kind,
                paragraphs=tuple(current_paragraphs),
            ))
        current_number = None
        current_paragraphs = []

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue
        section = detect_section(subject, text)
        if section:
            flush()
            current_section, current_kind = section
            continue

        m = QUESTION_RE.match(text)
        if m:
            flush()
            current_number = int(m.group(1))
            current_paragraphs = [m.group(2).strip()]
        elif current_number is not None:
            current_paragraphs.append(text)

    flush()
    return out

def split_section(section: SectionBlock, subject: str):
    if section.kind == "composition":
        return [CandidateBlock(
            number=None,
            section_key=section.section_key,
            kind=section.kind,
            paragraphs=section.paragraphs,
        )]

    if section.kind == "cloze_group":
        first_q = next(
            (i for i, p in enumerate(section.paragraphs) if QUESTION_RE.match(p)),
            len(section.paragraphs),
        )
        shared = section.paragraphs[:first_q]
        questions = split_numbered_questions(
            section.paragraphs[first_q:], subject,
            section_key=section.section_key, kind="single_choice",
        )
        return [GroupBlock(None, tuple(shared), tuple(questions))]

    if section.kind == "reading_group":
        groups: list[GroupBlock] = []
        section_intro: list[str] = []
        current_label: str | None = None
        current: list[str] = []

        def flush_group():
            nonlocal current
            if current_label is None:
                return
            first_q = next((i for i, p in enumerate(current) if QUESTION_RE.match(p)), len(current))
            shared = current[:first_q]
            qs = split_numbered_questions(
                current[first_q:], subject,
                section_key=section.section_key, kind="single_choice",
            )
            groups.append(GroupBlock(current_label, tuple(shared), tuple(qs)))
            current = []

        for p in section.paragraphs:
            if re.fullmatch(r"[A-Z]", p.strip()):
                flush_group()
                current_label = p.strip()
            elif current_label is None:
                section_intro.append(p)
            else:
                current.append(p)
        flush_group()

        if not groups:
            first_q = next((i for i, p in enumerate(section.paragraphs) if QUESTION_RE.match(p)), len(section.paragraphs))
            qs = split_numbered_questions(
                section.paragraphs[first_q:], subject,
                section_key=section.section_key, kind="single_choice",
            )
            groups.append(GroupBlock(None, tuple(section.paragraphs[:first_q]), tuple(qs)))
        return groups

    return split_numbered_questions(
        section.paragraphs, subject,
        section_key=section.section_key, kind=section.kind,
    )

def extract_answer_annotations(paragraphs: Iterable[str]) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    current: int | None = None

    explicit_answer = re.compile(
        r"^\s*(\d{1,3})(?:\s*[.．、]\s*|\s+)答案[:：]\s*(.+?)\s*$"
    )
    plain_answer = re.compile(r"^\s*答案[:：]\s*(.+?)\s*$")
    compact = re.compile(r"(\d{1,3})\.([^\d]+?)(?=(?:\d{1,3})\.|$)")

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue

        m = explicit_answer.match(text)
        if m:
            current = int(m.group(1))
            out.setdefault(current, {})["answer"] = m.group(2).strip()
            continue

        compact_hits = list(compact.finditer(text))
        if len(compact_hits) >= 2:
            for hit in compact_hits:
                qno = int(hit.group(1))
                out.setdefault(qno, {})["answer"] = hit.group(2).strip()
            current = None
            continue

        m = plain_answer.match(text)
        if m and current is not None:
            out.setdefault(current, {})["answer"] = m.group(1).strip()
            continue

        if text.startswith("解析：") or text.startswith("解析:"):
            if current is not None:
                out.setdefault(current, {})["analysis"] = (
                    text.split("：", 1)[-1] if "：" in text else text.split(":", 1)[-1]
                ).strip()
            continue

        if text.startswith("题干核心：") or text.startswith("题干核心:"):
            if current is not None:
                out.setdefault(current, {})["teacher_notes"] = (
                    text.split("：", 1)[-1] if "：" in text else text.split(":", 1)[-1]
                ).strip()
            continue

        m = QUESTION_RE.match(text)
        if m:
            current = int(m.group(1))
            # In answer-only documents, long-answer rows carry their answer directly.
            if current >= 20:
                out.setdefault(current, {}).setdefault("answer", m.group(2).strip())

    return out
