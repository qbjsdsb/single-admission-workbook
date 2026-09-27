# ADR-001: XeLaTeX first, renderer-neutral data model

Status: accepted for the current phase

## Context

The supplied source sample is already a competent XeLaTeX implementation of the desired A4 teaching-material visual language: Chinese font roles, emphasis dots, TeX mathematics, TikZ ornament, multi-column English reading, writing lines, and footer/header geometry.

The main defects are architectural rather than limitations of XeLaTeX: content is embedded directly in one TeX file, layout primitives do not share one grid, answer space is hand-tuned, and student/teacher editions are not data-driven.

## Decision

- Keep XeLaTeX as the first production PDF renderer.
- Move all durable content into renderer-neutral structured data.
- Treat the renderer as replaceable.
- Do not rewrite the project in Typst before the canonical data model and end-to-end student/teacher build are proven.
- Run a Typst comparison spike only after renderer contract v1 is stable.

## Why

This is the fastest low-risk path: it preserves the supplied visual source while avoiding long-term coupling of the question bank to LaTeX.

## Consequences

- Visual work can continue immediately.
- Future Typst/DOCX/HTML renderers remain possible.
- LaTeX macros must not become the canonical content format.
