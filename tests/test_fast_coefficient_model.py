from __future__ import annotations

import numpy as np

from airmirror_future import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    PRODUCTION_RIS_COEFFICIENT_MODEL,
    SimulationEngine,
)
from airmirror_future.optimization.coherent_focus import (
    generate_coherent_target_pattern,
)
from airmirror_future.physics.ris_scattering import ris_control_coefficients
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.coefficient_identity import (
    controller_ris_coefficient_identity,
)


def test_fast_1x1_uses_patch_centres_and_full_patch_area() -> None:
    scene = create_smart_space_scene("Current")
    tx = scene.transmitter()
    rx = scene.receiver()
    ris = scene.ris_surfaces[0]
    spec = FAST_1X1_RIS_COEFFICIENT_MODEL.quadrature_spec(ris)

    assert spec.order_x == spec.order_y == 1
    assert np.array_equal(spec.sample_coordinates, ris.cell_centers())
    assert np.array_equal(spec.parent_control_index, np.arange(ris.cell_count))
    assert np.array_equal(spec.weights, np.ones(ris.cell_count))

    coefficients = ris_control_coefficients(
        tx,
        rx.position,
        rx.gain_linear,
        ris,
        scene.frequency_hz,
        coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL,
    )
    point = ris.cell_centers()[0]
    tx_vector = tx.position.as_array() - point
    rx_vector = rx.position.as_array() - point
    d1 = np.linalg.norm(tx_vector)
    d2 = np.linalg.norm(rx_vector)
    direction = max(float((tx_vector / d1) @ ris.normal), 0.0) * max(
        float((rx_vector / d2) @ ris.normal), 0.0
    )
    k = 2.0 * np.pi * scene.frequency_hz / 299_792_458.0
    expected = (
        np.sqrt(tx.gain_linear * rx.gain_linear)
        * ris.cell_area_m2
        * direction ** (ris.direction_exponent / 2.0)
        / (4.0 * np.pi * d1 * d2)
        * np.exp(-1j * k * (d1 + d2))
    )
    assert coefficients[0] == expected


def test_fast_engine_and_focus_share_exact_1x1_coefficients() -> None:
    scene = create_smart_space_scene("Future")
    ris = scene.ris_surfaces[0]
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)

    coefficients, baseline = engine.controller_focus_terms(scene, ris=ris)
    pattern = generate_coherent_target_pattern(scene, engine=engine, ris=ris)
    result = engine.compute_channel(scene, ris_patterns={ris.id: pattern})
    gamma = np.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern)

    assert result.ris_channel == np.dot(coefficients, gamma)
    assert result.total_channel == baseline + result.ris_channel
    detail = next(item for item in result.path_details if item["kind"] == "RIS")
    assert detail["coefficient_model_id"] == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    assert detail["quadrature_policy_id"] == FAST_1X1_RIS_COEFFICIENT_MODEL.quadrature_identity


def test_production_m8_default_is_unchanged_and_fast_identity_is_distinct() -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    default_engine = SimulationEngine()
    explicit_m8_engine = SimulationEngine(
        coefficient_model=PRODUCTION_RIS_COEFFICIENT_MODEL
    )
    pattern = generate_coherent_target_pattern(scene, engine=default_engine)

    default = default_engine.compute_channel(scene, ris_patterns={ris.id: pattern})
    explicit = explicit_m8_engine.compute_channel(
        scene, ris_patterns={ris.id: pattern}
    )
    assert default == explicit

    tx, rx = scene.transmitter(), scene.receiver()
    production_identity = controller_ris_coefficient_identity(
        scene, default_engine, tx, rx, ris
    )
    fast_identity = controller_ris_coefficient_identity(
        scene,
        SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL),
        tx,
        rx,
        ris,
    )
    assert fast_identity != production_identity
