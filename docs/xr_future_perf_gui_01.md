# XR-FUTURE-PERF-GUI-01 isolated integration

Status: non-release isolated integration candidate. This work does not change
Foundation status, approve C/D candidates, start P1A, or modify the PR #21
candidate.

## Exact dependency set

- GUI candidate: `eb130ddba939f1996030d1dea62f7d0fafa56c74`.
- Current main: `8dd6f2ef0f14934977dfba06613d9e2155006b7f`.
- C phase-two candidate: `53ca7a984e477974364d5a5f7861e80a3a8b0d3a`.
- D performance candidate: `e30139c0e570c8afa98655980e7b0b36caa5e043`.
- D measured implementation: `27c1f8a8fb5e21daf95f4c75b99f824c8991a2d3`.
- D P0 prepared baseline: `2bf42ed2b2b36174f9e8c274da963b6c734201c0`.
- C explicit Fast 1×1 source: `2f96f7fb1178fdb26a7f1630a9c147ddf7c163fa`;
  D's P0-compatible transplant is `36740372960b015ddaecfcf3884cd0aa64cdec42`.
- D Fast prepared candidate: `8609f2259017ab59aef67324c4ffa6fa98c74b64`.

C `53ca7a9` contains D's older C dependency `08c2d28`; D `e30139c`
contains both `08c2d28` and `27c1f8a`. The isolated integration merged C latest
and then D HEAD, with no source conflict. Neither candidate is treated as
reviewed or mergeable-to-main by this document.

## GUI slice

The route editor exposes one explicit `Future Smart Space` template with the
unchanged 3×2 m, 64×48-control Future RIS. Model accuracy and map-grid resolution
are separate controls:

- `高速 1×1 · prepared` is the default and uses D's public snapshot-safe
  interface. The worker explicitly constructs
  `SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)` and passes
  that same engine to Focus, prepared link, and `prepare_controller_field()`.
- `精确 M8 · production` uses D's existing prepared interface and supports bounded
  `8×6`, `16×12`, and `48×36` fixed grids. `8×6` is the default quick native gate;
  it changes only receiver-map resolution, never RIS aperture or control count.

The prepared action builds one fixed receiver grid and a bounded route-command batch:

- Static uses the existing Focus path at route point 1.
- Adaptive uses the same existing Focus path at every sampled route point; the
  selected point remains the initial field/status anchor.
- No RIS uses the real Controller baseline at each route sample.
- D's `prepare_controller_field()` builds one matrix for the selected model and
  its `evaluate(pattern)` method hot-evaluates Static and the distinct Adaptive
  route commands.

The resulting field maps are cached only for those exact commands. The GUI
labels the result as one fixed grid plus a route-command batch and explicitly
says it is not a whole-route coefficient matrix. It does not retain a general
prepared cache.

The field key covers the full Scene snapshot, Profile identity, grid, selected
coefficient-model/quadrature identity, command hash, and a digest of D's per-grid
coefficient identities. The result
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

The D P0 candidate `2bf42ed2b2b36174f9e8c274da963b6c734201c0`
now supplies receiver-batch progress and `cancel_check` callbacks on
`prepare_controller_field()`. The GUI consumes both public callbacks: progress
is the real completed receiver count, and cancellation stops at a batch boundary
without publishing a partial prepared object. The P0 immutable evaluation
snapshot is consumed unchanged; the GUI does not own or mutate it.

No second long `48×36` build should be started on this environment until the
remaining Python 3.14 runtime difference is understood; the bounded P0
progress/cancellation seam is now connected.

## Small-grid native Windows gate

Fresh, visible `QApplication` runs on Windows/Python 3.14.3 exercised the real
Future worker and Production M8 calculation at `8×6`; they were not mocks and did
not run the benchmark harness. The post-P0 accepted run reported:

- cold matrix build: 17.64 s;
- Static hot evaluation: 0.64 ms;
- selected-point Adaptive hot evaluation: 0.26 ms;
- coefficient storage: 2.2 MiB;
- Static and Adaptive command hashes differed;
- No RIS display was exactly the same prepared solve's baseline array;
- real receiver progress ended `40/48`, `48/48`, then the two hot evaluations;
- all three GUI modes were selected after completion without further field physics.

A second real `16×12` build was cancelled after progress reached `16/192`.
Cancellation terminated at the next batch boundary, retained the already-published
three link rows, and did not publish or cache a partial field.

This closes only the small-grid exact-M8 native slice. Per-route-point coefficient
matrices and real dual-RIS physics remain open.

## Fast 1×1 prepared integration gate

D Fast candidate `8609f225` was merged without conflict. Its exact original
commits and trees were preserved; `3674037` is the candidate's P0-compatible
transplant of C `2f96f7f`, followed by implementation `3f2a193` and evidence
`8609f225`. Production M8 remains an explicit optional selection.

Visible Windows/Python 3.14.3 `QApplication` runs exercised the real GUI worker,
not a mock or benchmark harness:

- `8×6`: 0.60 s cold, 0.30 ms Static hot, 0.25 ms Adaptive hot, 2.2 MiB;
- `48×36`: 21.02 s cold, 2.18 ms Static hot, 1.48 ms Adaptive hot, 81.0 MiB;
- both runs retained the 3×2 m aperture and 64×48 control grid;
- both reported model `control_patch_center_bistatic_coefficients/1` and
  quadrature `midpoint_1x1_per_control_patch/1`;
- No RIS, Static, and selected-point Adaptive each displayed a real field; Static
  and Adaptive command hashes and fields differed.
- the sampled route's Adaptive command maps were hot-evaluated from the same one
  fixed-grid prepared matrix and cached before playback; no per-route field
  worker or second coefficient build runs during the 2 fps playback clock.

A separate real `48×36` cancellation run stopped after the first receiver batch
at `8/1728`. It emitted no partial result, no finished result, and no failure;
only worker termination was emitted. No partial field or prepared object entered
the GUI cache.

## Isolated dual-RIS editor slice

The XR editor can create a second RIS by cloning the selected scene's existing
aperture/control definition. It keeps two unique IDs and exposes per-instance
selection, XYZ movement (form or canvas), enable/disable state, and an independent
command-state line. TX/RX remain frozen while the two RIS graphics are draggable.
Any RIS edit invalidates prior commands, field identities, caches, and workers.

The current C/D route and prepared APIs remain single-RIS. Therefore the presence
of two RIS instances deliberately blocks Run and fixed-field actions with a visible
`joint dual-RIS complex-channel backend pending C/D` status. This editor never
computes two independent power maps, adds map values, or presents a single-RIS
result as dual-RIS. A future backend must accept both command snapshots and return
one channel in which both RIS contributions are coherently summed before power is
derived.
