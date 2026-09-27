from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

# Real Word exports frequently glue choices together: "A. oneB. twoC. threeD. four".
# Parse label markers by A->B->C->D sequence instead of requiring whitespace.
STRICT_MARKER = re.compile(r"([A-D])[.．、)]\s*")
# Page/volume separators can remain at the tail of the final question in a section.
# They are not option text and may be ignored only after a complete A-D set exists.
VOLUME_TAIL = re.compile(
    r"^\s*(?:第)?[一二三四五六七八九十0-9]+\s*卷"
    r"(?:\s*[（(].*?[）)])?\s*$"
)


@dataclass(frozen=True)
class ParsedOptions:
    stem_paragraphs: tuple[str, ...]
    options: tuple[tuple[str, str], ...]
    status: str


def _strict_pieces(text: str) -> tuple[str, list[tuple[str, str]], bool]:
    matches = list(STRICT_MARKER.finditer(text))
    if not matches:
        return text.strip(), [], False
    prefix = text[:matches[0].start()].strip()
    out: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.end():end].strip()
        out.append((match.group(1), content))
    starts_with_marker = bool(re.match(r"^\s*[A-D][.．、)]", text))
    return prefix, out, starts_with_marker


def _split_inline_options(
    text: str,
    *,
    expected_label: str,
) -> tuple[str, list[tuple[str, str]], bool]:
    """Split one option paragraph while recovering narrowly safe missing punctuation.

    Private English calibration found lines such as "A choice    B. choice" and
    later standalone lines such as "C choice". A bare leading label is accepted
    only when:
    - A is followed later on the same paragraph by a stricter B/C/D marker; or
    - option parsing has already started and B/C/D is exactly the next expected
      label.

    This deliberately does not treat an ordinary stem beginning with "A ..." as
    an option.
    """
    prefix, strict, starts_strict = _strict_pieces(text)

    bare = re.match(
        rf"^\s*{re.escape(expected_label)}\s+(?=\S)",
        text,
    )
    if bare is None:
        return prefix, strict, starts_strict

    strict_after = [
        match
        for match in STRICT_MARKER.finditer(text)
        if match.start() >= bare.end()
    ]
    order = "ABCD"
    allow_bare = expected_label != "A" or any(
        order.index(match.group(1)) > order.index(expected_label)
        for match in strict_after
    )
    if not allow_bare:
        return prefix, strict, starts_strict

    markers: list[tuple[str, int, int]] = [
        (expected_label, bare.start(), bare.end())
    ]
    markers.extend(
        (match.group(1), match.start(), match.end())
        for match in strict_after
    )

    out: list[tuple[str, str]] = []
    for index, (label, _start, end_marker) in enumerate(markers):
        end = markers[index + 1][1] if index + 1 < len(markers) else len(text)
        out.append((label, text[end_marker:end].strip()))

    return text[:bare.start()].strip(), out, True


def _sequence_like(labels: list[str]) -> bool:
    order = "ABCD"
    try:
        indices = [order.index(label) for label in labels]
    except ValueError:
        return False
    return indices == sorted(indices) and len(indices) == len(set(indices))


def parse_options(paragraphs: Iterable[str]) -> ParsedOptions:
    """Parse common 1/2/4-column Word exports without silently guessing ambiguity."""
    stem: list[str] = []
    found: list[tuple[str, str]] = []
    started = False

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue

        if len(found) >= 4:
            if VOLUME_TAIL.match(text):
                continue
            return ParsedOptions(tuple(stem), tuple(found), "ambiguous_continuation")

        expected_label = "ABCD"[len(found)]
        prefix, pieces, starts_with_marker = _split_inline_options(
            text,
            expected_label=expected_label,
        )
        labels_here = [label for label, _ in pieces]
        valid_marker_shape = (
            bool(pieces)
            and _sequence_like(labels_here)
            and labels_here[0] == expected_label
        )

        if valid_marker_shape and (starts_with_marker or len(pieces) >= 2):
            if prefix:
                if started:
                    return ParsedOptions(
                        tuple(stem),
                        tuple(found),
                        "ambiguous_continuation",
                    )
                stem.append(prefix)
            started = True
            found.extend(pieces)
        elif started:
            if len(found) == 4 and VOLUME_TAIL.match(text):
                continue
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
