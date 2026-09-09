from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from airmirror_future import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    SimulationEngine,
    evaluate_dual_ris_command,
    generate_coherent_target_pattern,
    generate_dual_ris_coordinated_patterns,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.ground_truth import GroundTruthModel


def _two_ris_scene():
    scene = create_smart_space_scene("Current")
    first = scene.ris_surfaces[0]
    second = replace(
        first,
        id="ris-2",
        position=replace(first.position, x=4.0, y=7.5),
        yaw_rad=first.yaw_rad + np.pi,
    )
    return replace(scene, ris_surfaces=[first, second])


def test_dual_ris_continuous_coordinated_sum_matches_engine() -> None:
    scene = _two_ris_scene()
    scene = replace(scene, ris_surfaces=[replace(r, phase_bits=None) for r in scene.ris_surfaces])
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    focused = generate_dual_ris_coordinated_patterns(scene, engine=engine)
    result = evaluate_dual_ris_command(scene, focused.patterns, engine=engine)

    assert set(focused.patterns) == {"ris-1", "ris-2"}
    assert focused.total_channel == result.total_channel
    assert result.total_channel == result.los_channel + result.wall_channel + result.ris_channel
    assert result.ris_channel == sum(focused.ris_channels.values())
    assert focused.rounds == 1
    assert focused.converged


def test_dual_ris_single_surface_degenerates_to_single_focus() -> None:
    scene = create_smart_space_scene("Current")
    engine = SimulationEngine()
    dual = generate_dual_ris_coordinated_patterns(scene, engine=engine, ris_ids=("ris-1",))
    single = generate_coherent_target_pattern(scene, engine=engine, ris=scene.ris_surfaces[0])
    assert np.array_equal(dual.patterns["ris-1"], single)
    assert dual.rounds <= 4


def test_dual_ris_skips_disabled_surface_and_supports_mixed_generations() -> None:
    scene = _two_ris_scene()
    disabled = replace(scene.ris_surfaces[1], enabled=False, generation="Future", phase_bits=None)
    scene = replace(scene, ris_surfaces=[replace(scene.ris_surfaces[0], generation="Advanced"), disabled])
    result = generate_dual_ris_coordinated_patterns(scene, ris_ids=("ris-1", "ris-2"), engine=SimulationEngine())
    assert set(result.patterns) == {"ris-1"}
    assert set(result.ris_channels) == set(result.patterns)


def test_dual_ris_mixed_continuous_and_finite_is_legal() -> None:
    scene = _two_ris_scene()
    mixed = [
        replace(scene.ris_surfaces[0], phase_bits=None, generation="Future"),
        replace(scene.ris_surfaces[1], phase_bits=2, generation="Current"),
    ]
    scene = replace(scene, ris_surfaces=mixed)
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    result = generate_dual_ris_coordinated_patterns(scene, engine=engine, max_rounds=3)
    assert set(result.patterns) == {"ris-1", "ris-2"}
    assert result.patterns["ris-1"].shape == (mixed[0].cell_count,)
    assert np.all(np.isfinite(result.patterns["ris-1"]))
    assert 1 <= result.rounds <= 3


def test_dual_ris_finite_coordination_is_bounded_and_controller_only() -> None:
    scene = _two_ris_scene()
    engine = SimulationEngine()
    result = generate_dual_ris_coordinated_patterns(scene, engine=engine, max_rounds=2)
    assert 1 <= result.rounds <= 2
    assert set(result.patterns) == {"ris-1", "ris-2"}
    assert np.isfinite(result.objective_power_w)
    with pytest.raises(ValueError, match="ControllerModel"):
        generate_dual_ris_coordinated_patterns(scene, GroundTruthModel(seed=7), engine=engine)
    with pytest.raises(ValueError, match="zero, one, or two"):
        evaluate_dual_ris_command(
            scene,
            {
                "ris-1": result.patterns["ris-1"],
                "ris-2": result.patterns["ris-2"],
                "extra": np.zeros(1),
            },
            engine=engine,
        )
