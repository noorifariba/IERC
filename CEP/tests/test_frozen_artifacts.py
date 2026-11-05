import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_scaleup_counts():
    d=json.loads((ROOT/'results/scaleup/analysis_summary.json').read_text())
    assert d['overall']['total_te']==1441
    assert d['overall']['accepted_total']==643
    assert d['overall']['technical_failure']==798

def test_semantic_primary_result():
    d=json.loads((ROOT/'results/human/reference_metrics.json').read_text())
    assert abs(d['primary_weighted_metrics']['te_facet_f1']-0.6334577146347347)<1e-12
