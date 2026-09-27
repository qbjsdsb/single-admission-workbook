# Mathematics and DOCX asset audit v0.1

Private calibration against the supplied source archive shows that legacy embedded equation objects and media assets are more important than OMML for this corpus.

## Whole DOCX corpus

Across 110 private DOCX files:

- 492 media payloads;
- 302 embedding payloads;
- 302 OLE objects;
- all 302 OLE objects are Equation-family objects;
- 378 DrawingML drawings;
- 394 VML image references;
- only 3 OMML math objects.

Media extensions:

- WMF: 270
- PNG: 166
- JPEG: 56

The Equation OLE objects are concentrated in the mathematics prep material.

## Mathematics prep DOCX

Observed aggregate facts from the private mathematics prep file:

- 302 embedded OLE objects;
- all 302 use Equation-family ProgIDs:
  - Equation.2: 169
  - Equation.DSMT4: 124
  - Equation.3: 9
- 218 media payloads:
  - 202 WMF
  - 16 PNG
- 302 embedding payloads;
- 42 DrawingML drawings.

This means a production-safe mathematics pipeline cannot rely on OMML conversion alone.

## Current policy

Document AST preserves:

- OLE relationship ID;
- Equation ProgID;
- preview-image relationship ID when present;
- object/preview asset hashes and package targets;
- DrawingML image relationship, dimensions and name;
- original OOXML evidence.

The private asset exporter stores relationship-backed payloads by SHA-256, so repeated extraction does not create multiple copies of the same binary asset.

The next conversion layer may choose a verified route:

1. equation-semantics converter;
2. preview-image fidelity route;
3. manual-review route.

Until one of these is verified, the canonical question pipeline must not silently flatten or discard equation objects.
