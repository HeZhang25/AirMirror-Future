from pathlib import Path

import numpy as np
import pytest

from airmirror_future.core.types import Scene, SimulationConfig
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel


def test_scene_json_round_trip(tmp_path: Path) -> None:
    scene = create_smart_space_scene()
    destination = tmp_path / "scene.json"
    scene.save(destination)
    loaded = Scene.load(destination)
    assert loaded.name == scene.name
    assert loaded.room_size == scene.room_size
    assert loaded.ris_surfaces[0].cell_count == 64


def test_fixed_ground_truth_seed_is_reproducible() -> None:
    scene = create_smart_space_scene()
    ris = scene.ris_surfaces[0]
    pattern = generate_focus_pattern(ris, scene.transmitter(), scene.receiver(), scene.frequency_hz)
    truth1 = GroundTruthModel(seed=42, ris_phase_error_sigma_rad=0.25, position_error_sigma_m=0.01)
    truth2 = GroundTruthModel(seed=42, ris_phase_error_sigma_rad=0.25, position_error_sigma_m=0.01)
    engine = SimulationEngine()
    first = engine.compute_channel(scene, ris_patterns={ris.id: pattern}, model=truth1)
    second = engine.compute_channel(scene, ris_patterns={ris.id: pattern}, model=truth2)
    assert first.total_channel == second.total_channel


def test_smart_space_integration_returns_finite_metrics() -> None:
    scene = create_smart_space_scene()
    ris = scene.ris_surfaces[0]
    pattern = generate_focus_pattern(ris, scene.transmitter(), scene.receiver(), scene.frequency_hz)
    engine = SimulationEngine()
    base = engine.compute_channel(scene)
    result = engine.compute_channel(scene, ris_patterns={ris.id: pattern})
    assert np.isfinite(result.received_power_dbm)
    assert np.isfinite(result.snr_db)
    assert result.received_power_dbm != base.received_power_dbm


def test_small_field_map_has_consistent_shape_and_coverage() -> None:
    scene = create_smart_space_scene()
    ris = scene.ris_surfaces[0]
    pattern = generate_focus_pattern(ris, scene.transmitter(), scene.receiver(), scene.frequency_hz)
    result = SimulationEngine().compute_field_map(
        scene, SimulationConfig(10, 8), {ris.id: pattern}
    )
    assert result.received_power_dbm.shape == (8, 10)
    assert 0.0 <= result.coverage_percent <= 100.0
    assert result.coverage_percent + result.dead_zone_percent == pytest.approx(100.0)

