# Memory diagnosis: improvement5/v3 versus improvement6/v2

Windows recorded a low-virtual-memory event (System event 2004) at 21:26:27
on September 30, 2026. VS Code recorded a renderer exit with `reason: oom`
at 21:26:46 in its `20260924T151454/main.log`. The host has 7.35 GiB usable
physical memory. These are observed out-of-memory failures, not inferred
Python syntax failures.

## Measured cause and change

Fresh Python 3.10 processes were measured with `psutil.Process.memory_info()`:

| Measurement | Private committed MB | Working-set MB |
|---|---:|---:|
| improvement5/v3 import, default numerical threads | 447.2 | 118.1 |
| improvement6/v2 import, before fix | approximately 447 | approximately 118 |
| improvement6/v2 import, after fix | 93.1 | 116.8 |
| Eight concurrent v2 imports, after fix (sum) | 746.0 | 936.3 |
| New lightweight supervisor | 9.5 | not sampled |

Private committed memory consumes Windows commit capacity backed by RAM or
the page file. It is not the same as resident physical RAM. The large gain
here is commit headroom; the import working set did not decrease materially.
Summing working sets can also count shared pages more than once.

Both versions' pipeline imports had similar memory use. The newer type
launcher additionally imported pandas/openpyxl, prepared the workbook, then
remained resident while launching a separate pipeline child. Loading pandas
and openpyxl alone used approximately 409 MB private commit with default
numerical thread settings. Eight launchers therefore added roughly 3.2 GB
of avoidable commit before counting their eight pipeline children.

The package now sets BLAS/OpenMP/NumExpr thread counts to one before pandas
imports. A standalone comparison measured pandas at 401.1 MB before versus
47.5 MB after this change. Workbook preparation runs in a short-lived child;
the supervisor does not import pandas. The full pipeline retains independent
parallelism across eight terminals, one question worker in each terminal.

The first proposed global process lock was replaced by a report-specific
lock. Eight different report paths can run simultaneously; duplicate writers
to the same report are rejected. Verbose logs are written to disk instead of
all eight terminal scrollbacks. Memory checks pause new work under critical
pressure but do not cap a question's allocations.

## Other processes

A snapshot before changes showed approximately 4,198 MB private commit across
24 Code processes, 2,367 MB across 29 Chrome processes, and 1,336 MB in Fuseki.
These values are snapshots, not fixed requirements. No user applications were
terminated and no global Windows or page-file settings were changed.

The Fuseki client implementation is identical between the two versions. Both
graph files are 39,985,711 bytes; both launchers ultimately use Java `-Xmx4G`.
The heap limit is not an allocation measurement. This comparison did not
establish Fuseki as a new v2-specific source of increased memory.

## Verification and limits

- 73 targeted unit tests passed: runtime guard (5), dataset preparation (2),
  V9 regressions (17), correctness (49).
- Eight concurrent full module imports and distinct report locks succeeded.
  Measurements are saved in `improvement6/.runtime/eight_process_startup.json`.
- The one-question smoke run loaded all 27 Fuseki classes and the input, and
  used about 107 MB private commit at the observed sample. Its model request
  was blocked by sandbox networking (`WinError 10013`), producing a retryable
  `TRANSIENT_ERROR` row. This is not a successful answer-generation test.
- An unsandboxed retry was rejected by automatic approval review pending
  explicit authorization for the question/schema payload sent to AWS Bedrock.
- Eight simultaneous full benchmark executions have not been verified.

Fresh reports default to `pipelien_output/run_v5_memory_safe`; previous results
are preserved because their source manifests identify older code. See the
experiment README for the eight terminal commands.
