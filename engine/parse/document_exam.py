from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from engine.document.consume import LocatedParagraph, safe_segmentation_paragraphs
from engine.parse.exam_split import QUESTION_RE, detect_section


@dataclass(frozen=True)
class LocatedSection:
    section_key: str
    kind: str
    heading: LocatedParagraph
    paragraphs: tuple[LocatedParagraph, ...]


@dataclass(frozen=True)
class LocatedCandidateBlock:
    number: int | None
    section_key: str
    kind: str
    paragraphs: tuple[LocatedParagraph, ...]

    @property
    def locators(self) -> tuple[str, ...]:
        return tuple(p.locator for p in self.paragraphs)


@dataclass(frozen=True)
class LocatedGroupBlock:
    label: str | None
    section_key: str
    kind: str
    shared_material: tuple[LocatedParagraph, ...]
    questions: tuple[LocatedCandidateBlock, ...]


def split_document_sections(
    document: Mapping[str, object], subject: str
) -> list[LocatedSection]:
    paragraphs = safe_segmentation_paragraphs(document)
    sections: list[LocatedSection] = []
    current_key: str | None = None
    current_kind: str | None = None
    heading: LocatedParagraph | None = None
    body: list[LocatedParagraph] = []

    def flush():
        nonlocal body
        if current_key is not None and current_kind is not None and heading is not None:
            sections.append(LocatedSection(
                current_key, current_kind, heading, tuple(body)
            ))
        body = []

    for paragraph in paragraphs:
        section = detect_section(subject, paragraph.text)
        if section:
            flush()
            current_key, current_kind = section
            heading = paragraph
        elif current_key is not None:
            body.append(paragraph)

    flush()
    return sections


def _split_numbered(
    paragraphs: tuple[LocatedParagraph, ...],
    section_key: str,
    kind: str,
) -> list[LocatedCandidateBlock]:
    out: list[LocatedCandidateBlock] = []
    current_number: int | None = None
    current: list[LocatedParagraph] = []

    def flush():
        nonlocal current_number, current
        if current_number is not None:
            out.append(LocatedCandidateBlock(
                number=current_number,
                section_key=section_key,
                kind=kind,
                paragraphs=tuple(current),
            ))
        current_number = None
        current = []

    for paragraph in paragraphs:
        match = QUESTION_RE.match(paragraph.text)
        if match:
            flush()
            current_number = int(match.group(1))
            # Preserve the original locator and rich inline evidence while using a
            # stripped text view for question recognition.
            current = [LocatedParagraph(
                locator=paragraph.locator,
                text=match.group(2).strip(),
                inlines=paragraph.inlines,
                page=paragraph.page,
            )]
        elif current_number is not None:
            current.append(paragraph)

    flush()
    return out


def split_located_section(section: LocatedSection):
    if section.kind == "composition":
        return [LocatedCandidateBlock(
            number=None,
            section_key=section.section_key,
            kind=section.kind,
            paragraphs=section.paragraphs,
        )]

    if section.kind == "cloze_group":
        first_q = next(
            (i for i, p in enumerate(section.paragraphs) if QUESTION_RE.match(p.text)),
            len(section.paragraphs),
        )
        questions = _split_numbered(
            section.paragraphs[first_q:], section.section_key, "single_choice"
        )
        return [LocatedGroupBlock(
            label=None,
            section_key=section.section_key,
            kind=section.kind,
            shared_material=section.paragraphs[:first_q],
            questions=tuple(questions),
        )]

    if section.kind == "reading_group":
        groups: list[LocatedGroupBlock] = []
        current_label: str | None = None
        current: list[LocatedParagraph] = []

        def flush_group():
            nonlocal current
            if current_label is None:
                return
            first_q = next(
                (i for i, p in enumerate(current) if QUESTION_RE.match(p.text)),
                len(current),
            )
            questions = _split_numbered(
                tuple(current[first_q:]), section.section_key, "single_choice"
            )
            groups.append(LocatedGroupBlock(
                label=current_label,
                section_key=section.section_key,
                kind=section.kind,
                shared_material=tuple(current[:first_q]),
                questions=tuple(questions),
            ))
            current = []

        for paragraph in section.paragraphs:
            if re.fullmatch(r"[A-Z]", paragraph.text.strip()):
                flush_group()
                current_label = paragraph.text.strip()
            elif current_label is not None:
                current.append(paragraph)
        flush_group()

        if groups:
            return groups

        first_q = next(
            (i for i, p in enumerate(section.paragraphs) if QUESTION_RE.match(p.text)),
            len(section.paragraphs),
        )
        return [LocatedGroupBlock(
            label=None,
            section_key=section.section_key,
            kind=section.kind,
            shared_material=section.paragraphs[:first_q],
            questions=tuple(_split_numbered(
                section.paragraphs[first_q:], section.section_key, "single_choice"
            )),
        )]

    return _split_numbered(section.paragraphs, section.section_key, section.kind)


def split_document_questions(document: Mapping[str, object], subject: str):
    out = []
    for section in split_document_sections(document, subject):
        out.extend(split_located_section(section))
    return out
