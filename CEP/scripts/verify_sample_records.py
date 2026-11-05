#!/usr/bin/env python3
"""Validate synthetic data and the schema-only fixture; no empirical model output."""
from pathlib import Path
import json
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
records=[json.loads(s) for s in (ROOT/'data/examples/sample_inputs.jsonl').read_text().splitlines() if s.strip()]
assert len(records)==15
assert all(r.get('synthetic') is True and isinstance(r.get('title'),str) and isinstance(r.get('description'),str) for r in records)
fixture=json.loads((ROOT/'data/examples/synthetic_schema_fixture.json').read_text())
schema=json.loads((ROOT/'schemas/cep_final_record_schema_v1.json').read_text())
Draft202012Validator(schema).validate(fixture)
assert fixture['run_metadata']['model_id']=='not-a-model-output'
assert fixture['te']['te_id'] in {r['te_id'] for r in records}
print('PASS: 15 synthetic examples and one schema-only fixture; no original TE content')
