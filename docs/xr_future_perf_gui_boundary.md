# XR-FUTURE-PERF-01 GUI Integration Boundary

Status: coordination checklist only. This document does not freeze a file schema,
introduce a physics contract, or authorize a low-order preview path. D owns the
calculation implementation and result format; A owns GUI validation, loading,
buffering, and playback after a concrete D candidate is published.

## Minimum handoff from D

Before A connects a loader, one single-Future candidate must expose enough data
to verify the result against the selected immutable route run:

- existing `XRRouteExperiment` identity values: `experiment_identity`,
  `scene_identity`, and `trajectory_identity`;
- one result for every trajectory sample and each existing mode (`No RIS`,
  `Static RIS`, and `Adaptive RIS`), including the real received-power and SNR
  metrics already represented by `DynamicLinkSample`;
- the exact per-sample command kind, command hash, and command values already
  represented by `DynamicLinkSample` (No RIS remains command-free);
- each complete field map keyed to its sample/mode command identity, without a
  fallback to a field from a different sample;
- an explicit model-accuracy label, the calculation implementation Git SHA, and
  the result directory or file path used for the run.

A will adapt the concrete D output to existing `MVPComputation`,
`DynamicLinkSample`, `FieldMapResult`, and route identity types after D publishes
the candidate. No parallel serializer or duplicate result model is defined here.

## GUI acceptance rules

The loader must reject an identity mismatch before replacing the currently
displayed route result. Loading is atomic: partial or invalid output leaves the
prior valid result intact.

Playback may start only when all three link-mode rows for the route are present.
For a selected field that is not complete, the GUI clears the old overlay, shows
`buffering`, and waits for the exact current sample result. It never presents an
old sample's field as current. Once the exact field arrives, a previously running
playback resumes; an explicit pause, cancel, route edit, rerun, or scenario switch
clears that resume intent.

Hot-cache playback performs no link or field physics. It reads the validated
result set continuously through the complete route, including mode switches.

The GUI displays physics accuracy separately from map-grid resolution. Current
in-process fields are labelled `Production M8` and `Fast grid 80×60`. Any future
lower-order preview must carry its own explicit non-production accuracy label and
must not share the production-result cache identity.

## Native Windows gate after D delivery

Using D's exact candidate SHA, run one fresh single-Future route with no prior
result cache and record: calculation start, buffering with no stale field,
completion, automatic playback resume, hot-cache replay, three-mode switching,
cancellation/worker termination, full-route completion, calculation SHA, model
accuracy, and result path. Do not promote release status from this gate.
