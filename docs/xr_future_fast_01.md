# XR Future Fast 1×1 prepared slice

This is a non-release performance candidate based on P0 `2bf42ed` plus C's
explicit coefficient-model commit `2f96f7f`. It does not approve or merge P0,
change C's physical contract, or start P1A.

## Model and API

```python
from airmirror_future import FAST_1X1_RIS_COEFFICIENT_MODEL, SimulationEngine
from airmirror_future.simulation.prepared_controller import prepare_controller_field

engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
prepared = prepare_controller_field(
    scene,
    SimulationConfig(48, 36, batch_size=8),
    engine=engine,
    receiver_batch_size=8,
    progress=lambda done, total: on_progress(done, total),
    cancel_check=cancel_event.is_set,
)
field = prepared.evaluate(pattern)
```

The model is independently identified as
`control_patch_center_bistatic_coefficients/1` with quadrature
`midpoint_1x1_per_control_patch/1`. Each existing control patch still has its
full physical area and command; only its internal aperture integration is
reduced to the patch centre. Production M8 remains the default and is never
claimed by this result.

`prepared.coefficient_model_identity` exposes the model identity for GUI/cache
labels. `prepared.coefficient_identities` remain per-receiver C identities and
include the fast model identity. Public mutable snapshots and bytes-backed
arrays retain the P0 immutability and cancellation semantics.

## Scope of this slice

The single-RIS API remains unchanged. The corresponding dual-RIS prepared API
is now available in the follow-on `prepared_dual_ris` module and consumes C's
physical/Focus contract. No GPU, mutual coupling, or persistent general cache
is introduced.
