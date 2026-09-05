"""Headless FND-QA-AP-01 quadrature verification runner.

This module is intentionally an experiments-layer implementation.  It keeps
the public RIS pattern shape unchanged, records candidate policy identities as
partial C2 provenance, and never mutates the signed preregistration.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import time
from typing import Any, Iterable

import numpy as np
from ctypes import wintypes

try:
    import resource as _resource
except ImportError:  # pragma: no cover - Windows reference environment
    _resource = None

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import Receiver, Scene, Vec3
from airmirror_future.core.units import watts_to_dbm
from airmirror_future.experiments.provenance import _build_provenance_fields
from airmirror_future.experiments.run_output import _REPOSITORY_ROOT
from airmirror_future.physics.ris_scattering import _ris_aperture_point_contributions
from airmirror_future.ris.generations import generation_preset
from airmirror_future.ris.phase import generate_ris_only_focus_pattern
from airmirror_future.ris.quadrature import QuadratureSpec, midpoint_quadrature, tensor_product_gauss_legendre
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel
from airmirror_future.simulation.profiles import PropagationPathContext
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern


QA_SCHEMA_ID = "airmirror_fnd_qa_ap"
QA_SCHEMA_VERSION = 1
QUADRATURE_POLICY_ID = "fnd_qa_ap_candidate"
QUADRATURE_POLICY_VERSION = "1"
PATTERN_DOMAIN = "airmirror_fnd_qa_ap_commanded_pattern"
PATTERN_SEMANTICS = "commanded_complex_gamma_from_phase_radians_v1"
FLATTEN_ORDER = "ris_cell_centers_meshgrid_xy_c_v1"
TAU = float.fromhex("0x1.921fb54442d18p+2")
A_FLOOR = 1.0e-12
AGGREGATE_FLOOR = 1.0e-12
REFERENCE_TOLERANCE = 0.001
PRODUCTION_TOLERANCE = 0.01
MAGNITUDE_TOLERANCE_DB = 0.1
PHASE_TOLERANCE_RAD = 0.05
DEEP_NULL_RATIO = 0.001
MIDPOINT_ORDERS = ((1, 1), (2, 2), (4, 4), (8, 8), (16, 16))
THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "MKL_DYNAMIC": "FALSE",
}
RANDOM_PATTERN_SEEDS = (1101, 2203, 3307, 4409, 5511)
GEOMETRY_CASES: dict[str, dict[str, tuple[float, float, float]]] = {
    "default_target": {"tx": (1.0, 4.0, 2.4), "focus": (8.5, 4.0, 1.2), "evaluation": (8.5, 4.0, 1.2)},
    "near_field": {"tx": (1.0, 4.0, 2.4), "focus": (6.5, 6.4, 1.5), "evaluation": (6.5, 6.4, 1.5)},
    "oblique_incidence": {"tx": (1.0, 6.0, 2.4), "focus": (8.5, 4.0, 1.2), "evaluation": (8.5, 4.0, 1.2)},
    "off_focus_receiver": {"tx": (1.0, 4.0, 2.4), "focus": (8.5, 4.0, 1.2), "evaluation": (8.5, 6.5, 1.2)},
}


def _finite(value: object) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and math.isfinite(float(value))


def _require_finite_complex(value: object, name: str) -> complex:
    """Validate and return one finite complex scalar."""
    try:
        result = complex(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be complex and non-finite values are not allowed") from exc
    if not (math.isfinite(result.real) and math.isfinite(result.imag)):
        raise ValueError(f"{name} must be complex and non-finite values are not allowed")
    return result


def _require_finite_array(value: object, name: str) -> np.ndarray:
    result = np.asarray(value)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} contains non-finite values")
    return result


def _process_peak_rss_mb() -> float | None:
    """Return process peak RSS/Windows peak working set in MiB when available."""
    try:
        if os.name == "nt":
            class _Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            get_current_process = ctypes.windll.kernel32.GetCurrentProcess
            get_current_process.argtypes = []
            get_current_process.restype = wintypes.HANDLE
            get_info = psapi.GetProcessMemoryInfo
            get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
            get_info.restype = wintypes.BOOL
            if not get_info(get_current_process(), ctypes.byref(counters), counters.cb):
                return None
            # WorkingSetSize is sampled at scope boundaries and accumulated by
            # _PeakRSSMeter.  Using the current working set keeps separate
            # conditional-32 measurements from contaminating the base scope.
            return float(counters.WorkingSetSize) / (1024.0 * 1024.0)
        # ru_maxrss is KiB on Linux and bytes on macOS/BSD.
        if _resource is None:
            return None
        value = float(_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            value /= 1024.0 * 1024.0
        else:
            value /= 1024.0
        return value
    except (AttributeError, OSError, TypeError, ValueError):
        return None


class _PeakRSSMeter:
    """Cheap single-threaded peak measurement for one scoped operation."""

    def __init__(self) -> None:
        self.peak = _process_peak_rss_mb()

    def sample(self) -> None:
        value = _process_peak_rss_mb()
        if value is not None:
            self.peak = value if self.peak is None else max(self.peak, value)

    def finish(self) -> float | None:
        self.sample()
        return self.peak


def _enforce_thread_process_policy() -> dict[str, str]:
    """Fail preflight unless the frozen one-process/thread policy is explicit."""
    for key, expected in THREAD_ENVIRONMENT.items():
        actual = os.environ.get(key)
        if (actual.upper() if key == "MKL_DYNAMIC" and actual is not None else actual) != expected:
            raise RuntimeError(f"frozen single-process/single-thread preflight failed: {key}={actual!r}, expected {expected!r}")
    return {key: os.environ[key] for key in THREAD_ENVIRONMENT}


def canonical_pattern_hash(ris: Any, phase: np.ndarray) -> str:
    """Hash only the commanded phase snapshot using the frozen byte contract."""
    values = validate_commanded_pattern(ris, phase)
    payload = {
        "control_grid_identity": {"flatten_order": FLATTEN_ORDER, "nx": int(ris.nx), "ny": int(ris.ny)},
        "domain_separator": PATTERN_DOMAIN,
        "flatten_order": FLATTEN_ORDER,
        "ordered_phase_binary64_be_hex": [struct.pack(">d", float(value)).hex() for value in values],
        "phase_bits": None if ris.phase_bits is None else int(ris.phase_bits),
        "phase_control_semantics": PATTERN_SEMANTICS,
        "schema_version": 1,
        "shape": [int(ris.nx), int(ris.ny)],
    }
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def deterministic_random_pattern(ris: Any, generation: str, geometry_case: str, pattern_seed: int) -> np.ndarray:
    """Generate the preregistered SHA-256-counter legal commanded pattern."""
    generation_bytes = generation.encode("utf-8")
    geometry_bytes = geometry_case.encode("utf-8")
    result = np.empty(ris.cell_count, dtype=float)
    for parent in range(ris.cell_count):
        blob = (
            b"fnd_qa_ap_pattern_v1\0" + struct.pack("<I", len(generation_bytes)) + generation_bytes
            + struct.pack("<I", len(geometry_bytes)) + geometry_bytes
            + struct.pack("<Q", int(pattern_seed)) + struct.pack("<Q", parent)
        )
        digest = hashlib.sha256(blob).digest()
        raw = int.from_bytes(digest[:8], "little")
        if ris.phase_bits is None:
            mantissa = raw >> 11
            unit = float(mantissa * 2.0 ** -53)
            result[parent] = float(unit * TAU)
        else:
            k = raw % (2 ** int(ris.phase_bits))
            result[parent] = float(TAU * k / (2 ** int(ris.phase_bits)))
    return validate_commanded_pattern(ris, result)


def tagged_series_identity(fields: dict[str, object]) -> str:
    """Create the C1 tagged scalar series identity."""
    def tag(value: object) -> object:
        if value is None:
            return ["null", None]
        if isinstance(value, bool):
            return ["bool", value]
        if isinstance(value, (int, np.integer)):
            return ["int", str(int(value))]
        if isinstance(value, (float, np.floating)):
            if not math.isfinite(float(value)):
                raise ValueError("identity values must be finite")
            return ["float64_hex", float(value).hex()]
        if isinstance(value, str):
            return ["str", value]
        if isinstance(value, dict):
            return {str(k): tag(v) for k, v in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [tag(v) for v in value]
        raise TypeError(f"unsupported identity scalar: {type(value).__name__}")
    encoded = json.dumps(tag(fields), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _scene_for_case(generation: str, case: str) -> tuple[Scene, Receiver, Receiver]:
    if case not in GEOMETRY_CASES:
        raise ValueError(f"unknown geometry case: {case}")
    base = create_smart_space_scene(generation)
    spec = GEOMETRY_CASES[case]
    tx = replace(base.transmitter(), position=Vec3(*spec["tx"]))
    focus_rx = replace(base.receiver(), position=Vec3(*spec["focus"]))
    evaluation_rx = replace(base.receiver(), position=Vec3(*spec["evaluation"]))
    scene = replace(base, transmitters=[tx], receivers=[evaluation_rx])
    return scene, focus_rx, evaluation_rx


def _pattern_for_series(scene: Scene, focus_rx: Receiver, geometry_case: str, pattern_class: str, pattern_seed: int | None, engine: SimulationEngine) -> tuple[np.ndarray, object]:
    ris = scene.ris_surfaces[0]
    tx = scene.transmitter()
    if pattern_class == "ris_only_focus":
        return generate_ris_only_focus_pattern(ris, tx, focus_rx, scene.frequency_hz), generate_ris_only_focus_pattern
    if pattern_class == "coherent_target_focus":
        focus_scene = replace(scene, receivers=[focus_rx])
        return generate_coherent_target_pattern(focus_scene, engine=engine), generate_coherent_target_pattern
    if pattern_class == "random_legal":
        if pattern_seed is None:
            raise ValueError("random_legal requires pattern_seed")
        return deterministic_random_pattern(ris, ris.generation, geometry_case, pattern_seed), generate_ris_only_focus_pattern
    raise ValueError(f"unknown pattern class: {pattern_class}")


def evaluate_quadrature(
    scene: Scene,
    pattern: np.ndarray,
    spec: QuadratureSpec,
    *,
    engine: SimulationEngine | None = None,
) -> dict[str, Any]:
    """Evaluate control-level ``a_n``, ``h_RIS`` and ``h_total`` for one rule."""
    active_engine = engine or SimulationEngine()
    ris = scene.ris_surfaces[0]
    tx = scene.transmitter()
    rx = scene.receiver()
    pattern = validate_commanded_pattern(ris, pattern)
    coefficient_ris = replace(ris, reflection_efficiency=1.0)
    # QuadratureSpec weights are normalized within a control patch; the
    # production kernel's area-normalized amplitude is applied here.
    physical_weights = spec.weights * ris.cell_area_m2
    zero_phase = np.zeros(ris.cell_count, dtype=float)
    samples = _ris_aperture_point_contributions(
        tx, np.asarray([rx.position.as_array()]), rx.gain_linear, coefficient_ris,
        spec.sample_coordinates, spec.parent_control_index, physical_weights,
        zero_phase, scene.frequency_hz,
    )[0]
    incident = active_engine.profile.environment_modifier(
        scene=scene,
        context=PropagationPathContext("ris_incident", tx.position, ris.position, ris_id=ris.id),
    ).value
    scattered = active_engine.profile.environment_modifier(
        scene=scene,
        context=PropagationPathContext("ris_scattered", ris.position, rx.position, ris_id=ris.id),
    ).value
    coefficients = np.zeros(ris.cell_count, dtype=complex)
    np.add.at(coefficients, spec.parent_control_index, samples)
    coefficients *= complex(incident) * complex(scattered)
    gamma = math.sqrt(ris.reflection_efficiency) * np.exp(1j * pattern)
    _require_finite_array(coefficients, "quadrature coefficient vector")
    _require_finite_array(gamma, "quadrature commanded coefficients")
    h_ris = _require_finite_complex(np.dot(coefficients, gamma), "h_ris")
    baseline_result = active_engine.compute_channel(scene, ris_patterns={}, model=ControllerModel())
    h_baseline = _require_finite_complex(baseline_result.los_channel + baseline_result.wall_channel, "h_baseline")
    h_total = _require_finite_complex(h_baseline + h_ris, "h_total")
    return {"a": coefficients, "gamma": gamma, "h_ris": h_ris, "h_baseline": h_baseline, "h_total": h_total}


def _complex_metrics(candidate: complex, reference: complex, scale: float) -> tuple[float, bool, float | None, float | None, str | None]:
    if not all(math.isfinite(v) for v in (candidate.real, candidate.imag, reference.real, reference.imag, scale)):
        raise ValueError("non-finite quadrature metric")
    robust = abs(candidate - reference) / scale
    reference_null = abs(reference) / scale <= DEEP_NULL_RATIO
    candidate_null = abs(candidate) / scale <= DEEP_NULL_RATIO
    if reference_null or candidate_null:
        return robust, scale == AGGREGATE_FLOOR, None, None, "deep_cancellation"
    magnitude = 20.0 * math.log10(abs(candidate) / abs(reference)) if abs(reference) else None
    phase = float(np.angle(candidate * np.conj(reference)))
    return robust, scale == AGGREGATE_FLOOR, magnitude, phase, None


def compare_to_reference(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Apply the frozen reference-only coefficient and aggregate metrics."""
    a = _require_finite_array(candidate["a"], "candidate coefficient vector")
    a_ref = _require_finite_array(reference["a"], "reference coefficient vector")
    if a.shape != a_ref.shape:
        raise ValueError("candidate and reference coefficient vectors must have the same shape")
    a_abs = float(np.max(np.abs(a - a_ref)))
    a_norm = float(np.max(np.abs(a_ref)))
    a_scale = max(a_norm, A_FLOOR)
    h_ris_ref = _require_finite_complex(reference["h_ris"], "reference h_ris")
    h_total_ref = _require_finite_complex(reference["h_total"], "reference h_total")
    h_baseline_ref = _require_finite_complex(reference["h_baseline"], "reference h_baseline")
    h_ris_candidate = _require_finite_complex(candidate["h_ris"], "candidate h_ris")
    h_total_candidate = _require_finite_complex(candidate["h_total"], "candidate h_total")
    gamma = _require_finite_array(reference["gamma"], "reference commanded coefficients")
    if gamma.shape != a_ref.shape:
        raise ValueError("reference coefficient and commanded vectors must have the same shape")
    s_ris = max(float(np.sum(np.abs(a_ref * gamma))), abs(h_ris_ref), AGGREGATE_FLOOR)
    s_total = max(abs(h_baseline_ref) + float(np.sum(np.abs(a_ref * gamma))), abs(h_total_ref), AGGREGATE_FLOOR)
    ris = _complex_metrics(h_ris_candidate, h_ris_ref, s_ris)
    total = _complex_metrics(h_total_candidate, h_total_ref, s_total)
    return {
        "a_inf_abs_error": a_abs,
        "a_inf_robust_rel_error": a_abs / a_scale,
        "reference_a_inf_norm": a_norm,
        "a_normalization_floor_active": a_norm <= A_FLOOR,
        "complex_robust_rel_error_h_ris": ris[0],
        "complex_robust_rel_error_h_total": total[0],
        "normalization_floor_active_h_ris": ris[1],
        "normalization_floor_active_h_total": total[1],
        "reference_deep_null_h_ris": abs(h_ris_ref) / s_ris <= DEEP_NULL_RATIO,
        "candidate_deep_null_h_ris": abs(h_ris_candidate) / s_ris <= DEEP_NULL_RATIO,
        "reference_deep_null_h_total": abs(h_total_ref) / s_total <= DEEP_NULL_RATIO,
        "candidate_deep_null_h_total": abs(h_total_candidate) / s_total <= DEEP_NULL_RATIO,
        "magnitude_error_db_h_ris": ris[2],
        "magnitude_error_db_h_total": total[2],
        "phase_error_rad_h_ris": ris[3],
        "phase_error_rad_h_total": total[3],
        "s_ris": s_ris,
        "s_total": s_total,
        "reason": ris[4] or total[4] or "",
    }


def select_internal_reference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the frozen reference hierarchy, or fail explicitly."""
    by_key = {(r["quadrature_rule"], r["quadrature_order_x"], r["quadrature_order_y"]): r for r in rows}
    midpoint8 = by_key.get(("midpoint", 8, 8))
    midpoint16 = by_key.get(("midpoint", 16, 16))
    gl16 = by_key.get(("tensor_product_gauss_legendre", 16, 16))
    if midpoint8 is None or midpoint16 is None or gl16 is None:
        raise ValueError("reference hierarchy requires midpoint8, midpoint16, and GL16")
    successive = compare_to_reference(midpoint16, midpoint8)
    # Cross-rule comparison uses midpoint16 as the denominator/reference
    # decomposition; neither candidate is allowed to set its own scale.
    cross = compare_to_reference(gl16, midpoint16)
    if max(successive["a_inf_robust_rel_error"], successive["complex_robust_rel_error_h_ris"], successive["complex_robust_rel_error_h_total"], cross["a_inf_robust_rel_error"], cross["complex_robust_rel_error_h_ris"], cross["complex_robust_rel_error_h_total"]) <= REFERENCE_TOLERANCE:
        return midpoint16
    midpoint32 = by_key.get(("midpoint", 32, 32))
    gl32 = by_key.get(("tensor_product_gauss_legendre", 32, 32))
    if midpoint32 is not None and gl32 is not None:
        successive32 = compare_to_reference(midpoint32, midpoint16)
        cross32 = compare_to_reference(gl32, midpoint32)
        if max(
            successive32["a_inf_robust_rel_error"],
            successive32["complex_robust_rel_error_h_ris"],
            successive32["complex_robust_rel_error_h_total"],
            cross32["a_inf_robust_rel_error"],
            cross32["complex_robust_rel_error_h_ris"],
            cross32["complex_robust_rel_error_h_total"],
        ) <= REFERENCE_TOLERANCE:
            return midpoint32
    raise ValueError("unresolved internal refined numerical reference")


def _create_qa_run_directory(output: Path | None) -> tuple[Path, str]:
    path = Path(output) if output is not None else Path("results") / "foundation_0_1_1" / "qa_ap" / f"{time.strftime('%Y%m%dT%H%M%S')}-{os.urandom(4).hex()}"
    if path.resolve() == (_REPOSITORY_ROOT / "results" / "phase_bits").resolve():
        raise ValueError(f"legacy results path is reserved: {path}")
    path.mkdir(parents=True, exist_ok=False)
    return path, path.name


def _quadrature_row_id(series_identity: str, row: dict[str, Any]) -> str:
    """Stable identity for the actual selected row in one series."""
    return (
        f"{series_identity}|{row['quadrature_rule']}|"
        f"{int(row['quadrature_order_x'])}x{int(row['quadrature_order_y'])}"
    )


def _assert_json_finite(value: object, path: str = "artifact") -> None:
    """Reject non-finite values before any QA artifact is written."""
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_json_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_json_finite(item, f"{path}[{index}]")
    elif isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        raise ValueError(f"non-finite value at {path}")


def _derive_gain_and_reason(
    row: dict[str, Any],
    reference: dict[str, Any],
    metrics: dict[str, Any],
    *,
    status_reference: str,
    candidate_status: bool,
) -> tuple[bool, str]:
    """Apply frozen deep-null semantics to RIS gain and final row reason."""
    s_total = float(metrics["s_total"])
    gain_null = (
        abs(_require_finite_complex(row["h_baseline"], "candidate h_baseline")) / s_total <= DEEP_NULL_RATIO
        or bool(metrics["reference_deep_null_h_total"])
        or bool(metrics["candidate_deep_null_h_total"])
    )
    if status_reference != "pass":
        reason = "unresolved_reference"
    elif metrics["reason"]:
        # Deep cancellation takes precedence over robust complex gate status;
        # null magnitude/phase fields must remain explainable in output.
        reason = str(metrics["reason"])
    elif gain_null:
        reason = "ill_conditioned"
    elif candidate_status:
        reason = ""
    else:
        reason = "failed_threshold"
    return gain_null, reason


RAW_COLUMNS = [
    "qa_schema_id", "qa_schema_version", "provenance_schema_id", "provenance_schema_version", "provenance_status", "pending_contracts_json", "run_id", "generation", "geometry_case", "focus_target_rx_x_m", "focus_target_rx_y_m", "focus_target_rx_z_m", "evaluation_rx_x_m", "evaluation_rx_y_m", "evaluation_rx_z_m", "tx_x_m", "tx_y_m", "tx_z_m", "ris_center_x_m", "ris_center_y_m", "ris_center_z_m", "frequency_hz", "width_m", "height_m", "nx", "ny", "pattern_class", "pattern_seed", "pattern_hash", "series_identity", "random_seed", "world_model_id", "profile_id", "profile_version", "profile_identity", "reflection_model_id", "reflection_model_version", "channel_frequency_model_id", "quadrature_policy_id", "quadrature_policy_version", "quadrature_rule", "quadrature_order_x", "quadrature_order_y", "reference_label", "reference_row_id", "a_reference_artifact_identity", "reference_a_inf_norm", "a_inf_abs_error", "a_inf_robust_rel_error", "a_normalization_floor_active", "a_successive_inf_robust_rel_error", "h_ris_real", "h_ris_imag", "h_total_real", "h_total_imag", "h_ris_abs_error", "h_total_abs_error", "complex_robust_rel_error_h_ris", "complex_robust_rel_error_h_total", "normalization_floor_active_h_ris", "normalization_floor_active_h_total", "successive_robust_rel_error_h_ris", "successive_robust_rel_error_h_total", "magnitude_error_db_h_ris", "magnitude_error_db_h_total", "phase_error_rad_h_ris", "phase_error_rad_h_total", "ris_only_power_dbm", "total_received_power_dbm", "ris_gain_db", "deep_null_ratio_h_ris", "deep_null_ratio_h_total", "status", "reason", "quadrature_runtime_s", "quadrature_peak_rss_mb"
]


def run(output: Path | None = None, *, generations: Iterable[str] = ("Current", "Advanced", "Future"), geometry_cases: Iterable[str] = tuple(GEOMETRY_CASES), include_random: bool = True) -> tuple[Path, Path, Path]:
    """Run the declared matrix; tests may pass a reduced smoke subset."""
    effective_environment = _enforce_thread_process_policy()
    started_run = time.perf_counter()
    run_meter = _PeakRSSMeter()
    output_path, run_id = _create_qa_run_directory(output)
    raw_rows: list[dict[str, Any]] = []
    artifact_records: list[dict[str, Any]] = []
    series_runtime_by_identity: dict[str, float] = {}
    series_peak_rss_by_identity: dict[str, float | None] = {}
    provenance_engine: SimulationEngine | None = None
    provenance_scene: Scene | None = None
    conditional_32_runtime_s = 0.0
    conditional_32_peak_rss_mb: float | None = None
    base_peak_rss_candidates: list[float] = []
    run_rss_sampling_enabled = True
    for generation in generations:
        for geometry_case in geometry_cases:
            scene, focus_rx, evaluation_rx = _scene_for_case(generation, geometry_case)
            engine = SimulationEngine()
            ris = scene.ris_surfaces[0]
            if provenance_engine is None:
                provenance_engine, provenance_scene = engine, scene
            pattern_descriptors: list[tuple[str, int | None]] = [("ris_only_focus", None), ("coherent_target_focus", None)]
            if include_random:
                pattern_descriptors.extend(("random_legal", seed) for seed in RANDOM_PATTERN_SEEDS)
            for pattern_class, pattern_seed in pattern_descriptors:
                # Start before the one-time Focus/pattern construction.  This
                # is the frozen series scope, not merely the refinement loop.
                series_started = time.perf_counter()
                series_meter = _PeakRSSMeter()
                if pattern_class == "random_legal":
                    pattern = deterministic_random_pattern(ris, generation, geometry_case, int(pattern_seed))
                    focus_callable = generate_ris_only_focus_pattern
                else:
                    pattern, focus_callable = _pattern_for_series(scene, focus_rx, geometry_case, pattern_class, pattern_seed, engine)
                series_meter.sample()
                series_fields = {"generation": generation, "geometry_case": geometry_case, "pattern_class": pattern_class, "pattern_seed": pattern_seed, "pattern_hash": canonical_pattern_hash(ris, pattern), "frequency_hz": scene.frequency_hz, "profile_identity": engine.profile_identity, "world_model_id": "controller_nominal", "random_seed": scene.random_seed, "baseline_identity": "controller_baseline_v1", "aperture_identity": [ris.width_m, ris.height_m], "control_grid_identity": [ris.nx, ris.ny]}
                series_identity = tagged_series_identity(series_fields)
                rows: list[dict[str, Any]] = []
                previous: dict[str, Any] | None = None
                base_specs = [("midpoint", x, y) for x, y in MIDPOINT_ORDERS] + [("tensor_product_gauss_legendre", 16, 16)]
                for rule, ox, oy in base_specs:
                    spec = midpoint_quadrature(ris, ox, oy) if rule == "midpoint" else tensor_product_gauss_legendre(ris, ox, oy)
                    row_meter = _PeakRSSMeter()
                    t0 = time.perf_counter()
                    value = evaluate_quadrature(scene, pattern, spec, engine=engine)
                    elapsed = time.perf_counter() - t0
                    row_meter.sample()
                    row = {"quadrature_rule": rule, "quadrature_order_x": ox, "quadrature_order_y": oy, **value, "quadrature_runtime_s": elapsed, "quadrature_peak_rss_mb": row_meter.finish()}
                    if previous is not None:
                        row["successive"] = compare_to_reference(row, previous)
                    rows.append(row)
                    previous = row
                    series_meter.sample()
                try:
                    reference = select_internal_reference(rows)
                    reference_label = "internal_refined_numerical_reference"
                    status_reference = "pass"
                except ValueError as exc:
                    if "non-finite" in str(exc):
                        raise
                    # Conditional 32x32 is measured separately and is not part
                    # of the base run wall-time scope.
                    run_meter.sample()
                    run_rss_sampling_enabled = False
                    conditional_meter = _PeakRSSMeter()
                    conditional_started = time.perf_counter()
                    for rule, ox, oy in (("midpoint", 32, 32), ("tensor_product_gauss_legendre", 32, 32)):
                        spec = midpoint_quadrature(ris, ox, oy) if rule == "midpoint" else tensor_product_gauss_legendre(ris, ox, oy)
                        row_meter = _PeakRSSMeter()
                        t0 = time.perf_counter()
                        value = evaluate_quadrature(scene, pattern, spec, engine=engine)
                        elapsed = time.perf_counter() - t0
                        row_meter.sample()
                        row32 = {"quadrature_rule": rule, "quadrature_order_x": ox, "quadrature_order_y": oy, **value, "quadrature_runtime_s": elapsed, "quadrature_peak_rss_mb": row_meter.finish()}
                        row32["successive"] = compare_to_reference(row32, rows[-2])
                        rows.append(row32)
                        conditional_meter.sample()
                        series_meter.sample()
                    conditional_32_runtime_s += time.perf_counter() - conditional_started
                    conditional_rss = conditional_meter.finish()
                    if conditional_rss is not None:
                        conditional_32_peak_rss_mb = conditional_rss if conditional_32_peak_rss_mb is None else max(conditional_32_peak_rss_mb, conditional_rss)
                    try:
                        reference = select_internal_reference(rows)
                        reference_label = "internal_refined_numerical_reference"
                        status_reference = "pass"
                    except ValueError as exc:
                        if "non-finite" in str(exc):
                            raise
                        reference = rows[-1]
                        reference_label = "unresolved_reference"
                        status_reference = "fail"
                ref_id = _quadrature_row_id(series_identity, reference)
                artifact_records.append({
                    "reference_row_id": ref_id,
                    "series_identity": series_identity,
                    "pattern_hash": series_fields["pattern_hash"],
                    "quadrature_rule": reference["quadrature_rule"],
                    "quadrature_order_x": reference["quadrature_order_x"],
                    "quadrature_order_y": reference["quadrature_order_y"],
                    "parent_control_index": list(range(ris.cell_count)),
                    "a": [[float(x.real), float(x.imag)] for x in reference["a"]],
                })
                for row in rows:
                    metrics = compare_to_reference(row, reference)
                    candidate_status = status_reference == "pass" and metrics["a_inf_robust_rel_error"] <= PRODUCTION_TOLERANCE and metrics["complex_robust_rel_error_h_ris"] <= PRODUCTION_TOLERANCE and metrics["complex_robust_rel_error_h_total"] <= PRODUCTION_TOLERANCE
                    baseline_power_dbm = watts_to_dbm(scene.transmitter().power_w * abs(row["h_baseline"]) ** 2)
                    ris_power_dbm = watts_to_dbm(scene.transmitter().power_w * abs(row["h_ris"]) ** 2) if abs(row["h_ris"]) > 0.0 else None
                    total_power_dbm = watts_to_dbm(scene.transmitter().power_w * abs(row["h_total"]) ** 2)
                    successive = row.get("successive") or {}
                    magnitude_phase_ok = all(
                        value is None or abs(float(value)) <= limit
                        for value, limit in (
                            (metrics["magnitude_error_db_h_ris"], MAGNITUDE_TOLERANCE_DB),
                            (metrics["magnitude_error_db_h_total"], MAGNITUDE_TOLERANCE_DB),
                            (metrics["phase_error_rad_h_ris"], PHASE_TOLERANCE_RAD),
                            (metrics["phase_error_rad_h_total"], PHASE_TOLERANCE_RAD),
                        )
                    )
                    candidate_status = candidate_status and magnitude_phase_ok
                    # RIS gain uses exactly the same fixed reference-only
                    # S_total as the aggregate h_total metric.
                    gain_null, reason = _derive_gain_and_reason(
                        row,
                        reference,
                        metrics,
                        status_reference=status_reference,
                        candidate_status=candidate_status,
                    )
                    raw_rows.append({"qa_schema_id": QA_SCHEMA_ID, "qa_schema_version": QA_SCHEMA_VERSION, "run_id": run_id, "generation": generation, "geometry_case": geometry_case, "focus_target_rx_x_m": focus_rx.position.x, "focus_target_rx_y_m": focus_rx.position.y, "focus_target_rx_z_m": focus_rx.position.z, "evaluation_rx_x_m": evaluation_rx.position.x, "evaluation_rx_y_m": evaluation_rx.position.y, "evaluation_rx_z_m": evaluation_rx.position.z, "tx_x_m": scene.transmitter().position.x, "tx_y_m": scene.transmitter().position.y, "tx_z_m": scene.transmitter().position.z, "ris_center_x_m": ris.position.x, "ris_center_y_m": ris.position.y, "ris_center_z_m": ris.position.z, "frequency_hz": scene.frequency_hz, "width_m": ris.width_m, "height_m": ris.height_m, "nx": ris.nx, "ny": ris.ny, "pattern_class": pattern_class, "pattern_seed": "" if pattern_seed is None else pattern_seed, "pattern_hash": series_fields["pattern_hash"], "series_identity": series_identity, "random_seed": scene.random_seed, "world_model_id": "controller_nominal", "profile_id": "", "profile_version": "", "profile_identity": "", "reflection_model_id": "", "reflection_model_version": "", "channel_frequency_model_id": "", "quadrature_policy_id": QUADRATURE_POLICY_ID, "quadrature_policy_version": QUADRATURE_POLICY_VERSION, "quadrature_rule": row["quadrature_rule"], "quadrature_order_x": row["quadrature_order_x"], "quadrature_order_y": row["quadrature_order_y"], "reference_label": reference_label if row is reference else "", "reference_row_id": ref_id, "reference_a_inf_norm": metrics["reference_a_inf_norm"], "a_inf_abs_error": metrics["a_inf_abs_error"], "a_inf_robust_rel_error": metrics["a_inf_robust_rel_error"], "a_normalization_floor_active": metrics["a_normalization_floor_active"], "a_successive_inf_robust_rel_error": successive.get("a_inf_robust_rel_error", ""), "h_ris_real": row["h_ris"].real, "h_ris_imag": row["h_ris"].imag, "h_total_real": row["h_total"].real, "h_total_imag": row["h_total"].imag, "h_ris_abs_error": abs(row["h_ris"] - reference["h_ris"]), "h_total_abs_error": abs(row["h_total"] - reference["h_total"]), "complex_robust_rel_error_h_ris": metrics["complex_robust_rel_error_h_ris"], "complex_robust_rel_error_h_total": metrics["complex_robust_rel_error_h_total"], "normalization_floor_active_h_ris": metrics["normalization_floor_active_h_ris"], "normalization_floor_active_h_total": metrics["normalization_floor_active_h_total"], "successive_robust_rel_error_h_ris": successive.get("complex_robust_rel_error_h_ris", ""), "successive_robust_rel_error_h_total": successive.get("complex_robust_rel_error_h_total", ""), "magnitude_error_db_h_ris": metrics["magnitude_error_db_h_ris"], "magnitude_error_db_h_total": metrics["magnitude_error_db_h_total"], "phase_error_rad_h_ris": metrics["phase_error_rad_h_ris"], "phase_error_rad_h_total": metrics["phase_error_rad_h_total"], "ris_only_power_dbm": ris_power_dbm, "total_received_power_dbm": total_power_dbm, "ris_gain_db": None if gain_null else total_power_dbm - baseline_power_dbm, "deep_null_ratio_h_ris": DEEP_NULL_RATIO, "deep_null_ratio_h_total": DEEP_NULL_RATIO, "status": "pass" if candidate_status else "fail", "reason": reason, "quadrature_runtime_s": row["quadrature_runtime_s"], "quadrature_peak_rss_mb": row["quadrature_peak_rss_mb"]})
                series_runtime_by_identity[series_identity] = time.perf_counter() - series_started
                series_peak_rss_by_identity[series_identity] = series_meter.finish()
                for base_row in rows[:6]:
                    rss = base_row.get("quadrature_peak_rss_mb")
                    if rss is not None:
                        base_peak_rss_candidates.append(float(rss))
                for raw_row in raw_rows:
                    if raw_row["series_identity"] == series_identity:
                        raw_row["series_runtime_s"] = series_runtime_by_identity[series_identity]
                        raw_row["series_peak_rss_mb"] = series_peak_rss_by_identity[series_identity]
                if run_rss_sampling_enabled:
                    run_meter.sample()
    if provenance_engine is None or provenance_scene is None:
        raise ValueError("runner matrix is empty")
    provenance = _build_provenance_fields(engine=provenance_engine, scene=provenance_scene, focus=generate_ris_only_focus_pattern, world=ControllerModel(), run_id=run_id, quadrature_policy_id=QUADRATURE_POLICY_ID, quadrature_policy_version=QUADRATURE_POLICY_VERSION, coefficient_model_identity="candidate:controller_coefficient_v1")
    for row in raw_rows:
        row.update({k: provenance.get(k, "") for k in ("provenance_schema_id", "provenance_schema_version", "provenance_status", "pending_contracts_json", "profile_id", "profile_version", "profile_identity", "reflection_model_id", "reflection_model_version", "channel_frequency_model_id")})
    _assert_json_finite(artifact_records)
    artifact_bytes = json.dumps(artifact_records, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    artifact_path = output_path / "fnd_qa_ap_01_coefficients.json"
    artifact_path.write_bytes(artifact_bytes)
    artifact_identity = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    raw_path = output_path / "fnd_qa_ap_01_raw.csv"
    for row in raw_rows:
        row["a_reference_artifact_identity"] = artifact_identity
    _assert_json_finite(raw_rows)
    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_COLUMNS, extrasaction="ignore"); writer.writeheader(); writer.writerows(raw_rows)
    summary_path = output_path / "fnd_qa_ap_01_summary.json"
    summary_records = [
        {
            key: row.get(key, "")
            for key in (
                "run_id", "generation", "geometry_case", "pattern_class", "pattern_seed",
                "pattern_hash", "series_identity", "quadrature_policy_id",
                "quadrature_policy_version", "quadrature_rule", "quadrature_order_x",
                "quadrature_order_y", "reference_label", "reference_row_id",
                "a_reference_artifact_identity", "reference_a_inf_norm", "a_inf_abs_error",
                "a_inf_robust_rel_error", "h_ris_abs_error", "h_total_abs_error",
                "complex_robust_rel_error_h_ris", "complex_robust_rel_error_h_total",
                "magnitude_error_db_h_ris", "magnitude_error_db_h_total",
                "phase_error_rad_h_ris", "phase_error_rad_h_total", "status", "reason",
            )
        }
        for row in raw_rows
        if row.get("quadrature_rule") == "midpoint"
    ]
    # Do not sample after a conditional extension: its working set is tracked
    # separately and must not inflate the base run peak RSS field.
    if base_peak_rss_candidates:
        run_peak_rss_mb = max([value for value in base_peak_rss_candidates if math.isfinite(value)] + ([run_meter.peak] if run_meter.peak is not None else []))
    else:
        run_peak_rss_mb = run_meter.peak
    for record in summary_records:
        record["series_runtime_s"] = series_runtime_by_identity.get(str(record["series_identity"]), "")
        record["series_peak_rss_mb"] = series_peak_rss_by_identity.get(str(record["series_identity"]), "")
        record["run_runtime_s"] = time.perf_counter() - started_run - conditional_32_runtime_s
        record["run_peak_rss_mb"] = run_peak_rss_mb
    _assert_json_finite(summary_records)
    summary_path.write_text(json.dumps({"qa_schema_id": QA_SCHEMA_ID, "qa_schema_version": QA_SCHEMA_VERSION, "run_id": run_id, "provenance_status": "partial", "pending_contracts": ["FND-PHY-NB", "FND-QA-AP", "FND-QA-CC"], "reference_artifact_identity": artifact_identity, "records": summary_records}, allow_nan=False, default=str, separators=(",", ":")), encoding="utf-8")
    run_path = output_path / "fnd_qa_ap_01_run.json"
    run_elapsed = time.perf_counter() - started_run - conditional_32_runtime_s
    run_metadata = {"qa_schema_id": QA_SCHEMA_ID, "qa_schema_version": QA_SCHEMA_VERSION, "run_id": run_id, "run_runtime_s": run_elapsed, "run_peak_rss_mb": run_peak_rss_mb, "peak_memory_method": "windows_working_set" if os.name == "nt" else "resource_ru_maxrss", "python": platform.python_version(), "os": platform.platform(), "blas_environment": effective_environment, "base_minimum_matrix_wall_budget_h": 8, "conditional_32_runtime_s": conditional_32_runtime_s, "conditional_32_peak_rss_mb": conditional_32_peak_rss_mb}
    _assert_json_finite(run_metadata)
    run_path.write_text(json.dumps(run_metadata, allow_nan=False, default=str, separators=(",", ":")), encoding="utf-8")
    return raw_path, summary_path, run_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="complete run directory (created exclusively)")
    args = parser.parse_args(argv)
    raw, summary, run_metadata = run(args.output)
    print(f"RAW: {raw}\nSUMMARY: {summary}\nRUN: {run_metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
