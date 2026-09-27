# Corpus audit v0.1

Basis: the user-provided `单招教研.zip`. This document stores aggregate research only; it does not publish the private source files or full path manifest.

## Archive inventory

- Files: 224
- Uncompressed size: about 440.8 MiB
- DOCX: 110
- PDF: 82
- legacy DOC: 31
- PNG: 1

### By subject

- Chinese: 66
- Mathematics: 32
- English: 75
- Politics: 51

### Filename/path heuristic source classes

These are routing hints, not final editorial judgments.

- mock_exam: 122
- past_exam: 63
- study_note: 32
- reference: 5
- syllabus: 1
- mind_map: 1
- other: 0

The classifier was calibrated on the real archive so terms such as “押题” and “冲刺” route to mock_exam. A true-exam parent directory can also recover a file whose own filename contains a typo.

### Pairing

Name normalization currently finds 38 exact candidate groups where a student/original version has a teacher/solution/answer counterpart. Pairing is still provisional until question-level/content fingerprints confirm that the documents contain the same question set.

## Important content capabilities already observed in the corpus

- Chinese DOCX uses semantic emphasis dots; flattening runs to plain text would destroy assessed “加点” information.
- The corpus contains underlines and OMML math objects.
- Several math resources depend on formulas and/or diagrams.
- Student/teacher and original/solution pairs are common enough to support automated alignment.
- At least one inspected politics student/teacher pair has inconsistent stated score totals, so teacher files cannot be trusted blindly as authoritative.
- Some source files contain third-party copyright/promotion markers. Source provenance and redistribution rights therefore stay private and separate from publication data.

## Processing policy

1. Inventory does not alter original files.
2. Probe determines text/scan/mixed PDF and DOCX capabilities.
3. Fast lane processes DOCX, converted DOC, and text PDFs first.
4. Slow lane handles scan/mixed PDFs only where needed.
5. Parsed questions are classified independently of the source folder.
6. Source provenance is internal and never rendered into student/teacher books by default.
