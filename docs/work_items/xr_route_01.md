# Work Item: XR Custom Route and Complex Indoor Headless Prototype

- Role / owner: B, XR Data Owner
- Task ID: `XR-ROUTE-01`
- Status: non-release prototype implementation; no formal capability promotion
- Data contract: `airmirror_xr_route_experiment/1`
- Dependencies: [Scene JSON v1](../adr/0005-scene-json-v1.md),
  [XR Dynamic Room MVP](xr_dynamic_room_mvp.md), and
  [Adaptive prototype](xr_dynamic_room_adaptive_prototype.md)

## A/B minimum interface

An XR route document references one unchanged Scene v1 file with a relative path. It does not add
trajectory, time, command, or result fields to Scene v1. All coordinates are metres, all times are
seconds, and waypoint array order is authoritative.

`trajectory.timing.kind` is either `explicit_times` or `speed`. Explicit waypoint times start at
exactly zero and strictly increase. Speed timing supplies either one positive default speed or one
positive speed per segment. A repeated position is legal only with explicit increasing times, where
it represents a dwell. A one-point route is legal and produces one sample at `t=0`.

Sampling is piecewise linear. The configured positive interval defines a uniform clock, while every
waypoint time and the final endpoint are also included exactly once. The result is a deterministic
`tuple[TrajectorySample, ...]`. `max_samples` is enforced before expensive simulation and has a hard
upper bound of 1,000,000.

The direct data API is:

- `load_route_experiment(path) -> XRRouteExperiment`
- `create_route_experiment(scene, route, sampling, validation, *, experiment_id, scene_path=None)`
- `save_route_experiment(experiment, path, overwrite=False)`
- `save_route_experiment_bundle(experiment, path, *, scene_path=None, overwrite=False)`
- `sample_route(route, sampling) -> tuple[TrajectorySample, ...]`
- `retime_route_from_previous_speed(route, waypoint_index, speed_m_s) -> RouteDefinition`
- `validate_route(scene, waypoints, policy) -> RouteValidationReport`
- `compute_route_experiment(experiment, ...) -> MVPComputation`
- `run_route_experiment(path, output=None, ...) -> XRRouteArtifacts`

Loading validates schema identity, numbers, timing, sampling, room bounds, walls, and axis-aligned
obstacles. Wall and obstacle contact, including endpoint contact, is an error. Doorways are real gaps
between wall segments. Clearance conditions are warnings, and exact contacts are retained as
structured collision records for a future visualizer. This task does not provide automatic routing.

Scene identity is SHA-256 over the canonical validated Scene v1 dataclass. Trajectory identity covers
the route definition, sampling policy, and exact sampled points. Experiment identity covers the
semantic scene identity and all route policies, so moving equivalent files does not change identity.

The in-memory factory deep-copies all inputs and is the only supported way to construct an
`XRRouteExperiment`; callers cannot manually supply trajectory, validation, or identity fields. A
provided `scene_path` must already contain the same validated Scene v1 semantics. Route-only saving
rechecks that reference and rejects an unbound or changed Scene file. For an in-memory editor Scene,
the controlled bundle saver writes an exclusive sibling `<route-stem>.scene.json` by default, then
returns a snapshot bound to that exact file. An existing different Scene file is never overwritten.

Speed retiming identifies the incoming segment by its destination waypoint index. The selected
arrival changes to `previous_time + distance / speed`, and all later explicit arrivals shift by the
same delta, preserving every downstream motion and dwell duration. A speed-timed route is converted
to explicit per-segment speeds with only the selected value changed. The first waypoint, a selected
zero-length dwell, a single-point route, and non-positive or non-finite speed are rejected.

## Headless semantics

The route runner uses the existing production `SimulationEngine`, `ControllerModel`, and Coherent
Target Focus. No RIS supplies no command. Static generates one legal command at the initial point and
keeps the same immutable command and hash. Adaptive generates a legal immutable command at every
sample. At `t=0`, Static and Adaptive use identical inputs and must match exactly.

CSV output retains actual command values and hashes, complex LOS/wall/RIS/total components,
Power/SNR, sample time and position, scene/trajectory/experiment identities, and canonical partial C2
provenance. Output directories are exclusive. The default is a unique system-temporary directory
outside the repository; an explicit existing target fails before physics starts.

Run the checked-in example with:

```powershell
python -m airmirror_future.experiments.xr_route_headless configs/xr_route_01/multi_room_route_v1.json
```

## Ownership boundary

Owned files are the XR route modules, this work item, route-focused tests, the XR route config, and its
complex Scene v1 template. Existing `build_trajectory()`, `compute_mvp()`, and two-mode/adaptive
entrypoints remain unchanged.

This work item must not modify GUI code, production physics, RIS coefficient construction, Focus or
M8 formulas, QA-CC, P1A, Scene v1 schema, shared requirements/status, or tracked result artifacts. It
does not establish formal v0.2 XR completion or open any gate.
