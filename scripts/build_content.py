#!/usr/bin/env python3
"""Generate student and teacher TeX from the same structured fixture data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SUBJECT_ORDER = ["chinese", "math", "politics", "english"]
SUBJECT_LABELS = {
    "chinese": "语文",
    "math": "数学",
    "politics": "政治",
    "english": "英语",
}
SUBJECT_NOTES = {
    "chinese": "\\chinesenote",
    "math": "\\mathnote",
    "politics": "\\politicsnote",
    "english": "\\englishnote",
}


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\~{}",
        "^": r"\^{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def segment_text(segments: list[dict[str, Any]] | None, fallback: str) -> str:
    if not segments:
        return tex_escape(fallback)
    rendered: list[str] = []
    for segment in segments:
        kind = segment.get("kind")
        text = str(segment.get("text", ""))
        if kind == "text":
            rendered.append(tex_escape(text))
        elif kind == "marked":
            rendered.append(r"\marked{" + tex_escape(text) + "}")
        elif kind == "math":
            rendered.append(r"\ensuremath{" + text + "}")
        elif kind == "blank":
            rendered.append(r"\answerblank{" + text + "}")
        elif kind == "emphasis":
            rendered.append(r"\uline{" + tex_escape(text) + "}")
        elif kind == "line_break":
            rendered.append(r"\\")
        else:
            raise ValueError(f"Unsupported segment kind: {kind}")
    return "".join(rendered)


def render_question(number: int, question: dict[str, Any]) -> list[str]:
    stem = question["stem"]
    lines = [
        f"% question-id: {question['question_id']}",
        f"\\question{{{number}}}{{{segment_text(stem.get('segments'), stem['text'])}}}",
    ]
    material = question.get("material")
    if material:
        lines.append(f"\\materialbox{{{segment_text(material.get('segments'), material.get('text', ''))}}}")
    choices = question.get("choices") or []
    if choices:
        lines.append("\\choices{")
        for choice in choices:
            lines.append(f"  \\choice{{{tex_escape(str(choice['text']))}}}")
        lines.append("}")
    lines.append(f"\\scoreline{{{question['score']['points']}}}")
    answer = question.get("answer") or {}
    if answer:
        lines.append(f"\\teacheranswer{{{tex_escape(str(answer.get('value', '')))}}}")
        basis = answer.get("basis")
        if basis:
            lines.append(f"\\teacherbasis{{{tex_escape(str(basis))}}}")
    explanation = question.get("explanation")
    if explanation:
        lines.append(f"\\teacherexplanation{{{tex_escape(str(explanation))}}}")
    source = question.get("source", {})
    note = f"{source.get('source_id', '')}；类型：{question.get('source_type', '')}；状态：{question.get('verification_status', '')}"
    lines.append(f"\\sourcenote{{{tex_escape(note)}}}")
    lines.append("\\medskip")
    return lines


def load_questions(fixtures_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], str]:
    subjects: dict[str, list[dict[str, Any]]] = {}
    digest = hashlib.sha256()
    for subject in SUBJECT_ORDER:
        files = sorted((fixtures_dir / subject).glob("*.json"))
        questions: list[dict[str, Any]] = []
        for path in files:
            raw = path.read_bytes()
            digest.update(path.relative_to(fixtures_dir).as_posix().encode("utf-8"))
            digest.update(raw)
            data = json.loads(raw.decode("utf-8"))
            questions.extend(data)
        subjects[subject] = questions
    return subjects, digest.hexdigest()


def make_document(
    subjects: dict[str, list[dict[str, Any]]],
    fingerprint: str,
    teacher: bool,
    subject_filter: str | None = None,
    single_question: bool = False,
) -> str:
    option = "teacher" if teacher else "student"
    if subject_filter:
        title = rf"体育单招文化考试{SUBJECT_LABELS[subject_filter]}样张（\workbookedition）"
        document_label = f"{SUBJECT_LABELS[subject_filter]}单科代表性样张"
    else:
        title = r"体育单招文化考试四科结构样章（\workbookedition）"
        document_label = "自拟四科结构压力样张"
    lines = [
        f"% content-fingerprint: {fingerprint}",
        f"\\documentclass[{option}]{{../src/workbook}}",
        "\\usepackage{../src/common/workbook-common}",
        "\\usepackage{../src/subjects/chinese}",
        "\\usepackage{../src/subjects/math}",
        "\\usepackage{../src/subjects/politics}",
        "\\usepackage{../src/subjects/english}",
        "",
        "\\begin{document}",
        f"\\workbooktitle{{{title}}}",
        f"\\workbookmeta{{{document_label}；自拟结构压力样本，不是官方真题}}",
    ]
    subjects_to_render = [subject_filter] if subject_filter else SUBJECT_ORDER
    for subject in subjects_to_render:
        label = SUBJECT_LABELS[subject]
        lines.append(f"\\subjectchapter{{{label}}}{{结构压力样本}}")
        lines.append(SUBJECT_NOTES[subject] + "")
        questions = subjects[subject][:1] if single_question else subjects[subject]
        for number, question in enumerate(questions, start=1):
            lines.extend(render_question(number, question))
    lines.extend(["\\end{document}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[1] / "fixtures")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "build")
    parser.add_argument("--subject", choices=SUBJECT_ORDER)
    parser.add_argument("--single-question", action="store_true", help="Use only the first fixture question for the selected subject.")
    args = parser.parse_args()
    subjects, fingerprint = load_questions(args.fixtures)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for teacher in (False, True):
        edition = "teacher" if teacher else "student"
        stem = f"generated_{args.subject}_" if args.subject else "generated_"
        name = f"{stem}{edition}.tex"
        document = make_document(subjects, fingerprint, teacher, args.subject, args.single_question)
        (args.output_dir / name).write_text(document, encoding="utf-8")
    print(f"Generated student and teacher TeX from fixture fingerprint {fingerprint}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
