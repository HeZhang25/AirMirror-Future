"""Post-result, versioned FND-QA-AP reference-resolution continuation.

This is intentionally separate from the signed/frozen v1 runner.  It replays
only the seven unresolved Future/near_field series from the immutable v1
parent run and extends the reference hierarchy to M64/GL64.  It does not edit
the v1 artifacts or change production quadrature policy.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Iterator

import numpy as np

from airmirror_future.experiments.fnd_qa_ap_01 import (
    GEOMETRY_CASES,
    MAGNITUDE_TOLERANCE_DB,
    PHASE_TOLERANCE_RAD,
    PRODUCTION_TOLERANCE,
    THREAD_ENVIRONMENT,
    _PeakRSSMeter,
    _assert_json_finite,
    _enforce_thread_process_policy,
    _process_peak_rss_mb,
    _pattern_for_series,
    _scene_for_case,
    _require_finite_array,
    _require_finite_complex,
    canonical_pattern_hash,
    compare_to_reference,
    evaluate_quadrature,
    tagged_series_identity,
)
from airmirror_future.experiments.run_output import _REPOSITORY_ROOT
from airmirror_future.physics.ris_scattering import _ris_aperture_point_contributions
from airmirror_future.ris.quadrature import (
    _rule_nodes_weights,
    midpoint_quadrature,
    tensor_product_gauss_legendre,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.profiles import PropagationPathContext


CONTINUATION_SCHEMA_ID = "airmirror_fnd_qa_ap_reference_resolution"
CONTINUATION_SCHEMA_VERSION = 1
CONTINUATION_CONFIG_PATH = _REPOSITORY_ROOT / "configs" / "foundation_0_1_1" / "fnd_qa_ap_reference_resolution_v1.json"
CONTINUATION_CONFIG_IDENTITY = "sha256:f8ef11480880493695eb6d41257c74a540b74e3f6969ea3f7eab1b859d23a7a2"
PARENT_EVIDENCE_MANIFEST_PATH = _REPOSITORY_ROOT / "configs" / "foundation_0_1_1" / "fnd_qa_ap_reference_resolution_parent_evidence_v1.json"
PARENT_RUN_ID = "20260906T094526-de4745c3"
PARENT_CONFIG_IDENTITY = "sha256:94dd4bf50ff0a5c5246980577ef4731e2e5d8504fa44fa1f56c4282ff4113cf7"
PARENT_ARTIFACT_IDENTITIES = {
    "raw": "sha256:2bea31fe69cf7aa4ae703411b86b3bdf075f99be2b9ca4a387f4f034d1f26a78",
    "run": "sha256:c2ced0eb1bb7f3b9592792621cd533f0c72f000fa9889f481b45e9b3eac53b8b",
    "summary": "sha256:9627c3689a5ac547aeb7e021d7188310a9987a2d801811dee1188ee21d1679a4",
    "coefficients": "sha256:1b3df9e155f0eb841ac44fb0086df2253214434b3e241161ed1cae53a2fc5454",
}
PARENT_EVIDENCE_MANIFEST_IDENTITY = "sha256:a035712d3ac477ba334c1c13a7c49708e9191589ec717eb98ad6e1ee59065208"
REFERENCE_TOLERANCE = 1.0e-3
M64_CHUNK_SIZE = 4096

UNRESOLVED_SCOPE: frozenset[tuple[str, int | None]] = frozenset({
    ("ris_only_focus", None),
    ("coherent_target_focus", None),
    ("random_legal", 1101),
    ("random_legal", 2203),
    ("random_legal", 3307),
    ("random_legal", 4409),
    ("random_legal", 5511),
})

EXPECTED_PARENT_SCOPE: tuple[tuple[str, int | None, str, str], ...] = (
    ("ris_only_focus", None, "sha256:85f3702ea6638c260deb89953dcd4d5c90c2704bdd19929e0e308f3aba525446", "sha256:7e5e5ddf889838463097bdb5d36747bf0530e1b310aecc22e6fba1c5973b4007"),
    ("coherent_target_focus", None, "sha256:856a800d43b8238c1034803b4359a81d368801a30452241a30fd019a23ff90c0", "sha256:91e8c6ba2f6db3cc963d2c510edca2766de2a24a1af23e620fa99fe0be9672e7"),
    ("random_legal", 1101, "sha256:b22186a05288748c9035c2c8b85487bdf6d4ac7160437d1a581a7c64af0174a6", "sha256:6da1821ff698d92825b327be55383ee83a47c82863271e1ddf5f587370f054ce"),
    ("random_legal", 2203, "sha256:4ad8985613f656537aa7663e3203280fff12c103f889d9c30624e936c02c313a", "sha256:b2ea986c95b333fed1a50f6f745d3808f9849e70838294b034f9062291103b52"),
    ("random_legal", 3307, "sha256:6e49d812d3bb820c4c3be3c2623f09af5fa023de63c35b6e352849d43fee62e3", "sha256:a972ee98973a5669c9d0566e9be765eb50a1fef53c3fe0aecec0c9af3612781e"),
    ("random_legal", 4409, "sha256:c2c704941ef88e52d190025e0df89932ca8ff90367ce2c1c1a1111b41377e537", "sha256:78e2485ee0ed85caeedddafda0022dce8a84153eef891c1b4cadb50bb7e53228"),
    ("random_legal", 5511, "sha256:1997d9c3301997677fc8279f1997ea4f1f88d959b84621d018644f2d6df1ca84", "sha256:8dd4819ab629e1ea5e1459a951dd40e0ad2b724c85ce5fcaa58af8ce70e0c92a"),
)


class StreamingQuadratureSpec:
    """Lazy experiment-layer quadrature descriptor for high-order rules.

    Unlike :class:`QuadratureSpec`, this object owns only rule metadata and
    emits bounded arrays one parent-major chunk at a time.  It is deliberately
    private to the continuation experiment; production quadrature APIs remain
    unchanged.
    """

    __slots__ = ("ris", "rule", "order_x", "order_y")

    def __init__(self, ris: Any, rule: str, order_x: int, order_y: int) -> None:
        self.ris = ris
        self.rule = rule
        self.order_x = int(order_x)
        self.order_y = int(order_y)

    @property
    def sample_count(self) -> int:
        return int(self.ris.cell_count * self.order_x * self.order_y)

    @property
    def control_count(self) -> int:
        return int(self.ris.cell_count)

    def iter_chunks(self, chunk_size: int) -> Iterator[tuple[np.ndarray, np.ndarray, np.ndarray]]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        nodes_x, weights_x = _rule_nodes_weights(self.rule, self.order_x)
        nodes_y, weights_y = _rule_nodes_weights(self.rule, self.order_y)
        tangent = np.array((-np.sin(self.ris.yaw_rad), np.cos(self.ris.yaw_rad), 0.0))
        vertical = np.array((0.0, 0.0, 1.0))
        center = self.ris.position.as_array()
        pitch_x = self.ris.width_m / self.ris.nx
        pitch_y = self.ris.height_m / self.ris.ny
        coordinates: list[np.ndarray] = []
        weights: list[float] = []
        parents: list[int] = []

        def flush() -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
            if not coordinates:
                return None
            result = (np.asarray(coordinates, dtype=float), np.asarray(weights, dtype=float), np.asarray(parents, dtype=np.int64))
            coordinates.clear()
            weights.clear()
            parents.clear()
            return result

        for iy in range(self.ris.ny):
            for ix in range(self.ris.nx):
                cell_center = center + (((ix + 0.5) / self.ris.nx - 0.5) * self.ris.width_m) * tangent
                cell_center = cell_center + (((iy + 0.5) / self.ris.ny - 0.5) * self.ris.height_m) * vertical
                parent = iy * self.ris.nx + ix
                for local_y, wy in zip(nodes_y, weights_y):
                    for local_x, wx in zip(nodes_x, weights_x):
                        coordinates.append(cell_center + local_x * pitch_x * tangent + local_y * pitch_y * vertical)
                        weights.append(float(wx * wy))
                        parents.append(parent)
                        if len(coordinates) >= chunk_size:
                            result = flush()
                            assert result is not None
                            yield result
        result = flush()
        if result is not None:
            yield result


def streaming_quadrature(ris: Any, *, rule: str, order_x: int, order_y: int | None = None) -> StreamingQuadratureSpec:
    """Build a lazy quadrature descriptor without materializing all samples."""
    return StreamingQuadratureSpec(ris, rule, order_x, order_x if order_y is None else order_y)


def _parent_path(parent_run: Path | None) -> Path:
    return Path(parent_run) if parent_run is not None else (
        _REPOSITORY_ROOT / "results" / "foundation_0_1_1" / "qa_ap" / PARENT_RUN_ID
    )


def _scope_key(row: dict[str, str]) -> tuple[str, int | None]:
    seed = row.get("pattern_seed", "")
    return row["pattern_class"], None if seed == "" else int(seed)


def _load_parent_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(PARENT_EVIDENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("immutable parent-evidence manifest is unavailable or invalid") from exc
    if manifest.get("parent_run_id") != PARENT_RUN_ID or manifest.get("parent_config_identity") != PARENT_CONFIG_IDENTITY:
        raise ValueError("parent-evidence manifest linkage mismatch")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or {key: artifacts.get(key, {}).get("sha256") for key in PARENT_ARTIFACT_IDENTITIES} != PARENT_ARTIFACT_IDENTITIES:
        raise ValueError("parent-evidence manifest artifact identities mismatch")
    entries = manifest.get("unresolved_scope")
    if not isinstance(entries, list) or len(entries) != 7:
        raise ValueError("parent-evidence manifest must contain exactly seven entries")
    actual = tuple((entry.get("pattern_class"), entry.get("pattern_seed"), entry.get("pattern_hash"), entry.get("series_identity")) for entry in entries)
    if set(actual) != {(kind, seed, pattern, series) for kind, seed, pattern, series in EXPECTED_PARENT_SCOPE}:
        raise ValueError("parent-evidence manifest scope or identities mismatch")
    identity = manifest.get("identity")
    if not isinstance(identity, dict) or identity.get("config_identity") != PARENT_EVIDENCE_MANIFEST_IDENTITY:
        raise ValueError("parent-evidence manifest identity is missing or unexpected")
    if identity:
        excluded = set(identity.get("canonicalization", {}).get("excluded_top_level_fields", ["identity"]))
        unsigned = {key: value for key, value in manifest.items() if key not in excluded}
        def tag(value: object) -> object:
            if value is None: return ["null", None]
            if type(value) is bool: return ["bool", value]
            if type(value) is int: return ["int", str(value)]
            if type(value) is float: return ["float64_hex", value.hex()]
            if type(value) is str: return ["str", value]
            if isinstance(value, list): return [tag(item) for item in value]
            if isinstance(value, dict): return {str(key): tag(value[key]) for key in sorted(value)}
            raise TypeError(type(value).__name__)
        encoded = json.dumps(tag(unsigned), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        actual_identity = "sha256:" + hashlib.sha256(encoded).hexdigest()
        if actual_identity != PARENT_EVIDENCE_MANIFEST_IDENTITY:
            raise ValueError("parent-evidence manifest identity mismatch")
    return manifest


def _validate_continuation_config() -> None:
    """Validate the versioned continuation identity before any formal work."""
    try:
        payload = json.loads(CONTINUATION_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("continuation config is unavailable or invalid") from exc
    if payload.get("parent_run_id") != PARENT_RUN_ID or payload.get("parent_config_identity") != PARENT_CONFIG_IDENTITY:
        raise ValueError("continuation parent linkage mismatch")
    evidence = payload.get("parent_evidence", {}).get("artifact_identities")
    if evidence != PARENT_ARTIFACT_IDENTITIES:
        raise ValueError("continuation parent artifact identities mismatch")
    identity = payload.get("identity", {})
    expected = identity.get("config_identity")
    excluded = set(identity.get("canonicalization", {}).get("excluded_top_level_fields", ["identity"]))
    unsigned = {key: value for key, value in payload.items() if key not in excluded}

    def tag(value: object) -> object:
        if value is None:
            return ["null", None]
        if type(value) is bool:
            return ["bool", value]
        if type(value) is int:
            return ["int", str(value)]
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("continuation config contains non-finite number")
            return ["float64_hex", value.hex()]
        if type(value) is str:
            return ["str", value]
        if isinstance(value, list):
            return [tag(item) for item in value]
        if isinstance(value, dict):
            return {str(key): tag(value[key]) for key in sorted(value)}
        raise TypeError(type(value).__name__)

    encoded = json.dumps(tag(unsigned), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    actual = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if expected != CONTINUATION_CONFIG_IDENTITY or actual != CONTINUATION_CONFIG_IDENTITY:
        raise ValueError("continuation config identity mismatch")


def synthetic_parent_scope() -> list[dict[str, str]]:
    """Return immutable manifest-backed rows for CI tests without v1 artifacts."""
    manifest = _load_parent_manifest()
    rows: list[dict[str, str]] = []
    for entry in manifest["unresolved_scope"]:
        rows.append({
            "generation": "Future",
            "geometry_case": "near_field",
            "pattern_class": entry["pattern_class"],
            "pattern_seed": "" if entry["pattern_seed"] is None else str(entry["pattern_seed"]),
            "pattern_hash": entry["pattern_hash"],
            "series_identity": entry["series_identity"],
            "reason": "unresolved_reference",
        })
    return rows


def _validate_parent_artifacts(root: Path) -> None:
    filenames = {
        "raw": "fnd_qa_ap_01_raw.csv",
        "run": "fnd_qa_ap_01_run.json",
        "summary": "fnd_qa_ap_01_summary.json",
        "coefficients": "fnd_qa_ap_01_coefficients.json",
    }
    for key, filename in filenames.items():
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(f"v1 parent artifacts are incomplete: {root}")
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != PARENT_ARTIFACT_IDENTITIES[key]:
            raise ValueError(f"blocking parent artifact hash mismatch: {key}")


def load_parent_scope(parent_run: Path | None = None) -> tuple[Path, list[dict[str, str]]]:
    """Load and validate exactly the seven immutable v1 unresolved series."""
    _load_parent_manifest()
    root = _parent_path(parent_run)
    _validate_parent_artifacts(root)
    raw_path = root / "fnd_qa_ap_01_raw.csv"
    run_path = root / "fnd_qa_ap_01_run.json"
    if not raw_path.is_file() or not run_path.is_file():
        raise FileNotFoundError(f"v1 parent artifacts are incomplete: {root}")
    metadata = json.loads(run_path.read_text(encoding="utf-8"))
    if metadata.get("run_id") != PARENT_RUN_ID:
        raise ValueError("parent run_id mismatch")
    frozen_config_path = _REPOSITORY_ROOT / "configs" / "foundation_0_1_1" / "fnd_qa_ap_01_preregistration_v1.json"
    frozen_config = json.loads(frozen_config_path.read_text(encoding="utf-8"))
    if frozen_config.get("identity", {}).get("config_identity") != PARENT_CONFIG_IDENTITY:
        raise ValueError("parent frozen config identity mismatch")
    with raw_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    scoped = [row for row in rows if row.get("generation") == "Future" and row.get("geometry_case") == "near_field"]
    keys = {_scope_key(row) for row in scoped}
    if keys != set(UNRESOLVED_SCOPE):
        raise ValueError(f"parent Future/near_field scope mismatch: {sorted(keys)!r}")
    identities = {(key, row.get("series_identity", ""), row.get("pattern_hash", "")) for key in keys for row in scoped if _scope_key(row) == key}
    if len(identities) != 7 or any(not series or not pattern for _, series, pattern in identities):
        raise ValueError("parent scope does not contain seven unique pattern/series identities")
    for key, series, _ in identities:
        if not any(_scope_key(row) == key and row.get("series_identity") == series and row.get("reason") == "unresolved_reference" for row in scoped):
            raise ValueError("parent scope contains a resolved series or missing unresolved marker")
    return root, scoped


def parent_scope_for_tests() -> list[dict[str, str]]:
    """Manifest-backed synthetic parent rows for CI-portable focused tests."""
    return synthetic_parent_scope()


def _validate_parent_identity(
    parent_rows: list[dict[str, str]],
    *,
    pattern_class: str,
    pattern_seed: int | None,
    pattern_hash: str,
    series_identity: str,
) -> None:
    matches = [row for row in parent_rows if _scope_key(row) == (pattern_class, pattern_seed)]
    if not matches or any(row.get("pattern_hash") != pattern_hash or row.get("series_identity") != series_identity for row in matches):
        raise ValueError("blocking parent pattern_hash/series_identity mismatch")


def evaluate_chunked(
    scene: Any,
    pattern: np.ndarray,
    spec: Any,
    *,
    engine: SimulationEngine,
    chunk_size: int = M64_CHUNK_SIZE,
) -> dict[str, Any]:
    """Streaming coefficient evaluation preserving the v1 quadrature math."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not isinstance(spec, StreamingQuadratureSpec) and spec.sample_count < chunk_size:
        return evaluate_quadrature(scene, pattern, spec, engine=engine)
    ris = scene.ris_surfaces[0]
    tx = scene.transmitter()
    rx = scene.receiver()
    pattern = np.asarray(pattern, dtype=float)
    _require_finite_array(pattern, "continuation commanded pattern")
    coefficient_ris = replace(ris, reflection_efficiency=1.0)
    coefficients = np.zeros(ris.cell_count, dtype=complex)
    chunks = spec.iter_chunks(chunk_size) if isinstance(spec, StreamingQuadratureSpec) else (
        (spec.sample_coordinates[start:end], spec.weights[start:end], spec.parent_control_index[start:end])
        for start in range(0, spec.sample_count, chunk_size)
        for end in [min(start + chunk_size, spec.sample_count)]
    )
    for sample_coordinates, sample_weights, sample_parents in chunks:
        samples = _ris_aperture_point_contributions(
            tx,
            np.asarray([rx.position.as_array()]),
            rx.gain_linear,
            coefficient_ris,
            sample_coordinates,
            sample_parents,
            sample_weights * ris.cell_area_m2,
            np.zeros(ris.cell_count, dtype=float),
            scene.frequency_hz,
        )[0]
        np.add.at(coefficients, sample_parents, samples)
    incident = engine.profile.environment_modifier(
        scene=scene,
        context=PropagationPathContext("ris_incident", tx.position, ris.position, ris_id=ris.id),
    ).value
    scattered = engine.profile.environment_modifier(
        scene=scene,
        context=PropagationPathContext("ris_scattered", ris.position, rx.position, ris_id=ris.id),
    ).value
    coefficients *= complex(incident) * complex(scattered)
    gamma = math.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern)
    _require_finite_array(coefficients, "continuation coefficient vector")
    _require_finite_array(gamma, "continuation commanded coefficients")
    h_ris = _require_finite_complex(np.dot(coefficients, gamma), "continuation h_ris")
    baseline_result = engine.compute_channel(scene, ris_patterns={})
    h_baseline = _require_finite_complex(baseline_result.los_channel + baseline_result.wall_channel, "continuation h_baseline")
    h_total = _require_finite_complex(h_baseline + h_ris, "continuation h_total")
    return {"a": coefficients, "gamma": gamma, "h_ris": h_ris, "h_baseline": h_baseline, "h_total": h_total}


def _convergence_metrics(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    metrics = compare_to_reference(candidate, reference)
    values = {
        "a_n": metrics["a_inf_robust_rel_error"],
        "h_ris": metrics["complex_robust_rel_error_h_ris"],
        "h_total": metrics["complex_robust_rel_error_h_total"],
    }
    values["pass"] = max(values.values()) <= REFERENCE_TOLERANCE
    return values


def _m8_result(m8: dict[str, Any], m64: dict[str, Any]) -> dict[str, Any]:
    metrics = compare_to_reference(m8, m64)
    magnitude_phase_ok = all(
        value is None or abs(float(value)) <= limit
        for value, limit in (
            (metrics["magnitude_error_db_h_ris"], MAGNITUDE_TOLERANCE_DB),
            (metrics["magnitude_error_db_h_total"], MAGNITUDE_TOLERANCE_DB),
            (metrics["phase_error_rad_h_ris"], PHASE_TOLERANCE_RAD),
            (metrics["phase_error_rad_h_total"], PHASE_TOLERANCE_RAD),
        )
    )
    passed = (
        metrics["a_inf_robust_rel_error"] <= PRODUCTION_TOLERANCE
        and metrics["complex_robust_rel_error_h_ris"] <= PRODUCTION_TOLERANCE
        and metrics["complex_robust_rel_error_h_total"] <= PRODUCTION_TOLERANCE
        and magnitude_phase_ok
    )
    return {"status": "pass" if passed else "fail", "reason": metrics["reason"] or ("failed_threshold" if not passed else ""), "metrics": metrics}


def _row_id(series_identity: str, rule: str, order: int) -> str:
    return f"{series_identity}|{rule}|{order}x{order}"


def resolve_one_series(
    parent_rows: list[dict[str, str]],
    *,
    pattern_class: str,
    pattern_seed: int | None,
    evaluator: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    key = (pattern_class, pattern_seed)
    if key not in UNRESOLVED_SCOPE:
        raise ValueError("continuation scope is exactly the seven frozen unresolved series")
    active_evaluator = evaluate_chunked if evaluator is None else evaluator
    started = time.perf_counter()
    meter = _PeakRSSMeter()
    scene, focus_rx, _ = _scene_for_case("Future", "near_field")
    engine = SimulationEngine()
    ris = scene.ris_surfaces[0]
    pattern, _ = _pattern_for_series(scene, focus_rx, "near_field", pattern_class, pattern_seed, engine)
    pattern_hash = canonical_pattern_hash(ris, pattern)
    series_identity = tagged_series_identity({
        "generation": "Future",
        "geometry_case": "near_field",
        "pattern_class": pattern_class,
        "pattern_seed": pattern_seed,
        "pattern_hash": pattern_hash,
        "frequency_hz": scene.frequency_hz,
        "profile_identity": engine.profile_identity,
        "world_model_id": "controller_nominal",
        "random_seed": scene.random_seed,
        "baseline_identity": "controller_baseline_v1",
        "aperture_identity": [ris.width_m, ris.height_m],
        "control_grid_identity": [ris.nx, ris.ny],
    })
    _validate_parent_identity(parent_rows, pattern_class=pattern_class, pattern_seed=pattern_seed, pattern_hash=pattern_hash, series_identity=series_identity)
    values: dict[tuple[str, int], dict[str, Any]] = {}
    for rule, order in (("midpoint", 8), ("midpoint", 32), ("midpoint", 64), ("tensor_product_gauss_legendre", 64)):
        # Keep the small equivalence/reference grids materialized, but ensure
        # formal M64/GL64 never constructs the 12.58M-sample arrays.
        spec = (
            streaming_quadrature(ris, rule=rule, order_x=order)
            if order >= 64
            else (midpoint_quadrature(ris, order) if rule == "midpoint" else tensor_product_gauss_legendre(ris, order))
        )
        values[(rule, order)] = active_evaluator(scene, pattern, spec, engine=engine, chunk_size=M64_CHUNK_SIZE)
    m8, m32, m64, gl64 = values[("midpoint", 8)], values[("midpoint", 32)], values[("midpoint", 64)], values[("tensor_product_gauss_legendre", 64)]
    successive = _convergence_metrics(m64, m32)
    cross_rule = _convergence_metrics(gl64, m64)
    resolved = bool(successive["pass"] and cross_rule["pass"])
    result = {
        "generation": "Future",
        "geometry_case": "near_field",
        "pattern_class": pattern_class,
        "pattern_seed": pattern_seed,
        "pattern_hash": pattern_hash,
        "series_identity": series_identity,
        "parent_run_id": PARENT_RUN_ID,
        "parent_config_identity": PARENT_CONFIG_IDENTITY,
        "continuation_config_identity": CONTINUATION_CONFIG_IDENTITY,
        "successive_m64_vs_m32": successive,
        "cross_rule_gl64_vs_m64": cross_rule,
        "status": "resolved" if resolved else "unresolved_blocking",
        "selected_reference_row_id": _row_id(series_identity, "midpoint", 64) if resolved else None,
        "m8_vs_m64": _m8_result(m8, m64) if resolved else None,
        "coefficient": [[float(value.real), float(value.imag)] for value in m64["a"]] if resolved else None,
        "series_runtime_s": time.perf_counter() - started,
        "series_peak_rss_mb": meter.finish(),
        "_values": values,
    }
    _assert_json_finite({key: value for key, value in result.items() if key not in {"_values", "coefficient"}})
    return result


def run_continuation(output: Path | None = None, *, parent_run: Path | None = None, execute: bool = True) -> tuple[Path, Path]:
    if not execute:
        raise RuntimeError("formal seven-series continuation execution is disabled for this implementation round")
    _enforce_thread_process_policy()
    _validate_continuation_config()
    parent_root, parent_rows = load_parent_scope(parent_run)
    output_path = Path(output) if output is not None else _REPOSITORY_ROOT / "results" / "foundation_0_1_1" / "qa_ap_reference_resolution" / f"{time.strftime('%Y%m%dT%H%M%S')}-{os.urandom(4).hex()}"
    output_path.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    meter = _PeakRSSMeter()
    results = [resolve_one_series(parent_rows, pattern_class=pattern_class, pattern_seed=pattern_seed) for pattern_class, pattern_seed in sorted(UNRESOLVED_SCOPE, key=lambda item: (item[0], -1 if item[1] is None else item[1]))]
    artifacts = [{key: value for key, value in result.items() if key not in {"_values", "coefficient"}} | {"coefficient": result["coefficient"]} for result in results]
    _assert_json_finite(artifacts)
    coefficient_bytes = json.dumps(artifacts, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    coefficient_identity = "sha256:" + hashlib.sha256(coefficient_bytes).hexdigest()
    coefficient_path = output_path / "fnd_qa_ap_reference_resolution_coefficients.json"
    coefficient_path.write_bytes(coefficient_bytes)
    summary = {
        "schema_id": CONTINUATION_SCHEMA_ID,
        "schema_version": CONTINUATION_SCHEMA_VERSION,
        "run_id": output_path.name,
        "parent_run_id": PARENT_RUN_ID,
        "parent_config_identity": PARENT_CONFIG_IDENTITY,
        "parent_artifact_identities": PARENT_ARTIFACT_IDENTITIES,
        "continuation_config_identity": CONTINUATION_CONFIG_IDENTITY,
        "coefficient_artifact_identity": coefficient_identity,
        "results": [{key: value for key, value in result.items() if key not in {"_values", "coefficient"}} for result in results],
    }
    _assert_json_finite(summary)
    summary_path = output_path / "fnd_qa_ap_reference_resolution_summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    metadata = {
        "schema_id": CONTINUATION_SCHEMA_ID,
        "schema_version": CONTINUATION_SCHEMA_VERSION,
        "run_id": output_path.name,
        "parent_run_id": PARENT_RUN_ID,
        "parent_config_identity": PARENT_CONFIG_IDENTITY,
        "parent_artifact_identities": PARENT_ARTIFACT_IDENTITIES,
        "continuation_config_identity": CONTINUATION_CONFIG_IDENTITY,
        "coefficient_artifact_identity": coefficient_identity,
        "runtime_s": time.perf_counter() - started,
        "peak_rss_mb": meter.finish(),
        "peak_memory_method": "windows_peak_working_set_counter" if os.name == "nt" else "resource_ru_maxrss",
        "blas_environment": {key: os.environ.get(key) for key in THREAD_ENVIRONMENT},
        "parent_artifact_root": str(parent_root),
    }
    _assert_json_finite(metadata)
    run_path = output_path / "fnd_qa_ap_reference_resolution_run.json"
    run_path.write_text(json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return summary_path, run_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--parent-run", type=Path)
    args = parser.parse_args(argv)
    summary, metadata = run_continuation(args.output, parent_run=args.parent_run)
    print(f"SUMMARY: {summary}\nRUN: {metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
