from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.experiments.fnd_qa_ap_01 import (
    canonical_pattern_hash,
    evaluate_quadrature,
    _scene_for_case,
    _pattern_for_series,
    tagged_series_identity,
)
from airmirror_future.experiments.fnd_qa_ap_reference_resolution import (
    CONTINUATION_CONFIG_IDENTITY,
    PARENT_CONFIG_IDENTITY,
    PARENT_RUN_ID,
    REFERENCE_TOLERANCE,
    UNRESOLVED_SCOPE,
    _convergence_metrics,
    _m8_result,
    evaluate_chunked,
    load_parent_scope,
    resolve_one_series,
    run_continuation,
)
from airmirror_future.ris.quadrature import midpoint_quadrature, tensor_product_gauss_legendre
from airmirror_future.simulation.engine import SimulationEngine


@pytest.fixture(autouse=True)
def _threads(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "BLIS_NUM_THREADS": "1",
        "MKL_DYNAMIC": "FALSE",
    }.items():
        monkeypatch.setenv(key, value)


def test_scope_exactly_seven_and_five_random_seeds() -> None:
    _, rows = load_parent_scope()
    assert len(UNRESOLVED_SCOPE) == 7
    assert {(r["pattern_class"], None if r["pattern_seed"] == "" else int(r["pattern_seed"])) for r in rows} == set(UNRESOLVED_SCOPE)
    assert {int(seed) for kind, seed in UNRESOLVED_SCOPE if kind == "random_legal"} == {1101, 2203, 3307, 4409, 5511}


def test_parent_v1_hash_and_series_identity_reproduce() -> None:
    _, parent_rows = load_parent_scope()
    scene, focus, _ = _scene_for_case("Future", "near_field")
    engine = SimulationEngine()
    ris = scene.ris_surfaces[0]
    for pattern_class, pattern_seed in sorted(UNRESOLVED_SCOPE, key=str):
        pattern, _ = _pattern_for_series(scene, focus, "near_field", pattern_class, pattern_seed, engine)
        pattern_hash = canonical_pattern_hash(ris, pattern)
        identity = tagged_series_identity({
            "generation": "Future", "geometry_case": "near_field", "pattern_class": pattern_class,
            "pattern_seed": pattern_seed, "pattern_hash": pattern_hash, "frequency_hz": scene.frequency_hz,
            "profile_identity": engine.profile_identity, "world_model_id": "controller_nominal",
            "random_seed": scene.random_seed, "baseline_identity": "controller_baseline_v1",
            "aperture_identity": [ris.width_m, ris.height_m], "control_grid_identity": [ris.nx, ris.ny],
        })
        matches = [r for r in parent_rows if r["pattern_class"] == pattern_class and (None if r["pattern_seed"] == "" else int(r["pattern_seed"])) == pattern_seed]
        assert {r["pattern_hash"] for r in matches} == {pattern_hash}
        assert {r["series_identity"] for r in matches} == {identity}


def test_m64_gl64_directional_rules_and_parent_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    _, parent_rows = load_parent_scope()
    calls: list[tuple[str, int]] = []
    from airmirror_future.experiments import fnd_qa_ap_reference_resolution as continuation
    original = continuation.evaluate_chunked

    def capture(scene, pattern, spec, *, engine, chunk_size):
        calls.append((spec.rule, spec.order_x))
        return original(scene, pattern, spec, engine=engine, chunk_size=chunk_size)

    result = resolve_one_series(parent_rows, pattern_class="ris_only_focus", pattern_seed=None, evaluator=capture)
    assert calls == [("midpoint", 8), ("midpoint", 32), ("midpoint", 64), ("tensor_product_gauss_legendre", 64)]
    assert result["selected_reference_row_id"] is None or result["selected_reference_row_id"].endswith("|midpoint|64x64")
    assert result["successive_m64_vs_m32"]["a_n"] >= 0.0
    assert result["cross_rule_gl64_vs_m64"]["h_total"] >= 0.0


def test_unresolved_after_64_is_blocking_and_no_m128(monkeypatch: pytest.MonkeyPatch) -> None:
    _, parent_rows = load_parent_scope()
    from airmirror_future.experiments import fnd_qa_ap_reference_resolution as continuation

    def fake(scene, pattern, spec, *, engine, chunk_size):
        value = float(spec.order_x)
        return {"a": np.array([value + 0j]), "gamma": np.array([1 + 0j]), "h_ris": value + 0j, "h_baseline": 1 + 0j, "h_total": value + 1j * 0}

    result = resolve_one_series(parent_rows, pattern_class="ris_only_focus", pattern_seed=None, evaluator=fake)
    assert result["status"] == "unresolved_blocking"
    assert result["selected_reference_row_id"] is None
    assert "m128" not in repr(result).lower()


def test_m8_vs_m64_production_evaluation_and_chunk_equivalence() -> None:
    scene, focus, _ = _scene_for_case("Future", "near_field")
    engine = SimulationEngine()
    ris = scene.ris_surfaces[0]
    pattern, _ = _pattern_for_series(scene, focus, "near_field", "ris_only_focus", None, engine)
    spec = midpoint_quadrature(ris, 8)
    direct = evaluate_quadrature(scene, pattern, spec, engine=engine)
    chunked = evaluate_chunked(scene, pattern, spec, engine=engine, chunk_size=17)
    assert np.array_equal(direct["a"], chunked["a"])
    assert direct["h_ris"] == pytest.approx(chunked["h_ris"], rel=1e-13, abs=1e-18)
    assert direct["h_total"] == pytest.approx(chunked["h_total"], rel=1e-13, abs=1e-18)
    result = _m8_result(direct, chunked)
    assert result["status"] in {"pass", "fail"}
    assert set(result["metrics"]) >= {"a_inf_robust_rel_error", "complex_robust_rel_error_h_ris", "complex_robust_rel_error_h_total"}


def test_nonfinite_and_no_overwrite(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _convergence_metrics({"a": np.array([np.nan + 0j]), "gamma": np.array([1 + 0j]), "h_ris": 1 + 0j, "h_baseline": 1 + 0j, "h_total": 2 + 0j}, {"a": np.array([1 + 0j]), "gamma": np.array([1 + 0j]), "h_ris": 1 + 0j, "h_baseline": 1 + 0j, "h_total": 2 + 0j})
    with pytest.raises(RuntimeError, match="disabled"):
        run_continuation(tmp_path / "forbidden", execute=False)


def test_continuation_output_is_no_overwrite_without_formal_physics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from airmirror_future.experiments import fnd_qa_ap_reference_resolution as continuation

    fake_result = {
        "generation": "Future", "geometry_case": "near_field", "pattern_class": "ris_only_focus",
        "pattern_seed": None, "pattern_hash": "sha256:pattern", "series_identity": "sha256:series",
        "parent_run_id": PARENT_RUN_ID, "parent_config_identity": PARENT_CONFIG_IDENTITY,
        "continuation_config_identity": CONTINUATION_CONFIG_IDENTITY,
        "successive_m64_vs_m32": {"a_n": 0.0, "h_ris": 0.0, "h_total": 0.0, "pass": True},
        "cross_rule_gl64_vs_m64": {"a_n": 0.0, "h_ris": 0.0, "h_total": 0.0, "pass": True},
        "status": "resolved", "selected_reference_row_id": "sha256:series|midpoint|64x64",
        "m8_vs_m64": {"status": "pass", "reason": "", "metrics": {}},
        "coefficient": [[0.0, 0.0]], "series_runtime_s": 0.0, "series_peak_rss_mb": 1.0,
        "_values": {},
    }
    monkeypatch.setattr(continuation, "resolve_one_series", lambda *args, **kwargs: dict(fake_result))
    output = tmp_path / "continuation"
    run_continuation(output)
    with pytest.raises(FileExistsError):
        run_continuation(output)


def test_frozen_config_and_continuation_linkage() -> None:
    config = json.loads(Path("configs/foundation_0_1_1/fnd_qa_ap_01_preregistration_v1.json").read_text(encoding="utf-8"))
    continuation = json.loads(Path("configs/foundation_0_1_1/fnd_qa_ap_reference_resolution_v1.json").read_text(encoding="utf-8"))
    assert config["identity"]["config_identity"] == PARENT_CONFIG_IDENTITY
    assert continuation["parent_run_id"] == PARENT_RUN_ID
    assert continuation["parent_config_identity"] == PARENT_CONFIG_IDENTITY
    assert continuation["identity"]["config_identity"] == CONTINUATION_CONFIG_IDENTITY
