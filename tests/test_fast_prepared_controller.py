from __future__ import annotations

import numpy as np

from airmirror_future import FAST_1X1_RIS_COEFFICIENT_MODEL, SimulationEngine
from airmirror_future.core.types import SimulationConfig
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_field,
    prepare_controller_link,
)


def test_fast_prepared_link_matches_fast_engine_and_has_named_identity() -> None:
    scene = create_smart_space_scene("Future")
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    pattern = generate_coherent_target_pattern(scene, engine=engine)
    prepared = prepare_controller_link(scene, engine=engine)
    expected = engine.compute_channel(scene, ris_patterns={scene.ris_surfaces[0].id: pattern})
    actual = prepared.evaluate(pattern)
    assert actual.total_channel == expected.total_channel
    assert actual.received_power_dbm == expected.received_power_dbm
    assert actual.snr_db == expected.snr_db
    assert prepared.coefficient_model_identity == FAST_1X1_RIS_COEFFICIENT_MODEL.identity


def test_fast_prepared_field_matches_fast_engine_for_multiple_patterns() -> None:
    scene = create_smart_space_scene("Future")
    config = SimulationConfig(4, 3, batch_size=2)
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    prepared = prepare_controller_field(
        scene, config, engine=engine, receiver_batch_size=2
    )
    assert prepared.coefficient_model_identity == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    ris_id = scene.ris_surfaces[0].id
    patterns = [
        np.zeros(scene.ris_surfaces[0].cell_count),
        generate_coherent_target_pattern(scene, engine=engine),
    ]
    for pattern in patterns:
        expected = engine.compute_field_map(scene, config, {ris_id: pattern})
        actual = prepared.evaluate(pattern)
        np.testing.assert_allclose(actual.received_power_dbm, expected.received_power_dbm)
        np.testing.assert_allclose(actual.snr_db, expected.snr_db)
        np.testing.assert_allclose(actual.baseline_power_dbm, expected.baseline_power_dbm)
        assert actual.coverage_percent == expected.coverage_percent


def test_fast_prepared_field_cancellation_has_no_partial_return() -> None:
    scene = create_smart_space_scene("Future")
    progress: list[tuple[int, int]] = []
    cancel = False

    def on_progress(done: int, total: int) -> None:
        nonlocal cancel
        progress.append((done, total))
        cancel = done >= 2

    try:
        prepare_controller_field(
            scene,
            SimulationConfig(4, 3, batch_size=2),
            engine=SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL),
            receiver_batch_size=2,
            progress=on_progress,
            cancel_check=lambda: cancel,
        )
    except SimulationCancelled:
        pass
    else:
        raise AssertionError("cancelled fast build returned a prepared object")
    assert progress == [(0, 12), (2, 12)]
