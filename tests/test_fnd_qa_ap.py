from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.experiments.fnd_qa_ap_01 import (
    canonical_pattern_hash,
    compare_to_reference,
    deterministic_random_pattern,
    evaluate_quadrature,
    run,
    select_internal_reference,
)
from airmirror_future.ris.quadrature import midpoint_quadrature, tensor_product_gauss_legendre
from airmirror_future.ris.phase import generate_ris_only_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine


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
