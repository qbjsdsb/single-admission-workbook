import unittest
from test_pairing_review import candidate, prompt, evidence
from test_editorial_queue import candidate as editorial_candidate, aggregate_row, score, classification, verified_bank
from engine.pipeline.reconcile import reconcile_candidate_and_evidence
from engine.pipeline.teacher_enrichment import build_teacher_enrichment
from engine.pipeline.editorial_queue import build_editorial_queue


class EvidenceBindingTests(unittest.TestCase):
    def pair(self, teacher_number=2):
        cb={'source_id':'STUDENT','subject':'english','candidates':[candidate('Q1',1,'Matching prompt.')]}
        eb={'source_id':'TEACHER','subject':'english',
            'question_records':[prompt('T2',teacher_number,'Matching prompt.')],
            'evidence':[evidence('E1',1,'A'),evidence('E2',2,'B'),
                        {**evidence('A1',1,'Wrong explanation'),'field':'analysis'},
                        {**evidence('A2',2,'Correct explanation'),'field':'analysis'}]}
        return cb,eb

    def test_shifted_number_binds_answer_and_analysis_to_matched_teacher(self):
        cb,eb=self.pair()
        review=reconcile_candidate_and_evidence(cb,eb)
        self.assertEqual(review['rows'][0]['normalized_answer'],'B')
        self.assertEqual(review['rows'][0]['evidence_ids'],['E2'])
        enriched=build_teacher_enrichment(review,eb)
        self.assertEqual(enriched['items'][0]['analysis'],'Correct explanation')

    def test_missing_matched_answer_does_not_fall_back_to_student_number(self):
        cb,eb=self.pair(3)
        review=reconcile_candidate_and_evidence(cb,eb)
        self.assertEqual(review['rows'][0]['answer_status'],'missing')
        self.assertEqual(build_teacher_enrichment(review,eb)['items'],[])

    def test_other_section_same_number_is_not_an_answer(self):
        cb,eb=self.pair(1)
        eb['evidence']=[evidence('X',1,'D',section='reading')]
        self.assertEqual(reconcile_candidate_and_evidence(cb,eb)['rows'][0]['answer_status'],'missing')

    def test_unsectioned_answer_sheet_still_supported(self):
        cb,eb=self.pair(1)
        eb['question_records']=[]
        eb['evidence']=[evidence('X',1,'D',section=None)]
        self.assertEqual(reconcile_candidate_and_evidence(cb,eb)['rows'][0]['normalized_answer'],'D')

    def test_notes_only_or_blank_analysis_are_not_ready(self):
        for item in ({'teacher_notes':'Hint'}, {'analysis':'  '}, {}):
            queue=build_editorial_queue(
                {'source_id':'SRC','subject':'english','candidates':[editorial_candidate('Q1',1)]},
                {'candidate_source_id':'SRC','subject':'english','rows':[aggregate_row('Q1')]},
                {'candidate_source_id':'SRC','subject':'english','sections':[score()]},
                {'candidate_source_id':'SRC','subject':'english','decisions':[classification('Q1')]},
                verified_candidate_bank=verified_bank(['Q1']),
                teacher_enrichment={'candidate_source_id':'SRC','items':[{'candidate_id':'Q1',**item}]})
            self.assertEqual(queue['entries'][0]['state'],'needs_review')
            self.assertEqual(queue['summary']['issue_counts']['teacher_analysis'],1)


class ReviewCommandTests(unittest.TestCase):
    def test_synthetic_docx_pair_runs_all_stages_without_auto_approval(self):
        import json
        import tempfile
        from pathlib import Path
        from scripts.build_e2e_demo import make_minimal_docx
        from scripts.review_docx_pair import review_pair, ROOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for role in ('student', 'teacher'):
                source = json.loads((ROOT / f'examples/e2e/politics_{role}_source.json').read_text())
                make_minimal_docx(source['paragraphs'], root / f'{role}.docx')
            summary = review_pair(root / 'student.docx', root / 'teacher.docx', 'politics', root / 'out')
            self.assertGreater(summary['candidate_units'], 0)
            self.assertEqual(summary['editorial']['ready_for_sample'], 0)
            self.assertEqual(len(list((root / 'out').glob('*.json'))), 9)

    def test_file_pairing_preserves_multiple_groups_and_empty_input(self):
        from engine.ingest.pairing import exact_pair_candidates
        self.assertEqual(exact_pair_candidates([]), [])
        inputs = [{'pair_key': key, 'role': role, 'subject': 'english', 'path': f'{key}/{role}'}
                  for key in ('first', 'second') for role in ('student', 'teacher')]
        self.assertEqual(len(exact_pair_candidates(inputs)), 2)
