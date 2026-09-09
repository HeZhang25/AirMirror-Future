# XR-FUTURE-PERF-01 P0 closure candidate

This document describes the bounded P0 repair on top of D `e30139c` plus C
final candidate `53ca7a9`. It is a review candidate only; it does not approve,
merge, or change Foundation status.

## Prepared snapshot safety

`PreparedControllerLink` and `PreparedControllerField` retain the public Scene,
Tx, Rx, RIS, and config objects for inspection, but `evaluate()` reads a
separate immutable scalar calculation snapshot. Coefficient, baseline, and grid
arrays are backed by immutable `bytes`, so changing nested public objects (or
re-enabling NumPy writes) cannot alter an already-built result. The snapshot
contains physical/metric inputs used by evaluation, while C's
`coefficient_identity` remains limited to coefficient physics: efficiency, Pt,
bandwidth/NF, coverage, phase bits, and RNG are intentionally excluded.

Regression coverage includes direct mutation of Scene, Tx, Rx, RIS, walls,
obstacles, config, and nested values, plus multiple legal patterns, profile
modifiers, Production M8, Gamma, Controller/GT rejection, and No-RIS baseline
equivalence.

## Cold-build progress and cancellation

```python
prepared = prepare_controller_field(
    scene,
    config,
    receiver_batch_size=8,
    progress=lambda completed, total: on_progress(completed, total),
    # `progress_callback=` is an equivalent alias; do not pass both.
    cancel_check=worker_cancel_event.is_set,
)
```

The callback receives exact receiver-point counts `(completed, total)` at
`(0,total)` and after each completed receiver batch. Counts are monotonic and
are not synthetic wall-clock percentages. Cancellation is checked before and
after each batch; it raises `SimulationCancelled`, stops subsequent work, and
cannot return or cache a partial prepared object. Exceptions from the callback
or build likewise leave no prepared result.

## Compatibility dependency

- D starting candidate: `e30139c0e570c8afa98655980e7b0b36caa5e043`
- C final candidate merged for focused compatibility: `53ca7a984e477974364d5a5f7861e80a3a8b0d3a`
- Shared C base: `08c2d28fd0e749643ff29f269259980369d30f0c`
- Main checked during this run: `4d7bfc66f7d05af731d884dd01a7bb619bdcb112`

The C production coefficient contract is consumed as-is; this D repair does
not change C's physical formula or identity ownership.

## Bounded runtime investigation

The original D evidence directories were neither overwritten nor rerun. The
P0 candidate was measured separately on Windows, Python 3.11.4, NumPy 2.4.6,
scipy-openblas 0.3.31, with OMP/OpenBLAS/MKL/NumExpr thread variables all set
to `1`.

After merging C `53ca7a9`, an initial diagnostic showed 8x6 at 20.04 s and
16x12 at 76.74 s. Staging isolated the cause: the M8 matrix itself took about
0.183 s per eight receivers, while C's final identity path repeatedly
canonicalized and serialized the exact 196,608-entry quadrature parent array
for every receiver. The P0 candidate now reuses the exact canonical
quadrature JSON bytes within one prepared build. A regression proves the
optimized identity SHA is byte-for-byte equivalent to C's direct path; no
identity field or physical input was removed.

Final bounded measurements on that same host:

| Grid | Cold build | Completed points | Coefficient bytes |
|---|---:|---:|---:|
| 8x6 | 2.22 s | 48/48 | 2,359,296 |
| 16x12 | 4.92 s | 192/192 | 9,437,184 |
| 48x36 | 37.03 s | 1,728/1,728 | 84,934,656 |

The single 48x36 attempt had a hard 90 s cancellation condition and completed
normally before it. These data do not explain or replace A's separate Python
3.14.3 / NumPy 2.4.4 approximately-150-second incomplete run. A should rerun
once with this candidate's real batch progress and cancellation seam before
any further performance conclusion.
