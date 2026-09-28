from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SUBJECT_NAMES = {
    "chinese": "语文",
    "mathematics": "数学",
    "english": "英语",
    "politics": "政治",
}

SUBJECT_MODULES = {
    "chinese": "语文\\quad 基础与阅读",
    "mathematics": "数学\\quad 基础与综合",
    "english": "英语\\quad 词汇、语法与阅读",
    "politics": "政治\\quad 基础知识与材料分析",
}

PAGE_LABELS = {
    "chinese": "阅读与选择",
    "mathematics": "选择·填空·解答",
    "english": "阅读·词汇·写作",
    "politics": "选择·填空·问答",
}

LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "_": r"\_",
    "%": r"\%",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

def escape_text(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch == "\n":
            out.append(r"\par ")
        else:
            out.append(LATEX_ESCAPES.get(ch, ch))
    return "".join(out)

def _render_table(node: dict[str, Any]) -> str:
    rows = node.get("rows") or []
    columns = max(
        (sum(max(1, int(cell.get("grid_span") or 1)) for cell in row.get("cells") or []) for row in rows),
        default=0,
    )
    if not columns:
        return ""
    preamble = "|" + "|".join(["X"] * columns) + "|"
    rendered_rows: list[str] = []
    for row in rows:
        cells: list[str] = []
        occupied = 0
        for cell in row.get("cells") or []:
            value = escape_text(str(cell.get("text") or ""))
            span = max(1, int(cell.get("grid_span") or 1))
            cells.append(rf"\multicolumn{{{span}}}{{|X|}}{{{value}}}" if span > 1 else value)
            occupied += span
        cells.extend([""] * max(0, columns - occupied))
        if cells:
            rendered_rows.append(" & ".join(cells) + r" \\")
    if not rendered_rows:
        return ""
    return (
        r"\par\smallskip\begingroup\small\renewcommand{\arraystretch}{1.2}"
        + r"\noindent\begin{tabularx}{\linewidth}{" + preamble + r"}\hline" + "\n"
        + "\n".join(rendered_rows)
        + r"\hline\end{tabularx}\par\endgroup\smallskip"
    )

def rich_text(nodes: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for node in nodes:
        kind = node["type"]
        if kind == "text":
            out.append(escape_text(node["text"]))
        elif kind == "emphasis_dot":
            out.append(r"\marked{" + rich_text(node["children"]) + "}")
        elif kind == "underline":
            out.append(r"\CJKunderline{" + rich_text(node["children"]) + "}")
        elif kind == "bold":
            out.append(r"\textbf{" + rich_text(node["children"]) + "}")
        elif kind == "italic":
            out.append(r"\textit{" + rich_text(node["children"]) + "}")
        elif kind == "math":
            tex = node["tex"]
            out.append(r"\[" + tex + r"\]" if node.get("display") else "$" + tex + "$")
        elif kind == "blank":
            out.append(r"\blank{" + str(node.get("width_mm", 25)) + "mm}")
        elif kind == "image":
            # Image support is explicit in the data model. Width policy will become richer later.
            out.append(r"\includegraphics[width=.55\linewidth]{" + escape_text(node["asset"]) + "}")
        elif kind == "table":
            out.append(_render_table(node))
        else:
            raise ValueError(f"unsupported rich-text node: {kind}")
    return "".join(out)

def _plain_length(nodes: list[dict[str, Any]]) -> int:
    total = 0
    for node in nodes:
        if node["type"] == "text":
            total += len(node["text"])
        elif "children" in node:
            total += _plain_length(node["children"])
        elif node["type"] == "math":
            total += max(4, len(node["tex"]) // 2)
        elif node["type"] == "blank":
            total += 8
    return total

def render_choices(question: dict[str, Any]) -> str:
    options = question.get("options") or []
    if not options:
        return ""
    mode = (question.get("layout") or {}).get("choice_mode", "auto")
    lengths = [_plain_length(opt["content"]) for opt in options]
    if mode == "auto":
        # Four-column choices are reserved for compact English options.
        # Chinese, Politics and Mathematics default to a calmer two-column grid.
        subject = question.get("subject")
        if (
            subject == "english"
            and len(options) == 4
            and max(lengths) <= 10
            and sum(lengths) <= 30
        ):
            mode = "four_columns"
        elif len(options) == 4 and max(lengths) <= 30:
            mode = "two_columns"
        else:
            mode = "single_column"

    rendered = [rich_text(opt["content"]) for opt in options]
    if len(rendered) == 4 and mode == "four_columns":
        return r"\optfour{" + "}{".join(rendered) + "}\n"
    if len(rendered) == 4 and mode == "two_columns":
        return r"\opt{" + "}{".join(rendered) + "}\n"

    lines = []
    for opt, content in zip(options, rendered):
        lines.append(r"\longoptline{" + escape_text(str(opt["label"])) + "}{" + content + "}")
    return "\\Needspace{4\\baselineskip}\n" + "\n".join(lines) + "\n\\vspace{3mm}\n"

def _teacher_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return rich_text(value)
    if isinstance(value, (dict, tuple)):
        return escape_text(json.dumps(value, ensure_ascii=False))
    return escape_text(str(value))

def render_question(question: dict[str, Any], display_number: int, edition: str) -> str:
    score = question["score"]
    score_text = str(int(score)) if float(score).is_integer() else str(score)
    out = []
    if question.get("options"):
        # Real English cloze calibration found that the prompt could fit at the
        # bottom of a page while the option grid moved alone to the next page.
        # Reserve enough space for the prompt + a normal option block; the
        # option renderer keeps its own secondary guard for unusually long text.
        reserve = 7 if edition == "teacher" else 6
        out.append(rf"\Needspace{{{reserve}\baselineskip}}")
    out.extend([
        rf"\q{{{display_number}}}{{{score_text}}}{{{rich_text(question['stem'])}}}",
        render_choices(question),
    ])

    for part in question.get("parts") or []:
        out.append(r"\subq{" + escape_text(part["label"]) + "}{" + rich_text(part["stem"]) + "}")
        if edition == "student":
            space = part.get("answer_space_mm", 30)
            out.append(rf"\vspace{{{space}mm}}")

    if edition == "student" and question["kind"] in {"short_answer", "material_question", "solution"}:
        space = (question.get("layout") or {}).get("answer_space_mm", 38)
        if question["kind"] in {"short_answer", "material_question"}:
            lines = max(3, round(float(space) / 8))
            out.append(rf"\answerlines{{{lines}}}")
        else:
            out.append(rf"\vspace{{{space}mm}}")

    if edition == "teacher":
        if question.get("source_sample_response"):
            out.append(
                r"\teachersampleresponse{"
                + _teacher_value(question.get("source_sample_response"))
                + "}"
            )
        if question.get("answer") not in (None, ""):
            out.append(r"\teacheranswer{" + _teacher_value(question.get("answer")) + "}")
        if question.get("analysis"):
            out.append(r"\teacheranalysis{" + _teacher_value(question.get("analysis")) + "}")
        if question.get("teacher_notes"):
            out.append(r"\teachernote{" + _teacher_value(question.get("teacher_notes")) + "}")

    return "\n".join(x for x in out if x)

def render_group_material(question: dict[str, Any]) -> str:
    return r"\groupmaterial{" + rich_text(question["stem"]) + "}"


def render_body(book: dict[str, Any], questions: dict[str, dict[str, Any]]) -> str:
    edition = book["edition"]
    parts: list[str] = []
    display_number = 0
    for chapter_index, chapter in enumerate(book["chapters"], start=1):
        parts.append(rf"\chapterhead{{第{chapter_index}章}}{{{escape_text(chapter['title'])}}}")
        for section_index, section in enumerate(chapter["sections"], start=1):
            parts.append(rf"\sectionhead{{第{section_index}节}}{{{escape_text(section['title'])}}}")
            for qid in section["question_ids"]:
                question = questions[qid]
                if question.get("kind") in {"cloze_group", "reading_group"}:
                    parts.append(render_group_material(question))
                    for child in question.get("children") or []:
                        display_number += 1
                        child_question = {
                            **child,
                            "subject": question["subject"],
                        }
                        parts.append(
                            render_question(child_question, display_number, edition)
                        )
                    continue

                display_number += 1
                parts.append(render_question(question, display_number, edition))
    return "\n".join(parts)

def render_book(*, template: str, book: dict[str, Any], questions: dict[str, dict[str, Any]]) -> str:
    body = render_body(book, questions)
    subject_name = SUBJECT_NAMES[book["subject"]]
    replacements = {
        "%%BOOK_TITLE%%": escape_text(book["title"]),
        "%%SUBJECT_NAME%%": subject_name,
        "%%SUBJECT_MODULE%%": SUBJECT_MODULES[book["subject"]],
        "%%PAGE_LABEL%%": PAGE_LABELS[book["subject"]],
        "%%QUOTE_SEED%%": str(int(book["quote_seed"]) % 997),
        "%%BODY%%": body,
        "%%FRONT_MATTER%%": r"\workbookcontents" if book.get("table_of_contents", False) else "",
    }
    out = template
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out

def stable_build_id(book: dict[str, Any], questions: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(
        {"book": book, "questions": questions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]
