from __future__ import annotations

import os
from pathlib import Path

import pytest

from airmirror_future.experiments import result_classification
from airmirror_future.experiments.result_classification import _classify_result_directory


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "results" / "phase_bits"
CHECKPOINT = (
    ROOT
    / "results"
    / "checkpoints"
    / "foundation_0_1_1_ab_checkpoint_20260903"
)


def _write_csv(path: Path, header: str, *rows: str) -> None:
    path.mkdir(parents=True)
    (path / "phase_bits.csv").write_text(
        "\n".join((header, *rows)) + "\n", encoding="utf-8"
    )


def _foundation_csv(path: Path, *, status: str = "partial") -> None:
    _write_csv(
        path,
        "provenance_schema_id,provenance_schema_version,provenance_status",
        f"airmirror_experiment_provenance,1,{status}",
    )


def test_confirmed_legacy_and_checkpoint_are_distinct() -> None:
    legacy_before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in LEGACY.iterdir()
        if path.is_file()
    }
    checkpoint_before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in CHECKPOINT.iterdir()
        if path.is_file()
    }

    assert _classify_result_directory(LEGACY) == "legacy_v0_1_unversioned"
    assert _classify_result_directory(CHECKPOINT) == "checkpoint_non_formal"

    legacy_after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in LEGACY.iterdir()
        if path.is_file()
    }
    checkpoint_after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in CHECKPOINT.iterdir()
        if path.is_file()
    }
    assert legacy_after == legacy_before
    assert checkpoint_after == checkpoint_before


def test_foundation_partial_and_complete_classification(tmp_path: Path) -> None:
    partial = tmp_path / "partial"
    complete = tmp_path / "complete"
    _foundation_csv(partial, status="partial")
    _foundation_csv(complete, status="complete")

    assert _classify_result_directory(partial) == "foundation_partial"
    assert _classify_result_directory(complete) == "foundation_complete"


def test_mixed_foundation_statuses_are_malformed(tmp_path: Path) -> None:
    path = tmp_path / "mixed"
    _write_csv(
        path,
        "provenance_schema_id,provenance_schema_version,provenance_status",
        "airmirror_experiment_provenance,1,partial",
        "airmirror_experiment_provenance,1,complete",
    )

    assert _classify_result_directory(path) == "malformed"


@pytest.mark.parametrize("status", ["legacy", "", "unknown"])
def test_invalid_foundation_status_is_malformed(tmp_path: Path, status: str) -> None:
    path = tmp_path / "invalid-status"
    _foundation_csv(path, status=status)

    assert _classify_result_directory(path) == "malformed"


def test_missing_csv_column_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "missing-column"
    _write_csv(
        path,
        "provenance_schema_id,provenance_schema_version,provenance_status",
        "airmirror_experiment_provenance,1",
    )

    assert _classify_result_directory(path) == "malformed"


@pytest.mark.parametrize(
    "header,row",
    [
        (
            "provenance_schema_id,provenance_schema_version,provenance_status",
            "airmirror_experiment_provenance,1,",
        ),
        (
            "provenance_schema_id,provenance_schema_version,provenance_status",
            ",1,partial",
        ),
        (
            "provenance_schema_id,provenance_schema_version,provenance_status",
            "airmirror_experiment_provenance,,partial",
        ),
    ],
)
def test_missing_or_empty_foundation_discriminator_is_malformed(
    tmp_path: Path, header: str, row: str
) -> None:
    path = tmp_path / "malformed"
    _write_csv(path, header, row)

    assert _classify_result_directory(path) == "malformed"


def test_unknown_nonempty_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unknown-schema"
    _write_csv(
        path,
        "provenance_schema_id,provenance_schema_version,provenance_status",
        "future_schema,1,partial",
    )

    with pytest.raises(ValueError, match="unknown provenance schema id"):
        _classify_result_directory(path)


def test_unknown_nonempty_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unknown-version"
    _write_csv(
        path,
        "provenance_schema_id,provenance_schema_version,provenance_status",
        "airmirror_experiment_provenance,2,partial",
    )

    with pytest.raises(ValueError, match="unknown provenance schema version"):
        _classify_result_directory(path)


def test_unknown_schema_less_directory_is_unclassified(tmp_path: Path) -> None:
    path = tmp_path / "unknown-source"
    _write_csv(path, "timestamp,scenario", "2026-09-04T00:00:00Z,example")

    assert _classify_result_directory(path) == "unclassified"


def test_foundation_run_without_schema_is_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(result_classification, "_REPOSITORY_ROOT", tmp_path)
    path = tmp_path / "results" / "foundation_0_1_1" / "phase_bits" / "missing"
    _write_csv(path, "timestamp,scenario", "2026-09-04T00:00:00Z,example")

    assert _classify_result_directory(path) == "malformed"


def test_classifier_does_not_change_directory_metadata(tmp_path: Path) -> None:
    path = tmp_path / "read-only"
    _foundation_csv(path)
    before = os.stat(path / "phase_bits.csv")

    assert _classify_result_directory(path) == "foundation_partial"

    after = os.stat(path / "phase_bits.csv")
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_size == before.st_size


def test_non_directory_path_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "phase_bits.csv"
    path.write_text("timestamp\n", encoding="utf-8")

    with pytest.raises(ValueError, match="result directory does not exist"):
        _classify_result_directory(path)
