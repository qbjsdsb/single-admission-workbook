# English real XeLaTeX smoke v0.1

Date: 2026-09-28

This note records a private-source visual calibration. No raw question text,
source filename, source path, answer payload, or private identifier is committed.

## Scope

One real English cloze group from the private corpus was normalized into the
existing grouped Canonical shape and rendered with the repository A4/XeLaTeX
visual language:

- 1 shared passage;
- 10 child choice questions;
- student and teacher editions use the same child order;
- every child in this smoke sample had source-provided answer and analysis evidence.

The local smoke output was 3 A4 student pages and 4 A4 teacher pages.

## Finding

The source text, Chinese/Latin font mix, option grids, footer and teacher
analysis all rendered without obvious clipping or broken glyphs in the inspected
pages. The smoke did expose one publication-layout defect: a choice-question
prompt could remain at the bottom of one page while its A/B/C/D option grid was
moved alone to the next page.

That split is legal TeX but poor workbook typography.

## Fix

Choice questions now reserve a small block before the prompt:

- student edition: 6 baselines;
- teacher edition: 7 baselines so the answer line is less likely to orphan.

The existing option-level Needspace guard remains in place as a secondary
protection for longer options. This is intentionally a narrow renderer fix,
not a new workflow layer.

## Boundary

This smoke verifies one real grouped question shape only. It does not replace
the planned full private English Canonical sample, subject-wide Editorial Queue,
or final visual review.
