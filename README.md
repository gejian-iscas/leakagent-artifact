# LeakAgent: core analysis artifact

This repository contains the core analysis artifact for **LeakAgent: Cross-Query Document Linkage in Encrypted Agent Memory**. It is a minimal executable analysis artifact, not the full encrypted-memory system or a reproduction of model-generated workloads. No software license has been selected; no license grant is implied by repository availability.

## Run the public example

Python 3.9 or later, standard library only. From this directory:

```sh
python3 verify.py
python3 analyze.py
python3 scripts/paper_table.py
```

`verify.py` checks a hand-derived synthetic example, preservation of the restricted B observation under query-identity projection, separation of the F observation, and the partial-knowledge probability against exhaustive subset enumeration for n=0 through 8. `analyze.py` writes `output/results.json`. `paper_table.py` writes `output/paper_table.md` and compares it to the expected published values. No network, GPU, model download or benchmark download is needed.

## What each result means

- **Synthetic example:** invented identifiers and events illustrate the algorithm. These are not anonymized participant data or experimental measurements, and do not establish a real server-side leakage path.
- **Published table:** the CSV contains the paper's real aggregate measurements. Rendering it checks transcription and computation from aggregates; it does not independently reproduce collection or reconstruct benchmark trajectories.
- **Optional private-archive analysis:** the portable analyzer can process normalized access traces from a legally acquired archive. It implements RQ1 pairwise-disjoint document links, RQ2 additional-record counts and uniform partial-knowledge expectations. It does not train a task predictor, construct domain maps, verify original timestamps, or execute object storage.

## Input schema and assumptions

A JSON array contains one stream per policy/user/seed. Each stream has `policy`, `user`, `seed`, `history` and `future`. Each task has `id`, `position` and `events`; each event has a `query` equality identity and an ordered list of `documents`. Identifiers are strings, comparable across a stream. Use query identities consistent with the intended evaluation: the paper's strict literal-query diagnostic case-folds raw query strings, including empty-result queries. Query plaintext is an evaluation input, not an adversarial feature.

The supplied cohort and temporal validity are upstream requirements. History is ordered by position, budgets select the most recent h histories, and future tasks never become history. A stream's document handles must refer to the same logical records across tasks. Server visibility is a separate implementation condition and cannot be inferred from this schema.

For each future task, `E = (N intersect A) minus R`, where A is historical accessed documents and N/R are new/repeated-query document unions. Partial knowledge draws k=round(rho*n) mappings uniformly without replacement from n historical anchors, using Python's rounding convention as in the source analysis. The probability is `1-C(n-a,k)/C(n,k)`. Summaries average future tasks and seeds within user before averaging users. The sample includes repeated/new-query overlap, all-new queries and zero extra disclosure.

## Use a legally obtained archive

The source benchmarks and original collection outputs are not bundled. Obtain them under their own terms. The importer accepts existing collection folders and an explicit eligible-user CSV containing a `user_id` column, plain or gzip. It does not infer or regenerate the strict cohort.

```sh
python3 scripts/import_archive.py --archive /path/to/archive --eligible-csv /path/to/history_eligibility.csv.gz --output private/traces.json
python3 analyze.py --input private/traces.json --config examples/full_config.json --output private/results.json
```

Expected source folders are `r011_memorycd_all_users`, `r012_qwen_memorycd_all_users` and `r013_deepseek_memorycd_all_users`, each containing `task_runs.jsonl`. The strict paper cohort has 254 users, ten histories and five future tasks, with one MiniLM and three seeds for each generative policy. The local full-cohort comparison is documented in VALIDATION.md.

The importer retains private identifiers and queries. Its output is excluded from Git by directory convention; do not treat this as anonymization. No original reviews, task descriptions, per-user traces, model weights or credentials are included in this package.

## Scope of reproduction

Included: observation projections, document-set partition, mapping expectation, cohort averaging, a private-archive importer and a reported aggregate table.

Not included: policy generation, encrypted server execution, domain-category extraction, learned mapping predictors, rotation execution, feedback collection, or an end-to-end server-only leakage demonstration. The source-linked history/rotation CSV is provided as aggregate evidence, not an implementation of these experiments. A successful demo must not be described as closing the paper's actual-server-observation gap.

## Release scope and license

See RELEASE_NOTES.md for the included material and reproduction boundaries. This repository contains code, synthetic fixtures and aggregate results only. Do not commit private imported traces or per-task outputs. No software license has been selected; obtain permission from the rights holder before reuse beyond permissions otherwise applicable.
