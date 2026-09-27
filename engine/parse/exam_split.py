from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

QUESTION_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]\s*(.*)$")

SECTION_PATTERNS = {
    "english": [
        (re.compile(r"单项选择"), "single_choice", "single_choice"),
        (re.compile(r"完形填空"), "cloze", "cloze_group"),
        (re.compile(r"阅读理解"), "reading", "reading_group"),
        (re.compile(r"单词拼写"), "word_spelling", "fill_blank"),
        (re.compile(r"书面表达|写作"), "writing", "composition"),
    ],
    "politics": [
        (re.compile(r"单选题|单项选择"), "single_choice", "single_choice"),
        (re.compile(r"填空题"), "fill_blank", "fill_blank"),
        (re.compile(r"问答题|材料题"), "material_answer", "material_question"),
    ],
}

@dataclass(frozen=True)
class CandidateBlock:
    number: int
    section_key: str | None
    kind: str | None
    paragraphs: tuple[str, ...]

def detect_section(subject: str, text: str):
    for pattern, key, kind in SECTION_PATTERNS.get(subject, []):
        if pattern.search(text):
            return key, kind
    return None

def split_numbered_questions(paragraphs: Iterable[str], subject: str) -> list[CandidateBlock]:
    current_section: str | None = None
    current_kind: str | None = None
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

def extract_answer_annotations(paragraphs: Iterable[str]) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    current: int | None = None

    answer_line = re.compile(r"^\s*(\d{1,3})\s*[.．]\s*答案[:：]\s*(.+?)\s*$")
    numbered_line = re.compile(r"^\s*(\d{1,3})\s*[.．]\s*(.+?)\s*$")
    compact = re.compile(r"(\d{1,3})\.([^\d]+?)(?=(?:\d{1,3})\.|$)")

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue

        m = answer_line.match(text)
        if m:
            current = int(m.group(1))
            out.setdefault(current, {})["answer"] = m.group(2).strip()
            continue

        if text.startswith("解析：") or text.startswith("解析:"):
            if current is not None:
                out.setdefault(current, {})["analysis"] = text.split("：", 1)[-1] if "：" in text else text.split(":", 1)[-1]
            continue

        if text.startswith("题干核心：") or text.startswith("题干核心:"):
            if current is not None:
                out.setdefault(current, {})["teacher_notes"] = text.split("：", 1)[-1] if "：" in text else text.split(":", 1)[-1]
            continue

        # Compact answer rows such as "26.甲27.乙28.丙".
        compact_hits = list(compact.finditer(text))
        if len(compact_hits) >= 2:
            for hit in compact_hits:
                qno = int(hit.group(1))
                out.setdefault(qno, {})["answer"] = hit.group(2).strip()
            current = None
            continue

        # Long-answer rows such as "31.第一点……第二点……".
        m = numbered_line.match(text)
        if m and int(m.group(1)) >= 20:
            qno = int(m.group(1))
            # Do not overwrite a richer explicit "答案：" record.
            out.setdefault(qno, {}).setdefault("answer", m.group(2).strip())
            current = qno

    return out
