#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PUBLIC_KEYS = {
    "source",
    "source_id",
    "source_file",
    "source_page",
    "source_question_number",
    "parser",
    "parser_version",
    "confidence",
    "copyright_status",
    "review_status",
    "commit",
    "build_id",
}

FORBIDDEN_PUBLIC_PHRASES = (
    "公开模板示例",
    "本地整理稿",
    "待审核",
    "内部ID",
    "parser confidence",
    "commit SHA",
)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def walk_public(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_PUBLIC_KEYS:
                raise ValueError(f"forbidden publication key {key!r} at {path}")
            walk_public(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            walk_public(child, f"{path}[{i}]")
    elif isinstance(value, str):
        lower = value.lower()
        for phrase in FORBIDDEN_PUBLIC_PHRASES:
            if phrase.lower() in lower:
                raise ValueError(f"forbidden publication phrase {phrase!r} at {path}")


def validate():
    q_schema = load_json(ROOT / "schema/question.schema.json")
    b_schema = load_json(ROOT / "schema/book.schema.json")
    p_schema = load_json(ROOT / "schema/internal-provenance.schema.json")

    # Validate the schemas themselves first.
    for schema in (q_schema, b_schema, p_schema):
        Draft202012Validator.check_schema(schema)

    q_validator = Draft202012Validator(q_schema)
    b_validator = Draft202012Validator(b_schema)

    question_paths = sorted((ROOT / "examples/questions").glob("*.json"))
    questions = {}
    for path in question_paths:
        doc = load_json(path)
        q_validator.validate(doc)
        walk_public(doc)
        if doc["id"] in questions:
            raise ValueError(f"duplicate question id: {doc['id']}")
        questions[doc["id"]] = doc

    book_paths = sorted((ROOT / "examples/books").glob("*.json"))
    for path in book_paths:
        doc = load_json(path)
        b_validator.validate(doc)
        walk_public(doc)
        for chapter in doc["chapters"]:
            for section in chapter["sections"]:
                for qid in section["question_ids"]:
                    if qid not in questions:
                        raise ValueError(f"{path}: unknown question id {qid}")

    with (ROOT / "content/quotes.yaml").open("r", encoding="utf-8") as f:
        quotes_doc = yaml.safe_load(f)
    quotes = [item["text"].strip() for item in quotes_doc["quotes"]]
    if not quotes or any(not q for q in quotes):
        raise ValueError("quote pool contains an empty quote")
    if len(quotes) != len(set(quotes)):
        raise ValueError("quote pool contains duplicates")
    too_long = [q for q in quotes if len(q) > 28]
    if too_long:
        raise ValueError(f"quote too long for footer: {too_long}")

    # Student and teacher demo manifests must demonstrate same-source rendering.
    student = load_json(ROOT / "examples/books/chinese-student-demo.json")
    teacher = load_json(ROOT / "examples/books/chinese-teacher-demo.json")
    s_ids = student["chapters"][0]["sections"][0]["question_ids"]
    t_ids = teacher["chapters"][0]["sections"][0]["question_ids"]
    if s_ids != t_ids:
        raise ValueError("student/teacher demo manifests are not sourced from the same question list")

    print(
        f"OK: {len(questions)} questions, {len(book_paths)} book manifests, "
        f"{len(quotes)} footer quotes; schemas and publication-cleanliness checks passed."
    )


if __name__ == "__main__":
    try:
        validate()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
