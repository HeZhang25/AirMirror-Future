"""Reproducible XR-FUTURE-PERF-01 exact-M8 benchmark and evidence writer."""

from __future__ import annotations

import argparse
import csv
import ctypes
from ctypes import wintypes
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

from airmirror_future.core.types import SimulationConfig
from airmirror_future.optimization.coherent_focus import (
    generate_coherent_target_pattern,
    generate_scene_aware_ris_only_pattern,
)
from airmirror_future.physics.ris_scattering import (
    PRODUCTION_QUADRATURE_POLICY_ID,
    PRODUCTION_QUADRATURE_POLICY_VERSION,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_field,
    prepare_controller_link,
)


BASE_SHA = "a7271648d3d6d98d6af953eadcc4784b7776222f"
C_IMPLEMENTATION_SHA = "11f65a3b0762d738c8880901e00244ace3dd2a88"
C_DEPENDENCY_SHA = "08c2d28fd0e749643ff29f269259980369d30f0c"
RTOL = 2e-13
CHANNEL_ATOL = 1e-18
DB_ATOL = 2e-12


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_working_set_bytes() -> int | None:
    if os.name != "nt":
        return None
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.argtypes = []
    get_current_process.restype = wintypes.HANDLE
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    get_process_memory_info.restype = wintypes.BOOL
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ok = get_process_memory_info(
        get_current_process(),
        ctypes.byref(counters),
        counters.cb,
    )
    return int(counters.PeakWorkingSetSize) if ok else None


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _pattern_hash(pattern: np.ndarray) -> str:
    data = np.asarray(pattern, dtype=">f8").tobytes(order="C")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _patterns(scene) -> list[tuple[str, np.ndarray]]:
    ris = scene.ris_surfaces[0]
    rng = np.random.default_rng(20260908)
    return [
        ("zero", np.zeros(ris.cell_count)),
        ("ris_only", generate_scene_aware_ris_only_pattern(scene)),
        ("coherent", generate_coherent_target_pattern(scene)),
        ("random_20260908", rng.uniform(0.0, 2.0 * np.pi, ris.cell_count)),
    ]


def _complex_row(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _worker_link_reference() -> dict[str, object]:
    scene = create_smart_space_scene("Future")
    engine = SimulationEngine()
    rows = []
    started = time.perf_counter()
    for name, pattern in _patterns(scene):
        item_started = time.perf_counter()
        result = engine.compute_channel(
            scene, ris_patterns={scene.ris_surfaces[0].id: pattern}
        )
        rows.append(
            {
                "pattern": name,
                "pattern_hash": _pattern_hash(pattern),
                "runtime_s": time.perf_counter() - item_started,
                "ris_channel": _complex_row(result.ris_channel),
                "total_channel": _complex_row(result.total_channel),
                "power_dbm": result.received_power_dbm,
                "snr_db": result.snr_db,
            }
        )
    return {
        "kind": "link_reference",
        "total_runtime_s": time.perf_counter() - started,
        "peak_working_set_bytes": _peak_working_set_bytes(),
        "patterns": rows,
    }


def _worker_link_prepared() -> dict[str, object]:
    scene = create_smart_space_scene("Future")
    engine = SimulationEngine()
    started = time.perf_counter()
    prepared = prepare_controller_link(scene, engine=engine)
    build_runtime = time.perf_counter() - started
    rows = []
    for name, pattern in _patterns(scene):
        samples = []
        result = None
        for _ in range(5):
            item_started = time.perf_counter()
            result = prepared.evaluate(pattern)
            samples.append(time.perf_counter() - item_started)
        assert result is not None
        rows.append(
            {
                "pattern": name,
                "pattern_hash": _pattern_hash(pattern),
                "runtime_samples_s": samples,
                "runtime_median_s": float(np.median(samples)),
                "ris_channel": _complex_row(result.ris_channel),
                "total_channel": _complex_row(result.total_channel),
                "power_dbm": result.received_power_dbm,
                "snr_db": result.snr_db,
            }
        )
    return {
        "kind": "link_prepared",
        "build_runtime_s": build_runtime,
        "coefficient_identity": prepared.coefficient_identity,
        "coefficient_bytes": prepared.coefficients.nbytes,
        "peak_working_set_bytes": _peak_working_set_bytes(),
        "patterns": rows,
    }


def _worker_field_reference(width: int, height: int) -> dict[str, object]:
    scene = create_smart_space_scene("Future")
    engine = SimulationEngine()
    pattern = dict(_patterns(scene))["coherent"]
    config = SimulationConfig(width, height, batch_size=8)
    started = time.perf_counter()
    field = engine.compute_field_map(
        scene, config, {scene.ris_surfaces[0].id: pattern}
    )
    return {
        "kind": "field_reference",
        "grid": [width, height],
        "runtime_s": time.perf_counter() - started,
        "peak_working_set_bytes": _peak_working_set_bytes(),
        "pattern": "coherent",
        "pattern_hash": _pattern_hash(pattern),
        "power_dbm": field.received_power_dbm.tolist(),
        "snr_db": field.snr_db.tolist(),
        "baseline_power_dbm": field.baseline_power_dbm.tolist(),
        "coverage_percent": field.coverage_percent,
    }


def _worker_field_prepared(width: int, height: int) -> dict[str, object]:
    scene = create_smart_space_scene("Future")
    config = SimulationConfig(width, height, batch_size=8)
    started = time.perf_counter()
    prepared = prepare_controller_field(
        scene,
        config,
        receiver_batch_size=8,
        coefficient_memory_budget_bytes=128 * 1024 * 1024,
    )
    build_runtime = time.perf_counter() - started
    rows = []
    for name, pattern in _patterns(scene):
        samples = []
        field = None
        for _ in range(5):
            item_started = time.perf_counter()
            field = prepared.evaluate(pattern)
            samples.append(time.perf_counter() - item_started)
        assert field is not None
        rows.append(
            {
                "pattern": name,
                "pattern_hash": _pattern_hash(pattern),
                "runtime_samples_s": samples,
                "runtime_median_s": float(np.median(samples)),
                "power_dbm": field.received_power_dbm.tolist(),
                "snr_db": field.snr_db.tolist(),
                "baseline_power_dbm": field.baseline_power_dbm.tolist(),
                "coverage_percent": field.coverage_percent,
            }
        )
    return {
        "kind": "field_prepared",
        "grid": [width, height],
        "build_runtime_s": build_runtime,
        "coefficient_bytes": prepared.coefficient_bytes,
        "receiver_batch_size": prepared.receiver_batch_size,
        "max_point_sample_pairs": prepared.max_point_sample_pairs,
        "peak_working_set_bytes": _peak_working_set_bytes(),
        "patterns": rows,
    }


def _run_worker(kind: str, width: int = 0, height: int = 0) -> dict[str, object]:
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", kind]
    if width:
        command.extend(["--width", str(width), "--height", str(height)])
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout)


def _compare_complex(a: dict[str, float], b: dict[str, float]) -> float:
    return abs(complex(a["real"], a["imag"]) - complex(b["real"], b["imag"]))


def _comparison(reference: dict[str, object], prepared: dict[str, object]) -> dict[str, float]:
    ref = {row["pattern"]: row for row in reference["patterns"]}
    opt = {row["pattern"]: row for row in prepared["patterns"]}
    return {
        "max_ris_channel_abs_error": max(
            _compare_complex(ref[name]["ris_channel"], opt[name]["ris_channel"])
            for name in ref
        ),
        "max_total_channel_abs_error": max(
            _compare_complex(ref[name]["total_channel"], opt[name]["total_channel"])
            for name in ref
        ),
        "max_power_db_abs_error": max(
            abs(ref[name]["power_dbm"] - opt[name]["power_dbm"]) for name in ref
        ),
        "max_snr_db_abs_error": max(
            abs(ref[name]["snr_db"] - opt[name]["snr_db"]) for name in ref
        ),
    }


def _field_comparison(reference: dict[str, object], prepared: dict[str, object]) -> dict[str, float]:
    coherent = next(row for row in prepared["patterns"] if row["pattern"] == "coherent")
    return {
        "max_power_db_abs_error": float(
            np.max(np.abs(np.asarray(reference["power_dbm"]) - np.asarray(coherent["power_dbm"])))
        ),
        "max_snr_db_abs_error": float(
            np.max(np.abs(np.asarray(reference["snr_db"]) - np.asarray(coherent["snr_db"])))
        ),
        "max_baseline_db_abs_error": float(
            np.max(
                np.abs(
                    np.asarray(reference["baseline_power_dbm"])
                    - np.asarray(coherent["baseline_power_dbm"])
                )
            )
        ),
        "coverage_percent_abs_error": abs(
            reference["coverage_percent"] - coherent["coverage_percent"]
        ),
    }


def _write_csv(path: Path, evidence: dict[str, object]) -> None:
    rows = []
    link_ref = evidence["link"]["reference"]
    link_opt = evidence["link"]["prepared"]
    rows.append(
        {
            "case": "link_four_patterns",
            "grid": "",
            "reference_s": link_ref["total_runtime_s"],
            "cold_build_s": link_opt["build_runtime_s"],
            "hot_pattern_s": np.median(
                [row["runtime_median_s"] for row in link_opt["patterns"]]
            ),
            "reference_peak_mib": link_ref["peak_working_set_bytes"] / 2**20,
            "prepared_peak_mib": link_opt["peak_working_set_bytes"] / 2**20,
            "max_error": evidence["link"]["comparison"]["max_total_channel_abs_error"],
        }
    )
    for item in evidence["fields"]:
        ref, opt = item["reference"], item["prepared"]
        coherent = next(row for row in opt["patterns"] if row["pattern"] == "coherent")
        rows.append(
            {
                "case": "field_coherent",
                "grid": f"{ref['grid'][0]}x{ref['grid'][1]}",
                "reference_s": ref["runtime_s"],
                "cold_build_s": opt["build_runtime_s"],
                "hot_pattern_s": coherent["runtime_median_s"],
                "reference_peak_mib": ref["peak_working_set_bytes"] / 2**20,
                "prepared_peak_mib": opt["peak_working_set_bytes"] / 2**20,
                "max_error": item["comparison"]["max_power_db_abs_error"],
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_png(path: Path, evidence: dict[str, object]) -> None:
    labels = ["link 4 patterns"]
    reference = [evidence["link"]["reference"]["total_runtime_s"]]
    build = [evidence["link"]["prepared"]["build_runtime_s"]]
    hot = [
        np.median(
            [row["runtime_median_s"] for row in evidence["link"]["prepared"]["patterns"]]
        )
    ]
    for item in evidence["fields"]:
        labels.append(f"{item['reference']['grid'][0]}x{item['reference']['grid'][1]} field")
        reference.append(item["reference"]["runtime_s"])
        build.append(item["prepared"]["build_runtime_s"])
        hot.append(
            next(
                row["runtime_median_s"]
                for row in item["prepared"]["patterns"]
                if row["pattern"] == "coherent"
            )
        )
    x = np.arange(len(labels))
    width = 0.25
    fig, axis = plt.subplots(figsize=(9, 5))
    axis.bar(x - width, reference, width, label="reference")
    axis.bar(x, build, width, label="prepared cold build")
    axis.bar(x + width, hot, width, label="prepared hot pattern")
    axis.set_yscale("log")
    axis.set_ylabel("seconds (log scale)")
    axis.set_xticks(x, labels)
    axis.set_title("XR-FUTURE-PERF-01 exact production M8")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run(output: Path, grids: list[tuple[int, int]]) -> None:
    output.mkdir(parents=True, exist_ok=False)
    link_reference = _run_worker("link-reference")
    link_prepared = _run_worker("link-prepared")
    fields = []
    for width, height in grids:
        reference = _run_worker("field-reference", width, height)
        prepared = _run_worker("field-prepared", width, height)
        fields.append(
            {
                "reference": reference,
                "prepared": prepared,
                "comparison": _field_comparison(reference, prepared),
            }
        )
    scene = create_smart_space_scene("Future")
    ris = scene.ris_surfaces[0]
    evidence = {
        "schema_id": "airmirror_xr_future_perf_01",
        "schema_version": 1,
        "task": "XR-FUTURE-PERF-01",
        "status": "non-release performance experiment",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "HeZhang25/AirMirror-Future",
        "base_sha": BASE_SHA,
        "c_implementation_sha": C_IMPLEMENTATION_SHA,
        "c_dependency_sha": C_DEPENDENCY_SHA,
        "implementation_sha": _git("rev-parse", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "executable": sys.executable,
            "numpy": np.__version__,
            "thread_environment": {
                key: os.environ.get(key)
                for key in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                )
            },
        },
        "scene": {
            "name": scene.name,
            "schema_version": scene.schema_version,
            "profile": "indoor_deterministic/1",
            "world": "ControllerModel",
            "frequency_hz": scene.frequency_hz,
            "bandwidth_hz": scene.bandwidth_hz,
            "tx_position_m": asdict(scene.transmitter().position),
            "rx_position_m": asdict(scene.receiver().position),
            "ris": {
                "generation": ris.generation,
                "width_m": ris.width_m,
                "height_m": ris.height_m,
                "nx": ris.nx,
                "ny": ris.ny,
                "control_count": ris.cell_count,
                "phase_bits": ris.phase_bits,
                "reflection_efficiency": ris.reflection_efficiency,
            },
            "quadrature_policy_id": PRODUCTION_QUADRATURE_POLICY_ID,
            "quadrature_policy_version": PRODUCTION_QUADRATURE_POLICY_VERSION,
        },
        "tolerance": {
            "rtol": RTOL,
            "channel_atol": CHANNEL_ATOL,
            "db_atol": DB_ATOL,
        },
        "command": " ".join(sys.argv),
        "link": {
            "reference": link_reference,
            "prepared": link_prepared,
            "comparison": _comparison(link_reference, link_prepared),
        },
        "fields": fields,
    }
    (output / "evidence.json").write_text(
        json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8"
    )
    _write_csv(output / "summary.csv", evidence)
    _write_png(output / "timings.png", evidence)
    print(json.dumps({"output": str(output), "implementation_sha": evidence["implementation_sha"]}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--grids", default="8x6,16x12")
    parser.add_argument(
        "--worker",
        choices=("link-reference", "link-prepared", "field-reference", "field-prepared"),
    )
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    args = parser.parse_args()
    if args.worker:
        if args.worker == "link-reference":
            result = _worker_link_reference()
        elif args.worker == "link-prepared":
            result = _worker_link_prepared()
        elif args.worker == "field-reference":
            result = _worker_field_reference(args.width, args.height)
        else:
            result = _worker_field_prepared(args.width, args.height)
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
        return
    if args.output is None:
        parser.error("--output is required")
    grids = []
    for item in args.grids.split(","):
        width, height = item.lower().split("x", maxsplit=1)
        grids.append((int(width), int(height)))
    run(args.output, grids)


if __name__ == "__main__":
    main()
