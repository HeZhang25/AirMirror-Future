from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
import subprocess
import sys

import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.optimization.coherent_focus import (
    _coefficient_phase_conjugate,
    generate_coherent_target_pattern,
    generate_scene_aware_ris_only_pattern,
)
from airmirror_future.physics.ris_scattering import ris_control_coefficients
from airmirror_future.ris.quadrature import midpoint_quadrature
from airmirror_future.ris.quadrature import QuadratureSpec
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.coefficient_identity import (
    controller_ris_coefficient_identity,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel
from airmirror_future.simulation.profiles import PropagationModifier
from airmirror_future.experiments.fnd_qa_ap_01 import _scene_for_case


def _scalar_oracle(scene, ris) -> np.ndarray:
    tx = scene.transmitter()
    rx = scene.receiver()
    spec = midpoint_quadrature(ris, 8, 8)
    result = np.zeros(ris.cell_count, complex)
    k = 2.0 * np.pi * scene.frequency_hz / 299_792_458.0
    for point, parent, weight in zip(
        spec.sample_coordinates, spec.parent_control_index, spec.weights, strict=True
    ):
        tx_vector = tx.position.as_array() - point
        d1 = np.linalg.norm(tx_vector)
        incoming = tx_vector / d1
        out_vector = rx.position.as_array() - point
        d2 = np.linalg.norm(out_vector)
        outgoing = out_vector / d2
        direction = max(float(incoming @ ris.normal), 0.0) * max(
            float(outgoing @ ris.normal), 0.0
        )
        amplitude = (
            np.sqrt(tx.gain_linear * rx.gain_linear)
            * weight * ris.cell_area_m2
            * direction ** (ris.direction_exponent / 2.0)
            / (4.0 * np.pi * d1 * d2)
        )
        result[parent] += amplitude * np.exp(-1j * k * (d1 + d2))
    return result


def test_fnd_t21_shared_m8_coefficient_matches_independent_scalar_oracle() -> None:
    scene = create_smart_space_scene("Current")
    scene = replace(scene, walls=[], obstacles=[])
    ris = scene.ris_surfaces[0]
    production = ris_control_coefficients(
        scene.transmitter(), scene.receiver().position, scene.receiver().gain_linear,
        ris, scene.frequency_hz,
    )
    oracle = _scalar_oracle(scene, ris)
    np.testing.assert_allclose(production, oracle, rtol=2e-14, atol=1e-18)


def test_fnd_t21_scene_aware_commands_are_legal_and_recompose_engine() -> None:
    for generation in ("Current", "Advanced", "Future"):
        scene = create_smart_space_scene(generation)
        engine = SimulationEngine()
        ris = scene.ris_surfaces[0]
        coefficients, _ = engine.controller_focus_terms(scene, ris=ris)
        pattern = generate_scene_aware_ris_only_pattern(scene, engine=engine)
        validate_commanded_pattern(ris, pattern)
        gamma = np.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern)
        channel = engine.compute_channel(scene, ris_patterns={ris.id: pattern})
        assert channel.ris_channel == np.dot(coefficients, gamma)


def test_fnd_t22_coherent_uses_shared_controller_terms_and_no_ground_truth() -> None:
    scene = create_smart_space_scene("Advanced")
    engine = SimulationEngine()
    pattern = generate_coherent_target_pattern(scene, engine=engine)
    validate_commanded_pattern(scene.ris_surfaces[0], pattern)
    assert np.array_equal(pattern, generate_coherent_target_pattern(scene, engine=engine))
    try:
        generate_coherent_target_pattern(
            scene,
            GroundTruthModel(seed=9, position_error_sigma_m=0.1,
                             ris_phase_error_sigma_rad=0.4),
            engine=engine,
        )
    except ValueError as error:
        assert "GroundTruthModel" in str(error)
    else:
        raise AssertionError("Coherent Focus accepted GroundTruthModel")


def test_coefficient_identity_mutation_and_exclusion_contract() -> None:
    scene = create_smart_space_scene("Current")
    engine = SimulationEngine()
    tx, rx, ris = scene.transmitter(), scene.receiver(), scene.ris_surfaces[0]
    identity = controller_ris_coefficient_identity(scene, engine, tx, rx, ris)
    excluded = replace(scene, bandwidth_hz=scene.bandwidth_hz * 2,
                       coverage_threshold_db=scene.coverage_threshold_db + 1,
                       random_seed=scene.random_seed + 1,
                       transmitters=[replace(tx, power_w=tx.power_w * 2)],
                       ris_surfaces=[replace(ris, phase_bits=3,
                                             reflection_efficiency=0.2)])
    assert controller_ris_coefficient_identity(
        excluded, engine, excluded.transmitter(), excluded.receiver(), excluded.ris_surfaces[0]
    ) == identity
    changed = replace(scene, frequency_hz=scene.frequency_hz * 1.01)
    assert controller_ris_coefficient_identity(
        changed, engine, changed.transmitter(), changed.receiver(), changed.ris_surfaces[0]
    ) != identity
    unrelated_wall = replace(
        scene,
        walls=scene.walls + [replace(scene.walls[0], id="unrelated-wall",
                                     start=replace(scene.walls[0].start, x=0.1, y=0.1),
                                     end=replace(scene.walls[0].end, x=0.2, y=0.1))],
    )
    assert controller_ris_coefficient_identity(
        unrelated_wall, engine, unrelated_wall.transmitter(), unrelated_wall.receiver(),
        unrelated_wall.ris_surfaces[0]
    ) == identity


@dataclass(frozen=True)
class _RoomSizeProfile:
    profile_id: str = "room_size_profile"
    profile_version: str = "1"
    canonical_parameters: tuple = (("mode", "room_size_x"),)

    def environment_modifier(self, *, scene, context):
        # Legitimate custom Profile dependency used to guard conservative
        # identity fallback: the scene collection is part of the input.
        return PropagationModifier(complex(1.0 + 1.0e-4 * scene.room_size.x, 0.0))


def test_custom_profile_scene_dependency_invalidates_identity() -> None:
    scene = create_smart_space_scene("Current")
    tx, rx, ris = scene.transmitter(), scene.receiver(), scene.ris_surfaces[0]
    from dataclasses import replace
    engine = SimulationEngine(_RoomSizeProfile())
    first = controller_ris_coefficient_identity(scene, engine, tx, rx, ris)
    changed = replace(scene, room_size=replace(scene.room_size, x=scene.room_size.x + 0.5))
    second = controller_ris_coefficient_identity(
        changed, engine, changed.transmitter(), changed.receiver(), changed.ris_surfaces[0]
    )
    assert first != second


def test_custom_quadrature_array_mutation_invalidates_identity() -> None:
    scene = create_smart_space_scene("Current")
    engine = SimulationEngine()
    tx, rx, ris = scene.transmitter(), scene.receiver(), scene.ris_surfaces[0]
    spec = midpoint_quadrature(ris, 2, 2)
    coordinates = np.array(spec.sample_coordinates, copy=True)
    coordinates[0, 0] += 1.0e-5
    changed = QuadratureSpec(
        spec.rule, spec.order_x, spec.order_y, coordinates,
        np.array(spec.weights, copy=True),
        np.array(spec.parent_control_index, copy=True),
    )
    kwargs = {"quadrature_policy_id": "test_quadrature", "quadrature_policy_version": "1"}
    assert controller_ris_coefficient_identity(
        scene, engine, tx, rx, ris, quadrature_spec=spec, **kwargs
    ) != controller_ris_coefficient_identity(
        scene, engine, tx, rx, ris, quadrature_spec=changed, **kwargs
    )


def test_fnd_t21_matrix_covers_three_generations_and_four_geometries() -> None:
    engine = SimulationEngine()
    for generation in ("Current", "Advanced", "Future"):
        for geometry in ("default_target", "near_field", "oblique_incidence", "off_focus_receiver"):
            scene, focus, evaluation = _scene_for_case(generation, geometry)
            focus_scene = replace(scene, receivers=[focus])
            ris = scene.ris_surfaces[0]
            coefficients, _ = engine.controller_focus_terms(focus_scene, ris=ris)
            pattern = generate_scene_aware_ris_only_pattern(focus_scene, engine=engine)
            gamma = np.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern)
            result = engine.compute_channel(focus_scene, ris_patterns={ris.id: pattern})
            assert result.ris_channel == np.dot(coefficients, gamma)
            identity = controller_ris_coefficient_identity(
                focus_scene, engine, focus_scene.transmitter(), focus, ris
            )
            assert identity.startswith("sha256:")


def test_fnd_t22_continuous_and_finite_bit_objectives_are_separate() -> None:
    for generation in ("Current", "Advanced", "Future"):
        for geometry in ("default_target", "near_field", "oblique_incidence", "off_focus_receiver"):
            scene, focus, evaluation = _scene_for_case(generation, geometry)
            focus_scene = replace(scene, receivers=[focus])
            engine = SimulationEngine()
            ris = focus_scene.ris_surfaces[0]
            pattern = generate_scene_aware_ris_only_pattern(focus_scene, engine=engine)
            validate_commanded_pattern(ris, pattern)
            if ris.phase_bits is None:
                assert pattern.shape == (ris.cell_count,)
            else:
                from airmirror_future.ris.phase import common_phase_offset_candidates
                base = _coefficient_phase_conjugate(engine.controller_focus_terms(focus_scene, ris=ris)[0])
                assert common_phase_offset_candidates(base, ris.phase_bits)[0] == 0.0
def test_coefficient_identity_is_cross_process_stable() -> None:
    script = (
        "from airmirror_future.scenarios.smart_space import create_smart_space_scene as c;"
        "from airmirror_future.simulation.engine import SimulationEngine as E;"
        "from airmirror_future.simulation.coefficient_identity import controller_ris_coefficient_identity as i;"
        "s=c('Current');print(i(s,E(),s.transmitter(),s.receiver(),s.ris_surfaces[0]))"
    )
    values = [subprocess.check_output([sys.executable, "-c", script], text=True).strip()
              for _ in range(2)]
    assert values[0] == values[1]


def test_zero_and_nonfinite_coefficient_contract() -> None:
    phases = _coefficient_phase_conjugate(np.array([0.0j, 1.0j, -1.0 + 0.0j]))
    assert phases[0] == 0.0
    np.testing.assert_allclose(phases[1:], [1.5 * np.pi, np.pi], rtol=0.0, atol=0.0)
    for bad in (complex(np.nan, 0.0), complex(0.0, np.inf)):
        try:
            _coefficient_phase_conjugate(np.array([bad]))
        except ValueError as error:
            assert "finite" in str(error)
        else:
            raise AssertionError("non-finite coefficient was accepted")


def test_fnd_t22_coherent_matches_controller_objective_candidate_oracle() -> None:
    scene = create_smart_space_scene("Current")
    engine = SimulationEngine()
    ris = scene.ris_surfaces[0]
    coefficients, baseline = engine.controller_focus_terms(scene, ris=ris)
    base = _coefficient_phase_conjugate(coefficients)
    from airmirror_future.ris.phase import apply_common_phase_offset, common_phase_offset_candidates

    patterns = [apply_common_phase_offset(base, float(offset), ris.phase_bits)
                for offset in common_phase_offset_candidates(base, ris.phase_bits)]
    powers = [scene.transmitter().power_w * abs(
        baseline + np.dot(coefficients, np.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern))
    ) ** 2 for pattern in patterns]
    best = 0
    eps = np.finfo(float).eps
    for index in range(1, len(powers)):
        tolerance = 8.0 * eps * max(abs(powers[index]), abs(powers[best]), np.finfo(float).tiny)
        if powers[index] > powers[best] + tolerance:
            best = index
    actual = generate_coherent_target_pattern(scene, engine=engine)
    assert np.array_equal(actual, patterns[best])
