#!/usr/bin/env python3
from __future__ import annotations
import json, statistics
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BATCH=json.loads((ROOT/'results/scaleup/batch_summary.json').read_text())
EXPECTED=json.loads((ROOT/'results/scaleup/analysis_summary.json').read_text())
RECORDS=[json.loads(x) for x in (ROOT/'results/scaleup/accepted_analysis_records.jsonl').read_text().splitlines() if x.strip()]

def etype(e): return str(e).split(':',1)[0]

def quantile(vals,p):
    # Same interpolation convention as Python/statistical descriptive output is not needed for primary checks.
    s=sorted(vals); n=len(s)
    if not n: return None
    i=(n-1)*p; lo=int(i); hi=min(lo+1,n-1); f=i-lo
    return s[lo]*(1-f)+s[hi]*f

def main():
    per=BATCH['per_te_results']
    accepted=[r for r in per if r['run_status']=='accepted']
    failed=[r for r in per if r['run_status']=='failed']
    failure_stage=Counter(r.get('failure_stage') for r in failed)
    occ=Counter(); unique=Counter()
    for r in failed:
        ts=[etype(e) for e in r.get('errors',[])]
        occ.update(ts); unique.update(set(ts))
    assert len(RECORDS)==len(accepted)==643
    abst=[r for r in RECORDS if r['cultural_abstention'] is True]
    non=[r for r in RECORDS if r['cultural_abstention'] is False]
    facets=Counter(); sal=Counter(); cover=[]; eligible_total=0
    for rec in non:
        eligible_total += int(rec['eligible_component_count'])
        for fs in rec['facet_summaries']:
            if fs.get('supported_membership') is True:
                facets[fs['facet']]+=1
                sal[str(fs['salience_ordinal'])]+=1
                cover.append(float(fs['component_coverage']))
    got={
      'total_te':len(per),'accepted_total':len(accepted),'technical_failure':len(failed),
      'accepted_cultural_abstention':len(abst),'accepted_nonabstaining':len(non),
      'failure_stage_counts':dict(failure_stage),
      'failure_type_unique_te_counts_nonexclusive':dict(unique),
      'failure_type_occurrence_counts_nonexclusive':dict(occ),
      'facet_te_counts':dict(facets),'salience_overall_counts':dict(sal),
      'coverage_n_pairs':len(cover),'coverage_mean':statistics.mean(cover),
      'coverage_median':statistics.median(cover),'coverage_min':min(cover),'coverage_max':max(cover),
      'cep_eligible_components_total':eligible_total,
    }
    exp=EXPECTED
    checks={
      'total_te':exp['overall']['total_te'],'accepted_total':exp['overall']['accepted_total'],
      'technical_failure':exp['overall']['technical_failure'],'accepted_cultural_abstention':exp['overall']['accepted_cultural_abstention'],
      'accepted_nonabstaining':exp['overall']['accepted_nonabstaining'],
      'failure_stage_counts':exp['technical_failures']['failure_stage_counts'],
      'failure_type_unique_te_counts_nonexclusive':exp['technical_failures']['failure_type_unique_te_counts_nonexclusive'],
      'failure_type_occurrence_counts_nonexclusive':exp['technical_failures']['failure_type_occurrence_counts_nonexclusive'],
      'facet_te_counts':exp['semantic_profiles']['facet_te_counts'],'salience_overall_counts':exp['semantic_profiles']['salience_overall_counts'],
      'coverage_n_pairs':exp['semantic_profiles']['component_coverage_overall']['n_pairs'],
      'coverage_mean':exp['semantic_profiles']['component_coverage_overall']['mean'],
      'coverage_median':exp['semantic_profiles']['component_coverage_overall']['median'],
      'coverage_min':exp['semantic_profiles']['component_coverage_overall']['min'],
      'coverage_max':exp['semantic_profiles']['component_coverage_overall']['max'],
      'cep_eligible_components_total':exp['semantic_profiles']['cep_eligible_components_total'],
    }
    for k,v in checks.items():
        gv=got[k]
        if isinstance(v,float):
            ok=abs(gv-v)<1e-12
        else: ok=gv==v
        if not ok: raise SystemExit(f'MISMATCH {k}: {gv!r} != {v!r}')
    print('PASS: frozen scale-up outcomes and descriptive CEP distributions reproduced')
    print(json.dumps(got,indent=2,sort_keys=True))
if __name__=='__main__':main()
