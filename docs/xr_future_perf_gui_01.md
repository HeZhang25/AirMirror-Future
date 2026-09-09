# XR-FUTURE-PERF-GUI-01 isolated integration

Status: non-release isolated integration candidate. This work does not change
Foundation status, approve C/D candidates, start P1A, or modify the PR #21
candidate.

## Exact dependency set

- GUI candidate: `eb130ddba939f1996030d1dea62f7d0fafa56c74`.
- Current main: `4d7bfc66f7d05af731d884dd01a7bb619bdcb112` (already contained by the GUI candidate).
- C phase-two candidate: `53ca7a984e477974364d5a5f7861e80a3a8b0d3a`.
- D performance candidate: `e30139c0e570c8afa98655980e7b0b36caa5e043`.
- D measured implementation: `27c1f8a8fb5e21daf95f4c75b99f824c8991a2d3`.

C `53ca7a9` contains D's older C dependency `08c2d28`; D `e30139c`
contains both `08c2d28` and `27c1f8a`. The isolated integration merged C latest
and then D HEAD, with no source conflict. Neither candidate is treated as
reviewed or mergeable-to-main by this document.

## GUI slice

The route editor exposes one explicit `Future Smart Space` template with the
unchanged 3×2 m, 64×48-control Future RIS. Model accuracy and map-grid resolution
are separate controls:

- `高速 1×1 · preview` is visible but disabled until D supplies a public,
  snapshot-safe interface. The GUI does not call a private quadrature helper or
  relabel an M8 result as 1×1.
- `精确 M8 · production` uses D's existing prepared interface and supports bounded
  `8×6`, `16×12`, and `48×36` fixed grids. `8×6` is the default quick native gate;
  it changes only receiver-map resolution, never RIS aperture or control count.

The exact action is bound to the selected route point:

- Static uses the existing Focus path at route point 1.
- Adaptive uses the same existing Focus path at the selected point.
- No RIS uses the real Controller baseline at that same selected point.
- D's `prepare_controller_field()` builds one Production-M8 matrix and its
  `evaluate(pattern)` method evaluates Static and Adaptive consecutively.

The resulting field maps are cached only for those exact commands. The GUI
labels the result as a selected-point fixed field and explicitly says it is not
a whole-route coefficient matrix. It does not retain a general prepared cache.

The field key covers the full Scene snapshot, Profile identity, grid, M8 policy,
command hash, and a digest of D's per-grid coefficient identities. The result
also carries the route experiment, Scene, and trajectory identities; all three
are checked again before a field can replace the display. Route edits, receiver
changes, reruns, cancellation, and scenario switches invalidate the result and
clear the old overlay.

Cold-build elapsed time, final cold-build duration, per-command hot evaluation
times, coefficient bytes, coefficient identity, and the independent 2 fps GUI
playback clock are displayed separately.

## Current native gate and minimal D interface request

D's checked-in Windows/Python 3.11 evidence for the same Future 48×36 matrix is
43.2158 s cold, 5.0979 ms hot, 81 MiB coefficient storage, and 197.26 MiB peak
working set. On this integration host, only Python 3.14.3 / NumPy 2.4.4 is
available with project dependencies. The first and only integration-host 48×36
run was stopped after approximately 150 s while still inside the cold build; no
field result was emitted or applied. It therefore is not recorded as a passed
native closed loop.

The minimal D-side interface needed for the final native gate is optional
receiver-batch progress and `cancel_check` callbacks on
`prepare_controller_field()`. They do not require a new formula, Focus path,
model, cache, or identity contract. Until that exists, the GUI shows truthful
elapsed time and an indeterminate cold-build state; cancellation isolates the
result immediately but the worker cannot return until D's in-flight build does.

No second long `48×36` build should be started on this environment until D confirms
the runtime difference or supplies that bounded progress/cancellation seam.

## Small-grid native Windows gate

One fresh, visible `QApplication` run on Windows/Python 3.14.3 exercised the real
Future worker and Production M8 calculation at `8×6`; it was not a mock and did
not run the benchmark harness. The complete GUI loop finished in 20.1462 s:

- cold matrix build: 18.16 s;
- Static hot evaluation: 0.58 ms;
- selected-point Adaptive hot evaluation: 0.20 ms;
- coefficient storage: 2.2 MiB;
- Static and Adaptive command hashes differed;
- No RIS display was exactly the same prepared solve's baseline array;
- all three GUI modes were selected after completion without further field physics.

This closes only the small-grid exact-M8 native slice. Fast 1×1, full-route prepared
fields, and the pending D progress/cancellation interface remain open.
