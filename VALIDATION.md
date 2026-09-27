# Validation performed locally

The public quick-start passed under Python 3.9.12. It uses no third-party dependencies.

The portable importer/analyzer was also run on the existing private strict temporal cohort: 254 users, 1,778 user/policy/seed streams, 35,560 future-task/history-budget records and 177,800 mapping expectations. Sixty anchor-summary cells (five metrics × four history budgets × three policies), three h=10 pairwise-disjoint coverage values, and sixty partial-knowledge coverage summary values agreed with the original analysis within floating-point tolerance (1e-12 absolute tolerance with NumPy default relative tolerance). No new policy trajectories were generated.

This comparison uses the existing archive, so it checks agreement of the portable reimplementation with the original analysis rather than independent collection or independent third-party replication. Real trace inputs and per-task outputs remain outside this package. The optional importer requires the original archive and explicit eligibility CSV; the public synthetic demonstration can run without them.

The probability verification independently enumerates every k-element subset for n=0..8. Expected synthetic counts and the reported three-policy table are supplied as readable files. `expected/local_validation.json` records only aggregate validation counts, without participant identifiers.
