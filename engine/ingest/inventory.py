#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import zipfile

SUBJECT_MARKERS = {
    "chinese": ("语文",),
    "mathematics": ("数学",),
    "english": ("英语",),
    "politics": ("政治",),
}

YEAR_RE = re.compile(r"(?<!\\d)(20(?:1[0-9]|2[0-9]))年?")

ROLE_RULES = (
    ("teacher", re.compile(r"教师版")),
    ("student", re.compile(r"学生版|学生卷|原卷版|（原卷）|\\(原卷\\)")),
    ("solution", re.compile(r"解析版|答案解析|含解析")),
    ("answer", re.compile(r"答案")),
)

PAIR_NOISE = re.compile(
    r"(学生版|学生卷|教师版|原卷版|解析版|原卷|答案解析|含解析|含答案|及答案解析|及答案|答案|"
    r"_?\\d{8,14}|【|】|\\[|\\]|（|）|\\(|\\)|\\s+)"
)

@dataclass(frozen=True)
class SourceItem:
    path: str
    size: int
    sha256: str
    extension: str
    subject: str
    year: int | None
    source_class: str
    role: str
    parser_lane: str
    pair_key: str
    rights_status: str = "unknown"
    import_status: str = "discovered"

def infer_subject(path: str) -> str:
    for subject, markers in SUBJECT_MARKERS.items():
        if any(marker in path for marker in markers):
            return subject
    return "unknown"

def infer_year(path: str) -> int | None:
    years = [int(m.group(1)) for m in YEAR_RE.finditer(path)]
    return years[-1] if years else None

def infer_source_class(path: str) -> str:
    name = Path(path).name
    if "备考笔记" in path:
        if "大纲" in name:
            return "syllabus"
        if "思维导图" in name:
            return "mind_map"
        if re.search(r"公式|速查|秘籍|考点清单|知识点", name):
            return "reference"
        return "study_note"
    if re.search(r"模拟|全真|检测|押题|冲刺|预测|密卷|仿真", name):
        return "mock_exam"
    if re.search(r"真题|统一招生考试.*试卷|单招.*试卷", name) or "全国体育单招真题" in path:
        return "past_exam"
    return "other"

def infer_role(name: str) -> str:
    matched = [role for role, pattern in ROLE_RULES if pattern.search(name)]
    if "solution" in matched:
        return "solution"
    if "teacher" in matched:
        return "teacher"
    if "student" in matched:
        return "student"
    if "answer" in matched:
        if re.search(r"真题.*(?:及|含)答案|试卷.*(?:及|含)答案", name):
            return "mixed"
        return "answer"
    return "standalone"

def parser_lane(extension: str) -> str:
    return {
        ".docx": "docx",
        ".doc": "legacy_doc",
        ".pdf": "pdf_probe",
        ".png": "image_ocr",
        ".jpg": "image_ocr",
        ".jpeg": "image_ocr",
    }.get(extension, "unsupported")

def normalized_pair_key(path: str) -> str:
    p = Path(path)
    stem = PAIR_NOISE.sub("", p.stem).lower()
    parent = PAIR_NOISE.sub("", p.parent.as_posix()).lower()
    return hashlib.sha1(f"{parent}/{stem}".encode("utf-8")).hexdigest()[:16]

def sha256_stream(stream) -> str:
    h = hashlib.sha256()
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()

def inventory_zip(zip_path: Path) -> list[SourceItem]:
    items: list[SourceItem] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            with zf.open(info) as stream:
                digest = sha256_stream(stream)
            items.append(SourceItem(
                path=info.filename,
                size=info.file_size,
                sha256=digest,
                extension=ext,
                subject=infer_subject(info.filename),
                year=infer_year(info.filename),
                source_class=infer_source_class(info.filename),
                role=infer_role(Path(info.filename).name),
                parser_lane=parser_lane(ext),
                pair_key=normalized_pair_key(info.filename),
            ))
    return items

def summarize(items: list[SourceItem]) -> dict:
    def counts(field: str):
        out: dict[str, int] = {}
        for item in items:
            key = str(getattr(item, field))
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items()))

    pair_groups: dict[str, set[str]] = {}
    for item in items:
        pair_groups.setdefault(item.pair_key, set()).add(item.role)
    candidate_pairs = sum(
        1 for roles in pair_groups.values()
        if "student" in roles and bool({"teacher", "solution", "answer"} & roles)
    )
    return {
        "files": len(items),
        "bytes": sum(i.size for i in items),
        "by_extension": counts("extension"),
        "by_subject": counts("subject"),
        "by_source_class": counts("source_class"),
        "by_role": counts("role"),
        "by_parser_lane": counts("parser_lane"),
        "candidate_student_teacher_or_solution_pairs": candidate_pairs,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory a private workbook source ZIP without extracting it.")
    parser.add_argument("zip", type=Path)
    parser.add_argument("--out", type=Path, help="Write full PRIVATE source manifest JSON here.")
    parser.add_argument("--summary", type=Path, help="Write aggregate summary JSON here.")
    args = parser.parse_args()
    items = inventory_zip(args.zip)
    summary = summarize(items)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2), encoding="utf-8")
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
