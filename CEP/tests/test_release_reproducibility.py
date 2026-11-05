import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_synthetic_examples():
    records=[json.loads(x) for x in (ROOT/'data/examples/sample_inputs.jsonl').read_text().splitlines() if x.strip()]
    assert len(records)==15
    assert {r['platform'] for r in records}=={'Airbnb','TripAdvisor','Booking.com'}
def test_numeric_reproduction():
    for script in ('reproduce_scaleup_summary.py','reproduce_semantic_evaluation.py'):
        subprocess.run([sys.executable,str(ROOT/'scripts'/script)],check=True,capture_output=True,text=True)
