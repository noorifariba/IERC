# ACM TORS Reproducibility Materials — TORS-2026-0158

**Paper:** *Less Data, More Context: A Multimodal Recommender Framework for Sparse Touristic Experiences with LLM-Assisted Cultural Enrichment*

This repository groups the two independently developed components of the submitted manuscript. Their original experimental results are reported separately; the CEP layer does **not** modify or retrain the original recommender.

## Repository layout

- `IERC-Recommender/` — the original IERC/IERN recommendation code and sample data supplied by Maryam Kamal Shahzad. **Both the code/sample files and the original `IERCReadMe.txt` have been retained unchanged.** Refer to `IERC-Recommender/IERCReadMe.txt` for her collection, processing, and code notes.
- `CEP-Reproducibility/` — the cultural-enrichment implementation, synthetic title/description examples, compact sanitized evaluation data, and reproducibility scripts. See `CEP-Reproducibility/README.md` for instructions and limitations.

## Quick verification of CEP results

```bash
cd CEP-Reproducibility
python scripts/reproduce_scaleup_summary.py
python scripts/reproduce_semantic_evaluation.py
```

For sample input checking or a model-backed demonstration, follow the CEP README. The original recommender and CEP code have **separate** requirements and execution procedures.

## Data and privacy

The complete datasets scraped from Airbnb, TripAdvisor, and Booking.com cannot be redistributed. Original material is represented by Maryam's limited sample package; the CEP folder instead includes five **synthetic illustrative title/description records per platform** and de-identified derived numeric results. The CEP synthetic records **are not the empirical inputs** to the paper's 1,441-item study. Neither the full listing descriptions nor the full 105-item human-reference workbooks are included.

All source-code artifacts, sample data, and licenses should be reviewed and approved by the coauthors **before public release**. Maryam's folder has deliberately not been edited as part of this integration; any remaining disclosure concerns in that original package must be resolved by its authors before GitHub publication.

## Reproducibility scope

The published CEP aggregate results can be recomputed from the supplied derived tables and technical outcomes. Re-running historical model generations needs the original restricted input records and compatible Gemma/llama.cpp environment. The complete IERC/IERN study has separate data and runtime requirements described in its own README. Contact the authors for availability of non-public materials, where permitted by applicable data-access rules.
