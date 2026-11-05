#!/usr/bin/env python3
"""Recalculate published CEP metrics from shareable derived adjudication tables.

The 105 original TE descriptions and annotation workbooks are NOT distributed.
These derived tables preserve the numerical judgements needed to reproduce
reported aggregates, but are not a replacement for auditing original annotations.
"""
from __future__ import annotations
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / 'data' / 'evaluation'
REFERENCE = ROOT / 'results' / 'human' / 'reference_metrics.json'

def rows(name):
    with (TABLES / name).open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def wsum(rs, key):
    return sum(float(r[key])*float(r['sampling_weight']) for r in rs)

def prf(tp, fp, fn):
    p = tp/(tp+fp) if tp+fp else 0.0
    r = tp/(tp+fn) if tp+fn else 0.0
    return p, r, (2*p*r/(p+r) if p+r else 0.0)

def counts_prf(rs, prefix):
    tp = wsum(rs,prefix+'tp'); fp = wsum(rs,prefix+'fp'); fn = wsum(rs,prefix+'fn')
    return prf(tp,fp,fn)

def qwk(rs):
    levels=[1,2,3]; idx={x:i for i,x in enumerate(levels)}
    observed=[[0.0]*3 for _ in range(3)]; true=[0.0]*3;pred=[0.0]*3;total=0.0
    for r in rs:
        i=idx[int(r['human_salience'])];j=idx[int(r['model_salience'])]; w=float(r['sampling_weight'])
        observed[i][j]+=w;true[i]+=w;pred[j]+=w;total+=w
    num=sum(((i-j)**2/4.0)*observed[i][j] for i in range(3) for j in range(3))
    den=sum(((i-j)**2/4.0)*true[i]*pred[j]/total for i in range(3) for j in range(3))
    return 1-num/den if den else float('nan')

def main():
    out={}
    ab=rows('abstention_rows.csv')
    assert len(ab)==105
    out['abstention_accuracy']=sum(float(r['sampling_weight']) for r in ab if r['human_abstain']==r['model_abstain'])/sum(float(r['sampling_weight']) for r in ab)
    out['te_facet_precision'],out['te_facet_recall'],out['te_facet_f1']=counts_prf(rows('te_facet_rows.csv'),'')
    out['component_precision'],out['component_recall'],out['component_f1']=counts_prf(rows('component_extraction_per_te.csv'),'component_')
    s1=rows('component_s1_facet_primary.csv')
    out['component_s1_precision'],out['component_s1_recall'],out['component_s1_f1']=prf(*(sum(float(r[k]) for r in s1) for k in ('tp','fp','fn')))
    conf=rows('assertion_state_confusion_weighted.csv')
    states=['S1','S2','S4','S5','S6']
    d={(r['human'],r['model']):float(r['count_or_weight']) for r in conf}
    total=sum(d.values())
    out['assertion_state_accuracy']=sum(d.get((x,x),0.0) for x in states)/total
    all_f1=[];observed_f1=[]
    for s in states:
        tp=d.get((s,s),0.0)
        fp=sum(d.get((o,s),0.0) for o in states if o!=s)
        fn=sum(d.get((s,o),0.0) for o in states if o!=s)
        f1=prf(tp,fp,fn)[2]
        all_f1.append(f1)
        if tp+fp+fn>0:observed_f1.append(f1)
    out['assertion_state_macro_f1_observed']=sum(observed_f1)/len(observed_f1)
    out['assertion_state_macro_f1_all5']=sum(all_f1)/len(all_f1)
    sal=rows('salience_pairs.csv')
    out['salience_qwk']=qwk(sal)
    out['salience_mae']=sum(abs(int(r['human_salience'])-int(r['model_salience']))*float(r['sampling_weight']) for r in sal)/sum(float(r['sampling_weight']) for r in sal)
    cov=rows('coverage_pairs.csv')
    out['coverage_mae']=sum(abs(float(r['human_coverage'])-float(r['model_coverage']))*float(r['sampling_weight']) for r in cov)/sum(float(r['sampling_weight']) for r in cov)
    ass=rows('assertion_matching.csv')
    out['grounding_supported_rate']=sum(float(r['sampling_weight']) for r in ass if r['semantic_grounding']=='SUPPORTED')/sum(float(r['sampling_weight']) for r in ass)
    expected=json.loads(REFERENCE.read_text())['primary_weighted_metrics']
    for metric,want in expected.items():
        got=out[metric]
        if not math.isclose(got,float(want),abs_tol=1e-10,rel_tol=0):
            raise SystemExit(f'FAILED {metric}: got {got}, expected {want}')
    print('PASS: all 17 published primary weighted CEP metrics reproduced from de-identified derived tables')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
