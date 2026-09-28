# Service observations and historical knowledge

Run from the repository root with Python 3.9 or later:

```sh
python3 -m pip install -r experiments/requirements.txt
python3 experiments/verify_synthetic.py
python3 scripts/plot_latest.py
```

The synthetic check executes encrypted lookup, client-side BM25, and real HTTP object reads in a separate localhost process. It checks fixed initial knowledge, fresh-handle rotation, unique-length recovery, and 1-KiB padding using invented records. It does not reproduce the empirical cohort. Generated files are in `output/`; no model inference is required.

## Archived workload replay

The full replay requires the original chronological archive and a gzip CSV with a `user_id` column selecting the strict cohort. They are not distributed here. Set `ARCHIVE` and `ELIGIBLE` to their local paths.

```sh
python3 experiments/analyze_fixed_knowledge_persistence.py --archive "$ARCHIVE" --eligible-csv "$ELIGIBLE" --output-dir output/fixed
python3 experiments/run_memorycd_object_pilot.py --archive "$ARCHIVE" --eligible-csv "$ELIGIBLE" --users 254 --output-dir output/stable
python3 experiments/run_memorycd_object_rotation.py --archive "$ARCHIVE" --eligible-csv "$ELIGIBLE" --users 30 --rotate --output-dir output/rotated
python3 experiments/run_memorycd_object_rotation.py --archive "$ARCHIVE" --eligible-csv "$ELIGIBLE" --users 30 --rotate --padding-block 1024 --output-dir output/padded
python3 experiments/summarize_object_server_study.py --stable output/stable --rotation output/rotated --padded output/padded --client-summary output/fixed/summary.csv --output-dir output/summary
```

The archive contains `memorycd_users_interactions.parquet` and `task_runs.jsonl` under `r011_memorycd_all_users`, `r012_qwen_memorycd_all_users`, and `r013_deepseek_memorycd_all_users`. Parquet rows have `user_id` and `interactions` keyed by the four domain names in `memorycd_data.py`; interactions are JSON strings with timestamps, titles, and review text. Task rows contain `user_id`, `task_position`, `task_role`, `timestamp`, `queries`, `events` (including `access_pattern`), and optional `policy_seed`. The synthetic check constructs an executable example of this schema.

The service replay uses archived MiniLM actions. The observer sees query-token history, task boundaries, object GET keys, and object lengths; initial document meanings are supplied separately. Rotation preserves query-token history while changing object handles, encryption keys, and nonces. The length attack knows the padding rule. Client truth is evaluated separately from attack inputs.

## Published aggregates

- `data/fixed_knowledge_summary.csv`: three policies, initial budgets 1/5/10, five future tasks, uniform and historical-frequency selections.
- `data/server_uniform_curve.csv`: coverage reconstructed from actual MiniLM service logs.
- `data/object_server_summary.json`: 254-user service replay and paired 30-user rotation/padding results.

The empirical rotation recovers 185/300 initial mappings and retains 16/26 extra record–task identifications through unique lengths. Padding suppresses that tested recovery with approximately 60% more object bytes. The five-task horizon and tested attack define the scope; these are not general unlinkability or production-service measurements.
