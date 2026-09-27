"""Private loss-aware OOXML capture. Unsupported objects remain explicit, never flattened away."""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def extract_structure(path: Path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read('word/document.xml'))
        rels = {}
        if 'word/_rels/document.xml.rels' in zf.namelist():
            for rel in ET.fromstring(zf.read('word/_rels/document.xml.rels')):
                rels[rel.attrib['Id']] = dict(rel.attrib)
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
                runs.append({'text': ''.join(pieces),
                             'properties': styles})
            blocks.append({'locator': f'word/document.xml/body/{index}',
                           'kind': block.tag.rsplit('}', 1)[-1], 'runs': runs,
                           'math_omml': [ET.tostring(m, encoding='unicode') for m in block.iter(f'{{{M}}}oMath')],
                           'image_relationships': [b.attrib.get(f'{{{R}}}embed') for b in block.iter(f'{{{A}}}blip')],
                           # Full block retained so tables/OLE/VML can be repaired from source.
                           'xml': ET.tostring(block, encoding='unicode')})
        return {'blocks': blocks, 'relationships': rels,
                'status': 'captured_not_canonical_verified'}
