# Workbook build image

This image pre-installs the stable publication toolchain used by the eight-book pipeline:

- Python 3 + pinned project Python dependencies;
- XeLaTeX and Chinese/extra TeX packages;
- Fandol Song/Hei/Kai from TeX Live;
- Tinos;
- Poppler PDF inspection/rendering tools.

The image is intentionally **publication-only**. Legacy DOC conversion and heavy OCR remain separate concerns so the common PDF build image stays smaller and faster.

## Rollout policy

1. Pull requests that change the image run a Docker build smoke test.
2. Pushes to `main` may publish a content-addressed GHCR tag.
3. The existing apt-based print job remains the fallback until the published image has produced equivalent eight-book artifacts.
4. Only after equivalence is proven should the main print job switch to the image.
