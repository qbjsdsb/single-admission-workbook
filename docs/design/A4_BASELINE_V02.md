# A4 Design Baseline v0.2

This prototype converts the current workbook visual target into explicit, testable layout rules.

## Frozen decisions

- Page size: A4 only.
- Publication pages contain no engineering metadata, source IDs, parser state, GitHub text, confidence values, or audit status.
- Header reproduces the current sample structure: subject/module at upper left, task label plus book icon at upper right, title below.
- Footer reproduces the current sample structure: 青云阁 / 教育, short connector line, deterministic motivational quotation, page number.
- Question layout uses a shared horizontal grid:
  - question number at the text edge;
  - score starts 4 mm after the text edge;
  - question stem starts at 21.05 mm;
  - answer choices start on the score column;
  - math sub-parts start on the score column.
- Chinese emphasis marks are semantic, not flattened into plain text.
- Math uses real math typesetting.
- Student answer space is part of layout, especially for math solution questions.

## Font policy

The supplied reference PDF embeds SimSun, SimHei, KaiTi and Times New Roman. Those proprietary Chinese fonts are not bundled in this public repository.

The public CI prototype therefore uses open/reproducible substitutes:
- Song-style body: AR PL SungtiL GB
- Hei-style headings: FandolHei
- Kai-style title/footer: AR PL KaitiM GB
- Latin: Tinos

If a private publishing environment later provides licensed fonts, the font layer can be swapped without changing the content model or layout API.

## Purpose

This is a visual baseline, not the final data model or book structure. Once the baseline is approved, the renderer will be separated from chapter/question data and student/teacher edition logic.
