from dataclasses import replace
import json
import subprocess
import sys

import numpy as np
import pytest

import airmirror_future.physics.ris_scattering as ris_scattering
import airmirror_future.simulation.engine as engine_module
from airmirror_future.core.types import RISSurface, Scene, SimulationConfig, Vec3
from airmirror_future.ris.quadrature import QuadratureSpec
from airmirror_future.ris.phase import generate_ris_only_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel


def _focus(scene: Scene) -> tuple[RISSurface, np.ndarray]:
    ris = scene.ris_surfaces[0]
    pattern = generate_ris_only_focus_pattern(
        ris,
        scene.transmitter(),
        scene.receiver(),
        scene.frequency_hz,
    )
    return ris, pattern


def test_production_path_builds_signed_midpoint_eight_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    ris, pattern = _focus(scene)
    original = ris_scattering.midpoint_quadrature
    calls: list[tuple[int, int, int]] = []

    def record_midpoint(
        surface: RISSurface,
        order_x: int = 1,
        order_y: int | None = None,
    ) -> QuadratureSpec:
        spec = original(surface, order_x=order_x, order_y=order_y)
        calls.append((order_x, spec.order_y, spec.sample_count))
        return spec

    monkeypatch.setattr(ris_scattering, "midpoint_quadrature", record_midpoint)
    result = SimulationEngine().compute_channel(
        scene,
        ris_patterns={ris.id: pattern},
    )

    assert calls == [(8, 8, ris.cell_count * 64)]
    assert np.isfinite(result.ris_channel.real)
    assert np.isfinite(result.ris_channel.imag)


def test_production_quadrature_identity_is_stable_across_processes() -> None:
    script = (
        "import json; "
        "from airmirror_future.physics.ris_scattering import "
        "PRODUCTION_QUADRATURE_POLICY_ID as i, "
        "PRODUCTION_QUADRATURE_POLICY_VERSION as v; "
        "print(json.dumps([i, v], separators=(',', ':')))"
    )
    outputs = [
        subprocess.check_output([sys.executable, "-c", script], text=True).strip()
        for _ in range(2)
    ]

    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0]) == ["midpoint_8x8_per_control_patch", "1"]


def test_production_m8_preserves_control_and_pattern_mapping() -> None:
    scene = create_smart_space_scene("Current")
    ris, pattern = _focus(scene)
    original_pattern = pattern.copy()
    spec = ris_scattering._production_quadrature_spec(ris)

    assert spec.control_count == ris.cell_count == ris.nx * ris.ny
    assert ris_scattering.PRODUCTION_QUADRATURE_POLICY_ID == (
        "midpoint_8x8_per_control_patch"
    )
    assert ris_scattering.PRODUCTION_QUADRATURE_POLICY_VERSION == "1"
    assert spec.rule == "midpoint"
    assert (spec.order_x, spec.order_y) == (8, 8)
    np.testing.assert_array_equal(
        spec.weights,
        np.full(spec.sample_count, 1.0 / 64.0),
    )
    np.testing.assert_allclose(
        spec.weights.reshape(ris.cell_count, 64).sum(axis=1),
        np.ones(ris.cell_count),
        rtol=0.0,
        atol=0.0,
    )
    assert pattern.shape == (ris.cell_count,)
    assert np.array_equal(
        spec.parent_control_index,
        np.repeat(np.arange(ris.cell_count), 64),
    )
    assert np.array_equal(
        spec.inherited_commands(pattern),
        pattern[spec.parent_control_index],
    )

    first_parent = spec.sample_coordinates[:64]
    tangent = np.array((-np.sin(ris.yaw_rad), np.cos(ris.yaw_rad), 0.0))
    local_x = first_parent @ tangent
    local_y = first_parent[:, 2]
    assert np.all(np.diff(local_x.reshape(8, 8), axis=1) > 0.0)
    assert np.all(np.diff(local_y.reshape(8, 8), axis=0) > 0.0)
    np.testing.assert_allclose(np.diff(local_y.reshape(8, 8), axis=1), 0.0)

    SimulationEngine().compute_channel(scene, ris_patterns={ris.id: pattern})
    assert np.array_equal(pattern, original_pattern)


def test_field_map_reuses_one_m8_sample_table_per_ris_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    ris, pattern = _focus(scene)
    original = engine_module._production_quadrature_spec
    calls: list[str] = []

    def record_spec(surface: RISSurface) -> QuadratureSpec:
        calls.append(surface.id)
        return original(surface)

    monkeypatch.setattr(engine_module, "_production_quadrature_spec", record_spec)
    result = SimulationEngine().compute_field_map(
        scene,
        SimulationConfig(2, 2),
        {ris.id: pattern},
    )

    assert calls == [ris.id]
    assert np.all(np.isfinite(result.received_power_dbm))
    assert np.all(np.isfinite(result.snr_db))


def test_field_map_per_call_reuse_preserves_ground_truth_geometry() -> None:
    scene = create_smart_space_scene("Current")
    ris, pattern = _focus(scene)
    truth = GroundTruthModel(
        seed=73,
        position_error_sigma_m=0.02,
        ris_phase_error_sigma_rad=0.1,
        ris_efficiency_sigma_fraction=0.03,
    )
    engine = SimulationEngine()
    field = engine.compute_field_map(
        scene,
        SimulationConfig(2, 2),
        {ris.id: pattern},
        model=truth,
    )

    for row, y_value in enumerate(field.y_m):
        for column, x_value in enumerate(field.x_m):
            receiver = replace(
                scene.receiver(),
                position=Vec3(float(x_value), float(y_value), scene.z_eval_m),
            )
            channel = engine.compute_channel(
                scene,
                rx=receiver,
                ris_patterns={ris.id: pattern},
                model=truth,
            )
            assert field.received_power_dbm[row, column] == pytest.approx(
                channel.received_power_dbm,
                rel=1e-13,
                abs=1e-13,
            )


def test_production_points_path_bounds_intermediate_pair_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    ris, pattern = _focus(scene)
    receiver_points = np.repeat(
        scene.receiver().position.as_array()[None, :],
        100,
        axis=0,
    )
    receiver_points[:, 0] += np.linspace(-0.1, 0.1, len(receiver_points))
    original = ris_scattering._ris_aperture_point_contributions
    pair_counts: list[int] = []

    def record_pairs(*args: object, **kwargs: object) -> np.ndarray:
        points = np.asarray(args[1])
        samples = np.asarray(args[4])
        pair_counts.append(len(points) * len(samples))
        return original(*args, **kwargs)

    monkeypatch.setattr(
        ris_scattering,
        "_ris_aperture_point_contributions",
        record_pairs,
    )
    values = ris_scattering.ris_channel_for_points(
        scene.transmitter(),
        receiver_points,
        scene.receiver().gain_linear,
        ris,
        pattern,
        scene.frequency_hz,
    )

    assert len(pair_counts) > 1
    assert max(pair_counts) <= ris_scattering._MAX_POINT_SAMPLE_PAIRS
    assert np.all(np.isfinite(values.real))
    assert np.all(np.isfinite(values.imag))


@pytest.mark.parametrize("generation", ("Current", "Advanced", "Future"))
def test_production_m8_generation_channel_smoke_is_finite(generation: str) -> None:
    scene = create_smart_space_scene(generation)
    ris, pattern = _focus(scene)
    result = SimulationEngine().compute_channel(
        scene,
        ris_patterns={ris.id: pattern},
    )

    assert np.isfinite(result.received_power_dbm)
    assert np.isfinite(result.snr_db)
    assert np.isfinite(result.ris_channel.real)
    assert np.isfinite(result.ris_channel.imag)
