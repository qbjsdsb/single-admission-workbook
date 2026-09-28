from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

# Some source files contain missing punctuation after question numbers (e.g. "12 Actually...").
# Allow either punctuation or at least one whitespace after a 1-3 digit question number.
_STANDARD_QUESTION_RE = re.compile(
    r"^\s*(\d{1,3})(?:\s*[.．、,，]\s*|\s+)(.+?)\s*$"
)
# A legacy Word conversion can render the leading "1" in a teen question
# number as the letter "l", for example "l8.". Only accept l/L + one nonzero
# digit followed by explicit question punctuation; never reinterpret a bare
# Roman-I section heading. Source text stays unchanged in Document AST/provenance.
_LEGACY_L_AS_ONE_QUESTION_RE = re.compile(
    r"^\s*[lL]([1-9])\s*[.．、,，]\s*(.+?)\s*$"
)
_LEGACY_BARE_L_QUESTION_RE = re.compile(
    r"^\s*[lL]\s*[.．、,，]\s*(.+?)\s*$"
)
_LEGACY_TRAILING_L_QUESTION_RE = re.compile(
    r"^\s*([1-9])[lL]\s*[.．、,，]\s*(.+?)\s*$"
)


class _QuestionMatch:
    def __init__(self, raw: str, number: int, rest: str):
        self._raw = raw
        self._number = number
        self._rest = rest

    def group(self, index: int = 0):
        if index == 0:
            return self._raw
        if index == 1:
            return str(self._number)
        if index == 2:
            return self._rest
        raise IndexError(index)


class _QuestionPattern:
    def match(self, text: str):
        standard = _STANDARD_QUESTION_RE.match(text)
        if standard:
            return standard
        legacy = _LEGACY_L_AS_ONE_QUESTION_RE.match(text)
        if legacy:
            return _QuestionMatch(text, 10 + int(legacy.group(1)), legacy.group(2))
        bare_l = _LEGACY_BARE_L_QUESTION_RE.match(text)
        if bare_l:
            return _QuestionMatch(text, 1, bare_l.group(1))
        trailing_l = _LEGACY_TRAILING_L_QUESTION_RE.match(text)
        if trailing_l:
            return _QuestionMatch(
                text,
                int(trailing_l.group(1)) * 10 + 1,
                trailing_l.group(2),
            )
        return None


QUESTION_RE = _QuestionPattern()

# Teacher/answer sections in mixed or standalone English sources sometimes print
# the key and explanation on one numbered line, for example "1.B【解析】..." or
# "1.C.考查...". These are evidence rows, not new question stems. Require an
# explicit analysis cue so ordinary numbered questions that happen to begin with
# an option letter remain untouched.
NUMBERED_INLINE_ANSWER_ANALYSIS_RE = re.compile(
    r"^\s*(\d{1,3})\s*[.．、]\s*([A-DＡ-Ｄ])"
    r"\s*(?:[.．、]\s*)?"
    r"(?:【\s*)?(解析|考点|考查|详解)(?:\s*】)?"
    r"\s*[:：]?\s*(.*?)\s*$",
    re.IGNORECASE,
)


def english_exam_section_for_number(number: int) -> str | None:
    if 1 <= number <= 20:
        return "single_choice"
    if 21 <= number <= 30:
        return "cloze"
    if 31 <= number <= 45:
        return "reading"
    if 46 <= number <= 55:
        return "word_spelling"
    if number == 56:
        return "writing"
    return None


def has_legacy_l_as_one_question_prefix(text: str) -> bool:
    return bool(
        _LEGACY_L_AS_ONE_QUESTION_RE.match(text)
        or _LEGACY_BARE_L_QUESTION_RE.match(text)
        or _LEGACY_TRAILING_L_QUESTION_RE.match(text)
    )

SECTION_LEAD = (
    r"^\s*(?:(?:[0-9]+|[IVXLC]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[一二三四五六七八九十]+)"
    r"\s*[.．、:：,，]?\s*)?"
)

ENGLISH_CLOZE_INSTRUCTION = re.compile(
    r"(?=.*阅读.{0,20}(?:短文|文章))(?=.*掌握其大意)"
    r"(?=.*\d{1,3}\s*(?:至|到|[-—–~～])\s*\d{1,3})",
    re.IGNORECASE,
)

SECTION_PATTERNS = {
    "english": [
        (re.compile(SECTION_LEAD + r"(?:单项选择(?:题)?|项选择(?:题)?|单项填空|选择题)", re.IGNORECASE), "single_choice", "single_choice"),
        (re.compile(SECTION_LEAD + r"完[形型]填空", re.IGNORECASE), "cloze", "cloze_group"),
        (ENGLISH_CLOZE_INSTRUCTION, "cloze", "cloze_group"),
        # A legacy 2015 Word source renders the Roman heading III as "11I" in
        # extracted text; its original page visibly reads "III、阅读理解".
        (re.compile(r"^\s*11I\s*[.．、:]?\s*阅读理解", re.IGNORECASE), "reading", "reading_group"),
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
    # PDF text blocks can contain a title line followed by the actual section
    # heading in the same block. Match the whole block first, then individual
    # lines; never search arbitrary mid-line prose for a section label.
    candidates = [text]
    if "\n" in text:
        candidates.extend(line.strip() for line in text.splitlines() if line.strip())
    for candidate in candidates:
        for pattern, key, kind in SECTION_PATTERNS.get(subject, []):
            if pattern.search(candidate):
                return key, kind
    return None


def is_english_cloze_instruction(text: str) -> bool:
    """Identify a numbered cloze instruction line separately from its section heading."""
    return bool(ENGLISH_CLOZE_INSTRUCTION.search(text))

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
