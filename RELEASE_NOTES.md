# Initial core-analysis release

Prepared: 2026-09-27.

Included: portable analysis code, entirely synthetic example traces, hand-derived expected outputs and paper-level aggregate CSVs. No external project code or original dataset records are bundled. The executable core depends only on Python standard-library modules.

The package reproduces observation transformations and disclosure calculations, not encrypted-server execution or workload generation. The private-archive comparison in VALIDATION.md checks agreement with existing analysis; it is not independent third-party replication. The README separates synthetic demonstration, aggregate table rendering and optional private-archive processing.

No software license has been selected or granted. No LICENSE file is included pending the rights holder's choice. Private traces and imported outputs must not be committed. An anonymous review mirror can be prepared separately from this repository.

## Historical knowledge and object-service experiments

Added fixed-initial-knowledge analysis, actual encrypted HTTP object replay, object rotation and padding, server-only attacks, aggregate results, and the three latest paper panels. Included the required index/ranking components and a synthetic end-to-end check. Archived workload replay requires separately supplied source data and traces; no per-user logs are distributed.
