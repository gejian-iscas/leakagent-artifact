# LeakAgent: Cross-Query Document Linkage in Encrypted Agent Memory

Analysis code and aggregate results accompanying the paper. The code measures cross-query document linkage, additional record disclosure, and disclosure under partial knowledge.

## Requirements

Python 3.9 or later. The core analysis has no additional dependencies.
Service experiments and figure generation use [optional dependencies](experiments/requirements.txt).

## Quick start

```sh
python3 verify.py
python3 analyze.py
python3 scripts/paper_table.py
```

These commands validate the analysis, run the synthetic example, and generate the paper’s summary table. Outputs are saved in `output/`.

## Contents

- `analyze.py`: document-linkage and disclosure analysis.
- `examples/`: synthetic traces and analysis configurations.
- `data/`: aggregate experimental results.
- `scripts/`: archive import, table generation, and latest experiment figures.
- `experiments/`: fixed-knowledge analysis, encrypted object-service replay, rotation, and padding. See [experiment instructions](experiments/README.md).

See [VALIDATION.md](VALIDATION.md) for validation details. Original per-user traces are not included.
