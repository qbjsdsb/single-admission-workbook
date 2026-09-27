# English option-structure calibration v0.3

Date: 2026-09-28

This is a private-corpus calibration note. No raw question text, source filename,
source path, answer payload, or private identifier is committed.

## Scope

The full English DOCX fast lane currently consists of 12 student/original
documents. A local private preflight was run across all of those files to
investigate the remaining P1 option-structure work without publishing any source
payload.

The preflight reproduced two additional source-format patterns:

1. bare A can occupy its own paragraph while B/C/D retain punctuation on later
   paragraphs;
2. an acronym ending in A-D plus a period can look like a strict option marker
   when the parser searches for labels anywhere inside a paragraph.

The second case is especially important because it can manufacture a fake
choice marker inside valid option content.

## Parser hardening

The option parser now:

- accepts a bare A on its own line only when the next non-empty paragraph starts
  with a strict B marker;
- still accepts bare A followed by later strict markers in the same paragraph;
- still accepts bare B/C/D only as the exact next expected label;
- prevents uppercase acronym tails such as "...C." from becoming option labels;
- preserves support for genuinely glued Word exports such as "oneB. two";
- continues to fail closed on arbitrary trailing prose;
- ignores only a recognized volume separator after a complete A-D set.

## Private full-fast-lane preflight

Using paragraph text from all 12 private English student/original DOCX files,
all 520 choice questions that sit under explicit section headings parsed to a
complete A-D structure with the v0.3 option rules.

One source omits the first single-choice heading; its 20 first-section questions
remain intentionally review-gated by Candidate Bank section inference even when
their options are structurally readable.

This preflight is strong evidence that much of the former 65-item P1 structure
queue is formatting noise rather than semantic ambiguity. It is still not a
replacement for rerunning the repository's full Document AST -> Batch Review
pipeline, because that pipeline may preserve Word structure differently from the
paragraph-only preflight.

## Next check

Rerun the private subject-wide Batch Review from the existing intake cache. Only
that run should update the official whole-corpus P1 count in PROJECT_STATE.
