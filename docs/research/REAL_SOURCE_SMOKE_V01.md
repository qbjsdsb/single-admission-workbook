# Real-source smoke test v0.1

This note records aggregate results from private local calibration against the user-provided source archive. No raw source text is published here.

## 2021 English true-paper pair

The student/original DOCX and parsed/solution DOCX were inspected privately.

Student document:
- 201 paragraphs
- section headings detected for:
  - single choice
  - cloze
  - reading comprehension
  - word spelling
  - written expression

Section-scoped numbered-question counts:
- single choice: 20 (1-20)
- cloze: 10 (21-30)
- reading comprehension: 15 (31-45)
- word spelling: 10 (46-55)
- written expression: treated as one composition task, not as numbered questions

Important parser lesson:
- the document contains numbered exam instructions before the first section;
- the writing prompt contains its own numbered bullet points;
- therefore global "line starts with a number" splitting is unsafe.
- section-first splitting correctly excludes exam instructions and preserves writing bullets inside the composition task.

Teacher/solution document:
- 296 paragraphs
- explicit answer lines are present and can be associated after section/question scoping.

## 2025 Politics mock student/answer pair

Private smoke-test counts:
- single choice: 25 (1-25)
- fill blanks: 5 (26-30)
- material/short-answer: 3 (31-33)

The answer document contains both:
- one compact answer-summary row for the choice section;
- per-question "答案 / 题干核心 / 解析" records.

This supports the current companion-answer parser strategy, but the answer file remains evidence rather than unquestioned truth; later content QA must still detect score and answer inconsistencies.

## Consequence

The first public E2E fixture remains fictional for redistribution safety, while parser decisions are calibrated against real private source structure.
