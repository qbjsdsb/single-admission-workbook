from __future__ import annotations

import re
from typing import Any, Mapping


# Direct mappings supported by the source section itself.
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
    "word_spelling": {
        "chapter_key": "vocabulary_patterns",
        "section_key": "word_spelling_training",
        "tags": ["单词拼写"],
    },
}

# Broad fallbacks are used only when trusted teacher prose does not expose a
# narrower type. They preserve the source exam section instead of inventing a
# semantic sub-skill.
ENGLISH_SECTION_FALLBACK = {
    "single_choice": {
        "chapter_key": "grammar",
        "section_key": "mixed_choice",
        "tags": ["单项选择", "综合训练"],
    },
    "reading": {
        "chapter_key": "reading",
        "section_key": "reading_training",
        "tags": ["阅读理解", "综合训练"],
    },
}

SINGLE_CHOICE_RULES = (
    (re.compile(r"情景(?:交际|对话)"), "vocabulary_patterns", "key_sentences", ["情景交际"]),
    (re.compile(r"动词短语"), "vocabulary_patterns", "verb_phrases", ["动词短语"]),
    (re.compile(r"(?:固定短语|固定搭配|短语辨析|介词短语)"), "vocabulary_patterns", "common_phrases", ["常用词组"]),
    (re.compile(r"冠词"), "grammar", "article", ["冠词"]),
    (re.compile(r"代词"), "grammar", "pronoun", ["代词"]),
    (re.compile(r"名词"), "grammar", "noun", ["名词"]),
    (re.compile(r"形容词"), "grammar", "adjective", ["形容词"]),
    (re.compile(r"副词"), "grammar", "adverb", ["副词"]),
    (re.compile(r"数词"), "grammar", "numeral", ["数词"]),
    (re.compile(r"介词"), "grammar", "preposition", ["介词"]),
    (re.compile(r"(?:连词|连接词)"), "grammar", "conjunction", ["连词"]),
    (
        re.compile(
            r"(?:定语从句|状语从句|宾语从句|名词从句|从句|强调句|"
            r"虚拟语气|倒装|主谓一致|特殊疑问句|疑问句)"
        ),
        "grammar",
        "syntax",
        ["句法"],
    ),
    (
        re.compile(
            r"(?:非谓语|情态动词|动词|时态|过去时|将来时|完成时|"
            r"进行时|被动语态|语态|分词|不定式)"
        ),
        "grammar",
        "verb",
        ["动词"],
    ),
)

READING_RULES = (
    (re.compile(r"(?:词句猜测|词义猜测|划线词|画线词|下划线词)"), "word_guessing", "词义猜测"),
    (re.compile(r"(?:主旨大意|主旨|主要讲|主要内容|主要目的|全文.*(?:讲|介绍|说明))"), "main_idea", "主旨大意"),
    (re.compile(r"(?:推理判断|推断|推知|可以看出|可看出)"), "inference", "推理判断"),
    (re.compile(r"细节理解"), "detail", "细节理解"),
    # Older teacher sources often give only a direct paragraph/sentence citation.
    # Treat that as detail evidence only when the prose itself names a textual
    # locator/citation cue; otherwise keep the broad reading fallback.
    (
        re.compile(r"(?:根据|由|从|文中|文章).*(?:段|句|可知|得知|提到|指出)"),
        "detail",
        "细节理解",
    ),
)


def _teacher_analysis_index(
    teacher_enrichment: Mapping[str, Any] | None,
) -> dict[str, str]:
    if not teacher_enrichment:
        return {}
    out: dict[str, str] = {}
    for item in teacher_enrichment.get("items") or []:
        candidate_id = str(item.get("candidate_id") or "")
        analysis = str(item.get("analysis") or "").strip()
        if candidate_id and analysis:
            out[candidate_id] = analysis
    return out


def _source_supported_semantic_mapping(
    section_key: str,
    analysis: str,
) -> tuple[str, str, list[str], str] | None:
    if section_key == "single_choice":
        for pattern, chapter, section, tags in SINGLE_CHOICE_RULES:
            if pattern.search(analysis):
                return chapter, section, list(tags), "trusted_teacher_analysis"
        return None

    if section_key == "reading":
        for pattern, section, tag in READING_RULES:
            if pattern.search(analysis):
                return "reading", section, [tag], "trusted_teacher_analysis"
        return None

    return None


def build_safe_classification_proposals(
    candidate_bank: Mapping[str, Any],
    *,
    teacher_enrichment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build source-supported placements without asking AI to guess semantics.

    Trusted teacher prose may refine English single-choice and reading questions.
    When prose does not expose a safe subtype, the question stays in a broad
    source-section training bucket rather than remaining unplaceable.
    """
    subject = str(candidate_bank.get("subject") or "")
    analyses = _teacher_analysis_index(teacher_enrichment)
    decisions: list[dict[str, Any]] = []

    for candidate in candidate_bank.get("candidates") or []:
        candidate_id = str(candidate.get("candidate_id") or "")
        section_key = str(candidate.get("section_key") or "")

        if (
            subject == "english"
            and section_key.startswith("single_choice_self_test_")
        ):
            decisions.append({
                "candidate_id": candidate_id,
                "decision": "assign",
                "chapter_key": "grammar",
                "section_key": "mixed_choice",
                "tags": ["自主检测", "综合训练"],
                "difficulty": "standard",
                "note": (
                    "explicit_source_self_test_mapping; no semantic subtype guessed"
                ),
            })
            continue

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

        if (
            subject == "english"
            and section_key == "reading"
            and candidate.get("group_id")
        ):
            mapping = ENGLISH_SECTION_FALLBACK["reading"]
            decisions.append({
                "candidate_id": candidate_id,
                "decision": "assign",
                "chapter_key": mapping["chapter_key"],
                "section_key": mapping["section_key"],
                "tags": list(mapping["tags"]),
                "difficulty": "standard",
                "note": (
                    "group_atomic_source_section_mapping; shared reading material "
                    "must remain one publication placement"
                ),
            })
            continue

        if subject == "english":
            analysis = analyses.get(candidate_id, "")
            semantic = _source_supported_semantic_mapping(section_key, analysis)
            if semantic is not None:
                chapter, section, tags, basis = semantic
                decisions.append({
                    "candidate_id": candidate_id,
                    "decision": "assign",
                    "chapter_key": chapter,
                    "section_key": section,
                    "tags": tags,
                    "difficulty": "standard",
                    "note": f"{basis}; difficulty requires later editorial calibration",
                })
                continue

            fallback = ENGLISH_SECTION_FALLBACK.get(section_key)
            if fallback is not None:
                decisions.append({
                    "candidate_id": candidate_id,
                    "decision": "assign",
                    "chapter_key": fallback["chapter_key"],
                    "section_key": fallback["section_key"],
                    "tags": list(fallback["tags"]),
                    "difficulty": "standard",
                    "note": "broad_source_section_fallback; no semantic subtype guessed",
                })
                continue

        reason = "semantic_classification_required"
        if subject == "politics":
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
