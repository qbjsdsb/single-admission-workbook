"""Private loss-aware OOXML capture. Unsupported objects remain explicit, never flattened away."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import zipfile
import xml.etree.ElementTree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
O = 'urn:schemas-microsoft-com:office:office'
V = 'urn:schemas-microsoft-com:vml'


def _package_path(target: str) -> str | None:
    if not target or '://' in target:
        return None
    path = PurePosixPath('word') / PurePosixPath(target)
    parts = []
    for part in path.parts:
        if part in ('', '.'):
            continue
        if part == '..':
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return '/'.join(parts)


def _relationship_assets(zf: zipfile.ZipFile, rels: dict[str, dict]) -> dict[str, dict]:
    names = set(zf.namelist())
    assets: dict[str, dict] = {}
    for rid, rel in rels.items():
        rel_type = rel.get('Type', '')
        if not (rel_type.endswith('/image') or rel_type.endswith('/oleObject')):
            continue
        target = rel.get('Target', '')
        package_path = _package_path(target)
        record = {
            'relationship_id': rid,
            'relationship_type': rel_type.rsplit('/', 1)[-1],
            'target': target,
            'package_path': package_path,
            'target_mode': rel.get('TargetMode', 'Internal'),
        }
        if package_path and package_path in names:
            payload = zf.read(package_path)
            record.update({
                'sha256': hashlib.sha256(payload).hexdigest(),
                'bytes': len(payload),
                'extension': Path(package_path).suffix.lower(),
            })
        else:
            record.update({
                'sha256': None,
                'bytes': None,
                'extension': Path(target).suffix.lower(),
            })
        assets[rid] = record
    return assets


def _drawing_records(block: ET.Element) -> list[dict]:
    out: list[dict] = []
    for drawing_index, drawing in enumerate(block.iter(f'{{{W}}}drawing')):
        blip = next(drawing.iter(f'{{{A}}}blip'), None)
        extent = next(drawing.iter(f'{{{WP}}}extent'), None)
        doc_pr = next(drawing.iter(f'{{{WP}}}docPr'), None)
        out.append({
            'index': drawing_index,
            'relationship_id': None if blip is None else blip.attrib.get(f'{{{R}}}embed'),
            'cx_emu': None if extent is None else int(extent.attrib.get('cx', 0) or 0),
            'cy_emu': None if extent is None else int(extent.attrib.get('cy', 0) or 0),
            'name': None if doc_pr is None else doc_pr.attrib.get('name'),
        })
    return out


def _ole_records(block: ET.Element) -> list[dict]:
    out: list[dict] = []
    for object_index, obj in enumerate(block.iter(f'{{{W}}}object')):
        ole = next(obj.iter(f'{{{O}}}OLEObject'), None)
        if ole is None:
            continue
        preview = next(obj.iter(f'{{{V}}}imagedata'), None)
        shape = next(obj.iter(f'{{{V}}}shape'), None)
        prog_id = ole.attrib.get('ProgID')
        out.append({
            'index': object_index,
            'relationship_id': ole.attrib.get(f'{{{R}}}id'),
            'preview_relationship_id': None if preview is None else preview.attrib.get(f'{{{R}}}id'),
            'prog_id': prog_id,
            'object_id': ole.attrib.get('ObjectID'),
            'shape_id': ole.attrib.get('ShapeID'),
            'shape_style': None if shape is None else shape.attrib.get('style'),
            'is_equation': bool(prog_id and prog_id.startswith('Equation.')),
        })
    return out


def extract_structure(path: Path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read('word/document.xml'))
        rels: dict[str, dict] = {}
        if 'word/_rels/document.xml.rels' in zf.namelist():
            for rel in ET.fromstring(zf.read('word/_rels/document.xml.rels')):
                rels[rel.attrib['Id']] = dict(rel.attrib)
        assets = _relationship_assets(zf, rels)

        blocks = []
        body = root.find(f'{{{W}}}body')
        for index, block in enumerate(body if body is not None else []):
            if block.tag == f'{{{W}}}sectPr':
                continue
            runs = []
            for run in block.iter(f'{{{W}}}r'):
                properties = run.find(f'{{{W}}}rPr')
                styles = {} if properties is None else {
                    p.tag.rsplit('}', 1)[-1]: p.attrib.get(f'{{{W}}}val', 'true') for p in properties}
                pieces = []
                for node in run.iter():
                    if node.tag == f'{{{W}}}t':
                        pieces.append(node.text or '')
                    elif node.tag == f'{{{W}}}tab':
                        pieces.append('\t')
                    elif node.tag == f'{{{W}}}br':
                        pieces.append('\n')
                runs.append({'text': ''.join(pieces), 'properties': styles})

            drawings = _drawing_records(block)
            ole_objects = _ole_records(block)
            vml_images = [
                image.attrib.get(f'{{{R}}}id')
                for image in block.iter(f'{{{V}}}imagedata')
                if image.attrib.get(f'{{{R}}}id')
            ]

            blocks.append({
                'locator': f'word/document.xml/body/{index}',
                'kind': block.tag.rsplit('}', 1)[-1],
                'runs': runs,
                'math_omml': [
                    ET.tostring(m, encoding='unicode')
                    for m in block.iter(f'{{{M}}}oMath')
                ],
                'image_relationships': [
                    record['relationship_id'] for record in drawings
                    if record.get('relationship_id')
                ],
                'vml_image_relationships': vml_images,
                'drawings': drawings,
                'ole_objects': ole_objects,
                # Full block retained so tables/OLE/VML can be repaired from source.
                'xml': ET.tostring(block, encoding='unicode'),
            })
        return {
            'blocks': blocks,
            'relationships': rels,
            'assets': assets,
            'status': 'captured_not_canonical_verified',
        }
