import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.rerun_private_checkpoint import refresh_checkpoint


def paragraph(index, text):
    return {
        "type": "paragraph",
        "locator": f"word/document.xml/body/{index}",
        "inlines": [{"type": "text", "text": text}],
    }


def student_ast():
    return {
        "version": 1,
        "source_format": "docx",
        "blocks": [
            paragraph(0, "I.单项选择（共1小题，每小题2分，满分2分）"),
            paragraph(1, "1. A fictional prompt."),
            paragraph(2, "A. one B. two C. three D. four"),
        ],
        "warnings": [],
    }


def teacher_ast():
    return {
        "version": 1,
        "source_format": "docx",
        "blocks": [
            paragraph(0, "I.单项选择（共1小题，每小题2分，满分2分）"),
            paragraph(1, "1. A fictional prompt."),
            paragraph(2, "A. one B. two C. three D. four"),
            paragraph(3, "答案：B"),
            paragraph(4, "解析：A fictional reviewed explanation."),
        ],
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


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def zip_tree(source: Path, output: Path):
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(source).as_posix())


class PrivateCheckpointRerunTests(unittest.TestCase):
    def _checkpoint(self, root: Path) -> Path:
        intake = root / "tree" / "production" / "english" / "intake"
        cache = intake / "cache"
        cache.mkdir(parents=True)

        student = source(
            "english/student.docx",
            "SRC-STUDENT",
            "student-cache",
            "a" * 64,
            "student",
        )
        teacher = source(
            "english/teacher.docx",
            "SRC-TEACHER",
            "teacher-cache",
            "b" * 64,
            "solution",
        )
        write_json(intake / "sources.private.json", [student, teacher])
        write_json(intake / "pairs.private.json", [{
            "pair_key": "fixture",
            "student_path": student["path"],
            "companion_path": teacher["path"],
            "companion_role": "solution",
            "confidence": "name_exact",
        }])
        for item, document in ((student, student_ast()), (teacher, teacher_ast())):
            write_json(
                cache / f"{item['cache_key']}.json",
                {
                    "source_sha256": item["sha256"],
                    "document_ast": document,
                    "required_work": ["question_segmentation"],
                },
            )

        stale = root / "tree" / "production" / "english" / "batch-review" / "stale.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("must disappear", encoding="utf-8")

        checkpoint = root / "input.zip"
        zip_tree(root / "tree", checkpoint)
        return checkpoint

    def test_refresh_reuses_cached_intake_and_replaces_old_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checkpoint = self._checkpoint(root)
            out = root / "refreshed.zip"

            result = refresh_checkpoint(checkpoint, out, subject="english")
            self.assertEqual(result["student_source_groups"], 1)
            self.assertEqual(result["candidate_units"], 1)
            self.assertEqual(result["failed_student_groups"], 0)

            with zipfile.ZipFile(out) as archive:
                names = set(archive.namelist())
                self.assertIn(
                    "production/english/batch-review/batch-summary.json",
                    names,
                )
                self.assertIn(
                    "production/english/refresh-summary.private.json",
                    names,
                )
                self.assertNotIn(
                    "production/english/batch-review/stale.txt",
                    names,
                )
                summary = json.loads(
                    archive.read(
                        "production/english/batch-review/batch-summary.json"
                    ).decode("utf-8")
                )
                self.assertEqual(summary["candidate_units"], 1)

    def test_refresh_output_is_deterministic_for_same_checkpoint_and_code(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checkpoint = self._checkpoint(root)
            first = root / "first.zip"
            second = root / "second.zip"

            refresh_checkpoint(checkpoint, first, subject="english")
            refresh_checkpoint(checkpoint, second, subject="english")

            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )

    def test_path_traversal_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checkpoint = root / "unsafe.zip"
            with zipfile.ZipFile(checkpoint, "w") as archive:
                archive.writestr("../escape.json", "{}")

            with self.assertRaisesRegex(ValueError, "unsafe checkpoint member"):
                refresh_checkpoint(
                    checkpoint,
                    root / "out.zip",
                    subject="english",
                )


if __name__ == "__main__":
    unittest.main()
