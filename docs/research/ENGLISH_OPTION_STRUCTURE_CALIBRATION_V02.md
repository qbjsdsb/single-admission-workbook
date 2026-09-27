# English option-structure calibration v0.2

Date: 2026-09-28

This is a private-corpus calibration note. No raw question text, source filename,
source path, answer payload, or private identifier is committed.

## Why this change exists

The first full English business run left 65 choice candidates fail-closed for
structural review. A focused check of two representative private student papers
showed a recurring source-format pattern rather than a semantic ambiguity:

- a leading option label can lose its punctuation while a later label on the
  same Word paragraph still has punctuation;
- later standalone option labels can also lose punctuation;
- a volume separator can remain after the final A-D option set of a section.

With the previous strict marker parser, those cases remained in the P1
candidate-structure queue.

## Narrow recovery rule

The parser now accepts a bare leading label only when evidence is strong:

- bare A is accepted only when a later strict B/C/D marker appears in the same
  paragraph;
- bare B/C/D is accepted only after option parsing has already started and the
  label is exactly the next expected label;
- an ordinary stem beginning with "A ..." is therefore not promoted into an
  option row;
- arbitrary free text after A-D still fails closed;
- only a recognized volume separator is ignored after a complete A-D set.

Synthetic regressions cover both recovery and false-positive guards.

## Private spot check

On the two representative student papers used for this calibration, the seven
choice-structure flags caused by these punctuation/volume patterns reduce to
zero under the new rules. This is a spot check, not a claim that all 65
subject-wide structural flags are resolved.

The next private subject-wide Batch Review must measure the actual reduction
before PROJECT_STATE changes the 65-item whole-corpus figure.
