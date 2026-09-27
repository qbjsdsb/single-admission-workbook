# Parser calibration v0.1

Private calibration corpus: user-provided source archive. No raw questions are reproduced here.

## 2021 English original / solution DOCX pair

The section splitter recovers the source structure as:

- single_choice: 20 numbered items (1-20)
- cloze: one shared passage + 10 numbered items (21-30)
- reading: four passage groups (A-D) + 15 numbered items (31-45)
- word_spelling: 10 numbered items (46-55)
- writing: one unnumbered composition task

The companion-answer parser recovers answer annotations for all numbered items 1-55 after accounting for two source lines where the punctuation after the question number is missing.

This is why the parser must tolerate both “12. …” and “12 …” while still limiting question numbers to 1-3 digits.

## 2025 Politics student / answer DOCX pair

The section splitter recovers:

- single_choice: 25 items
- fill_blank: 5 items
- material_answer: 3 items

The answer parser recovers annotations for numbered items 1-33 using three observed patterns:

- question + separate “答案：…” + “解析：…”
- compact fill-answer rows such as multiple numbered answers in one paragraph
- numbered long-answer rows

## Consequences

1. Section parsing must precede question parsing.
2. English cloze and reading cannot be flattened into independent questions before shared material is attached.
3. Writing tasks may be unnumbered in source documents.
4. Source punctuation errors are expected and should be normalized rather than silently dropping questions.
5. Pairing is first based on source metadata/name, then confirmed later by question-number coverage and content fingerprints.
