#!/usr/bin/env python3
"""Run existing review stages on one DOCX pair; never grants publication approval."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import jsonschema
from engine.document.docx_reader import read_docx_document
from engine.parse.candidate_bank import extract_candidate_bank
from engine.parse.evidence_bank import extract_evidence_bank
from engine.pipeline.reconcile import reconcile_candidate_and_evidence
from engine.pipeline.verification import aggregate_pairing_reviews
from engine.pipeline.scoring import build_score_evidence
from engine.pipeline.classification import build_safe_classification_proposals
from engine.pipeline.teacher_enrichment import build_teacher_enrichment
from engine.pipeline.editorial_queue import build_editorial_queue
from engine.pipeline.intake import write_json


def review_pair(student,teacher,subject,out):
    start=time.perf_counter()
    for path in (student,teacher):
        if path.suffix.lower()!='.docx':
            raise ValueError('Use normalized DOCX files; convert legacy DOC via intake first')
    sid='SRC-'+hashlib.sha256(student.read_bytes()).hexdigest()[:24]
    tid='SRC-'+hashlib.sha256(teacher.read_bytes()).hexdigest()[:24]
    if sid==tid:
        raise ValueError('Student and teacher input must be distinct sources')
    candidate=extract_candidate_bank(read_docx_document(student).to_dict(),subject=subject,source_id=sid)
    evidence=extract_evidence_bank(read_docx_document(teacher).to_dict(),subject=subject,source_id=tid)
    pairing=reconcile_candidate_and_evidence(candidate,evidence,source_pair_confidence='user_selected_pair')
    aggregate=aggregate_pairing_reviews([pairing])
    score=build_score_evidence(candidate)
    classification=build_safe_classification_proposals(candidate)
    enrichment=build_teacher_enrichment(pairing,evidence)
    queue=build_editorial_queue(candidate,aggregate,score,classification,teacher_enrichment=enrichment)
    outputs={'candidate-bank':candidate,'evidence-bank':evidence,'pairing-review':pairing,
             'verification-aggregate':aggregate,'score-evidence':score,
             'classification-manifest':classification,'teacher-enrichment-batch':enrichment,
             'editorial-queue':queue}
    # Validate everything before replacing any review outputs.
    for name,value in outputs.items():
        schema=json.loads((ROOT/f'schema/{name}.schema.json').read_text())
        jsonschema.Draft202012Validator(schema).validate(value)
    for name,value in outputs.items():
        write_json(out/f'{name}.json',value)
    summary={'candidate_units':len(candidate['candidates']),
             'pairing':pairing['summary'],'teacher_enrichment':enrichment['summary'],
             'editorial':queue['summary'],'seconds':round(time.perf_counter()-start,3),
             'status':'review_only_not_verified_or_publishable'}
    write_json(out/'summary.json',summary)
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('student',type=Path);ap.add_argument('teacher',type=Path)
    ap.add_argument('--subject',required=True,choices=['english','politics'])
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    print(json.dumps(review_pair(args.student,args.teacher,args.subject,args.out),ensure_ascii=False,indent=2))
