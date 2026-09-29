from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import jsonschema

from engine.render.latex import SUBJECT_NAMES, render_book
from engine.pipeline.intake import write_json
from engine.quality.evidence import validate_release_evidence
from engine.quality.dedup import exact_duplicate_clusters
from engine.quality.publication_content import validate_publication_content

ROOT = Path(__file__).resolve().parents[2]
SUBJECTS = tuple(SUBJECT_NAMES)


def has_content(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(has_content(v) for v in value)
    if isinstance(value, dict):
        return any(has_content(value.get(k)) for k in ('text', 'children', 'tex', 'asset'))
    return False


def _is_open_response(question):
    return (
        question.get("kind") == "composition"
        and question.get("answer_mode") == "open_response"
    )


def validate_inputs(questions, ledger, curriculum):
    """Ledger is private: every source occurrence must resolve before a full release."""
    errors = []
    ids = [q['id'] for q in questions]
    if len(ids) != len(set(ids)):
        errors.append('duplicate canonical question IDs')
    bank = {q['id']: q for q in questions}
    for cluster in exact_duplicate_clusters(questions):
        errors.append(
            "unresolved exact duplicate content: " + ", ".join(cluster.question_ids)
        )
    errors.extend(validate_publication_content(questions))
    schema = json.loads((ROOT / 'schema/question.schema.json').read_text())
    validator = jsonschema.Draft202012Validator(schema)
    for q in questions:
        try:
            validator.validate(q)
        except jsonschema.ValidationError as e:
            errors.append(f"{q['id']}: schema: {e.message}")
            continue
        if not has_content(q['stem']):
            errors.append(f"{q['id']}: empty stem")
        if q['kind'] in ('reading_group', 'cloze_group'):
            children = q.get('children') or []
            if not children:
                errors.append(f"{q['id']}: grouped question has no children")
            for index, child in enumerate(children, start=1):
                child_id = child.get('id') or f"child-{index}"
                if not has_content(child.get('stem')):
                    errors.append(f"{q['id']}/{child_id}: empty child stem")
                if not has_content(child.get('answer')) or not has_content(child.get('analysis')):
                    errors.append(f"{q['id']}/{child_id}: missing child answer or analysis")
        elif _is_open_response(q):
            if not has_content(q.get('analysis')):
                errors.append(f"{q['id']}: missing open-response analysis")
        elif not has_content(q.get('answer')) or not has_content(q.get('analysis')):
            errors.append(f"{q['id']}: missing answer or analysis")
    review_flags = ledger.get('content_review_flags', [])
    seen_review_flags = set()
    for flag in review_flags:
        flag_id = str(flag.get('id') or '')
        question_id = str(flag.get('question_id') or '')
        occurrence_id = str(flag.get('occurrence_id') or '')
        status = str(flag.get('status') or '')
        note = str(flag.get('note') or '').strip()
        if not flag_id or flag_id in seen_review_flags:
            errors.append('content review flags need unique non-empty ids')
            continue
        seen_review_flags.add(flag_id)
        if not question_id and not occurrence_id:
            errors.append(f"{flag_id}: content review flag missing target")
            continue
        if question_id and question_id not in bank:
            errors.append(f"{flag_id}: content review references unknown question")
        if status not in {'open', 'resolved'}:
            errors.append(f"{flag_id}: invalid content review status")
        elif status == 'open':
            target = question_id or occurrence_id
            errors.append(f"{target}: unresolved content review flag")
        elif not note:
            errors.append(f"{flag_id}: resolved content review flag needs note")

    if ledger.get('strict_answer_evidence'):
        fixed_answer_ids = [
            q['id']
            for q in questions
            if not _is_open_response(q)
        ]
        errors.extend(validate_release_evidence(
            fixed_answer_ids,
            ledger.get('answer_evidence', []),
            require_verified=True,
        ))
    sources = ledger.get('sources', [])
    source_ids = [s['id'] for s in sources]
    if not sources or len(source_ids) != len(set(source_ids)):
        errors.append('empty or duplicate source ledger')
    expected_sources = ledger.get('expected_source_ids', [])
    if not expected_sources or set(expected_sources) != set(source_ids):
        errors.append('source ledger does not match frozen intake source IDs')
    source_id_set = set(source_ids)
    occurrences = ledger.get('occurrences', [])
    source_counts = Counter(o['source_id'] for o in occurrences)
    occurrence_ids = [o['id'] for o in occurrences]
    if len(occurrence_ids) != len(set(occurrence_ids)):
        errors.append('duplicate occurrence IDs')
    covered = set()
    for source in sources:
        found_count = source_counts[source['id']]
        expected = source.get('expected_questions')
        if source.get('status') != 'verified' or type(expected) is not int or expected < 0:
            errors.append(f"{source['id']}: source segmentation not verified")
        elif found_count != expected:
            errors.append(f"{source['id']}: expected {expected}, accounted {found_count}")
        if expected == 0 and not source.get('non_question_reason'):
            errors.append(f"{source['id']}: zero-question source needs evidence")
    for o in occurrences:
        qid = o.get('question_id')
        if o['source_id'] not in source_id_set or qid not in bank or not o.get('locator'):
            errors.append(f"{o['id']}: unresolved provenance")
        else:
            covered.add(qid)
        if o.get('status') != 'verified':
            errors.append(f"{o['id']}: occurrence not verified")
    if covered != set(bank):
        errors.append('canonical bank and source coverage do not match')
    by_subject = defaultdict(list)
    for q in questions:
        by_subject[q['subject']].append(q)
    for subject in SUBJECTS:
        chapters = curriculum.get(subject, [])
        chapter_keys = [c['key'] for c in chapters]
        if not chapters or len(chapter_keys) != len(set(chapter_keys)):
            errors.append(f'{subject}: empty or duplicate chapters')
        valid = {(c['key'], s['key']) for c in chapters for s in c['sections']}
        for c in chapters:
            keys = [s['key'] for s in c['sections']]
            if len(keys) != len(set(keys)):
                errors.append(f'{subject}: duplicate section keys')
        subset = by_subject[subject]
        if not subset:
            errors.append(f'{subject}: no questions')
        for q in subset:
            if (q.get('chapter_key'), q.get('section_key')) not in valid:
                errors.append(f"{q['id']}: unresolved chapter assignment")
    if errors:
        raise ValueError('\n'.join(errors))
    return bank


def plan_books(questions, ledger, curriculum):
    bank = validate_inputs(questions, ledger, curriculum)
    books = []
    difficulty = {'basic': 0, 'standard': 1, 'advanced': 2}
    by_section = defaultdict(list)
    for q in questions:
        by_section[q['subject'], q['chapter_key'], q['section_key']].append(q)
    book_schema = json.loads((ROOT / 'schema/book.schema.json').read_text())
    book_validator = jsonschema.Draft202012Validator(book_schema)
    for subject in SUBJECTS:
        chapters = []
        for c in curriculum[subject]:
            sections = []
            for s in c['sections']:
                selected = sorted(by_section[subject, c['key'], s['key']],
                                  key=lambda q: (difficulty.get(q.get('difficulty'), 1), q['id']))
                if selected:
                    sections.append({**s, 'question_ids': [q['id'] for q in selected]})
            if sections:
                chapters.append({'key': c['key'], 'title': c['title'], 'sections': sections})
        for edition in ('student', 'teacher'):
            book = {'schema_version': 1, 'book_id': f'{subject}-{edition}',
                    'title': SUBJECT_NAMES[subject] + ('练习册' if edition == 'student' else '教师解析册'),
                    'subject': subject, 'edition': edition, 'paper': 'A4', 'quote_seed': 20260927,
                    'chapters': chapters, 'table_of_contents': True}
            book_validator.validate(book)
            books.append(book)
    # Exactly one placement in each edition; source duplicates retain all provenance links.
    for edition in ('student', 'teacher'):
        placed = Counter(qid for b in books if b['edition'] == edition for c in b['chapters']
                         for s in c['sections'] for qid in s['question_ids'])
        if placed != Counter({qid: 1 for qid in bank}):
            raise ValueError('book coverage mismatch')
    return books, bank


def prepare(questions, ledger, curriculum, out):
    books, bank = plan_books(questions, ledger, curriculum)
    template = (ROOT / 'templates/latex/workbook.tex').read_text(encoding='utf-8')
    # Include renderer + template + curriculum in edition identity, not just question JSON.
    render_source = (ROOT / 'engine/render/latex.py').read_bytes()
    for book in books:
        folder = out / book['book_id']
        write_json(folder / 'book.json', book)
        subset = {qid: bank[qid] for c in book['chapters'] for s in c['sections'] for qid in s['question_ids']}
        tex = render_book(template=template, book=book, questions=subset)
        (folder / 'main.tex').write_text(tex, encoding='utf-8')
        digest = hashlib.sha256(tex.encode() + render_source).hexdigest()
        (folder / 'build-id.txt').write_text(digest + '\n')
    write_json(out / 'coverage.json', {'books': len(books), 'unique_questions': len(bank),
                                      'source_occurrences': len(ledger['occurrences']),
                                      'verified_sources': len(ledger['sources']),
                                      'pdf_visual_approval': 'pending'})
    return books
