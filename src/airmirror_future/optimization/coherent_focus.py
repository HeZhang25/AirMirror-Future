"""Nominal single-link Coherent Target Focus strategy."""

from __future__ import annotations

import numpy as np

from airmirror_future.core.types import Receiver, RISSurface, Scene, Transmitter
from airmirror_future.ris.phase import (
    apply_common_phase_offset,
    common_phase_offset_candidates,
    generate_unquantized_ris_only_focus_pattern,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


_RELATIVE_DEGENERACY_TOLERANCE = 64.0 * np.finfo(float).eps


def coherent_common_phase_offset(
    baseline_channel: complex,
    ris_channel: complex,
) -> float:
    """Return the offset aligning ``ris_channel`` to ``baseline_channel``.

    If either component is negligible relative to the other, ``0.0`` is the
    deterministic fallback.  The result is always finite and in ``[0, 2*pi)``.
    """
    if not (
        np.isfinite(baseline_channel.real)
        and np.isfinite(baseline_channel.imag)
        and np.isfinite(ris_channel.real)
        and np.isfinite(ris_channel.imag)
    ):
        raise ValueError("channel components must be finite")

    baseline_magnitude = abs(baseline_channel)
    ris_magnitude = abs(ris_channel)
    scale = max(baseline_magnitude, ris_magnitude, np.finfo(float).tiny)
    if (
        baseline_magnitude <= _RELATIVE_DEGENERACY_TOLERANCE * scale
        or ris_magnitude <= _RELATIVE_DEGENERACY_TOLERANCE * scale
    ):
        return 0.0
    return float(
        np.mod(np.angle(baseline_channel) - np.angle(ris_channel), 2.0 * np.pi)
    )


def _resolve_ris(scene: Scene, ris: RISSurface | str | None) -> RISSurface:
    if isinstance(ris, RISSurface):
        identifier = ris.id
    else:
        identifier = ris

    if identifier is None:
        enabled = [surface for surface in scene.ris_surfaces if surface.enabled]
        if len(enabled) != 1:
            raise ValueError("Coherent Target Focus requires exactly one enabled RIS")
        return enabled[0]

    matches = [surface for surface in scene.ris_surfaces if surface.id == identifier]
    if not matches:
        raise ValueError(f"RIS id not found in scene: {identifier}")
    if len(matches) > 1:
        raise ValueError(f"RIS id is not unique in scene: {identifier}")
    if not matches[0].enabled:
        raise ValueError(f"RIS is disabled: {identifier}")
    return matches[0]


def _resolve_tx(scene: Scene, tx: Transmitter | str | None) -> Transmitter:
    if isinstance(tx, Transmitter):
        return tx
    try:
        return scene.transmitter(tx)
    except StopIteration as error:
        raise ValueError(f"transmitter id not found in scene: {tx}") from error


def _resolve_rx(scene: Scene, rx: Receiver | str | None) -> Receiver:
    if isinstance(rx, Receiver):
        return rx
    try:
        return scene.receiver(rx)
    except StopIteration as error:
        raise ValueError(f"receiver id not found in scene: {rx}") from error


def _strictly_better(candidate: float, incumbent: float) -> bool:
    scale = max(abs(candidate), abs(incumbent), np.finfo(float).tiny)
    tolerance = 8.0 * np.finfo(float).eps * scale
    return candidate > incumbent + tolerance


def generate_coherent_target_pattern(
    scene: Scene,
    controller_model: ControllerModel | None = None,
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris: RISSurface | str | None = None,
) -> np.ndarray:
    """Maximize nominal single-target power over a common phase-offset family.

    Continuous hardware uses the analytic offset that aligns the aggregate RIS
    channel to ``h_LOS + h_wall``.  Finite-bit hardware evaluates one command
    from every piecewise-constant common-offset interval.  Exact ``delta=0`` is
    evaluated first, so stable ties preserve the legacy RIS-only command.

    The strategy is model-based and accepts only a nominal Controller Model;
    Ground Truth state and MeasurementOracle data are intentionally excluded.
    """
    active_model = controller_model or ControllerModel()
    if not isinstance(active_model, ControllerModel):
        raise ValueError("controller_model must be a ControllerModel")
    if isinstance(active_model, GroundTruthModel):
        raise ValueError("Coherent Target Focus cannot use GroundTruthModel")

    active_engine = engine or SimulationEngine()
    target_ris = _resolve_ris(scene, ris)
    target_tx = _resolve_tx(scene, tx)
    target_rx = _resolve_rx(scene, rx)
    ideal = generate_unquantized_ris_only_focus_pattern(
        target_ris, target_tx, target_rx, scene.frequency_hz
    )

    baseline_result = active_engine.compute_channel(
        scene,
        target_tx,
        target_rx,
        ris_patterns={},
        model=active_model,
    )
    baseline_channel = baseline_result.los_channel + baseline_result.wall_channel
    unshifted = apply_common_phase_offset(ideal, 0.0, target_ris.phase_bits)
    unshifted_result = active_engine.compute_channel(
        scene,
        target_tx,
        target_rx,
        ris_patterns={target_ris.id: unshifted},
        model=active_model,
    )

    if target_ris.phase_bits is None:
        offset = coherent_common_phase_offset(
            baseline_channel, unshifted_result.ris_channel
        )
        return apply_common_phase_offset(ideal, offset, None)

    candidates = common_phase_offset_candidates(ideal, target_ris.phase_bits)
    best_pattern = unshifted
    best_power_w = unshifted_result.received_power_w
    for offset in candidates[1:]:
        candidate_pattern = apply_common_phase_offset(
            ideal, float(offset), target_ris.phase_bits
        )
        candidate_result = active_engine.compute_channel(
            scene,
            target_tx,
            target_rx,
            ris_patterns={target_ris.id: candidate_pattern},
            model=active_model,
        )
        if _strictly_better(candidate_result.received_power_w, best_power_w):
            best_pattern = candidate_pattern
            best_power_w = candidate_result.received_power_w
    return best_pattern
