from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
import subprocess
import shutil
import threading
import zipfile

from engine.ingest.inventory import inventory_zip, summarize
from engine.ingest.pairing import exact_pair_candidates
from engine.ingest.probe import probe_docx
from engine.parse.docx_text import extract_docx_paragraphs
from engine.document.docx_reader import structure_to_document_ast
from engine.document.pdf_reader import read_pdf_document_with_pages

VERSION = 'intake-3-document-ast'
PDF_LOCK = threading.Lock()
CONVERSION_LIMIT = threading.Semaphore(2)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def extract(path):
    if path.suffix == '.doc' and shutil.which('soffice'):
        with CONVERSION_LIMIT, tempfile.TemporaryDirectory() as td:
            destination = Path(td)
            result = subprocess.run(['soffice', '-env:UserInstallation=' + (destination / 'profile').as_uri(),
                                     '--headless', '--convert-to', 'docx', '--outdir', str(destination), str(path)],
                                    capture_output=True, timeout=120)
            converted = destination / (path.stem + '.docx')
            if result.returncode or not converted.exists():
                raise ValueError('legacy conversion failed')
            content = extract(converted)
            content['converted_from'] = 'doc'
            content['required_work'].append('conversion_fidelity_review')
            return content
    if path.suffix == '.docx':
        from engine.parse.docx_structure import extract_structure
        probe = asdict(probe_docx(path))
        warnings = [key for key in ('tables', 'emphasis_marks', 'underlines',
                                    'math_objects', 'media_files', 'embedded_files') if probe[key]]
        structure = extract_structure(path)
        document_ast = structure_to_document_ast(structure).to_dict()
        return {'format': 'docx', 'probe': probe,
                'paragraphs': extract_docx_paragraphs(path), 'structure': structure,
                'document_ast': document_ast,
                'required_work': ['rich_structure_review'] if warnings else ['question_segmentation'],
                'rich_features': warnings}
    if path.suffix == '.pdf':
        with PDF_LOCK:
            document_ast, pages = read_pdf_document_with_pages(path)
        return {'format': 'pdf', 'pages': pages, 'document_ast': document_ast.to_dict(),
                'required_work':
                ['ocr' if any(p['needs_ocr'] for p in pages) else 'layout_segmentation']}
    return {'format': path.suffix.lstrip('.'), 'required_work':
            ['legacy_conversion' if path.suffix == '.doc' else 'ocr' if path.suffix in
             ('.png', '.jpg', '.jpeg') else 'unsupported_format']}


def intake(archive: Path, out: Path, workers=4):
    if workers < 1 or workers > 8:
        raise ValueError('workers must be between 1 and 8')
    with zipfile.ZipFile(archive) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP member names require disambiguation before intake')
    items = inventory_zip(archive)
    cache = out / 'cache'
    cache.mkdir(parents=True, exist_ok=True)
    try:
        pdf_version = importlib.metadata.version('PyMuPDF')
    except importlib.metadata.PackageNotFoundError:
        pdf_version = 'unavailable'
    dependencies = [Path(__file__), Path(__file__).parents[1] / 'parse/docx_structure.py',
                    Path(__file__).parents[1] / 'parse/docx_text.py', Path(__file__).parents[1] / 'ingest/probe.py',
                    Path(__file__).parents[1] / 'document/model.py',
                    Path(__file__).parents[1] / 'document/docx_reader.py',
                    Path(__file__).parents[1] / 'document/pdf_reader.py']
    converter = subprocess.run(['soffice', '--version'], capture_output=True, timeout=15).stdout if shutil.which('soffice') else b'unavailable'
    engine_digest = hashlib.sha256(b''.join(p.read_bytes() for p in dependencies) + converter).hexdigest()
    # Inputs and parser implementation/version all affect cache identity.
    unique = {(i.sha256, i.extension): i for i in items}

    def process(item):
        key = hashlib.sha256(f'{VERSION}:{engine_digest}:{pdf_version}:{item.sha256}:{item.extension}'.encode()).hexdigest()
        target = cache / f'{key}.json'
        if target.exists():
            try:
                result = json.loads(target.read_text(encoding='utf-8'))
                if result.get('source_sha256') == item.sha256 and not result.get('error'):
                    return item.sha256, item.extension, key, result, True
            except (ValueError, OSError):
                pass
        try:
            # Never extract archive paths: ZIP traversal names cannot escape the private temp dir.
            with zipfile.ZipFile(archive) as zf, tempfile.TemporaryDirectory() as td:
                path = Path(td) / ('input' + item.extension)
                with zf.open(item.path) as src, path.open('wb') as dst:
                    import shutil
                    shutil.copyfileobj(src, dst)
                result = extract(path)
        except Exception as exc:
            result = {'error': type(exc).__name__, 'required_work': ['extraction_failed']}
        result['source_sha256'] = item.sha256
        write_json(target, result)
        return item.sha256, item.extension, key, result, False

    with ThreadPoolExecutor(max_workers=workers) as pool:
        processed = list(pool.map(process, unique.values()))
    lookup = {(digest, ext): (key, result) for digest, ext, key, result, _ in processed}
    manifest = []
    for i in items:
        key, result = lookup[i.sha256, i.extension]
        source_id = 'SRC-' + hashlib.sha256((i.path + ':' + i.sha256).encode()).hexdigest()[:24]
        manifest.append({**asdict(i), 'source_id': source_id, 'cache_key': key,
                         'required_work': result['required_work'], 'coverage_status': 'unsegmented'})
    summary = summarize(items)
    summary.update({'unique_payloads': len(unique), 'cache_hits': sum(r[4] for r in processed),
                    'extraction_errors': sum('error' in r[3] for r in processed),
                    'pdf_pages': sum(len(r[3].get('pages', [])) for r in processed),
                    'ocr_pages': sum(p['needs_ocr'] for r in processed for p in r[3].get('pages', [])),
                    'required_work': dict(Counter(w for r in processed for w in r[3]['required_work'])),
                    'publication_ready': False,
                    'note': 'File inventory and text extraction are NOT question coverage.'})
    write_json(out / 'sources.private.json', manifest)
    write_json(out / 'expected-source-ids.private.json', [i['source_id'] for i in manifest])
    write_json(out / 'pairs.private.json', [asdict(p) for p in exact_pair_candidates(manifest)])
    write_json(out / 'summary.json', summary)
    return summary
