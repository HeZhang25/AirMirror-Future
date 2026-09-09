"""Nominal single-link Coherent Target Focus strategy."""

from __future__ import annotations

import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import Receiver, RISSurface, Scene, Transmitter
from airmirror_future.ris.phase import (
    apply_common_phase_offset,
    common_phase_offset_candidates,
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


def _coefficient_phase_conjugate(coefficients: np.ndarray) -> np.ndarray:
    values = np.asarray(coefficients, dtype=complex)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("coefficients must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(values.real)) or not np.all(np.isfinite(values.imag)):
        raise ValueError("coefficients must contain only finite values")
    phase = np.zeros(values.size, dtype=float)
    nonzero = values != 0.0
    phase[nonzero] = np.mod(-np.angle(values[nonzero]), 2.0 * np.pi)
    return phase


def generate_scene_aware_ris_only_pattern(
    scene: Scene,
    controller_model: ControllerModel | None = None,
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris: RISSurface | str | None = None,
) -> np.ndarray:
    """Maximize nominal RIS-only power over the common-offset family."""
    active_model = controller_model or ControllerModel()
    if not isinstance(active_model, ControllerModel) or isinstance(active_model, GroundTruthModel):
        raise ValueError("scene-aware RIS-only Focus requires ControllerModel")
    active_engine = engine or SimulationEngine()
    target_ris = _resolve_ris(scene, ris)
    target_tx = _resolve_tx(scene, tx)
    target_rx = _resolve_rx(scene, rx)
    coefficients, _ = active_engine.controller_focus_terms(
        scene, target_tx, target_rx, target_ris, active_model
    )
    base_phase = _coefficient_phase_conjugate(coefficients)
    unshifted = validate_commanded_pattern(
        target_ris,
        apply_common_phase_offset(base_phase, 0.0, target_ris.phase_bits),
    )
    if target_ris.phase_bits is None:
        return unshifted
    offsets = common_phase_offset_candidates(base_phase, target_ris.phase_bits)
    efficiency = np.sqrt(target_ris.reflection_efficiency)
    best_pattern = unshifted
    best_power = target_tx.power_w * abs(np.dot(coefficients, efficiency * np.exp(1j * unshifted))) ** 2
    for offset in offsets[1:]:
        candidate = validate_commanded_pattern(
            target_ris,
            apply_common_phase_offset(base_phase, float(offset), target_ris.phase_bits),
        )
        power = target_tx.power_w * abs(np.dot(coefficients, efficiency * np.exp(1j * candidate))) ** 2
        if _strictly_better(float(power), float(best_power)):
            best_pattern = candidate
            best_power = power
    return best_pattern


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
    evaluated first, so stable ties preserve the unshifted scene-aware command.

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
    coefficients, baseline_channel = active_engine.controller_focus_terms(
        scene, target_tx, target_rx, target_ris, active_model
    )
    ideal = _coefficient_phase_conjugate(coefficients)

    unshifted = validate_commanded_pattern(
        target_ris,
        apply_common_phase_offset(ideal, 0.0, target_ris.phase_bits),
    )
    efficiency = np.sqrt(target_ris.reflection_efficiency)
    unshifted_ris = complex(
        np.dot(coefficients, efficiency * np.exp(1j * unshifted))
    )

    if target_ris.phase_bits is None:
        offset = coherent_common_phase_offset(
            baseline_channel, unshifted_ris
        )
        return validate_commanded_pattern(
            target_ris, apply_common_phase_offset(ideal, offset, None)
        )

    candidates = common_phase_offset_candidates(ideal, target_ris.phase_bits)
    best_pattern = unshifted
    best_power_w = target_tx.power_w * abs(baseline_channel + unshifted_ris) ** 2
    for offset in candidates[1:]:
        candidate_pattern = validate_commanded_pattern(
            target_ris,
            apply_common_phase_offset(ideal, float(offset), target_ris.phase_bits),
        )
        candidate_ris = np.dot(
            coefficients, efficiency * np.exp(1j * candidate_pattern)
        )
        candidate_power_w = target_tx.power_w * abs(baseline_channel + candidate_ris) ** 2
        if _strictly_better(float(candidate_power_w), float(best_power_w)):
            best_pattern = candidate_pattern
            best_power_w = candidate_power_w
    return best_pattern
