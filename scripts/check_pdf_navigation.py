#!/usr/bin/env python3
"""Check actual PDF outline and clickable TOC against each frozen book manifest."""
import json
from pathlib import Path
import sys
import fitz


def compact(text):
    return ''.join(text.split())


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
        if first_body<1 or '目录' not in compact(doc[0].get_text()):
            raise ValueError(f'{folder.name}: missing printed contents')
        linked_pages={link.get('page') for page in list(doc)[:first_body] for link in page.get_links()
                      if link.get('kind')==fitz.LINK_GOTO}
        for _,title,page_number in entries:
            if not 1<=page_number<=len(doc) or compact(title) not in compact(doc[page_number-1].get_text()):
                raise ValueError(f'{folder.name}: bookmark points to wrong page: {title}')
            if page_number-1 not in linked_pages:
                raise ValueError(f'{folder.name}: missing clickable contents destination: {title}')
    print(f'{folder.name}: outline, headings and contents links verified')


if __name__=='__main__':
    for manifest in sorted(Path(sys.argv[1]).glob('*/book.json')):
        check(manifest.parent)
