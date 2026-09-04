"""Exclusive run-directory primitives for Foundation experiments.

This module deliberately owns only run-directory allocation. Experiment
execution and artifact writing remain in the runner owned by the integration
task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_RUN_ROOT = Path("results") / "foundation_0_1_1" / "phase_bits"
_LEGACY_OUTPUT = _REPOSITORY_ROOT / "results" / "phase_bits"


@dataclass(frozen=True, slots=True)
class _RunDirectory:
    """A newly allocated Foundation run directory and its stable run ID."""

    path: Path
    run_id: str


def _new_run_id() -> str:
    """Return a UTC timestamp and lowercase UUID-derived run identifier."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{timestamp}-{uuid4().hex[:8]}"


def _is_reserved_legacy_path(path: Path) -> bool:
    """Return whether *path* resolves to the retained v0.1 output path."""
    try:
        resolved = path.resolve()
        legacy = _LEGACY_OUTPUT.resolve()
        return resolved == legacy
    except OSError:
        return False


def _create_run_directory(output: Path | None) -> _RunDirectory:
    """Exclusively create and return a Foundation experiment run directory.

    ``output`` is a complete run directory when provided. Passing ``None``
    creates a fresh run below the Foundation Phase Resolution root. Existing
    targets are never reused, and the retained legacy output path is always
    rejected.
    """
    path = _DEFAULT_RUN_ROOT / _new_run_id() if output is None else Path(output)
    if _is_reserved_legacy_path(path):
        raise ValueError(f"legacy results path is reserved: {path}")
    path.mkdir(parents=True, exist_ok=False)
    return _RunDirectory(path, path.name)
