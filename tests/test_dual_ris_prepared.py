from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from airmirror_future import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    SimulationEngine,
)
from airmirror_future.core.types import SimulationConfig
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_dual_ris_field,
    prepare_controller_dual_ris_link,
)


def _scene_two_ris():
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
    scene = _scene_two_ris()
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    prepared = prepare_controller_dual_ris_link(scene, engine=engine)
    patterns = {ris.id: np.zeros(ris.cell_count) for ris in prepared.ris}
    actual = prepared.evaluate(patterns)
    expected = engine.compute_channel(scene, ris_patterns=patterns)
    assert actual.total_channel == expected.total_channel
    assert actual.ris_channel == expected.ris_channel
    assert actual.los_channel == expected.los_channel
    assert actual.wall_channel == expected.wall_channel
    assert prepared.coefficient_model_identity == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    assert len(prepared.coefficient_identities) == 2


def test_dual_prepared_field_matches_engine_and_single_disabled_degrades() -> None:
    scene = _scene_two_ris()
    config = SimulationConfig(3, 2, batch_size=2)
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    prepared = prepare_controller_dual_ris_field(scene, config, engine=engine, receiver_batch_size=2)
    patterns = {ris.id: np.zeros(ris.cell_count) for ris in prepared.ris}
    actual = prepared.evaluate(patterns)
    expected = engine.compute_field_map(scene, config, ris_patterns=patterns)
    np.testing.assert_allclose(actual.received_power_dbm, expected.received_power_dbm)
    disabled_scene = replace(scene, ris_surfaces=[scene.ris_surfaces[0], replace(scene.ris_surfaces[1], enabled=False)])
    one = prepare_controller_dual_ris_field(disabled_scene, config, engine=engine)
    one_result = one.evaluate({scene.ris_surfaces[0].id: patterns[scene.ris_surfaces[0].id]})
    single_expected = engine.compute_field_map(disabled_scene, config, ris_patterns=patterns)
    np.testing.assert_allclose(one_result.received_power_dbm, single_expected.received_power_dbm)


def test_dual_prepared_snapshot_progress_cancel_and_identity() -> None:
    scene = _scene_two_ris()
    config = SimulationConfig(4, 3, batch_size=2)
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    progress: list[tuple[int, int]] = []
    cancelled = False

    def on_progress(done: int, total: int) -> None:
        nonlocal cancelled
        progress.append((done, total))
        cancelled = done >= 2

    with pytest.raises(SimulationCancelled):
        prepare_controller_dual_ris_field(
            scene,
            config,
            engine=engine,
            receiver_batch_size=2,
            progress=on_progress,
            cancel_check=lambda: cancelled,
        )
    assert progress == [(0, 12), (2, 12)]
    prepared = prepare_controller_dual_ris_link(scene, engine=engine)
    before = prepared.evaluate({})
    scene.ris_surfaces[0].reflection_efficiency = 0.01
    scene.bandwidth_hz = 1.0
    after = prepared.evaluate({})
    assert after.total_channel == before.total_channel
    with pytest.raises(ValueError, match="prepared RIS id"):
        prepared.evaluate({"unknown": np.zeros(1)})
