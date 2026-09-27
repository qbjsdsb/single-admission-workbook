# Document AST v1

The workbook project now uses a renderer-neutral intermediate document model between source readers and question extraction.

## Why

Previously DOCX intake exposed both flattened paragraphs and an OOXML-specific structure, while PDF intake exposed page dictionaries. Question extraction would eventually need separate logic for each source type and could accidentally lose semantic formatting.

Document AST v1 makes the boundary explicit:

```
DOCX reader ----\
PDF reader ------> Document AST -> question segmentation -> Canonical Question
OCR reader -----/
MinerU/Docling --/
```

## Preservation rules

- text remains text;
- bold, italic, underline and Chinese emphasis dots are semantic styles;
- DOCX OMML math is captured as `math_omml` until a verified converter exists;
- DOCX images remain `image_ref` nodes until asset extraction/placement is verified;
- tables remain explicit unsupported blocks until a table adapter is verified;
- PDF text keeps page number and bounding box;
- low-text PDF pages remain explicit `ocr_required` blocks rather than silently disappearing.

The question layer MUST NOT consume unsupported or unnormalized nodes as if they were plain text.

## Design constraint

Document AST is a private derived artifact. Source provenance remains private and publication renderers consume Canonical Questions, not raw Document AST.
