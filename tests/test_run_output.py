"""FND-EXP-01B run-directory and exclusive no-overwrite tests."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from airmirror_future.experiments.run_output import _RunDirectory, _create_run_directory


RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}$")


def test_default_run_directory_uses_foundation_root_and_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    run = _create_run_directory(None)

    assert isinstance(run, _RunDirectory)
    assert run.path.parent == Path("results/foundation_0_1_1/phase_bits")
    assert run.path.is_dir()
    assert run.path.name == run.run_id
    assert RUN_ID_PATTERN.fullmatch(run.run_id)


def test_explicit_output_is_complete_run_directory(tmp_path: Path) -> None:
    output = tmp_path / "20260904T120000.000000Z-deadbeef"

    run = _create_run_directory(output)

    assert run == _RunDirectory(output, output.name)
    assert run.path == output
    assert run.run_id == output.name
    assert output.is_dir()


def test_existing_explicit_output_fails_without_reuse(tmp_path: Path) -> None:
    output = tmp_path / "existing-run"
    output.mkdir()
    marker = output / "partial.marker"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        _create_run_directory(output)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_existing_default_target_fails_exclusively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    root = Path("results/foundation_0_1_1/phase_bits")
    root.mkdir(parents=True)
    target = root / "20260904T120000.000000Z-deadbeef"
    target.mkdir()

    monkeypatch.setattr(
        "airmirror_future.experiments.run_output._new_run_id",
        lambda: target.name,
    )

    with pytest.raises(FileExistsError):
        _create_run_directory(None)


def test_legacy_output_is_reserved_even_when_missing(tmp_path: Path) -> None:
    legacy = tmp_path / "results" / "phase_bits"
    assert not legacy.exists()

    with pytest.raises(ValueError, match="legacy results path is reserved"):
        _create_run_directory(legacy)

    assert not legacy.exists()


def test_legacy_symlink_or_equivalent_path_is_reserved(tmp_path: Path) -> None:
    legacy = tmp_path / "results" / "phase_bits"
    legacy.mkdir(parents=True)
    alias = tmp_path / "legacy-alias"
    try:
        alias.symlink_to(legacy, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="legacy results path is reserved"):
        _create_run_directory(alias)


def test_run_directory_is_immutable(tmp_path: Path) -> None:
    run = _create_run_directory(tmp_path / "run")

    with pytest.raises(AttributeError):
        run.run_id = "other"  # type: ignore[misc]
