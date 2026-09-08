from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "perf_prep_01.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("perf_prep_01", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_field_matrix_is_bounded_and_labels_probes() -> None:
    module = _load_module()

    assert module._field_grid("Current", full_fast=False, future_fast=False) == (
        80,
        60,
        "fast",
    )
    assert module._field_grid("Advanced", full_fast=False, future_fast=False) == (
        16,
        12,
        "representative_probe",
    )
    assert module._field_grid("Future", full_fast=False, future_fast=False) == (
        8,
        6,
        "representative_probe",
    )


def test_expensive_field_cases_require_explicit_flags() -> None:
    module = _load_module()

    assert module._field_grid("Advanced", full_fast=True, future_fast=False) == (
        80,
        60,
        "fast",
    )
    assert module._field_grid("Future", full_fast=True, future_fast=False) == (
        8,
        6,
        "representative_probe",
    )
    assert module._field_grid("Future", full_fast=False, future_fast=True) == (
        80,
        60,
        "fast_explicit_opt_in",
    )


def test_thread_environment_is_single_threaded() -> None:
    module = _load_module()

    assert module.THREAD_ENVIRONMENT == {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }


def test_reuse_core_option_is_explicit() -> None:
    module = _load_module()
    args = module._parser().parse_args(
        ["--output", "new.json", "--reuse-core", "previous.json"]
    )

    assert args.reuse_core == Path("previous.json")


def test_array_hash_is_byte_defined_and_shape_independent() -> None:
    import numpy as np

    module = _load_module()
    row = np.array([1.0, 2.0, 3.0, 4.0])
    grid = row.reshape(2, 2)

    assert module._array_sha256(row) == module._array_sha256(grid)
    assert module._array_sha256(row).startswith("sha256:")
