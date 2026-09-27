# Candidate Question Bank v0.1

Candidate Bank is the review boundary between source parsing and the canonical question bank.

It exists because a parser may be structurally confident that a source contains “question 12 in the reading section” without yet being entitled to publish that content as a verified canonical question.

## v0.1 fast lane

Supported subjects:

- English DOCX/text-like Document AST;
- Politics DOCX/text-like Document AST.

The extractor is section-first. Number-like lines before a recognized exam section are ignored, preventing exam instructions from becoming questions.

It preserves:

- source ID;
- source question number;
- section/type;
- source block locators;
- parsed A/B/C/D options when unambiguous;
- English cloze/reading shared-material groups;
- explicit 'needs_review' status for ambiguous option structure;
- explicit blockers for unsupported Document AST blocks or rich inline nodes.

## Safety boundary

Candidate Bank is not Canonical Question Bank.

A candidate may not enter publication merely because it parsed. Promotion still requires source/teacher pairing, answer-evidence verification, rich-content fidelity, duplicate/conflict checks, chapter assignment, and score/editorial validation.

Unsupported images, OMML, Equation OLE, tables, or OCR-required content remain blockers instead of being flattened away.

## Private-source operation

Real source content and candidate banks derived from it stay in the private work area. The public repository contains only parser code, schemas, aggregate research notes, and synthetic fixtures.
