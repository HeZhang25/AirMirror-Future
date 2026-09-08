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
from airmirror_future.simulation.engine import SimulationEngine
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
