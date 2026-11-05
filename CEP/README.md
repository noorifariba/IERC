# Cultural Experience Profile (CEP)

This folder contains the **item-side CEP cultural enrichment** implementation and reproducibility material for the submitted ACM TORS manuscript *Less Data, More Context: A Multimodal Recommender Framework for Sparse Touristic Experiences with LLM-Assisted Cultural Enrichment*. It is separate from the original IERC/IERN recommender. No recommender training or evaluation code has been modified for this CEP release.

## Contents

- `src/` — original CEP source code: data adapters, title/description preparation, exact-text evidence verification, model provider, runner, and deterministic post-processing.
- `prompts/`, `schemas/`, `configs/` — the prompt actually used for the reported scale-up (`prompt_cep_v1_1`), CEP JSON schemas, cultural definitions, and model/runtime configuration.
- `scripts/run_samples.py` — model-free input check and optional real-model demonstration.
- `data/examples/` — **15 synthetic input records**, five per platform. They show the input structure but **are not scraped research records**. The single schema fixture is also synthetic and **not a model prediction**.
- `data/evaluation/` — de-identified, derived numerical human/model adjudication tables for the final 105-TE evaluation; **no original listing text or source URLs**.
- `results/` — sanitized per-item technical outcomes for the 1,441-TE scale-up, compact analysis records, and primary reference values.
- `scripts/reproduce_*.py` — independent calculations of the published technical and semantic aggregate results.
- `scripts/evaluate_human_105.py` — original full evaluation implementation, supplied for methodological transparency; its original input workbooks are **not distributed**.

## Quick start

From this `CEP` directory, with Python 3.10 or newer:

```bash
python scripts/reproduce_scaleup_summary.py
python scripts/reproduce_semantic_evaluation.py
```

Both use the Python standard library. They recompute the principal statistics and compare them with the recorded results. The semantic metrics come from **derived adjudication/matching tables**, not reannotation of the 105 original experiences.

Optional schema check and tests:

```bash
python -m pip install -r requirements.txt
python scripts/run_samples.py --check-only
python scripts/verify_sample_records.py
python -m pytest -q -p no:cacheprovider tests
```

## Generating a CEP on the synthetic examples

The reported CEP prototype used **Title + Description only** for cultural inference. User profiles, reviewer identities, interaction histories, reviews and images were **not** cultural-generation inputs in the reported run. The full original scraped dataset is not published.

The extraction implementation uses Gemma 3 12B IT (`google/gemma-3-12b-it-qat-q4_0-gguf`, artifact `gemma-3-12b-it-q4_0.gguf`) served locally through llama.cpp (recorded release `b10516`). The recorded settings include temperature `0.0`, seed `20260825`, and the prompt `prompt_cep_v1_1`. A compatible running local endpoint is required for the following optional demonstration:

```bash
python scripts/run_samples.py --run --limit 1 --out-dir demo_output
```

Model weights and the original TE input data are not included. The optional demo uses fictional records and must **not** be interpreted as reproduction of individual historical CEP outputs. The source runner retains its original integrity checks; you do not need to publish separate checksum reports.

## What can and cannot be reproduced from this release

**Included and runnable without source data:** 1,441-item technical acceptance/failure and CEP distribution summaries; 105-item sampling-weighted primary semantic metrics computed from derived numerical judgments; schema/input checks.

**Requires restricted data or external model setup:** a verbatim replay of the original 1,441 LLM generations, human evidence-span verification against original listing descriptions, or the full annotation-level evaluation from `scripts/evaluate_human_105.py`. The 105-TE semantic analysis is **conditional on technically accepted outputs**; the 1,441-item study is primarily a technical robustness analysis, not semantic ground truth over every item.

### Data availability and disclosure

The original tourism listings from Airbnb, TripAdvisor, and Booking.com are not redistributed. The 15 illustrative records are synthetic; the frozen results are sanitized derived measurements. Identifiers in scale-up outcomes are release-only aliases and do not encode original listing IDs. The published results are unchanged by this release preparation.
