from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from engine.parse.docx_structure import extract_structure


def export_docx_assets(path: Path, out_dir: Path) -> dict:
    """Export relationship-backed DOCX assets by content hash.

    This is a private derived-artifact helper. It never mutates the source DOCX and
    does not place private assets into the public repository.
    """
    structure = extract_structure(path)
    assets = structure.get("assets") or {}
    out_dir.mkdir(parents=True, exist_ok=True)

    exported: dict[str, dict] = {}
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for rid, record in sorted(assets.items()):
            package_path = record.get("package_path")
            if not package_path or package_path not in names:
                exported[rid] = {**record, "export_status": "missing"}
                continue

            payload = zf.read(package_path)
            digest = hashlib.sha256(payload).hexdigest()
            extension = str(record.get("extension") or Path(package_path).suffix.lower())
            filename = digest + extension
            target = out_dir / filename
            if not target.exists():
                target.write_bytes(payload)

            exported[rid] = {
                **record,
                "sha256": digest,
                "bytes": len(payload),
                "export_status": "exported",
                "export_name": filename,
            }

    manifest = {
        "source_name": path.name,
        "asset_count": len(exported),
        "assets": exported,
    }
    (out_dir / "assets-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
