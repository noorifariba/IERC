#!/usr/bin/env python3
"""Load synthetic TE examples; optionally run the original CEP pipeline with local Gemma.

--check-only is model-free. --run requires a running compatible llama.cpp
server and model weights, which are not included in this repository.
This demonstrates code mechanics, not replication of reported study outputs.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.base import build_canonical_te

def load_examples():
    f=ROOT/'data/examples/sample_inputs.jsonl'
    records=[json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    assert len(records)==15 and all(r.get('synthetic') is True for r in records)
    assert {r['platform'] for r in records}=={'Airbnb','TripAdvisor','Booking.com'}
    assert len({r['te_id'] for r in records})==len(records)
    return records

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--check-only',action='store_true',help='Validate synthetic title/description sample inputs without model inference')
    ap.add_argument('--run',action='store_true',help='Run the original CEP runner against a local llama.cpp model server')
    ap.add_argument('--limit',type=int,default=1)
    ap.add_argument('--out-dir',type=Path,default=ROOT/'demo_output')
    args=ap.parse_args()
    if args.check_only == args.run:ap.error('choose exactly one of --check-only or --run')
    rows=load_examples()
    if args.check_only:
        for r in rows:
            assert isinstance(r['title'],str) and r['title'].strip()
            assert isinstance(r['description'],str) and r['description'].strip()
            c=build_canonical_te(title=r['title'],description=r['description'],provenance={'te_id':r['te_id']})
            assert set(c.generation_input)=={'title','description'}
        print(f'PASS: {len(rows)} synthetic records, five per platform; Title + Description only for CEP generation')
        return
    from src.runner.cep_runner import CEPRunner
    from src.providers.llama_cpp_provider import LlamaCppProvider
    from src.common.io import dump_json
    control=ROOT/'configs/experiment_regression_td24_r1_v02_prompt_v1_1.yaml'
    cfg=yaml.safe_load(control.read_text())
    canonical=[]
    for r in rows[:args.limit]:
        provenance={
          'te_id':r['te_id'],'platform':r['platform'],'dataset_destination':r['destination'],
          'url':None,'itinerary_status':'no_verified_structured_itinerary',
          'input_status':'complete','adapter_version':'adapters_v0.2'
        }
        obj=build_canonical_te(title=r['title'],description=r['description'],provenance=provenance)
        canonical.append({'te_id':r['te_id'], **obj.as_dict()})
    out=args.out_dir.resolve()
    if out.exists():raise SystemExit(f'Output directory exists; choose a new --out-dir: {out}')
    out.mkdir(parents=True)
    manifest=out/'canonical_examples.json'
    dump_json(manifest,{'experiment_id':cfg['experiment_id'],'records':canonical})
    provider=LlamaCppProvider.from_config_path(ROOT/'configs/local_gemma3_runtime_portable.yaml')
    runner=CEPRunner(provider,canonical_path=manifest,
         prompt_path=ROOT/'prompts/prompt_cep_v1_1.md',
         prompt_meta_path=ROOT/'prompts/prompt_cep_v1_1.meta.json',
         raw_schema_path=ROOT/'schemas/cep_schema_v1.json',
         final_schema_path=ROOT/'schemas/cep_final_record_schema_v1.json',
         config_path=control)
    for i,r in enumerate(rows[:args.limit],1):
        result=runner.run(te_id=r['te_id'],run_id=f'demo-{i}',run_dir=out/f'run-{i:02d}')
        print(r['te_id'],result.get('run_status'))
    print('Demo outputs:',out)

if __name__=='__main__':main()
