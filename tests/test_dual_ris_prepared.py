from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from airmirror_future import FAST_1X1_RIS_COEFFICIENT_MODEL, SimulationEngine
from airmirror_future.core.types import SimulationConfig, Vec3
from airmirror_future.optimization.dual_ris_focus import (
    generate_dual_ris_coordinated_patterns,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled
from airmirror_future.simulation.prepared_dual_ris import (
    prepare_dual_ris_controller_field,
    prepare_dual_ris_controller_link,
)


def _two_ris_scene():
    scene = create_smart_space_scene("Future")
    first = scene.ris_surfaces[0]
    second = replace(
        first,
        id="ris-2",
        position=replace(first.position, x=4.0, y=7.5),
        yaw_rad=first.yaw_rad + np.pi,
    )
    return replace(scene, ris_surfaces=[first, second])


def test_dual_prepared_link_is_coherent_and_matches_engine() -> None:
    scene = _two_ris_scene()
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    prepared = prepare_dual_ris_controller_link(scene, engine=engine)
    focused = generate_dual_ris_coordinated_patterns(scene, engine=engine)
    actual = prepared.evaluate(focused.patterns)
    expected = engine.compute_channel(scene, ris_patterns=focused.patterns)
    assert prepared.ris_ids == ("ris-1", "ris-2")
    assert actual.total_channel == pytest.approx(expected.total_channel, rel=2e-13, abs=1e-18)
    assert actual.ris_channel == pytest.approx(expected.ris_channel, rel=2e-13, abs=1e-18)
    assert actual.received_power_w == pytest.approx(expected.received_power_w, rel=2e-13, abs=1e-18)
    assert actual.ris_channel == sum(
        detail["channel"] for detail in actual.path_details
    )
    assert prepared.coefficient_model_identity == FAST_1X1_RIS_COEFFICIENT_MODEL.identity


def test_dual_prepared_link_single_and_disabled_degenerate() -> None:
    scene = _two_ris_scene()
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    one = prepare_dual_ris_controller_link(scene, engine=engine, ris_ids=("ris-1",))
    pattern = generate_dual_ris_coordinated_patterns(scene, engine=engine, ris_ids=("ris-1",)).patterns
    expected = engine.compute_channel(scene, ris_patterns=pattern)
    assert one.evaluate(pattern).total_channel == pytest.approx(expected.total_channel)

    disabled_scene = replace(
        scene,
        ris_surfaces=[scene.ris_surfaces[0], replace(scene.ris_surfaces[1], enabled=False)],
    )
    disabled = prepare_dual_ris_controller_link(
        disabled_scene, engine=engine, ris_ids=("ris-1", "ris-2")
    )
    assert disabled.ris_ids == ("ris-1", "ris-2")
    assert disabled.evaluate(pattern).total_channel == pytest.approx(
        engine.compute_channel(disabled_scene, ris_patterns=pattern).total_channel
    )


def test_dual_prepared_field_matches_engine_and_cancel_is_bounded() -> None:
    scene = _two_ris_scene()
    config = SimulationConfig(3, 2, batch_size=1)
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    prepared = prepare_dual_ris_controller_field(
        scene, config, engine=engine, receiver_batch_size=1
    )
    patterns = generate_dual_ris_coordinated_patterns(scene, engine=engine).patterns
    expected = engine.compute_field_map(scene, config, patterns)
    actual = prepared.evaluate(patterns)
    np.testing.assert_allclose(actual.received_power_dbm, expected.received_power_dbm, rtol=2e-13, atol=2e-12)
    np.testing.assert_allclose(actual.baseline_power_dbm, expected.baseline_power_dbm, rtol=2e-13, atol=2e-12)
    assert prepared.coefficient_bytes == sum(value.nbytes for value in prepared.coefficients.values())

    progress: list[tuple[int, int]] = []
    with pytest.raises(SimulationCancelled):
        prepare_dual_ris_controller_field(
            scene,
            config,
            engine=engine,
            receiver_batch_size=1,
            progress=lambda done, total: progress.append((done, total)),
            cancel_check=lambda: bool(progress and progress[-1][0] >= 1),
        )
    assert progress == [(0, 6), (1, 6)]


def test_dual_prepared_field_exposes_two_independent_matrices_and_budget() -> None:
    scene = _two_ris_scene()
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    prepared = prepare_dual_ris_controller_field(
        scene,
        SimulationConfig(2, 2),
        engine=engine,
        coefficient_memory_budget_bytes=2 * 2 * 2 * scene.ris_surfaces[0].cell_count * 16,
    )
    assert set(prepared.coefficients_by_ris) == {"ris-1", "ris-2"}
    assert all(value.shape == (4, scene.ris_surfaces[0].cell_count) for value in prepared.coefficients_by_ris.values())
    with pytest.raises(MemoryError, match="dual RIS coefficient matrices"):
        prepare_dual_ris_controller_field(
            scene,
            SimulationConfig(2, 2),
            engine=engine,
            coefficient_memory_budget_bytes=1,
        )
