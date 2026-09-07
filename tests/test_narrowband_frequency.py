from __future__ import annotations

from dataclasses import replace
import json

import numpy as np

from airmirror_future.core.types import Scene
from airmirror_future.experiments.provenance import (
    CHANNEL_FREQUENCY_MODEL_ID,
    _build_provenance_fields,
)
from airmirror_future.physics.free_space import wave_number_rad_m, wavelength_m
from airmirror_future.physics.noise import (
    noise_power_dbm,
    shannon_capacity_bps,
    snr_db,
)
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


def _channel_snapshot(scene: Scene):
    ris = scene.ris_surfaces[0]
    pattern = generate_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    return SimulationEngine().compute_channel(
        scene, ris_patterns={ris.id: pattern}
    )


def test_fnd_t20a_center_frequency_recomputes_wavelength_and_complex_channel() -> None:
    scene = create_smart_space_scene("Advanced")
    original = _channel_snapshot(scene)
    changed = replace(scene, frequency_hz=scene.frequency_hz * 1.1)
    updated = _channel_snapshot(changed)

    np.testing.assert_allclose(
        wavelength_m(changed.frequency_hz),
        299_792_458.0 / changed.frequency_hz,
        rtol=0.0,
        atol=1e-15,
    )
    np.testing.assert_allclose(
        wave_number_rad_m(changed.frequency_hz),
        2.0 * np.pi / wavelength_m(changed.frequency_hz),
        rtol=0.0,
        atol=1e-12,
    )
    assert updated.total_channel != original.total_channel
    assert updated.los_channel != original.los_channel
    assert updated.wall_channel != original.wall_channel
    assert updated.ris_channel != original.ris_channel


def test_fnd_t20b_bandwidth_changes_only_link_metrics() -> None:
    scene = create_smart_space_scene("Advanced")
    original = _channel_snapshot(scene)
    changed = replace(scene, bandwidth_hz=scene.bandwidth_hz * 2.0)
    updated = _channel_snapshot(changed)

    np.testing.assert_equal(updated.los_channel, original.los_channel)
    np.testing.assert_equal(updated.wall_channel, original.wall_channel)
    np.testing.assert_equal(updated.ris_channel, original.ris_channel)
    np.testing.assert_equal(updated.total_channel, original.total_channel)
    np.testing.assert_equal(updated.received_power_w, original.received_power_w)
    assert updated.noise_power_dbm > original.noise_power_dbm
    assert updated.snr_db < original.snr_db
    expected_noise = noise_power_dbm(
        changed.bandwidth_hz, changed.receiver().noise_figure_db
    )
    expected_snr = snr_db(updated.received_power_dbm, expected_noise)
    expected_capacity = shannon_capacity_bps(changed.bandwidth_hz, expected_snr)
    np.testing.assert_allclose(
        updated.noise_power_dbm, expected_noise, rtol=0.0, atol=1e-12
    )
    np.testing.assert_allclose(updated.snr_db, expected_snr, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(
        updated.shannon_capacity_bps, expected_capacity, rtol=1e-12, atol=1e-6
    )


def test_fnd_t20c_frequency_model_identity_is_canonical() -> None:
    scene = create_smart_space_scene("Advanced")
    fields = _build_provenance_fields(
        engine=SimulationEngine(),
        scene=scene,
        focus=generate_focus_pattern,
        world=ControllerModel(),
        run_id="20260907T010203.123456Z-abcdef12",
    )

    assert fields["channel_frequency_model_id"] == CHANNEL_FREQUENCY_MODEL_ID
    assert json.loads(str(fields["pending_contracts_json"])) == [
        "FND-PHY-NB",
        "FND-QA-CC",
    ]


def test_scene_v1_round_trip_does_not_add_frequency_model_field(tmp_path) -> None:
    scene = create_smart_space_scene("Advanced")
    destination = tmp_path / "scene.json"
    scene.save(destination)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert "channel_frequency_model_id" not in payload
    assert "channel_frequency_model_id" not in payload["ris_surfaces"][0]
    assert Scene.load(destination).frequency_hz == scene.frequency_hz
    assert Scene.load(destination).bandwidth_hz == scene.bandwidth_hz
