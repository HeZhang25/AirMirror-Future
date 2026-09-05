"""C2 integration wiring tests for the Phase Resolution runner.

These tests exercise the D-owned orchestration seam with a small deterministic
engine double.  Physics kernels remain covered by their existing tests; here we
verify ordering, ownership and artifact/provenance boundaries.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace

import numpy as np
import pytest

import airmirror_future
from airmirror_future.experiments import phase_bits
from airmirror_future.experiments.provenance import (
    _build_provenance_fields as _real_build_provenance_fields,
)
from airmirror_future.experiments.result_classification import (
    _classify_result_directory,
)
from airmirror_future.simulation.engine import SimulationEngine


RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}$")


class _RecordingEngine:
    """Tiny engine double that records the selected world on every call."""

    def __init__(self, profile):
        self.profile = profile
        self.profile_identity = SimulationEngine(profile).profile_identity
        self.calls: list[tuple[str, object]] = []

    def compute_channel(self, scene, *args, model=None, **kwargs):
        self.calls.append(("channel", model))
        # Baseline has no commanded pattern; focused points do.  Distinct but
        # finite values keep CSV generation independent of the physics engine.
        focused = bool(kwargs.get("ris_patterns")) or any(
            isinstance(value, np.ndarray) for value in args
        )
        return SimpleNamespace(
            received_power_dbm=-45.0 if focused else -50.0,
            snr_db=35.0 if focused else 30.0,
        )

    def compute_field_map(self, scene, *args, model=None, **kwargs):
        self.calls.append(("field_map", model))
        return SimpleNamespace(coverage_percent=75.0)


def _patch_small_deterministic_run(monkeypatch: pytest.MonkeyPatch) -> list[_RecordingEngine]:
    """Patch only the expensive simulation while retaining a real scene/focus."""
    engines: list[_RecordingEngine] = []
    profile = SimulationEngine().profile

    def make_engine(*args, **kwargs):
        engine = _RecordingEngine(profile)
        engines.append(engine)
        return engine

    monkeypatch.setattr(phase_bits, "SimulationEngine", make_engine)
    monkeypatch.setattr(
        phase_bits,
        "field_quality_preset",
        lambda key: SimpleNamespace(grid_width=2, grid_height=2),
    )
    return engines


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_c2_run_wires_single_controller_and_writes_schema_v1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engines = _patch_small_deterministic_run(monkeypatch)
    provenance_inputs: list[dict[str, object]] = []

    def capture_provenance(*args, **kwargs):
        provenance_inputs.append(kwargs)
        return _real_build_provenance_fields(*args, **kwargs)

    monkeypatch.setattr(phase_bits, "_build_provenance_fields", capture_provenance)
    output = tmp_path / "20260904T120000.000000Z-c2c2c2c2"

    csv_path, png_path = phase_bits.run(output)

    assert csv_path.parent == output
    assert png_path.parent == output
    assert png_path.is_file()
    rows = _read_rows(csv_path)
    assert len(rows) == 5
    assert [row["phase_bits"] for row in rows] == ["1", "2", "3", "4", "continuous"]
    required_provenance = {
        "provenance_schema_id",
        "provenance_schema_version",
        "provenance_status",
        "pending_contracts_json",
        "run_id",
        "software_version",
        "focus_mode_id",
        "focus_mode_version",
        "profile_id",
        "profile_version",
        "profile_parameters_json",
        "profile_identity",
        "reflection_model_id",
        "reflection_model_version",
        "world_model_id",
        "world_model_version",
        "world_model_parameters_json",
        "random_seed",
    }
    assert required_provenance <= set(rows[0])
    for row in rows:
        assert row["run_id"] == output.name
        assert row["provenance_schema_id"] == "airmirror_experiment_provenance"
        assert row["provenance_schema_version"] == "1"
        assert row["provenance_status"] == "partial"
        assert row["pending_contracts_json"] == '["FND-PHY-NB","FND-QA-AP","FND-QA-CC"]'
        assert row["software_version"] == airmirror_future.__version__
        assert row["focus_mode_id"] == "ris_only_phase_conjugate"
        assert row["world_model_id"] == "controller_nominal"
        assert row["profile_id"] == "indoor_deterministic"
        assert row["reflection_model_id"] == "finite_wall_single_bounce_image"

    assert _classify_result_directory(output, expected_foundation=True) == "foundation_partial"
    assert engines and all(engine.calls for engine in engines)
    worlds = [model for _kind, model in engines[0].calls]
    assert worlds and all(model is worlds[0] for model in worlds)
    assert len(provenance_inputs) == 1
    assert provenance_inputs[0]["engine"] is engines[0]
    assert provenance_inputs[0]["scene"].name == "Future Smart Space"
    assert provenance_inputs[0]["focus"] is phase_bits.generate_focus_pattern
    assert provenance_inputs[0]["world"] is worlds[0]
    assert provenance_inputs[0]["run_id"] == output.name
    assert worlds[0].__class__.__name__ == "ControllerModel"


def test_existing_output_fails_before_scene_or_engine_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "already-there"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(
        phase_bits,
        "create_smart_space_scene",
        lambda *args, **kwargs: pytest.fail("scene created before exclusive directory check"),
    )
    monkeypatch.setattr(
        phase_bits,
        "SimulationEngine",
        lambda *args, **kwargs: pytest.fail("engine created before exclusive directory check"),
    )

    with pytest.raises(FileExistsError):
        phase_bits.run(output)

    assert marker.read_text(encoding="utf-8") == "unchanged"


def test_runner_does_not_offer_force_or_reuse_flags() -> None:
    with pytest.raises(SystemExit) as exc_info:
        phase_bits.main(["--force"])
    assert exc_info.value.code == 2


def test_default_run_directory_is_unique_versioned_and_classified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_small_deterministic_run(monkeypatch)
    ids = iter(("20260904T120000.000000Z-aaaa1111", "20260904T120001.000000Z-bbbb2222"))
    monkeypatch.setattr("airmirror_future.experiments.run_output._new_run_id", lambda: next(ids))

    first_csv, first_png = phase_bits.run(None)
    second_csv, second_png = phase_bits.run(None)

    assert first_csv.parent != second_csv.parent
    assert RUN_ID_PATTERN.fullmatch(first_csv.parent.name)
    assert RUN_ID_PATTERN.fullmatch(second_csv.parent.name)
    assert first_csv.parent.name == "20260904T120000.000000Z-aaaa1111"
    assert second_csv.parent.name == "20260904T120001.000000Z-bbbb2222"
    assert first_png.parent == first_csv.parent
    assert second_png.parent == second_csv.parent
    assert _classify_result_directory(first_csv.parent, expected_foundation=True) == "foundation_partial"
    assert _classify_result_directory(second_csv.parent, expected_foundation=True) == "foundation_partial"


def test_legacy_and_checkpoint_artifacts_remain_byte_and_timestamp_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    legacy = Path(__file__).resolve().parents[1] / "results" / "phase_bits"
    checkpoint = (
        Path(__file__).resolve().parents[1]
        / "results"
        / "checkpoints"
        / "foundation_0_1_1_ab_checkpoint_20260903"
    )

    def snapshot(path: Path) -> dict[str, tuple[str, int, int]]:
        return {
            item.name: (
                hashlib.sha256(item.read_bytes()).hexdigest(),
                item.stat().st_size,
                item.stat().st_mtime_ns,
            )
            for item in path.iterdir()
            if item.is_file()
        }

    before = (snapshot(legacy), snapshot(checkpoint))
    _patch_small_deterministic_run(monkeypatch)
    phase_bits.run(tmp_path / "new-run")
    after = (snapshot(legacy), snapshot(checkpoint))

    assert before == after
    assert _classify_result_directory(legacy) == "legacy_v0_1_unversioned"
    assert _classify_result_directory(checkpoint) == "checkpoint_non_formal"
