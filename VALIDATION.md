# Validation performed locally

The public quick-start passed under Python 3.9.12. It uses no third-party dependencies.

The portable importer/analyzer was also run on the existing private strict temporal cohort: 254 users, 1,778 user/policy/seed streams, 35,560 future-task/history-budget records and 177,800 mapping expectations. Sixty anchor-summary cells (five metrics × four history budgets × three policies), three h=10 pairwise-disjoint coverage values, and sixty partial-knowledge coverage summary values agreed with the original analysis within floating-point tolerance (1e-12 absolute tolerance with NumPy default relative tolerance). No new policy trajectories were generated.

This comparison uses the existing archive, so it checks agreement of the portable reimplementation with the original analysis rather than independent collection or independent third-party replication. Real trace inputs and per-task outputs remain outside this package. The optional importer requires the original archive and explicit eligibility CSV; the public synthetic demonstration can run without them.

The probability verification independently enumerates every k-element subset for n=0..8. Expected synthetic counts and the reported three-policy table are supplied as readable files. `expected/local_validation.json` records only aggregate validation counts, without participant identifiers.

## Service and persistence update

The packaged code passed the existing quick start, fixed-knowledge subset enumeration, Python compilation, and generation of the three new paper panels. A separate-process HTTP witness completed six encrypted lookups and seven object GETs with zero truth mismatches.

`experiments/verify_synthetic.py` additionally exercised all archive adapters and the aggregation path using invented records. Stable identity yielded five extra identifications; rotation ended direct matching while unique lengths recovered all ten initial mappings and five identifications; 1-KiB padding yielded zero recovered mappings and identifications. Returned sets matched the synthetic archive, and server/client uniform expectations agreed within 1e-12. These are packaging checks, not new empirical findings. The published empirical aggregates were copied from the completed study; the full real cohort was not rerun for this release.
