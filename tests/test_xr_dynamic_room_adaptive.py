from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import ChannelResult
from airmirror_future.experiments import xr_dynamic_room_mvp as mvp
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


@pytest.fixture(scope="module")
def adaptive_computation() -> mvp.MVPComputation:
    return mvp.compute_adaptive_mvp()


def _sample_lookup(
    computation: mvp.MVPComputation,
) -> dict[tuple[int, str], mvp.DynamicLinkSample]:
    return {
        (sample.trajectory.sample_index, sample.mode): sample
        for sample in computation.samples
    }


def test_adaptive_real_physics_uses_legal_immutable_commands_and_shared_conditions(
    adaptive_computation: mvp.MVPComputation,
) -> None:
    computation = adaptive_computation
    ris = computation.scene.ris_surfaces[0]
    lookup = _sample_lookup(computation)

    assert computation.trajectory == mvp.build_trajectory()
    assert len(computation.trajectory) == 11
    assert len(computation.samples) == 11 * len(mvp.ADAPTIVE_MVP_MODES)
    assert not computation.static_pattern.flags.writeable

    static_hashes: set[str] = set()
    adaptive_hashes: list[str] = []
    adaptive_arrays: list[np.ndarray] = []
    for point in computation.trajectory:
        no_ris = lookup[(point.sample_index, mvp.NO_RIS_MODE)]
        static = lookup[(point.sample_index, mvp.STATIC_RIS_MODE)]
        adaptive = lookup[(point.sample_index, mvp.ADAPTIVE_RIS_MODE)]

        assert no_ris.trajectory == static.trajectory == adaptive.trajectory == point
        assert no_ris.command_kind == "none"
        assert no_ris.commanded_pattern is None
        assert no_ris.command_hash == ""
        assert no_ris.ris_channel == 0.0j

        assert static.command_kind == "static"
        assert static.commanded_pattern is computation.static_pattern
        assert static.command_hash == mvp._pattern_hash(computation.static_pattern)
        assert static.static_pattern_hash == static.command_hash
        static_hashes.add(static.command_hash)

        assert adaptive.command_kind == "adaptive"
        assert adaptive.commanded_pattern is not None
        assert not adaptive.commanded_pattern.flags.writeable
        assert np.array_equal(
            validate_commanded_pattern(ris, adaptive.commanded_pattern),
            adaptive.commanded_pattern,
        )
        assert adaptive.command_hash == mvp._pattern_hash(adaptive.commanded_pattern)
        adaptive_hashes.append(adaptive.command_hash)
        adaptive_arrays.append(adaptive.commanded_pattern)

        for sample in (no_ris, static, adaptive):
            assert sample.trajectory.position == point.position
            assert all(
                math.isfinite(value)
                for value in (
                    sample.received_power_dbm,
                    sample.snr_db,
                    sample.noise_power_dbm,
                    sample.total_channel.real,
                    sample.total_channel.imag,
                    sample.los_channel.real,
                    sample.los_channel.imag,
                    sample.wall_channel.real,
                    sample.wall_channel.imag,
                    sample.ris_channel.real,
                    sample.ris_channel.imag,
                )
            )
        assert no_ris.los_channel == static.los_channel == adaptive.los_channel
        assert no_ris.wall_channel == static.wall_channel == adaptive.wall_channel
        assert no_ris.noise_power_dbm == static.noise_power_dbm == adaptive.noise_power_dbm

    assert len(static_hashes) == 1
    assert len(adaptive_hashes) == len(computation.trajectory)
    assert all(
        not np.shares_memory(left, right)
        for index, left in enumerate(adaptive_arrays)
        for right in adaptive_arrays[index + 1 :]
    )

    static_zero = lookup[(0, mvp.STATIC_RIS_MODE)]
    adaptive_zero = lookup[(0, mvp.ADAPTIVE_RIS_MODE)]
    assert adaptive_zero.commanded_pattern is not None
    assert np.array_equal(adaptive_zero.commanded_pattern, computation.static_pattern)
    assert adaptive_zero.command_hash == static_zero.command_hash
    assert adaptive_zero.total_channel == static_zero.total_channel
    assert adaptive_zero.received_power_dbm == static_zero.received_power_dbm
    assert adaptive_zero.snr_db == static_zero.snr_db


def test_repeated_adaptive_computation_is_numerically_reproducible(
    adaptive_computation: mvp.MVPComputation,
) -> None:
    repeated = mvp.compute_adaptive_mvp()

    assert repeated.scene == adaptive_computation.scene
    assert repeated.trajectory == adaptive_computation.trajectory
    assert np.array_equal(repeated.static_pattern, adaptive_computation.static_pattern)
    for first, second in zip(
        adaptive_computation.samples,
        repeated.samples,
        strict=True,
    ):
        assert first.trajectory == second.trajectory
        assert first.mode == second.mode
        assert first.command_kind == second.command_kind
        assert first.command_hash == second.command_hash
        if first.commanded_pattern is None:
            assert second.commanded_pattern is None
        else:
            assert second.commanded_pattern is not None
            assert np.array_equal(first.commanded_pattern, second.commanded_pattern)
        assert (
            first.total_channel,
            first.los_channel,
            first.wall_channel,
            first.ris_channel,
            first.received_power_dbm,
            first.snr_db,
            first.noise_power_dbm,
        ) == (
            second.total_channel,
            second.los_channel,
            second.wall_channel,
            second.ris_channel,
            second.received_power_dbm,
            second.snr_db,
            second.noise_power_dbm,
        )


def test_adaptive_focus_runs_once_per_sample_at_the_current_receiver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = mvp.create_mvp_scene()
    trajectory = mvp.build_trajectory()
    static = np.zeros(scene.ris_surfaces[0].cell_count)
    static.setflags(write=False)
    focused_positions = []

    def focus(scene_arg, model_arg, **kwargs):
        assert scene_arg is scene
        assert isinstance(model_arg, ControllerModel)
        focused_positions.append(kwargs["rx"].position)
        phase = 0.0 if len(focused_positions) % 2 else np.pi
        return np.full(scene.ris_surfaces[0].cell_count, phase)

    class FiniteEngine:
        profile = SimulationEngine().profile
        profile_identity = SimulationEngine().profile_identity

        def compute_channel(self, _scene, tx=None, rx=None, ris_patterns=None, model=None):
            ris_channel = 0.0j if not ris_patterns else complex(len(ris_patterns), 0.0)
            return ChannelResult(
                total_channel=1.0 + ris_channel,
                los_channel=1.0 + 0.0j,
                wall_channel=0.0j,
                ris_channel=ris_channel,
                received_power_w=1.0,
                received_power_dbm=0.0,
                noise_power_dbm=-90.0,
                snr_db=90.0,
                shannon_capacity_bps=1.0,
            )

    monkeypatch.setattr(mvp, "generate_coherent_target_pattern", focus)
    samples = mvp.evaluate_adaptive_trajectory(
        scene,
        trajectory,
        static,
        engine=FiniteEngine(),
        model=ControllerModel(),
    )

    assert focused_positions == [point.position for point in trajectory]
    assert [sample.mode for sample in samples[:3]] == list(mvp.ADAPTIVE_MVP_MODES)


def test_adaptive_evaluation_has_sample_boundary_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = mvp.create_mvp_scene()
    trajectory = mvp.build_trajectory()
    static = np.zeros(scene.ris_surfaces[0].cell_count)
    static.setflags(write=False)
    cancel = False

    def focus(*_args, **_kwargs):
        return np.zeros(scene.ris_surfaces[0].cell_count)

    class FiniteEngine:
        def compute_channel(self, *_args, ris_patterns=None, **_kwargs):
            return ChannelResult(
                total_channel=1.0 + 0.0j,
                los_channel=1.0 + 0.0j,
                wall_channel=0.0j,
                ris_channel=0.0j if not ris_patterns else 1.0 + 0.0j,
                received_power_w=1.0,
                received_power_dbm=0.0,
                noise_power_dbm=-90.0,
                snr_db=90.0,
                shannon_capacity_bps=1.0,
            )

    def progress(done: int, total: int) -> None:
        nonlocal cancel
        assert total == len(trajectory)
        if done == 1:
            cancel = True

    monkeypatch.setattr(mvp, "generate_coherent_target_pattern", focus)
    with pytest.raises(SimulationCancelled, match="cancelled"):
        mvp.evaluate_adaptive_trajectory(
            scene,
            trajectory,
            static,
            engine=FiniteEngine(),
            model=ControllerModel(),
            cancel_check=lambda: cancel,
            progress=progress,
        )


def test_adaptive_csv_png_provenance_and_lossless_command_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    adaptive_computation: mvp.MVPComputation,
) -> None:
    monkeypatch.setattr(
        mvp,
        "compute_adaptive_mvp",
        lambda **_kwargs: adaptive_computation,
    )
    output = tmp_path / "adaptive-run"
    artifacts = mvp.run_adaptive(output)

    assert artifacts.run_id == output.name
    assert artifacts.csv_path == output / "xr_dynamic_room_adaptive.csv"
    assert artifacts.png_path == output / "xr_dynamic_room_adaptive.png"
    assert artifacts.png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert artifacts.runtime_s > 0.0

    with artifacts.csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == mvp.ADAPTIVE_CSV_FIELDS
    assert len(rows) == 11 * len(mvp.ADAPTIVE_MVP_MODES)
    assert {row["mode"] for row in rows} == set(mvp.ADAPTIVE_MVP_MODES)
    assert {row["run_id"] for row in rows} == {output.name}
    assert {row["provenance_schema_id"] for row in rows} == {
        "airmirror_experiment_provenance"
    }
    assert {row["provenance_schema_version"] for row in rows} == {"1"}
    assert {row["provenance_status"] for row in rows} == {"partial"}
    assert all(
        {"FND-QA-CC"}
        == set(json.loads(row["pending_contracts_json"]))
        for row in rows
    )
    assert {row["focus_mode_id"] for row in rows} == {"coherent_target"}
    assert {row["world_model_id"] for row in rows} == {"controller_nominal"}
    assert {row["channel_frequency_model_id"] for row in rows} == {
        "narrowband_center_frequency_flat_v1"
    }
    identities = {row["coefficient_model_identity"] for row in rows}
    assert len(identities) == 1
    assert next(iter(identities)).startswith("sha256:")
    assert {row["quadrature_policy_id"] for row in rows} == {
        "midpoint_8x8_per_control_patch"
    }
    assert {row["quadrature_policy_version"] for row in rows} == {"1"}
    assert {row["production_quadrature"] for row in rows} == {
        "midpoint_8x8_per_control_patch"
    }
    assert {float(row["tx_power_w"]) for row in rows} == {
        adaptive_computation.scene.transmitter().power_w
    }
    assert {float(row["rx_noise_figure_db"]) for row in rows} == {
        adaptive_computation.scene.receiver().noise_figure_db
    }
    assert {row["prototype_status"] for row in rows} == {
        "non_release_adaptive_provisional"
    }
    assert {row["adaptive_time_semantics"] for row in rows} == {
        "discrete_samples_ideal_instantaneous_reconfiguration"
    }

    ris = adaptive_computation.scene.ris_surfaces[0]
    for row in rows:
        assert all(
            math.isfinite(float(row[field]))
            for field in (
                "received_power_dbm",
                "snr_db",
                "noise_power_dbm",
                "total_channel_real",
                "total_channel_imag",
                "los_channel_real",
                "los_channel_imag",
                "wall_channel_real",
                "wall_channel_imag",
                "ris_channel_real",
                "ris_channel_imag",
            )
        )
        if row["mode"] == mvp.NO_RIS_MODE:
            assert row["command_kind"] == "none"
            assert row["command_hash"] == ""
            assert row["command_values_json"] == ""
            assert row["command_size"] == "0"
            assert row["ris_gain_db"] == ""
        else:
            rebuilt = np.asarray(json.loads(row["command_values_json"]), dtype=float)
            rebuilt = validate_commanded_pattern(ris, rebuilt)
            assert rebuilt.size == int(row["command_size"])
            assert mvp._pattern_hash(rebuilt) == row["command_hash"]

    by_key = {(int(row["sample_index"]), row["mode"]): row for row in rows}
    assert by_key[(0, mvp.STATIC_RIS_MODE)]["command_values_json"] == by_key[
        (0, mvp.ADAPTIVE_RIS_MODE)
    ]["command_values_json"]
    assert by_key[(0, mvp.STATIC_RIS_MODE)]["received_power_dbm"] == by_key[
        (0, mvp.ADAPTIVE_RIS_MODE)
    ]["received_power_dbm"]


def test_adaptive_explicit_output_fails_before_physics_when_target_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    called = False

    def unexpected(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("physics must not run")

    monkeypatch.setattr(mvp, "compute_adaptive_mvp", unexpected)
    with pytest.raises(FileExistsError):
        mvp.run_adaptive(output)
    assert called is False
    assert marker.read_text(encoding="utf-8") == "keep"
