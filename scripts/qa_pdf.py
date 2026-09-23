#!/usr/bin/env python3
"""Run lightweight, reproducible PDF and log checks after compilation."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_B5 = (176 / 25.4 * 72, 250 / 25.4 * 72)
SUBJECT_LABELS = {"chinese": "语文", "math": "数学", "politics": "政治", "english": "英语"}
TEACHER_ONLY_LABELS = ("参考答案：", "依据/得分点：", "解析：", "来源与审核备注：")


def command_output(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode, result.stdout + result.stderr


def check_pdf(
    path: Path,
    build_dir: Path,
    expected_subjects: tuple[str, ...] = (),
    expected_pages: int | None = None,
) -> dict[str, object]:
    if not path.exists():
        return {"file": path.name, "ok": False, "errors": ["missing PDF"]}
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return {"file": path.name, "ok": False, "errors": ["pdfinfo not found"]}
    code, output = command_output([pdfinfo, str(path)])
    errors: list[str] = []
    if code != 0:
        errors.append("pdfinfo failed")
    pages_match = re.search(r"^Pages:\s+(\d+)", output, re.MULTILINE)
    pages = int(pages_match.group(1)) if pages_match else 0
    if pages <= 0:
        errors.append("PDF has no pages")
    if expected_pages is not None and pages != expected_pages:
        errors.append(f"expected {expected_pages} page(s), got {pages}")
    size_match = re.search(r"^Page size:\s+([0-9.]+) x ([0-9.]+) pts", output, re.MULTILINE)
    if size_match:
        width, height = float(size_match.group(1)), float(size_match.group(2))
        if min(abs(width - EXPECTED_B5[0]) + abs(height - EXPECTED_B5[1]), abs(width - EXPECTED_B5[1]) + abs(height - EXPECTED_B5[0])) > 3:
            errors.append(f"page size is not B5: {width} x {height} pt")
    else:
        errors.append("could not read page size")

    log = build_dir / f"{path.stem}.log"
    if log.exists():
        log_text = log.read_text(encoding="utf-8", errors="replace")
        for pattern, label in [
            (r"! LaTeX Error:", "LaTeX error"),
            (r"Emergency stop", "emergency stop"),
            (r"Fatal error", "fatal error"),
            (r"Overfull \\[vh\\]box", "overfull box"),
        ]:
            if re.search(pattern, log_text):
                errors.append(label)
    else:
        errors.append("missing compilation log")

    pdftotext = shutil.which("pdftotext")
    text_sample = ""
    if pdftotext:
        text_path = build_dir / f"{path.stem}.txt"
        code, _ = command_output([pdftotext, str(path), str(text_path)])
        if code == 0 and text_path.exists():
            text_sample = text_path.read_text(encoding="utf-8", errors="replace")
            for expected in expected_subjects:
                if expected not in text_sample:
                    errors.append(f"text extraction missing subject label: {expected}")
    else:
        errors.append("pdftotext not found")
    return {"file": path.name, "ok": not errors, "pages": pages, "errors": errors}


def check_shared_content(build_dir: Path, fixtures_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    student_source = build_dir / "generated_student.tex"
    teacher_source = build_dir / "generated_teacher.tex"
    if not student_source.exists() or not teacher_source.exists():
        return {"ok": False, "errors": ["missing generated student/teacher TeX"]}

    student_text = student_source.read_text(encoding="utf-8")
    teacher_text = teacher_source.read_text(encoding="utf-8")
    student_normalized = student_text.replace(r"\documentclass[student]", r"\documentclass[edition]", 1)
    teacher_normalized = teacher_text.replace(r"\documentclass[teacher]", r"\documentclass[edition]", 1)
    if student_normalized != teacher_normalized:
        errors.append("student and teacher generated TeX differ beyond their edition option")

    expected_ids: set[str] = set()
    for path in sorted(fixtures_dir.glob("*/questions.json")):
        try:
            for question in json.loads(path.read_text(encoding="utf-8")):
                expected_ids.add(question["question_id"])
        except Exception as exc:
            errors.append(f"could not read fixture {path.name}: {exc}")
    student_ids = set(re.findall(r"^% question-id: ([A-Z][A-Z0-9-]+)$", student_text, re.MULTILINE))
    teacher_ids = set(re.findall(r"^% question-id: ([A-Z][A-Z0-9-]+)$", teacher_text, re.MULTILINE))
    if student_ids != expected_ids:
        errors.append(f"student TeX question IDs differ from fixtures: missing={sorted(expected_ids-student_ids)} extra={sorted(student_ids-expected_ids)}")
    if teacher_ids != expected_ids:
        errors.append(f"teacher TeX question IDs differ from fixtures: missing={sorted(expected_ids-teacher_ids)} extra={sorted(teacher_ids-expected_ids)}")

    student_pdf_text = build_dir / "student.txt"
    teacher_pdf_text = build_dir / "teacher.txt"
    if student_pdf_text.exists() and teacher_pdf_text.exists():
        student_pdf = student_pdf_text.read_text(encoding="utf-8", errors="replace")
        teacher_pdf = teacher_pdf_text.read_text(encoding="utf-8", errors="replace")
        for label in TEACHER_ONLY_LABELS:
            if label in student_pdf:
                errors.append(f"student PDF leaks teacher-only label: {label}")
            if label not in teacher_pdf:
                errors.append(f"teacher PDF is missing teacher-only label: {label}")
    else:
        errors.append("missing extracted student/teacher PDF text")
    return {"ok": not errors, "fixture_question_count": len(expected_ids), "errors": errors}


def check_subject_samples(build_dir: Path, fixtures_dir: Path) -> dict[str, object]:
    subject_reports: dict[str, object] = {}
    all_errors: list[str] = []
    for subject, label in SUBJECT_LABELS.items():
        fixture_path = fixtures_dir / subject / "questions.json"
        if not fixture_path.exists():
            all_errors.append(f"missing fixture for subject sample: {subject}")
            subject_reports[subject] = {"ok": False, "errors": ["missing fixture"]}
            continue
        try:
            questions = json.loads(fixture_path.read_text(encoding="utf-8"))
            expected_ids = {questions[0]["question_id"]} if questions else set()
        except Exception as exc:
            all_errors.append(f"could not read {fixture_path}: {exc}")
            subject_reports[subject] = {"ok": False, "errors": [str(exc)]}
            continue

        errors: list[str] = []
        student_source_path = build_dir / f"generated_{subject}_student.tex"
        teacher_source_path = build_dir / f"generated_{subject}_teacher.tex"
        if not student_source_path.exists() or not teacher_source_path.exists():
            errors.append("missing generated student/teacher TeX")
        else:
            student_source = student_source_path.read_text(encoding="utf-8")
            teacher_source = teacher_source_path.read_text(encoding="utf-8")
            student_normalized = student_source.replace(r"\documentclass[student]", r"\documentclass[edition]", 1)
            teacher_normalized = teacher_source.replace(r"\documentclass[teacher]", r"\documentclass[edition]", 1)
            if student_normalized != teacher_normalized:
                errors.append("student and teacher sample TeX differ beyond their edition option")
            for edition, source in (("student", student_source), ("teacher", teacher_source)):
                actual_ids = set(re.findall(r"^% question-id: ([A-Z][A-Z0-9-]+)$", source, re.MULTILINE))
                if actual_ids != expected_ids:
                    errors.append(f"{edition} sample question IDs differ from its fixture: {sorted(actual_ids)}")

        for edition in ("student", "teacher"):
            path = build_dir / f"{subject}-sample-{edition}.pdf"
            pdf_report = check_pdf(path, build_dir, (label,), expected_pages=1)
            if not pdf_report["ok"]:
                errors.extend(f"{edition} PDF: {error}" for error in pdf_report["errors"])

        student_text_path = build_dir / f"{subject}-sample-student.txt"
        teacher_text_path = build_dir / f"{subject}-sample-teacher.txt"
        if not student_text_path.exists() or not teacher_text_path.exists():
            errors.append("missing extracted student/teacher sample PDF text")
        else:
            student_pdf = student_text_path.read_text(encoding="utf-8", errors="replace")
            teacher_pdf = teacher_text_path.read_text(encoding="utf-8", errors="replace")
            for marker in TEACHER_ONLY_LABELS:
                if marker in student_pdf:
                    errors.append(f"student PDF leaks teacher-only label: {marker}")
                if marker not in teacher_pdf:
                    errors.append(f"teacher PDF is missing teacher-only label: {marker}")

        subject_reports[subject] = {"ok": not errors, "question_id": next(iter(expected_ids), None), "errors": errors}
        all_errors.extend(f"{subject}: {error}" for error in errors)
    return {"ok": not all_errors, "subjects": subject_reports, "errors": all_errors}


def check_render_outputs(pdf_reports: list[dict[str, object]], build_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    checked: list[str] = []
    for report in pdf_reports:
        stem = Path(str(report["file"])).stem
        pages = int(report.get("pages", 0))
        for mode in ("color", "grayscale"):
            render_dir = build_dir / "render" / stem / mode
            rendered = list(render_dir.glob("page-*.png")) if render_dir.is_dir() else []
            if len(rendered) != pages:
                errors.append(f"{stem} {mode}: expected {pages} rendered page(s), found {len(rendered)}")
        checked.append(stem)
    return {"ok": not errors, "checked": checked, "errors": errors}


def check_dot_mark(path: Path, build_dir: Path) -> dict[str, object]:
    report = check_pdf(path, build_dir)
    errors = list(report.get("errors", []))
    text_path = build_dir / "dot-mark-regression.txt"
    if not text_path.exists():
        errors.append("missing extracted dot-mark regression text")
    else:
        extracted = re.sub(r"\s+", "", text_path.read_text(encoding="utf-8", errors="replace"))
        for expected in ("语文着重号回归样张", "单字：馁", "多字词：循序渐进", "粗体：贼、造", "楷体：馁、食", "行末位置测试", "窄栏换行测试", "关键字、目标字"):
            if re.sub(r"\s+", "", expected) not in extracted:
                errors.append(f"dot-mark PDF text extraction missing: {expected}")
    report["errors"] = errors
    report["ok"] = not errors
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    reports = [
        check_pdf(args.build_dir / "student.pdf", args.build_dir, ("语文", "数学", "政治", "英语")),
        check_pdf(args.build_dir / "teacher.pdf", args.build_dir, ("语文", "数学", "政治", "英语")),
        check_dot_mark(args.build_dir / "dot-mark-regression.pdf", args.build_dir),
    ]
    for subject, label in SUBJECT_LABELS.items():
        for edition in ("student", "teacher"):
            reports.append(check_pdf(args.build_dir / f"{subject}-sample-{edition}.pdf", args.build_dir, (label,), expected_pages=1))
    shared = check_shared_content(args.build_dir, args.fixtures)
    samples = check_subject_samples(args.build_dir, args.fixtures)
    renders = check_render_outputs(reports, args.build_dir)
    result = {
        "ok": all(bool(report.get("ok")) for report in reports) and bool(shared["ok"]) and bool(samples["ok"]) and bool(renders["ok"]),
        "pdfs": reports,
        "shared_content": shared,
        "subject_samples": samples,
        "renders": renders,
    }
    (args.build_dir / "qa-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
