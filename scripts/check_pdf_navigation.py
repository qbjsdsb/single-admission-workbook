#!/usr/bin/env python3
"""Check actual PDF outline and clickable TOC against each frozen book manifest."""
import json
from pathlib import Path
import re
import sys
import fitz


def compact(text):
    return ''.join(text.split())


def internal_target_page(link):
    # Hyperref / XeTeX commonly emits named destinations. PyMuPDF resolves
    # these to a concrete page while keeping kind=LINK_NAMED rather than
    # LINK_GOTO, so both are valid internal navigation links.
    if link.get('kind') not in (fitz.LINK_GOTO, fitz.LINK_NAMED):
        return None
    page = link.get('page')
    return page if isinstance(page, int) and page >= 0 else None


STUDENT_FOOTER_QUOTES = (
    "今天会的，比昨天多一点",
    "认真做完每一道题，进步自然发生",
    "把错题变成下一次的得分点",
    "稳住节奏，一题一题拿分",
    "看懂一道题，就多一分底气",
    "不怕慢，只怕没有落实",
    "先做对，再做快",
    "每一次订正都算数",
)

TEACHER_FOOTER_QUOTES = (
    "讲清一道题，比讲完十道题更重要",
    "让学生知道为什么，比只知道答案更重要",
    "错因找准，训练才有效",
    "反馈及时，进步才可见",
    "课堂有重点，训练有闭环",
    "一题多问，胜过机械重复",
    "先看学情，再定讲法",
    "解析要能教，答案要可核",
)

SCORE_RE = re.compile(r"（\s*\d+(?:\.\d+)?\s*分\s*）")


def check(folder):
    book=json.loads((folder/'book.json').read_text())
    if not book.get('table_of_contents'):
        return
    expected=[]
    for i,chapter in enumerate(book['chapters'],1):
        expected.append((1,f'第{i}章'+chapter['title']))
        expected.extend((2,f'第{j}节'+section['title']) for j,section in enumerate(chapter['sections'],1))
    with fitz.open(folder/'main.pdf') as doc:
        outline=doc.get_toc()
        entries=[row for row in outline if compact(row[1])!='目录']
        actual=[(row[0],compact(row[1])) for row in entries]
        if actual!=expected:
            raise ValueError(f'{folder.name}: outline does not match book manifest: {actual}')
        first_body=entries[0][2]-1
        contents_text=''.join(page.get_text() for page in list(doc)[:first_body])
        compact_contents=compact(contents_text)
        if first_body<1 or '目录' not in compact_contents:
            raise ValueError(f'{folder.name}: missing printed contents')
        for _, expected_title in expected:
            if expected_title not in compact_contents:
                raise ValueError(
                    f'{folder.name}: printed contents missing named entry: {expected_title}'
                )

        body_pages=list(doc)[first_body:min(len(doc), first_body+3)]
        body_text=''.join(page.get_text() for page in body_pages)
        if not SCORE_RE.search(body_text):
            raise ValueError(f'{folder.name}: visible parenthesized question score missing')

        quotes = (
            STUDENT_FOOTER_QUOTES
            if book.get('edition') == 'student'
            else TEACHER_FOOTER_QUOTES
        )
        if not any(quote in body_text for quote in quotes):
            raise ValueError(f'{folder.name}: expected edition footer encouragement missing')

        linked_pages={
            target
            for page in list(doc)[:first_body]
            for link in page.get_links()
            if (target := internal_target_page(link)) is not None
        }
        for _,title,page_number in entries:
            if not 1<=page_number<=len(doc) or compact(title) not in compact(doc[page_number-1].get_text()):
                raise ValueError(f'{folder.name}: bookmark points to wrong page: {title}')
            if page_number-1 not in linked_pages:
                raise ValueError(f'{folder.name}: missing clickable contents destination: {title}')
    print(f'{folder.name}: outline, headings and contents links verified')


if __name__=='__main__':
    for manifest in sorted(Path(sys.argv[1]).glob('*/book.json')):
        check(manifest.parent)
