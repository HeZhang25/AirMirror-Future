from __future__ import annotations

import csv
from dataclasses import replace
import math
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import Vec3
from airmirror_future.experiments import xr_dynamic_room_mvp as mvp
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


def _evaluate_once():
    scene = mvp.create_mvp_scene()
    trajectory = mvp.build_trajectory()
    engine = SimulationEngine()
    model = ControllerModel()
    pattern = mvp.generate_static_pattern(
        scene,
        trajectory[0].position,
        engine=engine,
        model=model,
    )
    samples = mvp.evaluate_trajectory(
        scene,
        trajectory,
        pattern,
        engine=engine,
        model=model,
    )
    return scene, trajectory, pattern, samples


def test_trajectory_is_deterministic_repeated_and_inside_room() -> None:
    first = mvp.build_trajectory()
    second = mvp.build_trajectory()
    scene = mvp.create_mvp_scene()

    assert first == second
    assert len(first) == 11
    assert first[0].time_s == 0.0
    assert first[-1].time_s == 5.0
    assert first[0].position == mvp.TRAJECTORY_START
    assert first[-1].position == Vec3(7.0, 5.5, 1.2)
    assert [sample.sample_index for sample in first] == list(range(len(first)))
    assert [sample.time_s for sample in first] == pytest.approx(
        [index * 0.5 for index in range(len(first))]
    )
    assert all(
        0.0 < sample.position.x < scene.room_size.x
        and 0.0 < sample.position.y < scene.room_size.y
        and 0.0 < sample.position.z < scene.room_size.z
        for sample in first
    )


def test_static_pattern_uses_current_default_model_based_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = mvp.create_mvp_scene()
    initial_position = mvp.build_trajectory()[0].position
    engine = SimulationEngine()
    model = ControllerModel()
    expected = np.zeros(scene.ris_surfaces[0].cell_count)
    captured: dict[str, object] = {}

    def focus(scene_arg, model_arg, **kwargs):
        captured.update(scene=scene_arg, model=model_arg, **kwargs)
        return expected

    monkeypatch.setattr(mvp, "generate_coherent_target_pattern", focus)
    actual = mvp.generate_static_pattern(
        scene,
        initial_position,
        engine=engine,
        model=model,
    )

    assert np.array_equal(actual, expected)
    assert captured["scene"] is scene
    assert captured["model"] is model
    assert captured["engine"] is engine
    assert captured["tx"] is scene.transmitter()
    assert captured["ris"] is scene.ris_surfaces[0]
    assert captured["rx"] == replace(scene.receiver(), position=initial_position)


def test_repeated_configuration_is_numerically_reproducible() -> None:
    first_scene, first_trajectory, first_pattern, first_samples = _evaluate_once()
    second_scene, second_trajectory, second_pattern, second_samples = _evaluate_once()

    assert first_scene.frequency_hz == second_scene.frequency_hz
    assert first_scene.bandwidth_hz == second_scene.bandwidth_hz
    assert first_trajectory == second_trajectory
    assert np.array_equal(first_pattern, second_pattern)
    assert [
        (sample.mode, sample.received_power_dbm, sample.snr_db, sample.ris_channel)
        for sample in first_samples
    ] == [
        (sample.mode, sample.received_power_dbm, sample.snr_db, sample.ris_channel)
        for sample in second_samples
    ]


def test_static_command_is_legal_immutable_and_reused_for_all_samples() -> None:
    scene = mvp.create_mvp_scene()
    trajectory = mvp.build_trajectory()
    model = ControllerModel()

    class RecordingEngine(SimulationEngine):
        def __init__(self) -> None:
            super().__init__()
            self.patterns: list[np.ndarray | None] = []

        def compute_channel(self, scene, *args, ris_patterns=None, **kwargs):
            if ris_patterns is not None:
                pattern = ris_patterns.get(scene.ris_surfaces[0].id)
                self.patterns.append(None if pattern is None else np.array(pattern, copy=True))
            return super().compute_channel(
                scene,
                *args,
                ris_patterns=ris_patterns,
                **kwargs,
            )

    focus_engine = SimulationEngine()
    pattern = mvp.generate_static_pattern(
        scene,
        trajectory[0].position,
        engine=focus_engine,
        model=model,
    )
    before = np.array(pattern, copy=True)
    expected_hash = mvp._pattern_hash(pattern)
    recording_engine = RecordingEngine()
    samples = mvp.evaluate_trajectory(
        scene,
        trajectory,
        pattern,
        engine=recording_engine,
        model=model,
    )

    assert not pattern.flags.writeable
    assert np.array_equal(validate_commanded_pattern(scene.ris_surfaces[0], pattern), pattern)
    assert np.array_equal(pattern, before)
    assert mvp._pattern_hash(pattern) == expected_hash
    commanded = [value for value in recording_engine.patterns if value is not None]
    assert commanded
    assert all(np.array_equal(value, pattern) for value in commanded)
    assert {mvp._pattern_hash(value) for value in commanded} == {expected_hash}
    assert {
        sample.static_pattern_hash
        for sample in samples
        if sample.mode == mvp.STATIC_RIS_MODE
    } == {expected_hash}


def test_modes_share_non_ris_conditions_and_no_ris_disables_contribution() -> None:
    scene, trajectory, _, samples = _evaluate_once()
    by_point = {
        (sample.trajectory.sample_index, sample.mode): sample for sample in samples
    }

    assert len(scene.transmitters) == len(scene.receivers) == len(scene.ris_surfaces) == 1
    for point in trajectory:
        no_ris = by_point[(point.sample_index, mvp.NO_RIS_MODE)]
        static = by_point[(point.sample_index, mvp.STATIC_RIS_MODE)]
        assert no_ris.trajectory == static.trajectory == point
        assert no_ris.ris_channel == 0.0j
        assert math.isfinite(no_ris.received_power_dbm)
        assert math.isfinite(no_ris.snr_db)
        assert math.isfinite(static.received_power_dbm)
        assert math.isfinite(static.snr_db)


def test_headless_csv_and_png_generation(tmp_path: Path) -> None:
    output = tmp_path / "xr-mvp-run"
    artifacts = mvp.run(output)

    assert artifacts.csv_path == output / "xr_dynamic_room_mvp.csv"
    assert artifacts.png_path == output / "xr_dynamic_room_mvp.png"
    assert artifacts.runtime_s > 0.0
    assert artifacts.png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with artifacts.csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert tuple(reader.fieldnames or ()) == mvp.MVP_CSV_FIELDS
    assert len(rows) == 2 * len(mvp.build_trajectory())
    assert {row["mode"] for row in rows} == set(mvp.MVP_MODES)
    assert all(
        math.isfinite(float(row[field]))
        for row in rows
        for field in ("received_power_dbm", "snr_db", "ris_channel_abs")
    )
    no_ris_rows = [row for row in rows if row["mode"] == mvp.NO_RIS_MODE]
    static_rows = [row for row in rows if row["mode"] == mvp.STATIC_RIS_MODE]
    assert all(float(row["ris_channel_abs"]) == 0.0 for row in no_ris_rows)
    assert {row["static_pattern_hash"] for row in static_rows} == {
        artifacts.static_pattern_hash
    }
    invariant_fields = {
        "sample_index",
        "time_s",
        "rx_x_m",
        "rx_y_m",
        "rx_z_m",
        "scenario",
        "tx_id",
        "rx_id",
        "ris_id",
        "generation",
        "frequency_hz",
        "bandwidth_hz",
        "profile_id",
        "profile_version",
        "profile_identity",
        "simulation_model",
        "focus_path",
        "channel_behavior",
        "production_quadrature",
    }
    for no_ris, static in zip(no_ris_rows, static_rows, strict=True):
        assert {field: no_ris[field] for field in invariant_fields} == {
            field: static[field] for field in invariant_fields
        }


def test_explicit_output_is_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        mvp.run(output)

    assert marker.read_text(encoding="utf-8") == "keep"
