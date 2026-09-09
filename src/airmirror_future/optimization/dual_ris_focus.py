"""Bounded Controller-only coordination for up to two independent RIS surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import ChannelResult, RISSurface, Scene, Receiver, Transmitter
from airmirror_future.optimization.coherent_focus import (
    _coefficient_phase_conjugate,
    _strictly_better,
    coherent_common_phase_offset,
)
from airmirror_future.ris.phase import apply_common_phase_offset, common_phase_offset_candidates
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


@dataclass(frozen=True, slots=True)
class DualRISFocusResult:
    """Commands and Controller channel decomposition for one coordinated target."""

    patterns: dict[str, np.ndarray]
    baseline_channel: complex
    ris_channels: dict[str, complex]
    total_channel: complex
    objective_power_w: float
    rounds: int
    converged: bool


def _resolve_ris_pair(scene: Scene, ris_ids: tuple[str, ...] | list[str] | None) -> list[RISSurface]:
    if ris_ids is None:
        return [ris for ris in scene.ris_surfaces if ris.enabled][:2]
    if not isinstance(ris_ids, (tuple, list)) or not 0 < len(ris_ids) <= 2:
        raise ValueError("ris_ids must contain one or two RIS ids")
    if any(not isinstance(identifier, str) or not identifier for identifier in ris_ids):
        raise ValueError("ris_ids must contain non-empty strings")
    if len(set(ris_ids)) != len(ris_ids):
        raise ValueError("ris_ids must be unique")
    selected: list[RISSurface] = []
    for identifier in ris_ids:
        matches = [ris for ris in scene.ris_surfaces if ris.id == identifier]
        if len(matches) != 1:
            raise ValueError(f"RIS id not found or not unique: {identifier}")
        if matches[0].enabled:
            selected.append(matches[0])
    return selected


def _compose_channel(
    baseline: complex,
    coefficients: Mapping[str, np.ndarray],
    surfaces: Mapping[str, RISSurface],
    patterns: Mapping[str, np.ndarray],
) -> tuple[complex, dict[str, complex]]:
    ris_channels: dict[str, complex] = {}
    total = complex(baseline)
    for identifier, coefficient in coefficients.items():
        ris = surfaces[identifier]
        pattern = validate_commanded_pattern(ris, patterns[identifier])
        gamma = np.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern)
        contribution = complex(np.dot(coefficient, gamma))
        ris_channels[identifier] = contribution
        total += contribution
    return total, ris_channels


def _candidate_patterns(ris: RISSurface, base_phase: np.ndarray) -> list[np.ndarray]:
    if ris.phase_bits is None:
        return [validate_commanded_pattern(ris, base_phase)]
    return [
        validate_commanded_pattern(ris, apply_common_phase_offset(base_phase, float(offset), ris.phase_bits))
        for offset in common_phase_offset_candidates(base_phase, ris.phase_bits)
    ]


def _continuous_aligned_pattern(
    ris: RISSurface,
    coefficients: np.ndarray,
    base_phase: np.ndarray,
    target_channel: complex,
) -> np.ndarray:
    unshifted = np.dot(
        coefficients,
        np.sqrt(ris.reflection_efficiency) * np.exp(1j * base_phase),
    )
    offset = coherent_common_phase_offset(target_channel, unshifted)
    return validate_commanded_pattern(
        ris, apply_common_phase_offset(base_phase, offset, None)
    )


def generate_dual_ris_coordinated_patterns(
    scene: Scene,
    controller_model: ControllerModel | None = None,
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris_ids: tuple[str, ...] | list[str] | None = None,
    max_rounds: int = 4,
) -> DualRISFocusResult:
    """Generate deterministic Controller commands for one or two independent RIS.

    Continuous surfaces receive phase-conjugate commands with one shared target
    phase. Finite-bit surfaces use bounded common-offset coordinate improvement:
    each RIS enumerates its legal offset family while the other command is held
    fixed. A sweep stops when no strict objective improvement occurs, or after
    ``max_rounds`` sweeps. RIS-to-RIS reflections and Ground Truth state are not
    part of this model.
    """
    active_model = controller_model or ControllerModel()
    if not isinstance(active_model, ControllerModel) or isinstance(active_model, GroundTruthModel):
        raise ValueError("dual RIS Focus requires ControllerModel")
    if isinstance(max_rounds, (bool, np.bool_)) or not isinstance(max_rounds, (int, np.integer)) or max_rounds <= 0:
        raise ValueError("max_rounds must be a positive integer")
    selected = _resolve_ris_pair(scene, ris_ids)
    active_engine = engine or SimulationEngine()
    if not selected:
        baseline_result = active_engine.compute_channel(scene, tx=tx, rx=rx, ris_patterns={}, model=active_model)
        return DualRISFocusResult({}, baseline_result.total_channel, {}, baseline_result.total_channel, baseline_result.received_power_w, 0, True)

    coefficients: dict[str, np.ndarray] = {}
    surfaces = {ris.id: ris for ris in selected}
    baseline: complex | None = None
    target_tx = active_engine._resolve_tx(scene, tx)
    target_rx = active_engine._resolve_rx(scene, rx)
    for ris in selected:
        values, ris_baseline = active_engine.controller_focus_terms(scene, target_tx, target_rx, ris, active_model)
        coefficients[ris.id] = values
        if baseline is None:
            baseline = ris_baseline
        elif ris_baseline != baseline:
            raise ValueError("Controller baseline changed while resolving RIS pair")
    assert baseline is not None

    base_phases = {identifier: _coefficient_phase_conjugate(value) for identifier, value in coefficients.items()}
    patterns: dict[str, np.ndarray] = {}
    if all(ris.phase_bits is None for ris in selected):
        target_phase = 0.0 if abs(baseline) == 0.0 else float(np.angle(baseline))
        for ris in selected:
            unshifted = np.dot(coefficients[ris.id], np.sqrt(ris.reflection_efficiency) * np.exp(1j * base_phases[ris.id]))
            offset = 0.0
            if abs(unshifted) > 0.0 and abs(baseline) > 0.0:
                offset = float(np.mod(target_phase - np.angle(unshifted), 2.0 * np.pi))
            patterns[ris.id] = validate_commanded_pattern(ris, apply_common_phase_offset(base_phases[ris.id], offset, None))
        total, ris_channels = _compose_channel(baseline, coefficients, surfaces, patterns)
        return DualRISFocusResult(patterns, baseline, ris_channels, total, target_tx.power_w * abs(total) ** 2, 1, True)

    for ris in selected:
        if ris.phase_bits is None:
            patterns[ris.id] = _continuous_aligned_pattern(
                ris, coefficients[ris.id], base_phases[ris.id], baseline
            )
        else:
            patterns[ris.id] = _candidate_patterns(ris, base_phases[ris.id])[0]
    total, ris_channels = _compose_channel(baseline, coefficients, surfaces, patterns)
    best_power = target_tx.power_w * abs(total) ** 2
    converged = False
    rounds_completed = 0
    for round_index in range(int(max_rounds)):
        improved = False
        for ris in selected:
            incumbent = patterns[ris.id]
            local_best = incumbent
            local_power = best_power
            if ris.phase_bits is None:
                other_patterns = {
                    identifier: value
                    for identifier, value in patterns.items()
                    if identifier != ris.id
                }
                other_coefficients = {
                    identifier: coefficients[identifier]
                    for identifier in other_patterns
                }
                other_surfaces = {
                    identifier: surfaces[identifier]
                    for identifier in other_patterns
                }
                residual, _ = _compose_channel(
                    baseline, other_coefficients, other_surfaces, other_patterns
                ) if other_patterns else (baseline, {})
                candidates = [
                    _continuous_aligned_pattern(
                        ris, coefficients[ris.id], base_phases[ris.id], residual
                    )
                ]
            else:
                candidates = _candidate_patterns(ris, base_phases[ris.id])
            for candidate in candidates:
                trial = dict(patterns)
                trial[ris.id] = candidate
                trial_total, _ = _compose_channel(baseline, coefficients, surfaces, trial)
                trial_power = target_tx.power_w * abs(trial_total) ** 2
                if _strictly_better(float(trial_power), float(local_power)):
                    local_best = candidate
                    local_power = trial_power
            if not np.array_equal(local_best, incumbent):
                patterns[ris.id] = local_best
                best_power = float(local_power)
                improved = True
        rounds_completed = round_index + 1
        if not improved:
            converged = True
            break
    total, ris_channels = _compose_channel(baseline, coefficients, surfaces, patterns)
    return DualRISFocusResult(patterns, baseline, ris_channels, total, target_tx.power_w * abs(total) ** 2, rounds_completed, converged)


def evaluate_dual_ris_command(
    scene: Scene,
    patterns: Mapping[str, np.ndarray],
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    model: ControllerModel | GroundTruthModel | None = None,
) -> ChannelResult:
    """Evaluate one or two RIS commands through the existing Engine sum."""
    if not isinstance(patterns, Mapping) or not 0 <= len(patterns) <= 2:
        raise ValueError("patterns must contain zero, one, or two RIS commands")
    active_model = model or ControllerModel()
    if not isinstance(active_model, (ControllerModel, GroundTruthModel)):
        raise ValueError("model must be ControllerModel or GroundTruthModel")
    return (engine or SimulationEngine()).compute_channel(scene, tx=tx, rx=rx, ris_patterns=patterns, model=active_model)


__all__ = ["DualRISFocusResult", "evaluate_dual_ris_command", "generate_dual_ris_coordinated_patterns"]
