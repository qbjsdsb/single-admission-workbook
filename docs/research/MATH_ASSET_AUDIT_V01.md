# Mathematics asset audit v0.1

Private calibration against the supplied mathematics prep DOCX revealed that legacy embedded equation objects are more important than OMML for this corpus.

Observed aggregate facts from the private source file:

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

The next conversion layer may choose a verified route:

1. equation semantics converter;
2. preview-image fidelity route;
3. manual-review route.

Until one of these is verified, the canonical question pipeline must not silently flatten or discard equation objects.
