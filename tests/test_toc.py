import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from engine.pipeline.books import plan_books
from engine.render.latex import render_book
from engine.render.compile import compile_xelatex
from engine.quality.evidence import validate_release_evidence

ROOT=Path(__file__).resolve().parents[1]

class NavigationTests(unittest.TestCase):
    def test_toc_shared_chapters_independent_editions(self):
        data=json.loads((ROOT/'examples/eight-books/dataset.json').read_text())
        books,bank=plan_books(data['questions'], data['ledger'], data['curriculum'])
        template=(ROOT/'templates/latex/workbook.tex').read_text()
        for a,b in zip(books[::2],books[1::2]):
            self.assertEqual(a['chapters'],b['chapters'])
            self.assertTrue(a['table_of_contents'])
        rendered=render_book(template=template,book=books[0],questions=bank)
        self.assertIn('\\begin{document}\n\\workbookcontents', rendered)
        sample=copy.deepcopy(books[0]);sample.pop('table_of_contents')
        legacy=render_book(template=template,book=sample,questions=bank)
        self.assertNotIn('\\begin{document}\n\\workbookcontents',legacy)

    def test_compile_until_directory_stable_not_fixed_two_passes(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);values=iter(['1','2','2'])
            def run(*args,**kwargs):
                (folder/'main.toc').write_text(next(values));(folder/'main.log').write_text('')
                return SimpleNamespace(returncode=0)
            with patch('engine.render.compile.subprocess.run',side_effect=run):
                self.assertEqual(compile_xelatex(folder),3)

    def test_unstable_directory_blocks_completion(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);counter=iter(range(10))
            def run(*args,**kwargs):
                (folder/'main.toc').write_text(str(next(counter)));(folder/'main.log').write_text('')
                return SimpleNamespace(returncode=0)
            with patch('engine.render.compile.subprocess.run',side_effect=run):
                with self.assertRaisesRegex(ValueError,'did not converge'):
                    compile_xelatex(folder,max_passes=3)

    def test_indexed_evidence_accepts_generator_keeps_conflicts(self):
        evidence=iter([{'question_id':'A','value':'X','status':'verified'},
                       {'question_id':'B','value':'Y','status':'verified'},
                       {'question_id':'B','value':'Z','status':'verified'}])
        errors=validate_release_evidence(['A','B','C'],evidence)
        self.assertEqual(len(errors),2)
        self.assertTrue(any('B: conflicting' in e for e in errors))
        self.assertTrue(any('C: missing' in e for e in errors))
