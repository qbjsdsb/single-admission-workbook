# English real business run v0.1

Date: 2026-09-28

This is a private-corpus calibration report. No raw questions, source filenames, source paths, teacher text, or private IDs are committed.

## Scope

The first real production run used 12 paired English student/original and teacher/solution DOCX source pairs from the user's private corpus.

The run exercised the current production chain:

Document AST -> Candidate Bank -> Evidence Bank -> Pairing Review -> Verification Aggregate -> Score Evidence -> Safe Classification -> Teacher Enrichment -> Editorial Queue -> Grouped Canonical sample selection.

## Structural extraction

Across the 12 student/original sources:

- 672 candidate units were extracted;
- every source produced 56 units;
- the common shape was 55 numbered items plus one writing item;
- 475 choice items parsed with a complete option structure;
- 65 choice items remained fail-closed for structural review.

No structural-review candidate was silently promoted.

## Answer evidence

After the real-source Evidence Bank calibration fixes in this PR:

- 660 / 660 numbered items have one unique answer-evidence value;
- 0 numbered items are missing answer evidence;
- 0 machine-visible answer conflicts remain in this calibration set.

This is evidence completeness, not an independent claim that every answer is academically correct. Verification Manifest approval remains a separate gate.

## Teacher analysis

- 581 / 660 numbered items have teacher-analysis evidence;
- 79 numbered items currently lack teacher-analysis evidence.

Missing teacher analysis remains visible to the Editorial Queue and blocks teacher-sample eligibility by default.

## Score evidence

Across 60 source sections:

- 59 sections have usable score evidence;
- 1 section remains incomplete because the source omits the first-section heading and therefore does not expose a safe score declaration.

The incomplete section remains review-gated rather than receiving a guessed default score.

## Safe classification

Only taxonomy placement directly supported by source structure is auto-proposed:

- 132 candidate units receive safe direct assignments;
- 540 remain deferred for semantic/editorial classification.

No reading sub-skill, grammar point, vocabulary category, or Politics taxonomy is guessed from question number alone.

## First private real sample

A first private grouped-cloze sample was produced from source pairs meeting all sample prerequisites:

- 7 cloze groups;
- 70 child questions;
- every selected child has a unique bound answer and reviewed teacher analysis;
- shared cloze material is preserved once per group;
- the student and teacher samples use exactly the same selected groups/questions.

Private output validation:

- student sample: 16 A4 pages;
- teacher sample: 23 A4 pages;
- both rendered successfully for visual inspection;
- no obvious clipping, missing blocks, or black-glyph failures were observed in the rendered overview.

The ReportLab sample is a business-loop proof, not the final visual master. Production publication continues to target the repository XeLaTeX/A4 renderer and its typography/navigation gates.

## Real-source parser failures discovered by this run

The real run found and regression-tested three previously hidden evidence risks:

1. teacher analysis labeled with a combined topic/analysis prefix was not captured;
2. compact range answer summaries were not captured;
3. decimal prose could be misread as a compact numbered answer row;
4. a teacher source with no first single-choice heading could leave its first-section evidence unscoped.

The parser now handles these cases fail-closed with synthetic regressions.

## Next business step

Use the subject-wide Editorial Queue to resolve P0/P1 items first, then produce the first repository-rendered real English chapter sample. After English stabilizes, repeat the same production loop for Politics, Chinese, then Mathematics.
