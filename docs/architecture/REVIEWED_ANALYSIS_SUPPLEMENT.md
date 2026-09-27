# Reviewed teacher-analysis supplementation v0.1

Date: 2026-09-28

## Purpose

Some real source papers contain verified answers but no teacher explanation.
Those gaps must not be filled by pretending generated prose came from the source.

This workflow keeps two truths separate:

1. source-derived Teacher Enrichment remains unchanged;
2. generated or editorial explanations live in a separate supplement manifest
   until an explicit review decision approves them.

## Publication boundary

An approved supplement row must contain a non-empty review note. Deferred or
rejected rows never enter Canonical Draft input.

A reviewed supplement may fill a missing analysis only. It cannot overwrite a
different source-provided teacher analysis. Unknown candidate IDs fail closed.

The Canonical Draft build accepts the optional analysis-supplement manifest and
applies that boundary immediately before Canonical promotion.

## English use

The current private English audit shows 75 numbered questions where the source
genuinely lacks teacher analysis after parser-caused omissions are recovered.
Those 75 may now be drafted by an AI/editor, reviewed explicitly, and then
merged without contaminating source evidence.

This mechanism does not generate explanations itself and does not weaken answer
verification, classification, scoring, or publication gates.
