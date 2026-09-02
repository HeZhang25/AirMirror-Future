from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from airmirror_future import (
    generate_coherent_target_pattern as top_level_coherent_target_pattern,
    generate_ris_only_focus_pattern as top_level_ris_only_focus_pattern,
)
from airmirror_future.core.types import Scene
from airmirror_future.optimization.coherent_focus import (
    coherent_common_phase_offset,
    generate_coherent_target_pattern,
)
from airmirror_future.ris.phase import (
    apply_common_phase_offset,
    common_phase_offset_candidates,
    generate_focus_pattern,
    generate_ris_only_focus_pattern,
    generate_unquantized_ris_only_focus_pattern,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel


def _continuous_smart_space() -> Scene:
    scene = create_smart_space_scene("Current")
    continuous_ris = replace(scene.ris_surfaces[0], phase_bits=None)
    return replace(scene, ris_surfaces=[continuous_ris])


def test_ris_only_focus_preserves_legacy_phase_conjugation() -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    explicit = generate_ris_only_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    legacy = generate_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    assert np.array_equal(explicit, legacy)


def test_continuous_coherent_focus_aligns_with_nominal_baseline() -> None:
    scene = _continuous_smart_space()
    ris = scene.ris_surfaces[0]
    engine = SimulationEngine()
    baseline = engine.compute_channel(scene, ris_patterns={})
    pattern = generate_coherent_target_pattern(scene, engine=engine)
    result = engine.compute_channel(scene, ris_patterns={ris.id: pattern})

    phase_difference = np.angle(result.ris_channel * np.conj(baseline.total_channel))
    assert abs(phase_difference) < 1.0e-12


def test_continuous_coherent_focus_reaches_analytic_total_amplitude() -> None:
    scene = _continuous_smart_space()
    ris = scene.ris_surfaces[0]
    engine = SimulationEngine()
    baseline = engine.compute_channel(scene, ris_patterns={})
    pattern = generate_coherent_target_pattern(scene, engine=engine)
    result = engine.compute_channel(scene, ris_patterns={ris.id: pattern})

    expected = abs(baseline.total_channel) + abs(result.ris_channel)
    assert abs(result.total_channel) == pytest.approx(expected, rel=1.0e-12)


def test_coherent_focus_does_not_reduce_nominal_target_below_baseline() -> None:
    scene = _continuous_smart_space()
    ris = scene.ris_surfaces[0]
    engine = SimulationEngine()
    baseline = engine.compute_channel(scene, ris_patterns={})
    pattern = generate_coherent_target_pattern(scene, engine=engine)
    result = engine.compute_channel(scene, ris_patterns={ris.id: pattern})
    assert result.received_power_w >= baseline.received_power_w


def test_quantized_common_offset_beats_unshifted_candidate() -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    engine = SimulationEngine()
    ideal = generate_unquantized_ris_only_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    assert ris.phase_bits is not None
    candidates = common_phase_offset_candidates(ideal, ris.phase_bits)
    assert candidates[0] == 0.0

    unshifted = apply_common_phase_offset(ideal, 0.0, ris.phase_bits)
    coherent = generate_coherent_target_pattern(scene, engine=engine)
    unshifted_result = engine.compute_channel(scene, ris_patterns={ris.id: unshifted})
    coherent_result = engine.compute_channel(scene, ris_patterns={ris.id: coherent})
    assert coherent_result.received_power_w >= unshifted_result.received_power_w


def test_common_offset_candidates_cover_all_reachable_two_bit_patterns() -> None:
    ideal = np.array([0.13, 0.91, 2.77])
    candidates = common_phase_offset_candidates(ideal, bits=2)
    candidate_patterns = {
        tuple(apply_common_phase_offset(ideal, offset, bits=2))
        for offset in candidates
    }
    dense_patterns = {
        tuple(apply_common_phase_offset(ideal, offset, bits=2))
        for offset in np.linspace(0.0, 2.0 * np.pi, 20_000, endpoint=False)
    }
    assert dense_patterns <= candidate_patterns


def test_zero_baseline_focus_has_deterministic_fallback() -> None:
    assert coherent_common_phase_offset(0.0j, 1.0 + 2.0j) == 0.0
    assert coherent_common_phase_offset(1.0 + 2.0j, 0.0j) == 0.0
    assert coherent_common_phase_offset(1.0e-30j, 1.0 + 0.0j) == 0.0


def test_coherent_focus_rejects_ground_truth_model() -> None:
    scene = create_smart_space_scene("Current")
    with pytest.raises(ValueError, match="GroundTruthModel"):
        generate_coherent_target_pattern(scene, GroundTruthModel())


def test_a1_public_exports_are_importable() -> None:
    assert top_level_coherent_target_pattern is generate_coherent_target_pattern
    assert top_level_ris_only_focus_pattern is generate_ris_only_focus_pattern


@pytest.mark.parametrize(
    "operation",
    (
        lambda: apply_common_phase_offset(np.array([[0.0]]), 0.0, bits=1),
        lambda: apply_common_phase_offset(np.array([np.nan]), 0.0, bits=None),
        lambda: common_phase_offset_candidates(np.array([]), bits=1),
        lambda: common_phase_offset_candidates(np.array([0.0]), bits=0),
        lambda: common_phase_offset_candidates(np.array([0.0]), bits=1.5),
    ),
)
def test_common_offset_helpers_reject_invalid_inputs(operation) -> None:
    with pytest.raises(ValueError):
        operation()


@pytest.mark.parametrize("bad_offset", (np.nan, np.inf, -np.inf))
def test_common_phase_offset_rejects_nonfinite_offset(bad_offset: float) -> None:
    with pytest.raises(ValueError, match="common_phase_offset_rad must be finite"):
        apply_common_phase_offset(np.array([0.0]), bad_offset, bits=1)


@pytest.mark.parametrize(
    "bad_channel",
    (complex(np.nan, 0.0), complex(np.inf, 0.0), complex(-np.inf, 0.0)),
)
@pytest.mark.parametrize("bad_component", ("baseline", "ris"))
def test_coherent_common_phase_offset_rejects_nonfinite_channel(
    bad_channel: complex,
    bad_component: str,
) -> None:
    baseline = bad_channel if bad_component == "baseline" else 1.0 + 0.0j
    ris = bad_channel if bad_component == "ris" else 1.0 + 0.0j
    with pytest.raises(ValueError, match="channel components must be finite"):
        coherent_common_phase_offset(baseline, ris)


def test_coherent_focus_requires_unambiguous_enabled_ris() -> None:
    scene = create_smart_space_scene("Current")
    second = replace(scene.ris_surfaces[0], id="ris-2")
    ambiguous = replace(scene, ris_surfaces=[scene.ris_surfaces[0], second])
    with pytest.raises(ValueError, match="exactly one enabled RIS"):
        generate_coherent_target_pattern(ambiguous)
    with pytest.raises(ValueError, match="RIS id not found"):
        generate_coherent_target_pattern(scene, ris="missing")


def test_coherent_focus_rejects_disabled_ris() -> None:
    scene = create_smart_space_scene("Current")
    disabled = replace(scene.ris_surfaces[0], enabled=False)
    scene = replace(scene, ris_surfaces=[disabled])
    with pytest.raises(ValueError, match="RIS is disabled"):
        generate_coherent_target_pattern(scene, ris=disabled.id)


def test_quantized_coherent_focus_keeps_unshifted_pattern_on_tie() -> None:
    scene = create_smart_space_scene("Current")
    back_facing = replace(
        scene.ris_surfaces[0], yaw_rad=scene.ris_surfaces[0].yaw_rad + np.pi
    )
    scene = replace(scene, ris_surfaces=[back_facing])
    ideal = generate_unquantized_ris_only_focus_pattern(
        back_facing, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    unshifted = apply_common_phase_offset(ideal, 0.0, back_facing.phase_bits)

    result = generate_coherent_target_pattern(scene)
    channel = SimulationEngine().compute_channel(
        scene, ris_patterns={back_facing.id: result}
    )
    assert channel.ris_channel == 0.0j
    assert np.array_equal(result, unshifted)


@pytest.mark.parametrize("bits", (1, 2, 3, 4))
def test_quantized_coherent_focus_is_not_worse_for_supported_bits(bits: int) -> None:
    scene = create_smart_space_scene("Current")
    ris = replace(scene.ris_surfaces[0], nx=4, ny=3, phase_bits=bits)
    scene = replace(scene, ris_surfaces=[ris])
    engine = SimulationEngine()
    ideal = generate_unquantized_ris_only_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    unshifted = apply_common_phase_offset(ideal, 0.0, bits)
    coherent = generate_coherent_target_pattern(scene, engine=engine)

    unshifted_result = engine.compute_channel(scene, ris_patterns={ris.id: unshifted})
    coherent_result = engine.compute_channel(scene, ris_patterns={ris.id: coherent})
    assert coherent_result.received_power_w >= unshifted_result.received_power_w
