# XR Future dual RIS fast prepared slice

This candidate extends D's single-RIS fast path (`8609f225`) with bounded
prepared coefficients for one or two independent RIS surfaces. It consumes the
existing C `SimulationEngine.controller_focus_terms()` seam and does not add a
new propagation model or RIS-to-RIS reflection path.

```python
from airmirror_future import FAST_1X1_RIS_COEFFICIENT_MODEL, SimulationEngine
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_dual_ris_field,
)

engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
prepared = prepare_controller_dual_ris_field(
    scene,
    SimulationConfig(48, 36, batch_size=8),
    engine=engine,
    ris_ids=("ris-1", "ris-2"),
    receiver_batch_size=8,
    progress=lambda done, total: on_progress(done, total),
    cancel_check=cancel_event.is_set,
)
field = prepared.evaluate({
    "ris-1": pattern1,
    "ris-2": pattern2,
})
```

The prepared field stores separate `A1` and `A2` matrices and evaluates the
shared complex channel as `h_baseline + A1 @ Gamma1 + A2 @ Gamma2`; powers are
computed only after this coherent sum. Omitted commands disable that RIS for
the evaluation. Selecting one enabled RIS gives the single-RIS degradation;
explicitly disabled RIS are excluded during preparation.

`PreparedDualRISLink` provides the same contract for one receiver. Both classes
expose `coefficient_model_identity`, per-RIS `coefficient_identities`, exact
batch progress, safe-boundary cancellation, and immutable internal snapshots.
The default dual-field coefficient budget is 192 MiB, sufficient for two
64x48 RIS matrices on a 48x36 receiver grid (about 162 MiB), while callers may
lower it to force an explicit bounded failure.

This remains a non-release candidate. Production M8 is unchanged and must be
selected explicitly by using the default `SimulationEngine()` model.
