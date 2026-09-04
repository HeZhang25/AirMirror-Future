"""Classify experiment result directories without mutating their artifacts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal, cast


ResultClassification = Literal[
    "foundation_partial",
    "foundation_complete",
    "legacy_v0_1_unversioned",
    "checkpoint_non_formal",
    "malformed",
    "unclassified",
]

FOUNDATION_SCHEMA_ID = "airmirror_experiment_provenance"
FOUNDATION_SCHEMA_VERSION = 1

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_LEGACY_RELATIVE_PATH = Path("results/phase_bits")
_CHECKPOINT_RELATIVE_PATH = Path(
    "results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903"
)
_FOUNDATION_RUNS_RELATIVE_PATH = Path("results/foundation_0_1_1/phase_bits")

_SCHEMA_ID_FIELD = "provenance_schema_id"
_SCHEMA_VERSION_FIELD = "provenance_schema_version"
_STATUS_FIELD = "provenance_status"


def _is_exact_directory(path: Path, relative_path: Path) -> bool:
    """Return whether ``path`` is exactly a repository-owned result directory."""
    try:
        return path.resolve() == (_REPOSITORY_ROOT / relative_path).resolve()
    except OSError:
        return False


def _is_under_directory(path: Path, relative_path: Path) -> bool:
    """Return whether ``path`` is within a repository-owned result root."""
    try:
        path.resolve().relative_to((_REPOSITORY_ROOT / relative_path).resolve())
    except (OSError, ValueError):
        return False
    return True


def _read_result_rows(path: Path) -> list[dict[str, str | None]]:
    """Read direct CSV artifacts from a result directory without writing to it."""
    csv_paths = sorted(path.glob("*.csv"))
    if not csv_paths:
        return []

    rows: list[dict[str, str | None]] = []
    for csv_path in csv_paths:
        try:
            with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                rows.extend(dict(row) for row in reader)
        except (OSError, csv.Error, UnicodeError) as exc:
            raise ValueError(f"unable to read result CSV: {csv_path}") from exc
    return rows


def _schema_fields_present(rows: list[dict[str, str | None]]) -> bool:
    return any(
        _SCHEMA_ID_FIELD in row or _SCHEMA_VERSION_FIELD in row
        for row in rows
    )


def _cell_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _classify_schema_rows(
    rows: list[dict[str, str | None]], *, foundation_path: bool
) -> ResultClassification:
    """Classify provenance discriminators, rejecting unknown schema versions."""
    if not rows:
        return "malformed" if foundation_path else "unclassified"

    schema_fields_present = _schema_fields_present(rows)
    if not schema_fields_present:
        return "malformed" if foundation_path else "unclassified"

    statuses: set[str] = set()
    for row in rows:
        schema_id = _cell_text(row.get(_SCHEMA_ID_FIELD))
        raw_version = _cell_text(row.get(_SCHEMA_VERSION_FIELD))

        if schema_id and schema_id != FOUNDATION_SCHEMA_ID:
            raise ValueError(f"unknown provenance schema id: {schema_id!r}")
        if not schema_id or not raw_version:
            return "malformed"
        try:
            version = int(raw_version)
        except ValueError as exc:
            raise ValueError(
                f"unknown provenance schema version: {raw_version!r}"
            ) from exc
        if version != FOUNDATION_SCHEMA_VERSION:
            raise ValueError(f"unknown provenance schema version: {version}")

        status = _cell_text(row.get(_STATUS_FIELD))
        if status not in {"partial", "complete"}:
            return "malformed"
        statuses.add(status)

    if len(statuses) != 1:
        return "malformed"
    return cast(
        ResultClassification,
        "foundation_partial" if statuses == {"partial"} else "foundation_complete",
    )


def _classify_result_directory(path: Path) -> ResultClassification:
    """Classify a result directory according to the C2 provenance contract.

    The classifier only reads direct CSV artifacts. The repository's confirmed
    legacy and checkpoint paths are recognized before schema inspection, while
    an unknown non-empty schema ID/version is rejected with ``ValueError``.
    """
    path = Path(path)
    if not path.is_dir():
        raise ValueError(f"result directory does not exist: {path}")

    if _is_exact_directory(path, _LEGACY_RELATIVE_PATH):
        return "legacy_v0_1_unversioned"
    if _is_exact_directory(path, _CHECKPOINT_RELATIVE_PATH):
        return "checkpoint_non_formal"

    foundation_path = _is_under_directory(path, _FOUNDATION_RUNS_RELATIVE_PATH)
    rows = _read_result_rows(path)
    return _classify_schema_rows(rows, foundation_path=foundation_path)
