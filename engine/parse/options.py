from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

MARKER = re.compile(r"(?:(?<=^)|(?<=\s))([A-D])[.．、)]\s*")


@dataclass(frozen=True)
class ParsedOptions:
    stem_paragraphs: tuple[str, ...]
    options: tuple[tuple[str, str], ...]
    status: str


def _split_inline_options(text: str) -> list[tuple[str, str]]:
    matches = list(MARKER.finditer(text))
    if not matches:
        return []
    out: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.end():end].strip()
        out.append((match.group(1), content))
    return out


def parse_options(paragraphs: Iterable[str]) -> ParsedOptions:
    """Parse common 1/2/4-column Word exports without silently guessing ambiguity."""
    stem: list[str] = []
    found: list[tuple[str, str]] = []
    started = False

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue
        pieces = _split_inline_options(text)
        starts_with_marker = bool(re.match(r"^\s*[A-D][.．、)]", text))
        if pieces and (starts_with_marker or len(pieces) >= 2):
            started = True
            found.extend(pieces)
        elif started:
            # Once option parsing starts, free text is ambiguous: it may be a wrapped
            # option or the next structural block. Do not append it to an option.
            return ParsedOptions(tuple(stem), tuple(found), "ambiguous_continuation")
        else:
            stem.append(text)

    labels = [label for label, _ in found]
    if not found:
        return ParsedOptions(tuple(stem), (), "none")
    if labels != ["A", "B", "C", "D"] or any(not value for _, value in found):
        return ParsedOptions(tuple(stem), tuple(found), "ambiguous_labels")
    return ParsedOptions(tuple(stem), tuple(found), "ok")
