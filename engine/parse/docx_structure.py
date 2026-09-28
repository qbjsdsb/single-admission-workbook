"""Private loss-aware OOXML capture. Unsupported objects remain explicit, never flattened away."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
O = 'urn:schemas-microsoft-com:office:office'
V = 'urn:schemas-microsoft-com:vml'


def _embedded_mathml(payload: bytes) -> dict[str, str] | None:
    """Read MathType's plain MathML clipboard payload when embedded in a WMF.

    A substantial subset of legacy Word WMF previews contain an XML MathML
    comment alongside the drawing records.  Only flat identifier/number/
    operator expressions are normalized to text; structural expressions stay
    rich-content blockers so we never flatten fractions, scripts, or layouts.
    """
    match = re.search(rb'(<math\b[\s\S]*?</math>)', payload)
    if not match:
        return None
    try:
        mathml = match.group(1).decode('utf-8', 'strict')
    except UnicodeDecodeError:
        return {'mathml_status': 'embedded_unparseable_encoding'}
    try:
        root = ET.fromstring(mathml)
    except ET.ParseError:
        return {'mathml_xml': mathml, 'mathml_status': 'embedded_unparseable'}
    tags = [element.tag.rsplit('}', 1)[-1] for element in root.iter()]
    flat_tags = {'math', 'mi', 'mn', 'mo', 'mtext'}
    if not tags or any(tag not in flat_tags for tag in tags):
        return {'mathml_xml': mathml, 'mathml_status': 'embedded_complex_unverified'}
    text = ''.join(root.itertext())
    if not text:
        return {'mathml_xml': mathml, 'mathml_status': 'embedded_empty'}
    return {
        'mathml_xml': mathml,
        'mathml_status': 'inline_text',
        'mathml_inline_text': text,
    }


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
            if Path(package_path).suffix.lower() == '.wmf':
                record.update(_embedded_mathml(payload) or {})
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


def _run_properties(run: ET.Element) -> dict[str, str]:
    properties = run.find(f'{{{W}}}rPr')
    return {} if properties is None else {
        child.tag.rsplit('}', 1)[-1]: child.attrib.get(f'{{{W}}}val', 'true')
        for child in properties
    }


def _ordered_inline_content(
    block: ET.Element,
    drawings: list[dict],
    ole_objects: list[dict],
) -> list[dict]:
    drawing_elements = list(block.iter(f'{{{W}}}drawing'))
    drawing_by_id = {id(element): index for index, element in enumerate(drawing_elements)}
    ole_by_element_index = {int(record['index']): record for record in ole_objects}
    object_elements = list(block.iter(f'{{{W}}}object'))
    object_by_id = {
        id(element): ole_by_element_index[index]
        for index, element in enumerate(object_elements)
        if index in ole_by_element_index
    }
    content: list[dict] = []

    def walk(element: ET.Element, properties: dict[str, str] | None = None) -> None:
        tag = element.tag
        if tag in {f'{{{W}}}pPr', f'{{{W}}}rPr'}:
            return
        if tag == f'{{{W}}}r':
            run_properties = _run_properties(element)
            for child in element:
                if child.tag != f'{{{W}}}rPr':
                    walk(child, run_properties)
            return
        if tag == f'{{{W}}}t':
            if element.text:
                content.append({'kind': 'text', 'text': element.text, 'properties': properties or {}})
            return
        if tag == f'{{{W}}}tab':
            content.append({'kind': 'text', 'text': '\t', 'properties': properties or {}})
            return
        if tag == f'{{{W}}}br':
            content.append({'kind': 'text', 'text': '\n', 'properties': properties or {}})
            return
        if tag == f'{{{W}}}drawing':
            index = drawing_by_id.get(id(element))
            if index is not None:
                content.append({'kind': 'drawing', **drawings[index]})
            return
        if tag == f'{{{W}}}object':
            record = object_by_id.get(id(element))
            if record is not None:
                content.append({'kind': 'ole_object', **record})
                return
        if tag == f'{{{M}}}oMath':
            content.append({
                'kind': 'math_omml',
                'xml': ET.tostring(element, encoding='unicode'),
            })
            return
        if tag == f'{{{V}}}imagedata':
            rid = element.attrib.get(f'{{{R}}}id')
            if rid:
                content.append({'kind': 'vml_image', 'relationship_id': rid})
            return
        for child in element:
            walk(child, properties)

    for child in block:
        if child.tag != f'{{{W}}}pPr':
            walk(child)
    return content


def _numbering_definitions(zf: zipfile.ZipFile) -> tuple[dict[str, dict], dict[str, dict]]:
    """Read the direct OOXML list definitions needed to preserve printed labels."""
    if 'word/numbering.xml' not in zf.namelist():
        return {}, {}
    root = ET.fromstring(zf.read('word/numbering.xml'))
    abstract: dict[str, dict] = {}
    for node in root.findall(f'{{{W}}}abstractNum'):
        abstract_id = node.attrib.get(f'{{{W}}}abstractNumId')
        if abstract_id is None:
            continue
        levels: dict[int, dict] = {}
        for level in node.findall(f'{{{W}}}lvl'):
            ilvl = int(level.attrib.get(f'{{{W}}}ilvl', '0'))
            value = {}
            for name in ('start', 'numFmt', 'lvlText'):
                child = level.find(f'{{{W}}}{name}')
                if child is not None:
                    value[name] = child.attrib.get(f'{{{W}}}val')
            levels[ilvl] = value
        abstract[abstract_id] = levels

    numbers: dict[str, dict] = {}
    for node in root.findall(f'{{{W}}}num'):
        num_id = node.attrib.get(f'{{{W}}}numId')
        abstract_id = node.find(f'{{{W}}}abstractNumId')
        if num_id is None or abstract_id is None:
            continue
        record = {'abstract_id': abstract_id.attrib.get(f'{{{W}}}val'), 'overrides': {}}
        for override in node.findall(f'{{{W}}}lvlOverride'):
            ilvl = int(override.attrib.get(f'{{{W}}}ilvl', '0'))
            value: dict[str, str] = {}
            start = override.find(f'{{{W}}}startOverride')
            if start is not None and start.attrib.get(f'{{{W}}}val') is not None:
                value['start'] = start.attrib[f'{{{W}}}val']
            level = override.find(f'{{{W}}}lvl')
            if level is not None:
                for name in ('start', 'numFmt', 'lvlText'):
                    child = level.find(f'{{{W}}}{name}')
                    if child is not None and child.attrib.get(f'{{{W}}}val') is not None:
                        value[name] = child.attrib[f'{{{W}}}val']
            record['overrides'][ilvl] = value
        numbers[num_id] = record
    return abstract, numbers


def _numbering_marker(
    block: ET.Element,
    abstract: dict[str, dict],
    numbers: dict[str, dict],
    counters: dict[tuple[str, int], int],
    seen_instances: set[tuple[str, int]],
) -> tuple[str | None, bool]:
    ppr = block.find(f'{{{W}}}pPr')
    num_pr = None if ppr is None else ppr.find(f'{{{W}}}numPr')
    if num_pr is None:
        return None, False
    num_node = num_pr.find(f'{{{W}}}numId')
    if num_node is None:
        return None, False
    num_id = num_node.attrib.get(f'{{{W}}}val')
    if not num_id or num_id not in numbers:
        return None, True
    level_node = num_pr.find(f'{{{W}}}ilvl')
    ilvl = int(level_node.attrib.get(f'{{{W}}}val', '0')) if level_node is not None else 0
    number = numbers[num_id]
    level = (abstract.get(str(number.get('abstract_id'))) or {}).get(ilvl, {})
    config = {**level, **(number.get('overrides') or {}).get(ilvl, {})}
    fmt = str(config.get('numFmt') or 'decimal')
    level_text = str(config.get('lvlText') or '')
    if fmt == 'none' or not level_text:
        return None, False
    # Only synthesize the common one-level Arabic markers used for numbered
    # questions. Leave other list schemes visible to review instead of guessing.
    if ilvl != 0 or fmt != 'decimal' or level_text not in {'%1.', '%1', '%1)', '(%1)'}:
        return None, True
    abstract_id = str(number.get('abstract_id') or '')
    counter_key = (abstract_id, ilvl)
    instance_key = (num_id, ilvl)
    overrides = number.get('overrides') or {}
    override = overrides.get(ilvl) or {}

    # Word processors sometimes create a new numId in the middle of a list
    # while keeping the same abstractNum. In that case the printed sequence
    # continues unless the new instance has an explicit startOverride. Keep
    # the counter at abstractNum/level scope to match that rendered sequence.
    try:
        if instance_key not in seen_instances:
            seen_instances.add(instance_key)
            if override.get('start') is not None:
                counters[counter_key] = int(override['start'])
            elif counter_key in counters:
                counters[counter_key] += 1
            else:
                counters[counter_key] = int(level.get('start') or '1')
        else:
            counters[counter_key] += 1
    except (KeyError, ValueError):
        return None, True
    return level_text.replace('%1', str(counters[counter_key])), False


def extract_structure(path: Path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read('word/document.xml'))
        rels: dict[str, dict] = {}
        if 'word/_rels/document.xml.rels' in zf.namelist():
            for rel in ET.fromstring(zf.read('word/_rels/document.xml.rels')):
                rels[rel.attrib['Id']] = dict(rel.attrib)
        assets = _relationship_assets(zf, rels)
        abstract_numbering, numbering_lists = _numbering_definitions(zf)

        blocks = []
        warnings: set[str] = set()
        numbering_counters: dict[tuple[str, int], int] = {}
        seen_numbering_instances: set[tuple[str, int]] = set()
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

            numbering_marker, numbering_unsupported = _numbering_marker(
                block, abstract_numbering, numbering_lists,
                numbering_counters, seen_numbering_instances,
            )
            if numbering_unsupported:
                warnings.add('numbering_not_normalized')
            record = {
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
                'inline_content': _ordered_inline_content(block, drawings, ole_objects),
                # Full block retained so tables/OLE/VML can be repaired from source.
                'xml': ET.tostring(block, encoding='unicode'),
            }
            if numbering_marker is not None:
                record['numbering_marker'] = numbering_marker
            blocks.append(record)
        return {
            'blocks': blocks,
            'relationships': rels,
            'assets': assets,
            'warnings': sorted(warnings),
            'status': 'captured_not_canonical_verified',
        }
