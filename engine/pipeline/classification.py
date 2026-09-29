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



# Politics placement follows the official 2023 sport-single-admission syllabus.
# Rules are deliberately conservative: a question is auto-assigned only when
# source wording / trusted teacher prose points to one unique syllabus section.
POLITICS_RULES = (
    (re.compile(r"(?:原始社会|奴隶社会|封建社会|资本主义社会|空想社会主义|科学社会主义|共产党宣言)"),
     "chinese_socialism", "socialist_development", ["中国特色社会主义", "社会主义发展"]),
    (re.compile(r"(?:新民主主义革命|三大改造|过渡时期总路线|社会主义制度.{0,8}确立)"),
     "chinese_socialism", "socialism_saves_china", ["中国特色社会主义", "只有社会主义才能救中国"]),
    (re.compile(r"(?:中国特色社会主义.{0,12}(?:开创|道路|理论|制度|文化)|邓小平理论|三个代表|科学发展观)"),
     "chinese_socialism", "socialism_develops_china", ["中国特色社会主义", "改革开放"]),
    (re.compile(r"(?:新时代.{0,16}主要矛盾|中国梦|中华民族伟大复兴|两步走|习近平新时代中国特色社会主义思想)"),
     "chinese_socialism", "new_era_rejuvenation", ["中国特色社会主义", "新时代"]),
    (re.compile(r"(?:生产资料所有制|公有制|非公有制|国有经济|集体经济|两个不动摇|两个毫不动摇)"),
     "economy_society", "ownership", ["经济与社会", "所有制"]),
    (re.compile(r"(?:社会主义市场经济|市场调节|市场缺陷|市场失灵|宏观调控|政府的经济职能)"),
     "economy_society", "market_economy", ["经济与社会", "市场经济"]),
    (re.compile(r"(?:新发展理念|高质量发展|现代化经济体系|创新发展|协调发展|绿色发展|开放发展|共享发展)"),
     "economy_society", "economic_development", ["经济与社会", "经济发展"]),
    (re.compile(r"(?:收入分配|按劳分配|社会保障|社会保险|社会救助|社会福利)"),
     "economy_society", "distribution_security", ["经济与社会", "分配与社会保障"]),
    (re.compile(r"(?:党的领导|中国共产党.{0,12}(?:性质|宗旨|执政|领导)|全面从严治党|先锋模范作用)"),
     "politics_law", "party_leadership", ["政治与法治", "党的领导"]),
    (re.compile(r"(?:人民代表大会|人大代表|人民民主专政|全过程人民民主|人民民主|民族区域自治|基层群众自治|政党制度|宗教政策)"),
     "politics_law", "people_as_masters", ["政治与法治", "人民当家作主"]),
    (re.compile(r"(?:依法治国|法治国家|法治政府|法治社会|科学立法|严格执法|公正司法|全民守法)"),
     "politics_law", "rule_of_law", ["政治与法治", "依法治国"]),
    (re.compile(r"(?:哲学|唯物主义|唯心主义|物质.{0,8}意识|意识.{0,8}物质|规律|联系观|发展观|矛盾|辩证法|量变|质变)"),
     "philosophy_culture", "world_and_laws", ["哲学与文化", "世界与规律"]),
    (re.compile(r"(?:实践.{0,12}认识|认识.{0,12}实践|真理|社会存在|社会意识|生产力|生产关系|经济基础|上层建筑|人民群众.{0,8}历史|价值判断|价值选择|人生价值)"),
     "philosophy_culture", "society_and_values", ["哲学与文化", "社会与价值"]),
    (re.compile(r"(?:中华优秀传统文化|民族精神|文化自信|文化强国|革命文化|社会主义先进文化|文化.{0,10}(?:传承|创新|多样性|民族性|功能))"),
     "philosophy_culture", "culture_innovation", ["哲学与文化", "文化传承与创新"]),
)


def _politics_mapping(
    candidate: Mapping[str, Any],
    analysis: str,
) -> tuple[str, str, list[str], str] | None:
    section_key = str(candidate.get("section_key") or "")
    if section_key in {
        "current_affairs",
        "current_events",
        "annual_current_affairs",
        "时事政治",
    } or "时事政治" in analysis:
        return (
            "current_affairs",
            "annual_current_affairs",
            ["时事政治"],
            "explicit_source_current_affairs_section",
        )

    source_text = str(candidate.get("stem_text") or "")
    evidence_text = "\n".join(part for part in (source_text, analysis) if part)
    matches: dict[tuple[str, str], list[str]] = {}
    for pattern, chapter, section, tags in POLITICS_RULES:
        if pattern.search(evidence_text):
            matches[(chapter, section)] = list(tags)

    if len(matches) != 1:
        return None

    (chapter, section), tags = next(iter(matches.items()))
    basis = "source_stem_or_trusted_teacher_analysis"
    return chapter, section, tags, basis

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

        if subject == "politics":
            analysis = analyses.get(candidate_id, "")
            semantic = _politics_mapping(candidate, analysis)
            if semantic is not None:
                chapter, section, tags, basis = semantic
                decisions.append({
                    "candidate_id": candidate_id,
                    "decision": "assign",
                    "chapter_key": chapter,
                    "section_key": section,
                    "tags": tags,
                    "difficulty": "standard",
                    "note": (
                        f"{basis}; aligned_to_official_2023_syllabus; "
                        "difficulty requires later editorial calibration"
                    ),
                })
                continue
            decisions.append({
                "candidate_id": candidate_id,
                "decision": "defer",
                "note": "politics_semantic_ambiguous_or_unsupported",
            })
            continue

        decisions.append({
            "candidate_id": candidate_id,
            "decision": "defer",
            "note": "semantic_classification_required",
        })

    return {
        "schema_version": 1,
        "candidate_source_id": candidate_bank.get("source_id"),
        "subject": subject,
        "decisions": decisions,
    }
