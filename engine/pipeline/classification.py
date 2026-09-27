from __future__ import annotations

from typing import Any, Mapping


# Only mappings directly supported by the source-derived English taxonomy and
# source section type. Semantic sub-skill classification is deliberately excluded.
ENGLISH_DIRECT = {
    "cloze": {
        "chapter_key": "cloze",
        "section_key": "cloze_training",
        "tags": ["完形填空"],
    },
    "writing": {
        "chapter_key": "writing",
        "section_key": "writing_training",
        "tags": ["写作"],
    },
}


def build_safe_classification_proposals(
    candidate_bank: Mapping[str, Any],
) -> dict[str, Any]:
    subject = str(candidate_bank.get("subject") or "")
    decisions: list[dict[str, Any]] = []

    for candidate in candidate_bank.get("candidates") or []:
        candidate_id = str(candidate.get("candidate_id") or "")
        section_key = str(candidate.get("section_key") or "")

        if subject == "english" and section_key in ENGLISH_DIRECT:
            mapping = ENGLISH_DIRECT[section_key]
            decisions.append({
                "candidate_id": candidate_id,
                "decision": "assign",
                "chapter_key": mapping["chapter_key"],
                "section_key": mapping["section_key"],
                "tags": list(mapping["tags"]),
                "difficulty": "standard",
                "note": "direct_source_section_mapping; difficulty requires later editorial calibration",
            })
            continue

        reason = "semantic_classification_required"
        if subject == "english" and section_key == "reading":
            reason = "reading_subskill_unknown"
        elif subject == "english" and section_key in {"single_choice", "word_spelling"}:
            reason = "grammar_or_vocabulary_semantics_required"
        elif subject == "politics":
            reason = "politics_taxonomy_not_approved"

        decisions.append({
            "candidate_id": candidate_id,
            "decision": "defer",
            "note": reason,
        })

    return {
        "schema_version": 1,
        "candidate_source_id": candidate_bank.get("source_id"),
        "subject": subject,
        "decisions": decisions,
    }
