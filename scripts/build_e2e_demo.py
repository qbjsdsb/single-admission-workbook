#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html import escape as xml_escape
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.parse.docx_text import extract_docx_paragraphs
from engine.parse.exam_split import extract_answer_annotations, split_section, split_sections
from engine.render.latex import render_book, stable_build_id

OPTION_RE = re.compile(r"^([A-D])[.．]\s*(.+)$")

def make_minimal_docx(paragraphs: list[str], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>"""
    body = []
    for p in paragraphs:
        body.append(
            '<w:p><w:r><w:t xml:space="preserve">'
            + xml_escape(p)
            + "</w:t></w:r></w:p>"
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + "<w:sectPr/></w:body></w:document>"
    )
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)

def rich(text: str):
    # Fixture sources use underscores to represent a writing blank.
    nodes = []
    cursor = 0
    for m in re.finditer(r"_{4,}", text):
        if m.start() > cursor:
            nodes.append({"type": "text", "text": text[cursor:m.start()]})
        nodes.append({"type": "blank", "width_mm": 30})
        cursor = m.end()
    if cursor < len(text):
        nodes.append({"type": "text", "text": text[cursor:]})
    return nodes or [{"type": "text", "text": text}]

def candidate_to_question(candidate, annotations: dict[int, dict[str, str]], qid: str):
    paras = list(candidate.paragraphs)
    stem_parts = []
    options = []
    for p in paras:
        m = OPTION_RE.match(p)
        if m:
            options.append({"label": m.group(1), "content": rich(m.group(2))})
        else:
            stem_parts.append(p)
    stem_text = "\n".join(stem_parts)

    score = 3
    if candidate.kind == "material_question":
        score = 20
    question = {
        "id": qid,
        "subject": "politics",
        "kind": candidate.kind or "short_answer",
        "chapter_key": "demo",
        "section_key": candidate.section_key or "demo",
        "tags": ["e2e-demo"],
        "difficulty": "standard",
        "score": score,
        "stem": rich(stem_text),
        "layout": {
            "choice_mode": "auto",
            "keep_together": True,
            **({"answer_space_mm": 42} if candidate.kind == "material_question" else {}),
        },
    }
    if options:
        question["options"] = options
    anno = annotations.get(candidate.number or -1, {})
    if "answer" in anno:
        question["answer"] = anno["answer"]
    if "analysis" in anno:
        question["analysis"] = rich(anno["analysis"])
    return question

def build(out: Path):
    student_source = json.loads((ROOT / "examples/e2e/politics_student_source.json").read_text(encoding="utf-8"))
    teacher_source = json.loads((ROOT / "examples/e2e/politics_teacher_source.json").read_text(encoding="utf-8"))

    source_dir = out / "source"
    student_docx = source_dir / "student.docx"
    teacher_docx = source_dir / "teacher.docx"
    make_minimal_docx(student_source["paragraphs"], student_docx)
    make_minimal_docx(teacher_source["paragraphs"], teacher_docx)

    student_paras = extract_docx_paragraphs(student_docx)
    teacher_paras = extract_docx_paragraphs(teacher_docx)
    annotations = extract_answer_annotations(teacher_paras)

    candidates = []
    section_titles = {}
    for section in split_sections(student_paras, "politics"):
        section_titles[section.section_key] = section.heading
        candidates.extend(split_section(section, "politics"))

    canonical_dir = out / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    questions = {}
    question_ids_by_section: dict[str, list[str]] = {}
    for index, candidate in enumerate(candidates, start=1):
        if candidate.number is None:
            continue
        qid = f"POL-E2E-{index:03d}"
        question = candidate_to_question(candidate, annotations, qid)
        questions[qid] = question
        question_ids_by_section.setdefault(question["section_key"], []).append(qid)
        (canonical_dir / f"{qid}.json").write_text(
            json.dumps(question, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    sections = []
    for key, qids in question_ids_by_section.items():
        title = {
            "single_choice": "单项选择题",
            "fill_blank": "填空题",
            "material_answer": "材料题",
        }.get(key, section_titles.get(key, key))
        sections.append({"key": key, "title": title, "question_ids": qids})

    manifests = {}
    for edition in ("student", "teacher"):
        manifests[edition] = {
            "schema_version": 1,
            "book_id": f"politics-e2e-{edition}",
            "title": "政治练习册样章",
            "subject": "politics",
            "edition": edition,
            "paper": "A4",
            "quote_seed": 20260927,
            "chapters": [{"key": "demo", "title": "基础训练", "sections": sections}],
        }
        (out / f"{edition}.book.json").write_text(
            json.dumps(manifests[edition], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    template = (ROOT / "templates/latex/workbook.tex").read_text(encoding="utf-8")
    for edition, book in manifests.items():
        edition_dir = out / edition
        edition_dir.mkdir(parents=True, exist_ok=True)
        tex = render_book(template=template, book=book, questions=questions)
        (edition_dir / "main.tex").write_text(tex, encoding="utf-8")
        (edition_dir / "build-id.txt").write_text(
            stable_build_id(book, questions) + "\n", encoding="utf-8"
        )

    summary = {
        "source_docx_files": 2,
        "questions": len(questions),
        "sections": {k: len(v) for k, v in question_ids_by_section.items()},
        "answers_linked": sum(1 for q in questions.values() if "answer" in q),
        "analyses_linked": sum(1 for q in questions.values() if "analysis" in q),
        "student_question_ids": [q for s in sections for q in s["question_ids"]],
        "teacher_question_ids": [q for s in sections for q in s["question_ids"]],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "build/e2e")
    args = ap.parse_args()
    build(args.out)

if __name__ == "__main__":
    main()
