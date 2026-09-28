from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

# Word exports can glue labels directly to the previous option text, e.g.
# "oneB. two". Keep that recovery path, but reject capital-letter acronym tails
# such as "TTEC." from becoming a fake C option marker.
STRICT_MARKER = re.compile(r"(?<![A-Z0-9])([A-D])[.．、)]\s*")
BARE_FOLLOWUP_MARKER = re.compile(r"(?:\t+| {3,})([A-D])\s+(?=\S)")
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
    recoveries: tuple[str, ...] = ()


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
    next_text: str | None,
) -> tuple[str, list[tuple[str, str]], bool]:
    """Split one option paragraph while recovering narrowly safe missing punctuation.

    Private English calibration found lines such as "A choice    B. choice",
    standalone later labels such as "C choice", and a few cases where bare A is
    on its own line followed by a strict B line.

    Bare-label recovery is deliberately sequence-driven:
    - A requires either a later strict B/C/D marker in the same paragraph or a
      strict B marker at the start of the next paragraph;
    - B/C/D are accepted only when they are exactly the next expected label after
      option parsing has already started.

    An ordinary stem beginning with "A ..." therefore stays stem text.
    """
    prefix, strict, starts_strict = _strict_pieces(text)

    def with_bare_followups(
        markers: list[tuple[str, int, int]],
    ) -> list[tuple[str, int, int]]:
        """Recover punctuationless labels only in an already started A-D row."""
        if not markers:
            return markers
        order = "ABCD"
        result = sorted(markers, key=lambda item: item[1])
        for match in BARE_FOLLOWUP_MARKER.finditer(text):
            label = match.group(1)
            position = match.start(1)
            if any(start == position for _label, start, _end in result):
                continue
            preceding = [item for item in result if item[1] < position]
            if not preceding:
                continue
            preceding_labels = [item[0] for item in preceding]
            start_index = order.index(expected_label)
            expected_prefix = list(order[start_index:start_index + len(preceding_labels)])
            next_index = start_index + len(preceding_labels)
            if (
                preceding_labels == expected_prefix
                and next_index < len(order)
                and label == order[next_index]
            ):
                result.append((label, match.start(1), match.end(1)))
                result.sort(key=lambda item: item[1])
        return result

    bare = re.match(
        rf"^\s*{re.escape(expected_label)}\s+(?=\S)",
        text,
    )
    if bare is None:
        if strict and strict[0][0] == expected_label:
            markers = with_bare_followups([
                (match.group(1), match.start(), match.end())
                for match in STRICT_MARKER.finditer(text)
            ])
            out: list[tuple[str, str]] = []
            for index, (label, _start, end_marker) in enumerate(markers):
                end = markers[index + 1][1] if index + 1 < len(markers) else len(text)
                out.append((label, text[end_marker:end].strip()))
            return prefix, out, starts_strict
        return prefix, strict, starts_strict

    strict_after = [
        match
        for match in STRICT_MARKER.finditer(text)
        if match.start() >= bare.end()
    ]
    order = "ABCD"
    strict_labels = [match.group(1) for match in strict_after]
    next_is_strict_b = bool(
        next_text is not None
        and re.match(r"^\s*B[.．、)]", next_text)
    )
    allow_bare = (
        expected_label != "A"
        or (
            "A" not in strict_labels
            and (
                any(
                    order.index(label) > order.index(expected_label)
                    for label in strict_labels
                )
                or next_is_strict_b
            )
        )
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

    markers = with_bare_followups(markers)
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


def _complete_option_set(labels: list[str]) -> bool:
    """Accept a visually ordered two-column option set when all labels are unique.

    Legacy Word files may serialize two-column choices by reading order, e.g.
    B/A on the first row and D/C on the second. Sorting is safe only after the
    full A-D set is present exactly once; partial or duplicate sets stay blocked.
    """
    return len(labels) == 4 and set(labels) == set("ABCD")


def parse_options(paragraphs: Iterable[str]) -> ParsedOptions:
    """Parse common 1/2/4-column Word exports without silently guessing ambiguity."""
    texts = [raw.strip() for raw in paragraphs if raw.strip()]
    stem: list[str] = []
    found: list[tuple[str, str]] = []
    started = False

    for index, text in enumerate(texts):
        if len(found) >= 4:
            if VOLUME_TAIL.match(text):
                continue
            return ParsedOptions(tuple(stem), tuple(found), "ambiguous_continuation")

        expected_label = "ABCD"[len(found)]
        next_text = texts[index + 1] if index + 1 < len(texts) else None
        prefix, pieces, starts_with_marker = _split_inline_options(
            text,
            expected_label=expected_label,
            next_text=next_text,
        )
        labels_here = [label for label, _ in pieces]
        unique_known_labels = (
            bool(pieces)
            and all(label in "ABCD" for label in labels_here)
            and len(labels_here) == len(set(labels_here))
        )
        valid_marker_shape = (
            unique_known_labels
            and (
                _sequence_like(labels_here)
                and labels_here[0] == expected_label
                or starts_with_marker and len(pieces) >= 2
            )
        )
        bare_a_confirmed_by_next_b = (
            expected_label == "A"
            and len(pieces) == 1
            and next_text is not None
            and bool(re.match(r"^\s*B[.．、)]", next_text))
        )

        if valid_marker_shape and (
            starts_with_marker
            or len(pieces) >= 2
            or bare_a_confirmed_by_next_b
        ):
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
        elif started and unique_known_labels:
            if len(found) + len(pieces) > 4 or set(label for label, _ in found) & set(labels_here):
                return ParsedOptions(tuple(stem), tuple(found), "ambiguous_labels")
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
    if _complete_option_set(labels):
        found = sorted(found, key=lambda item: "ABCD".index(item[0]))
        if any(not value for _, value in found):
            return ParsedOptions(tuple(stem), tuple(found), "ambiguous_labels")
        return ParsedOptions(tuple(stem), tuple(found), "ok")
    if (
        labels == ["A", "B", "B", "D"]
        and all(value for _, value in found)
    ):
        # A paired real source prints the third option label as B in both
        # editions. A/B/B/D is structurally impossible for a four-choice item;
        # preserve source order and recover only the missing C label. The
        # candidate records this recovery explicitly instead of silently fixing it.
        repaired = list(found)
        repaired[2] = ("C", repaired[2][1])
        return ParsedOptions(
            tuple(stem),
            tuple(repaired),
            "ok",
            ("duplicate_b_in_abbd_relabelled_c",),
        )
    if labels != ["A", "B", "C", "D"] or any(not value for _, value in found):
        return ParsedOptions(tuple(stem), tuple(found), "ambiguous_labels")
    return ParsedOptions(tuple(stem), tuple(found), "ok")
