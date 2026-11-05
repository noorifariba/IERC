# Less Data, More Context

**Reproducibility materials for:** *Less Data, More Context: A Multimodal Recommender Framework for Sparse Touristic Experiences with LLM-Assisted Cultural Enrichment* (ACM TORS, TORS-2026-0158).

This repository contains the code, sample inputs and evaluation artifacts for touristic-experience recommendation and Cultural Experience Profile (CEP) enrichment. The instructions below cover how to inspect the supplied data, run the available examples and reproduce the released evaluation calculations.

## Repository layout

```text
.
├── README.md
├── IERC-Recommender/
│   ├── IERCReadMe.txt
│   └── IERC-SampleCode-Data/
│       ├── AirBnbCode/
│       ├── BookingDotCom/
│       ├── TripAdvisor/
│       ├── utilities/
│       └── data/
└── CEP-Reproducibility/
    ├── README.md
    ├── requirements.txt
    ├── src/
    ├── scripts/
    ├── configs/
    ├── prompts/
    ├── schemas/
    ├── data/
    ├── results/
    └── tests/
```

## Quick start: reproduce the CEP evaluation results

These commands require **Python 3.10 or later** and use only the Python standard library. Run them from the `CEP-Reproducibility` directory:

```bash
cd CEP-Reproducibility
python scripts/reproduce_scaleup_summary.py
python scripts/reproduce_semantic_evaluation.py
```

The first command checks technical outcomes and descriptive statistics from the 1,441-experience run. The second recomputes the primary weighted metrics for the 105-experience semantic evaluation. Both use included derived results; they do not call an LLM or download the original dataset.

To validate the sample inputs and CEP output schema, or run the included tests:

```bash
python -m pip install -r requirements.txt
python scripts/run_samples.py --check-only
python scripts/verify_sample_records.py
python -m pytest -q -p no:cacheprovider tests
```

For model-backed CEP generation on sample inputs, follow [`CEP-Reproducibility/README.md`](CEP-Reproducibility/README.md). This requires a compatible local Gemma 3 / llama.cpp setup and is optional for reproducing the aggregate evaluation calculations.

## Running the recommendation notebooks

The recommender implementation is supplied as Jupyter notebooks with shared utilities and representative platform data. The notebooks are grouped by input platform:

- `IERC-Recommender/IERC-SampleCode-Data/AirBnbCode/IERN_Models/`
- `IERC-Recommender/IERC-SampleCode-Data/BookingDotCom/IERN_Models/`
- `IERC-Recommender/IERC-SampleCode-Data/TripAdvisor/IERC_Models/`

Use a Python environment with Jupyter and the libraries imported by the notebooks and `utilities/` (including PyTorch, PyTorch Geometric, Transformers, Top2Vec, NLTK, NumPy, pandas and scikit-learn). For example, to inspect the Airbnb notebooks:

```bash
cd IERC-Recommender/IERC-SampleCode-Data/AirBnbCode/IERN_Models
jupyter notebook
```

Open the relevant `.ipynb` file in Jupyter. Some notebooks reference additional precomputed files under `tempdata/` and rely on datasets or pretrained resources that are **not included** in the limited public sample. Full recommender experiments may therefore require the original research environment and permitted access to restricted inputs. The included sample is intended to illustrate the data layout and implementation, not to guarantee a full retraining run.

## Inputs and available results

The source data were collected from Airbnb, TripAdvisor and Booking.com for seven destinations. The complete scraped datasets are not redistributed. The supplied recommender sample demonstrates portions of the original data structure; see [`IERCReadMe.txt`](IERC-Recommender/IERCReadMe.txt) for collection and preprocessing details.

CEP generation uses **experience title and description** as cultural-inference inputs. `CEP-Reproducibility/data/examples/sample_inputs.jsonl` contains 15 **synthetic** examples (five per platform) for demonstrating the input interface; these are not the empirical items used to report study results. The CEP evaluation files contain de-identified numerical judgments and derived technical outcomes, not the full source descriptions.

The published CEP summary statistics can be recomputed from these derived artifacts. Replaying every original model generation or independently rechecking the evidence against original listings requires restricted data and the original model runtime; the supplied evaluation files do not replace that source-level audit.

## Further instructions

See [`CEP-Reproducibility/README.md`](CEP-Reproducibility/README.md) for the CEP runtime configuration, input format, example generation command and evaluation data descriptions. See [`IERC-Recommender/IERCReadMe.txt`](IERC-Recommender/IERCReadMe.txt) for the touristic-experience data preparation notes.
