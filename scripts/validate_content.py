#!/usr/bin/env python3
"""Validate public representative fixtures against the JSON Schema and guardrails."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


SUBJECTS = {"chinese", "math", "politics", "english"}
SOURCE_TYPES = {
    "official_exam",
    "official_syllabus",
    "teacher_reviewed_transcription",
    "secondary_transcription",
    "recall",
    "mock",
    "lecture_note",
    "textbook_note",
    "knowledge_summary",
    "derived_exercise",
    "self_authored",
}
STATUSES = {
    "unknown",
    "inventoried",
    "reviewed",
    "teacher_reviewed",
    "cross_checked",
    "verified",
    "disputed",
    "rejected",
}
USAGES = {
    "research_only",
    "structure_reference",
    "knowledge_reference",
    "transformation_source",
    "exercise_candidate",
    "student_release",
    "teacher_release",
}
SEGMENT_KINDS = {"text", "marked", "math", "blank", "emphasis", "line_break"}
ABSOLUTE_WINDOWS = re.compile(r"^[A-Za-z]:[\\/]|^\\\\|^/")


def walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_question(question: Any, subject_dir: str, seen: set[str], errors: list[str]) -> None:
    require(isinstance(question, dict), f"{subject_dir}: question must be an object", errors)
    if not isinstance(question, dict):
        return

    required = {"question_id", "subject", "source", "source_type", "verification_status", "allowed_usage", "stem", "score"}
    missing = sorted(required - question.keys())
    require(not missing, f"{subject_dir}: missing fields {missing}", errors)

    question_id = question.get("question_id")
    require(isinstance(question_id, str) and re.fullmatch(r"[A-Z][A-Z0-9-]+", question_id or ""), f"{subject_dir}: invalid question_id {question_id!r}", errors)
    if isinstance(question_id, str):
        require(question_id not in seen, f"duplicate question_id: {question_id}", errors)
        seen.add(question_id)

    require(question.get("subject") == subject_dir, f"{question_id}: subject does not match directory {subject_dir}", errors)
    require(question.get("source_type") in SOURCE_TYPES, f"{question_id}: invalid source_type", errors)
    require(question.get("verification_status") in STATUSES, f"{question_id}: invalid verification_status", errors)
    require(question.get("allowed_usage") in USAGES, f"{question_id}: invalid allowed_usage", errors)

    source = question.get("source")
    require(isinstance(source, dict), f"{question_id}: source must be an object", errors)
    if isinstance(source, dict):
        require(isinstance(source.get("source_id"), str) and bool(source.get("source_id")), f"{question_id}: source_id missing", errors)
        require(isinstance(source.get("title"), str) and bool(source.get("title")), f"{question_id}: source title missing", errors)
        require(source.get("format") in {"pdf", "doc", "docx", "zip", "html", "text", "self_authored"}, f"{question_id}: invalid source format", errors)

    stem = question.get("stem")
    require(isinstance(stem, dict) and isinstance(stem.get("text"), str) and bool(stem.get("text")), f"{question_id}: stem.text missing", errors)
    if isinstance(stem, dict) and "segments" in stem:
        require(isinstance(stem["segments"], list), f"{question_id}: stem.segments must be a list", errors)
        for segment in stem.get("segments", []):
            require(isinstance(segment, dict) and segment.get("kind") in SEGMENT_KINDS, f"{question_id}: invalid stem segment", errors)

    score = question.get("score")
    require(isinstance(score, dict) and isinstance(score.get("points"), (int, float)) and score.get("points", 0) > 0, f"{question_id}: score.points must be positive", errors)
    if isinstance(score, dict):
        require(score.get("kind") in {"objective", "fill_in", "solution", "writing", "unknown"}, f"{question_id}: invalid score.kind", errors)

    if question.get("allowed_usage") in {"student_release", "teacher_release"}:
        require(isinstance(question.get("answer"), dict) and bool(question["answer"].get("value")), f"{question_id}: release fixture needs an answer value", errors)

    for string in walk_strings(question):
        require(not ABSOLUTE_WINDOWS.match(string), f"{question_id}: absolute/private path found in fixture: {string}", errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[1] / "fixtures")
    parser.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[1] / "schemas" / "question.schema.json")
    args = parser.parse_args()

    errors: list[str] = []
    seen: set[str] = set()
    total = 0
    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_validator = Draft202012Validator(schema, format_checker=FormatChecker())
    except Exception as exc:
        print(f"Could not load a valid JSON Schema from {args.schema}: {exc}")
        return 1

    for subject in sorted(SUBJECTS):
        directory = args.fixtures / subject
        require(directory.is_dir(), f"missing fixture directory: {directory}", errors)
        if not directory.is_dir():
            continue
        files = sorted(directory.glob("*.json"))
        require(bool(files), f"no fixture JSON in {directory}", errors)
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - command-line diagnostics
                errors.append(f"{path}: invalid JSON: {exc}")
                continue
            require(isinstance(data, list), f"{path}: top level must be an array", errors)
            if isinstance(data, list):
                for question in data:
                    total += 1
                    validate_question(question, subject, seen, errors)
                    for schema_error in schema_validator.iter_errors(question):
                        location = ".".join(str(part) for part in schema_error.absolute_path) or "<root>"
                        errors.append(f"{path.name}:{location}: {schema_error.message}")

    if errors:
        print("Content validation failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(f"Content validation passed: {total} representative questions across {len(SUBJECTS)} subjects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
