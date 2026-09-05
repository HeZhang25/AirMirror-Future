from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.experiments.fnd_qa_ap_01 import (
    _assert_json_finite,
    canonical_pattern_hash,
    compare_to_reference,
    deterministic_random_pattern,
    evaluate_quadrature,
    _enforce_thread_process_policy,
    run,
    select_internal_reference,
)
from airmirror_future.ris.quadrature import midpoint_quadrature, tensor_product_gauss_legendre
from airmirror_future.ris.phase import generate_ris_only_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine


@pytest.fixture(autouse=True)
def _frozen_thread_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
        "MKL_DYNAMIC": "FALSE",
    }.items():
        monkeypatch.setenv(key, value)


def test_fnd_t16_refinement_keeps_control_order_and_command_ownership() -> None:
    ris = create_smart_space_scene("Current").ris_surfaces[0]
    midpoint = midpoint_quadrature(ris, 2, 3)
    gl = tensor_product_gauss_legendre(ris, 2, 3)
    commands = np.arange(ris.cell_count, dtype=float) + 1j

    expected_parents = np.repeat(np.arange(ris.cell_count), 6)
    assert np.array_equal(midpoint.parent_control_index, expected_parents)
    assert np.array_equal(gl.parent_control_index, expected_parents)
    assert np.array_equal(midpoint.inherited_commands(commands), commands[expected_parents])
    assert midpoint.control_count == gl.control_count == ris.cell_count
    assert midpoint.sample_count == gl.sample_count == ris.cell_count * 6
    for weights in (midpoint.weights, gl.weights):
        assert np.allclose(
            [np.sum(weights[i * 6 : (i + 1) * 6]) for i in range(ris.cell_count)], 1.0
        )


def test_midpoint_one_matches_existing_production_center_point_behavior() -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    pattern = generate_ris_only_focus_pattern(ris, scene.transmitter(), scene.receiver(), scene.frequency_hz)
    qa = evaluate_quadrature(scene, pattern, midpoint_quadrature(ris))
    production = SimulationEngine().compute_channel(scene, ris_patterns={ris.id: pattern})

    assert qa["h_ris"] == pytest.approx(production.ris_channel, rel=1e-14, abs=1e-15)


def test_fnd_t17_reference_selection_is_reproducible_and_unresolved_is_explicit() -> None:
    base = {"a": np.array([1 + 0j]), "gamma": np.array([1 + 0j]), "h_ris": 1 + 0j, "h_baseline": 2 + 0j, "h_total": 3 + 0j}
    rows = []
    for rule, order in (("midpoint", 8), ("midpoint", 16), ("tensor_product_gauss_legendre", 16)):
        rows.append({**base, "quadrature_rule": rule, "quadrature_order_x": order, "quadrature_order_y": order})
    assert select_internal_reference(rows) is rows[1]
    assert select_internal_reference(rows) is rows[1]

    rows[2] = {**rows[2], "a": np.array([2 + 0j]), "h_ris": 2 + 0j, "h_total": 4 + 0j}
    with pytest.raises(ValueError, match="unresolved internal refined numerical reference"):
        select_internal_reference(rows)


def test_fnd_t18_reference_only_normalization_and_deep_null_semantics() -> None:
    reference = {"a": np.array([1 + 0j, -1 + 0j]), "gamma": np.ones(2, dtype=complex), "h_ris": 0j, "h_baseline": 0j, "h_total": 0j}
    candidate = {**reference, "h_ris": 1e-6 + 0j, "h_total": 1e-6 + 0j}
    metrics = compare_to_reference(candidate, reference)

    assert metrics["complex_robust_rel_error_h_ris"] == pytest.approx(5e-7)
    assert metrics["magnitude_error_db_h_ris"] is None
    assert metrics["phase_error_rad_h_ris"] is None
    assert metrics["reason"] == "deep_cancellation"
    assert all(np.isfinite(value) for key, value in metrics.items() if isinstance(value, float))


def test_gl16_and_gl32_construction_is_fixed_control_grid() -> None:
    ris = create_smart_space_scene("Current").ris_surfaces[0]
    gl16 = tensor_product_gauss_legendre(ris, 16, 16)
    gl32 = tensor_product_gauss_legendre(ris, 32, 32)
    assert gl16.control_count == gl32.control_count == ris.cell_count
    assert gl16.sample_count == ris.cell_count * 16 * 16
    assert gl32.sample_count == ris.cell_count * 32 * 32
    assert np.array_equal(gl16.parent_control_index[:: 16 * 16], np.arange(ris.cell_count))
    assert np.array_equal(gl32.parent_control_index[:: 32 * 32], np.arange(ris.cell_count))


def test_conditional_32_reference_runs_both_rules_and_is_measured_separately(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import airmirror_future.experiments.fnd_qa_ap_01 as qa

    original_select = qa.select_internal_reference
    original_evaluate = qa.evaluate_quadrature
    select_calls: list[int] = []
    evaluated: list[tuple[str, int, int]] = []

    def force_conditional(rows: list[dict[str, object]]) -> dict[str, object]:
        select_calls.append(len(rows))
        if len(rows) == 6:
            raise ValueError("forced base reference failure")
        return rows[-1]

    def record_evaluate(scene: object, pattern: np.ndarray, spec: object, *, engine: object = None) -> dict[str, object]:
        evaluated.append((str(spec.rule), int(spec.order_x), int(spec.order_y)))
        return original_evaluate(scene, pattern, spec, engine=engine)

    monkeypatch.setattr(qa, "select_internal_reference", force_conditional)
    monkeypatch.setattr(qa, "evaluate_quadrature", record_evaluate)
    raw_path, _, run_path = run(
        tmp_path / "conditional",
        generations=("Current",),
        geometry_cases=("near_field",),
        include_random=False,
    )
    assert select_calls == [6, 8, 6, 8]
    assert ("midpoint", 32, 32) in evaluated
    assert ("tensor_product_gauss_legendre", 32, 32) in evaluated
    run_metadata = json.loads(run_path.read_text(encoding="utf-8"))
    assert run_metadata["conditional_32_runtime_s"] > 0.0
    assert run_metadata["conditional_32_peak_rss_mb"] is None or run_metadata["conditional_32_peak_rss_mb"] > 0.0
    with raw_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["reference_row_id"].split("|")[-1] for row in rows} == {"32x32"}


def test_runner_runtime_rss_and_reference_identity_metadata(tmp_path: Path) -> None:
    raw_path, summary_path, run_path = run(
        tmp_path / "metadata",
        generations=("Current",),
        geometry_cases=("near_field",),
        include_random=False,
    )
    with raw_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(float(row["quadrature_runtime_s"]) >= 0.0 for row in rows)
    assert all(row["reference_row_id"].startswith(row["series_identity"] + "|") for row in rows)
    assert all(row["quadrature_peak_rss_mb"] == "" or float(row["quadrature_peak_rss_mb"]) > 0.0 for row in rows)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert all(record["series_runtime_s"] > 0.0 for record in summary["records"])
    assert all(record["series_peak_rss_mb"] is None or record["series_peak_rss_mb"] > 0.0 for record in summary["records"])
    metadata = json.loads(run_path.read_text(encoding="utf-8"))
    assert metadata["run_runtime_s"] > 0.0
    assert metadata["run_peak_rss_mb"] is None or metadata["run_peak_rss_mb"] > 0.0
    assert metadata["conditional_32_runtime_s"] >= 0.0


def test_deep_null_reason_and_ris_gain_use_reference_only_total_scale() -> None:
    reference = {
        "a": np.array([1 + 0j, -1 + 0j]),
        "gamma": np.ones(2, dtype=complex),
        "h_ris": 0j,
        "h_baseline": 10 + 0j,
        "h_total": 10 + 0j,
    }
    # Candidate total is deep-null against the fixed S_total=12, while the
    # robust complex error is finite and can be made to pass another gate.
    candidate = {**reference, "h_ris": -10 + 0j, "h_total": 1e-6 + 0j}
    metrics = compare_to_reference(candidate, reference)
    assert metrics["s_total"] == pytest.approx(12.0)
    assert metrics["candidate_deep_null_h_total"]
    assert metrics["magnitude_error_db_h_total"] is None
    assert metrics["phase_error_rad_h_total"] is None
    assert metrics["reason"] == "deep_cancellation"


def test_nonfinite_values_are_hard_failures_and_not_serializable() -> None:
    reference = {"a": np.array([1 + 0j]), "gamma": np.array([1 + 0j]), "h_ris": 1 + 0j, "h_baseline": 1 + 0j, "h_total": 2 + 0j}
    with pytest.raises(ValueError, match="non-finite"):
        compare_to_reference({**reference, "a": np.array([np.nan + 0j])}, reference)
    with pytest.raises(ValueError, match="non-finite"):
        compare_to_reference({**reference, "h_total": complex(float("inf"), 0.0)}, reference)
    with pytest.raises(ValueError, match="non-finite"):
        _assert_json_finite({"coefficient": [[float("nan"), 0.0]]})


def test_thread_policy_rejects_incompatible_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    with pytest.raises(RuntimeError, match="single-process/single-thread"):
        _enforce_thread_process_policy()


def test_random_patterns_and_snapshot_hashes_are_deterministic_and_context_separated() -> None:
    ris = create_smart_space_scene("Advanced").ris_surfaces[0]
    first = deterministic_random_pattern(ris, "Advanced", "near_field", 1101)
    second = deterministic_random_pattern(ris, "Advanced", "near_field", 1101)
    other = deterministic_random_pattern(ris, "Advanced", "default_target", 1101)

    assert np.array_equal(first, second)
    assert not np.array_equal(first, other)
    assert canonical_pattern_hash(ris, first) == canonical_pattern_hash(ris, second)
    assert set(np.unique(first)) <= set(np.arange(8) * (2 * np.pi / 8))


def test_runner_smoke_writes_partial_c2_artifacts_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "qa-ap-smoke"
    raw_path, summary_path, run_path = run(output, generations=("Current",), geometry_cases=("near_field",), include_random=False)

    assert raw_path.name == "fnd_qa_ap_01_raw.csv"
    assert summary_path.name == "fnd_qa_ap_01_summary.json"
    assert run_path.name == "fnd_qa_ap_01_run.json"
    with raw_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) in {12, 16}
    assert {row["provenance_status"] for row in rows} == {"partial"}
    assert {row["quadrature_policy_id"] for row in rows} == {"fnd_qa_ap_candidate"}
    assert all("FND-QA-CC" in row["pending_contracts_json"] for row in rows)
    assert {row["pattern_seed"] for row in rows} == {""}
    assert len({row["series_identity"] for row in rows}) == 2
    assert len({row["pattern_hash"] for row in rows}) == 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["provenance_status"] == "partial"
    assert summary["reference_artifact_identity"].startswith("sha256:")

    with pytest.raises(FileExistsError):
        run(output, generations=("Current",), geometry_cases=("near_field",), include_random=False)
