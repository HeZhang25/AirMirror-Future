from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

import airmirror_future.physics.ris_scattering as ris_scattering
from airmirror_future.core.types import SimulationConfig, Vec3
from airmirror_future.optimization.coherent_focus import (
    generate_coherent_target_pattern,
    generate_scene_aware_ris_only_pattern,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.coefficient_identity import (
    controller_ris_coefficient_identity,
)
from airmirror_future.simulation.ground_truth import GroundTruthModel
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_field,
    prepare_controller_link,
)


def _patterns(scene) -> list[np.ndarray]:
    ris = scene.ris_surfaces[0]
    rng = np.random.default_rng(20260908)
    if ris.phase_bits is None:
        random_pattern = rng.uniform(0.0, 2.0 * np.pi, ris.cell_count)
    else:
        states = 1 << ris.phase_bits
        random_pattern = (
            rng.integers(0, states, ris.cell_count) * (2.0 * np.pi / states)
        )
    return [
        np.zeros(ris.cell_count),
        generate_scene_aware_ris_only_pattern(scene),
        generate_coherent_target_pattern(scene),
        random_pattern,
    ]


def test_prepared_link_reuses_c_coefficients_for_multiple_patterns() -> None:
    scene = create_smart_space_scene("Current")
    engine = SimulationEngine()
    prepared = prepare_controller_link(scene, engine=engine)

    for pattern in _patterns(scene):
        reference = engine.compute_channel(
            scene, ris_patterns={prepared.ris.id: pattern}
        )
        actual = prepared.evaluate(pattern)
        assert actual.los_channel == reference.los_channel
        assert actual.wall_channel == reference.wall_channel
        np.testing.assert_allclose(
            [actual.ris_channel, actual.total_channel],
            [reference.ris_channel, reference.total_channel],
            rtol=2e-13,
            atol=1e-18,
        )
        assert actual.received_power_dbm == pytest.approx(
            reference.received_power_dbm, rel=2e-13, abs=2e-12
        )
        assert actual.snr_db == pytest.approx(reference.snr_db, rel=2e-13, abs=2e-12)


def test_prepared_link_identity_invalidates_only_coefficient_inputs() -> None:
    scene = create_smart_space_scene("Current")
    original = prepare_controller_link(scene)
    excluded = replace(
        scene,
        bandwidth_hz=scene.bandwidth_hz * 2.0,
        coverage_threshold_db=scene.coverage_threshold_db + 1.0,
        random_seed=scene.random_seed + 1,
        ris_surfaces=[
            replace(
                scene.ris_surfaces[0],
                phase_bits=3,
                reflection_efficiency=0.4,
            )
        ],
    )
    assert prepare_controller_link(excluded).coefficient_identity == original.coefficient_identity

    moved = replace(
        scene,
        receivers=[replace(scene.receiver(), position=Vec3(8.4, 4.0, 1.2))],
    )
    assert prepare_controller_link(moved).coefficient_identity != original.coefficient_identity
    changed_frequency = replace(scene, frequency_hz=scene.frequency_hz * 1.01)
    assert (
        prepare_controller_link(changed_frequency).coefficient_identity
        != original.coefficient_identity
    )


def test_prepared_link_owns_an_immutable_physics_snapshot() -> None:
    scene = create_smart_space_scene("Current")
    pattern = generate_coherent_target_pattern(scene)
    prepared = prepare_controller_link(scene)
    before = prepared.evaluate(pattern)
    scene.frequency_hz *= 1.01
    scene.ris_surfaces[0].position = Vec3(4.5, 7.9, 1.5)
    after = prepared.evaluate(pattern)
    assert after.total_channel == before.total_channel
    assert prepare_controller_link(scene).coefficient_identity != prepared.coefficient_identity


def test_prepared_link_rejects_public_snapshot_mutation_as_a_semantic_input() -> None:
    scene = create_smart_space_scene("Current")
    pattern = generate_coherent_target_pattern(scene)
    prepared = prepare_controller_link(scene)
    before = prepared.evaluate(pattern)

    prepared.scene.bandwidth_hz *= 2.0
    prepared.tx.power_w *= 3.0
    prepared.rx.noise_figure_db += 4.0
    prepared.ris.reflection_efficiency = 0.0
    prepared.ris.phase_bits = 3
    prepared.ris.position = Vec3(1.0, 1.0, 1.0)

    after = prepared.evaluate(pattern)
    assert after == before
    with pytest.raises(ValueError):
        prepared.coefficients.setflags(write=True)


def test_prepared_controller_rejects_ground_truth() -> None:
    scene = create_smart_space_scene("Current")
    with pytest.raises(ValueError, match="GroundTruthModel"):
        prepare_controller_link(scene, controller_model=GroundTruthModel())
    with pytest.raises(ValueError, match="GroundTruthModel"):
        prepare_controller_field(
            scene,
            SimulationConfig(2, 2),
            controller_model=GroundTruthModel(),
        )


def test_control_coefficient_matrix_matches_scalar_and_bounds_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    points = np.array(
        [[8.5, 4.0, 1.2], [8.0, 3.0, 1.2], [7.5, 5.0, 1.2]], dtype=float
    )
    original = ris_scattering._ris_aperture_point_contributions
    pair_counts: list[int] = []

    def record(*args: object, **kwargs: object) -> np.ndarray:
        pair_counts.append(len(np.asarray(args[1])) * len(np.asarray(args[4])))
        return original(*args, **kwargs)

    monkeypatch.setattr(ris_scattering, "_ris_aperture_point_contributions", record)
    matrix = ris_scattering.ris_control_coefficient_matrix(
        scene.transmitter(),
        points,
        scene.receiver().gain_linear,
        ris,
        scene.frequency_hz,
        max_point_sample_pairs=128,
        receiver_batch_size=3,
    )
    expected = np.stack(
        [
            ris_scattering.ris_control_coefficients(
                scene.transmitter(),
                Vec3(*point.tolist()),
                scene.receiver().gain_linear,
                ris,
                scene.frequency_hz,
            )
            for point in points
        ]
    )
    assert max(pair_counts[: len(pair_counts) - len(points)]) <= 128
    np.testing.assert_allclose(matrix, expected, rtol=2e-14, atol=1e-18)


def test_prepared_field_matches_reference_for_multiple_patterns() -> None:
    scene = create_smart_space_scene("Current")
    config = SimulationConfig(3, 2, batch_size=2)
    engine = SimulationEngine()
    prepared = prepare_controller_field(
        scene,
        config,
        engine=engine,
        coefficient_memory_budget_bytes=1024 * 1024,
        max_point_sample_pairs=512,
    )
    assert prepared.coefficients.shape == (6, scene.ris_surfaces[0].cell_count)
    assert prepared.coefficient_bytes == prepared.coefficients.nbytes
    direct_identities = []
    for y_value in prepared.y_m:
        for x_value in prepared.x_m:
            receiver = replace(
                scene.receiver(),
                position=Vec3(float(x_value), float(y_value), scene.z_eval_m),
            )
            direct_identities.append(
                controller_ris_coefficient_identity(
                    scene,
                    engine,
                    scene.transmitter(),
                    receiver,
                    scene.ris_surfaces[0],
                )
            )
    assert prepared.coefficient_identities == tuple(direct_identities)

    for pattern in _patterns(scene)[:2]:
        reference = engine.compute_field_map(
            scene, config, {prepared.ris.id: pattern}
        )
        actual = prepared.evaluate(pattern)
        np.testing.assert_allclose(
            actual.received_power_dbm,
            reference.received_power_dbm,
            rtol=2e-13,
            atol=2e-12,
        )
        np.testing.assert_allclose(
            actual.baseline_power_dbm,
            reference.baseline_power_dbm,
            rtol=2e-13,
            atol=2e-12,
        )
        np.testing.assert_allclose(actual.snr_db, reference.snr_db, rtol=2e-13, atol=2e-12)


def test_prepared_field_public_mutation_cannot_change_evaluation_semantics() -> None:
    scene = create_smart_space_scene("Current")
    config = SimulationConfig(3, 2, batch_size=2)
    pattern = generate_coherent_target_pattern(scene)
    prepared = prepare_controller_field(scene, config)
    before = prepared.evaluate(pattern)

    prepared.scene.bandwidth_hz *= 2.0
    prepared.scene.coverage_threshold_db += 100.0
    prepared.scene.room_size = Vec3(20.0, 20.0, 4.0)
    prepared.config.grid_width = 99
    prepared.config.grid_height = 88
    prepared.config.coverage_threshold_db = -100.0
    prepared.tx.power_w *= 5.0
    prepared.rx_template.noise_figure_db += 20.0
    prepared.ris.reflection_efficiency = 0.0
    prepared.ris.phase_bits = 4
    prepared.ris.position = Vec3(2.0, 2.0, 2.0)
    prepared.scene.walls[0].attenuation_db += 10.0
    prepared.scene.obstacles[0].max_corner = Vec3(9.0, 7.0, 2.0)

    after = prepared.evaluate(pattern)
    np.testing.assert_array_equal(after.received_power_dbm, before.received_power_dbm)
    np.testing.assert_array_equal(after.snr_db, before.snr_db)
    assert after.coverage_percent == before.coverage_percent
    for values in (
        prepared.coefficients,
        prepared.baseline_channels,
        prepared.x_m,
        prepared.y_m,
    ):
        with pytest.raises(ValueError):
            values.setflags(write=True)


def test_prepared_field_progress_is_exact_and_monotonic() -> None:
    scene = create_smart_space_scene("Current")
    progress: list[tuple[int, int]] = []
    prepared = prepare_controller_field(
        scene,
        SimulationConfig(3, 2, batch_size=2),
        receiver_batch_size=2,
        progress=lambda done, total: progress.append((done, total)),
    )
    assert progress == [(0, 6), (2, 6), (4, 6), (6, 6)]
    assert prepared.receiver_batch_size == 2


def test_prepared_field_progress_callback_alias_is_backward_compatible() -> None:
    scene = create_smart_space_scene("Current")
    progress: list[tuple[int, int]] = []
    prepare_controller_field(
        scene,
        SimulationConfig(2, 2, batch_size=2),
        progress_callback=lambda done, total: progress.append((done, total)),
    )
    assert progress == [(0, 4), (2, 4), (4, 4)]
    with pytest.raises(ValueError, match="only one"):
        prepare_controller_field(
            scene,
            SimulationConfig(2, 2),
            progress=lambda _done, _total: None,
            progress_callback=lambda _done, _total: None,
        )


def test_prepared_field_cancels_at_batch_boundary_without_returning_partial() -> None:
    scene = create_smart_space_scene("Current")
    progress: list[tuple[int, int]] = []
    cancelled = False

    def record(done: int, total: int) -> None:
        nonlocal cancelled
        progress.append((done, total))
        if done == 2:
            cancelled = True

    with pytest.raises(SimulationCancelled, match="cancelled"):
        prepare_controller_field(
            scene,
            SimulationConfig(3, 2, batch_size=2),
            receiver_batch_size=2,
            progress=record,
            cancel_check=lambda: cancelled,
        )
    assert progress == [(0, 6), (2, 6)]


def test_prepared_field_progress_exception_aborts_remaining_batches() -> None:
    scene = create_smart_space_scene("Current")
    progress: list[tuple[int, int]] = []

    def fail(done: int, total: int) -> None:
        progress.append((done, total))
        if done == 2:
            raise RuntimeError("GUI progress receiver failed")

    with pytest.raises(RuntimeError, match="GUI progress receiver failed"):
        prepare_controller_field(
            scene,
            SimulationConfig(3, 2, batch_size=2),
            receiver_batch_size=2,
            progress=fail,
        )
    assert progress == [(0, 6), (2, 6)]


def test_prepared_field_applies_scene_profile_modifiers() -> None:
    scene = create_smart_space_scene("Current")
    config = SimulationConfig(8, 6, batch_size=4)
    engine = SimulationEngine()
    pattern = generate_coherent_target_pattern(scene, engine=engine)
    reference = engine.compute_field_map(
        scene, config, {scene.ris_surfaces[0].id: pattern}
    )
    actual = prepare_controller_field(
        scene, config, engine=engine, receiver_batch_size=4
    ).evaluate(pattern)
    np.testing.assert_allclose(
        actual.received_power_dbm,
        reference.received_power_dbm,
        rtol=2e-13,
        atol=2e-12,
    )


def test_prepared_field_enforces_coefficient_memory_budget() -> None:
    scene = create_smart_space_scene("Future")
    with pytest.raises(MemoryError, match="exceeding budget"):
        prepare_controller_field(
            scene,
            SimulationConfig(48, 36),
            coefficient_memory_budget_bytes=80 * 1024 * 1024,
        )
