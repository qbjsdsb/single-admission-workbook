import json
from pathlib import Path
import tempfile
import unittest

from engine.pipeline.batch_review import (
    review_cached_source_group,
    review_intake_directory,
)


def paragraph(index, text):
    return {
        "type": "paragraph",
        "locator": f"word/document.xml/body/{index}",
        "inlines": [{"type": "text", "text": text}],
    }


def student_ast():
    texts = [
        "I.单项选择（共1小题，每小题2分，满分2分）",
        "1. A fictional prompt.",
        "A. one B. two C. three D. four",
    ]
    return {
        "version": 1,
        "source_format": "docx",
        "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
        "warnings": [],
    }


def teacher_ast(analysis="A reviewed fictional explanation."):
    texts = [
        "I.单项选择（共1小题，每小题2分，满分2分）",
        "1. A fictional prompt.",
        "A. one B. two C. three D. four",
        "答案：B",
        f"解析：{analysis}",
    ]
    return {
        "version": 1,
        "source_format": "docx",
        "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
        "warnings": [],
    }


def student_writing_ast():
    texts = [
        "V. 书面表达（满分10分）",
        "56. Write a letter to a fictional friend.",
        "1. Mention the fictional event.",
        "2. Explain your fictional plan.",
        "3. Close the letter politely.",
    ]
    return {
        "version": 1,
        "source_format": "docx",
        "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
        "warnings": [],
    }


def teacher_writing_ast():
    texts = [
        "V. 书面表达（满分10分）",
        "56. Write a letter to a fictional friend.",
        "1. Mention the fictional event.",
        "2. Explain your fictional plan.",
        "3. Close the letter politely.",
        "【答案】例文：",
        "Dear Mark,",
        "A fictional source teacher sample.",
    ]
    return {
        "version": 1,
        "source_format": "docx",
        "blocks": [paragraph(i, text) for i, text in enumerate(texts)],
        "warnings": [],
    }


def source(path, source_id, cache_key, sha, role):
    return {
        "path": path,
        "source_id": source_id,
        "cache_key": cache_key,
        "sha256": sha,
        "subject": "english",
        "role": role,
    }


class BatchReviewTests(unittest.TestCase):
    def test_multiple_companions_aggregate_answer_without_reparsing_student(self):
        student = source("student.docx", "SRC-STUDENT", "student-cache", "a" * 64, "student")
        teacher_a = source("teacher-a.docx", "SRC-TA", "ta-cache", "b" * 64, "solution")
        teacher_b = source("teacher-b.docx", "SRC-TB", "tb-cache", "c" * 64, "solution")

        result = review_cached_source_group(
            student_source=student,
            student_document=student_ast(),
            companions=[
                (teacher_a, teacher_ast(), "name_exact"),
                (teacher_b, teacher_ast(), "name_exact"),
            ],
            subject="english",
        )

        self.assertEqual(result["candidate_bank"]["summary"]["candidate_count"], 1)
        aggregate = result["verification_aggregate"]["rows"][0]
        self.assertEqual(aggregate["aggregate_status"], "machine_corroborated")
        self.assertEqual(aggregate["normalized_answer"], "B")
        self.assertEqual(
            aggregate["strong_evidence_source_ids"],
            ["SRC-TA", "SRC-TB"],
        )
        self.assertEqual(len(result["teacher_enrichment"]["items"]), 1)

    def test_batch_review_uses_trusted_teacher_analysis_for_classification(self):
        student = source(
            "student.docx",
            "SRC-STUDENT",
            "student-cache",
            "a" * 64,
            "student",
        )
        teacher = source(
            "teacher.docx",
            "SRC-TEACHER",
            "teacher-cache",
            "b" * 64,
            "solution",
        )

        result = review_cached_source_group(
            student_source=student,
            student_document=student_ast(),
            companions=[
                (
                    teacher,
                    teacher_ast("考查非谓语动词。A reviewed fictional explanation."),
                    "name_exact",
                ),
            ],
            subject="english",
        )

        decision = result["classification_manifest"]["decisions"][0]
        self.assertEqual(decision["decision"], "assign")
        self.assertEqual(
            (decision["chapter_key"], decision["section_key"]),
            ("grammar", "verb"),
        )
        self.assertIn("trusted_teacher_analysis", decision["note"])

    def test_different_teacher_analysis_variants_are_not_silently_chosen(self):
        student = source("student.docx", "SRC-STUDENT", "student-cache", "a" * 64, "student")
        teacher_a = source("teacher-a.docx", "SRC-TA", "ta-cache", "b" * 64, "solution")
        teacher_b = source("teacher-b.docx", "SRC-TB", "tb-cache", "c" * 64, "solution")

        result = review_cached_source_group(
            student_source=student,
            student_document=student_ast(),
            companions=[
                (teacher_a, teacher_ast("Explanation A."), "name_exact"),
                (teacher_b, teacher_ast("Explanation B."), "name_exact"),
            ],
            subject="english",
        )

        self.assertEqual(result["teacher_enrichment"]["items"], [])
        unresolved = result["teacher_enrichment_unresolved"]
        self.assertEqual(unresolved[0]["reason"], "multiple_teacher_analysis_variants")
        self.assertEqual(unresolved[0]["variant_count"], 2)

    def test_writing_pair_keeps_requirement_bullets_in_one_prompt(self):
        student = source(
            "writing-student.docx",
            "SRC-WRITING-STUDENT",
            "writing-student-cache",
            "d" * 64,
            "student",
        )
        teacher = source(
            "writing-teacher.docx",
            "SRC-WRITING-TEACHER",
            "writing-teacher-cache",
            "e" * 64,
            "solution",
        )
        result = review_cached_source_group(
            student_source=student,
            student_document=student_writing_ast(),
            companions=[(teacher, teacher_writing_ast(), "name_exact")],
            subject="english",
        )

        candidate = result["candidate_bank"]["candidates"][0]
        pair = result["companions"][0]["pairing_review"]["rows"][0]
        self.assertEqual(candidate["kind"], "composition")
        self.assertEqual(pair["prompt_pair_confidence"], "exact")
        self.assertEqual(pair["binding_strength"], "content_exact")
        self.assertEqual(pair["companion_source_number"], 56)
        self.assertEqual(pair["answer_status"], "missing")

        enrichment = result["teacher_enrichment"]["items"][0]
        self.assertIn("source_sample_response", enrichment)
        self.assertIn("source_sample_response_provenance", enrichment)
        self.assertEqual(
            enrichment["source_sample_response_provenance"]["evidence_source_id"],
            "SRC-WRITING-TEACHER",
        )

    def test_intake_batch_uses_cached_document_asts_and_writes_subject_summary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            intake = root / "intake"
            cache = intake / "cache"
            cache.mkdir(parents=True)
            out = root / "review"

            student = source(
                "english/student.docx",
                "SRC-STUDENT",
                "student-cache",
                "a" * 64,
                "student",
            )
            teacher_a = source(
                "english/teacher-a.docx",
                "SRC-TA",
                "ta-cache",
                "b" * 64,
                "solution",
            )
            teacher_b = source(
                "english/teacher-b.docx",
                "SRC-TB",
                "tb-cache",
                "c" * 64,
                "solution",
            )
            sources = [student, teacher_a, teacher_b]
            pairs = [
                {
                    "pair_key": "fixture",
                    "student_path": student["path"],
                    "companion_path": teacher_a["path"],
                    "companion_role": "solution",
                    "confidence": "name_exact",
                },
                {
                    "pair_key": "fixture",
                    "student_path": student["path"],
                    "companion_path": teacher_b["path"],
                    "companion_role": "solution",
                    "confidence": "name_exact",
                },
            ]
            (intake / "sources.private.json").write_text(
                json.dumps(sources), encoding="utf-8"
            )
            (intake / "pairs.private.json").write_text(
                json.dumps(pairs), encoding="utf-8"
            )

            for item, document in (
                (student, student_ast()),
                (teacher_a, teacher_ast()),
                (teacher_b, teacher_ast()),
            ):
                (cache / f"{item['cache_key']}.json").write_text(
                    json.dumps({
                        "source_sha256": item["sha256"],
                        "document_ast": document,
                        "required_work": ["question_segmentation"],
                    }),
                    encoding="utf-8",
                )

            summary = review_intake_directory(
                intake,
                out,
                subject="english",
                workers=2,
            )

            self.assertEqual(summary["student_source_groups"], 1)
            self.assertEqual(summary["companion_sources"], 2)
            self.assertEqual(summary["candidate_units"], 1)
            self.assertEqual(summary["failed_student_groups"], 0)
            self.assertEqual(
                summary["verification_aggregate_counts"]["machine_corroborated"],
                1,
            )
            self.assertTrue((out / "batch-summary.json").is_file())
            self.assertTrue((out / "editorial-queue.csv").is_file())
            self.assertTrue(
                (
                    out
                    / "SRC-STUDENT"
                    / "companions"
                    / "SRC-TA"
                    / "pairing-review.json"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
