"""Reproducible PERF-PREP-01 benchmark for the current production paths.

The default suite deliberately avoids the full QA-AP matrix and avoids a
Future Fast 80x60 field map.  Expensive cases are opt-in through explicit
CLI flags so an ordinary preparation run remains bounded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from typing import Any, Callable


THREAD_ENVIRONMENT = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}

DEFAULT_GENERATIONS = ("Current", "Advanced", "Future")
DEFAULT_FIELD_GRIDS = {
    "Current": (80, 60, "fast"),
    "Advanced": (16, 12, "representative_probe"),
    "Future": (8, 6, "representative_probe"),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _percentile(values: list[float], fraction: float) -> float:
    import numpy as np

    return float(np.percentile(np.asarray(values, dtype=float), fraction * 100.0))


def _timed_repeats(
    operation: Callable[[], Any],
    *,
    warmups: int,
    repeats: int,
) -> tuple[dict[str, float], Any]:
    for _ in range(warmups):
        operation()
    values: list[float] = []
    last: Any = None
    for _ in range(repeats):
        started = time.perf_counter()
        last = operation()
        values.append(time.perf_counter() - started)
    return (
        {
            "minimum_s": min(values),
            "median_s": _percentile(values, 0.5),
            "p95_s": _percentile(values, 0.95),
            "maximum_s": max(values),
            "repeat_count": float(repeats),
            "warmup_count": float(warmups),
        },
        last,
    )


def _process_memory_bytes() -> tuple[int, int]:
    """Return current and process-lifetime peak RSS without third-party tools."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
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

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)

    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF)
    peak = int(usage.ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    return peak, peak


def _total_memory_bytes() -> int | None:
    if os.name != "nt":
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
        except (AttributeError, ValueError, OSError):
            return None
        return int(page_size * page_count)

    import ctypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullTotalPhys)


def _environment(root: Path) -> dict[str, Any]:
    import numpy as np
    try:
        from threadpoolctl import threadpool_info
    except ImportError:
        threadpools: list[dict[str, Any]] = []
    else:
        threadpools = threadpool_info()
    return {
        "git_head": _git(root, "rev-parse", "HEAD"),
        "git_origin_main": _git(root, "rev-parse", "origin/main"),
        "git_branch": _git(root, "branch", "--show-current"),
        "git_status_porcelain": _git(root, "status", "--porcelain"),
        "remote_origin": _git(root, "remote", "get-url", "origin"),
        "platform": platform.platform(),
        "os_name": os.name,
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", ""),
        "logical_cpu_count": os.cpu_count(),
        "total_memory_bytes": _total_memory_bytes(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "numpy_version": np.__version__,
        "thread_environment": {
            key: os.environ.get(key) for key in THREAD_ENVIRONMENT
        },
        "threadpools": threadpools,
    }


def _scenario_record(scene: object) -> dict[str, Any]:
    from airmirror_future.physics.ris_scattering import PRODUCTION_QUADRATURE_ORDER

    ris = scene.ris_surfaces[0]
    return {
        "scene": scene.name,
        "profile": "IndoorDeterministicProfile",
        "world": "ControllerModel",
        "random_seed": scene.random_seed,
        "frequency_hz": scene.frequency_hz,
        "bandwidth_hz": scene.bandwidth_hz,
        "ris": {
            "generation": ris.generation,
            "width_m": ris.width_m,
            "height_m": ris.height_m,
            "nx": ris.nx,
            "ny": ris.ny,
            "control_count": ris.cell_count,
            "phase_bits": ris.phase_bits,
            "reflection_efficiency": ris.reflection_efficiency,
            "production_quadrature": (
                f"midpoint_{PRODUCTION_QUADRATURE_ORDER}x"
                f"{PRODUCTION_QUADRATURE_ORDER}_per_control_patch"
            ),
            "production_sample_count": (
                ris.cell_count * PRODUCTION_QUADRATURE_ORDER**2
            ),
        },
    }


def _array_sha256(values: object) -> str:
    import numpy as np

    array = np.ascontiguousarray(np.asarray(values, dtype=">f8"))
    return "sha256:" + hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _measure_equivalence_anchors() -> dict[str, Any]:
    from airmirror_future.core.types import SimulationConfig
    from airmirror_future.ris.phase import generate_ris_only_focus_pattern
    from airmirror_future.scenarios.smart_space import create_smart_space_scene
    from airmirror_future.simulation.engine import SimulationEngine
    from airmirror_future.simulation.ground_truth import ControllerModel

    results: dict[str, Any] = {}
    for generation in DEFAULT_GENERATIONS:
        scene = create_smart_space_scene(generation)
        ris = scene.ris_surfaces[0]
        pattern = generate_ris_only_focus_pattern(
            ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
        )
        engine = SimulationEngine()
        channel = engine.compute_channel(
            scene,
            ris_patterns={ris.id: pattern},
            model=ControllerModel(),
        )
        width, height, label = DEFAULT_FIELD_GRIDS[generation]
        field = engine.compute_field_map(
            scene,
            SimulationConfig(width, height, "power"),
            {ris.id: pattern},
            ControllerModel(),
        )
        results[generation] = {
            "scenario": _scenario_record(scene),
            "pattern_sha256_float64_be": _array_sha256(pattern),
            "channel": {
                "total_real": channel.total_channel.real,
                "total_imag": channel.total_channel.imag,
                "los_real": channel.los_channel.real,
                "los_imag": channel.los_channel.imag,
                "wall_real": channel.wall_channel.real,
                "wall_imag": channel.wall_channel.imag,
                "ris_real": channel.ris_channel.real,
                "ris_imag": channel.ris_channel.imag,
                "received_power_dbm": channel.received_power_dbm,
                "snr_db": channel.snr_db,
            },
            "field_grid": [width, height],
            "field_quality_label": label,
            "field_hashes_float64_be": {
                "received_power_dbm": _array_sha256(field.received_power_dbm),
                "snr_db": _array_sha256(field.snr_db),
                "baseline_power_dbm": _array_sha256(field.baseline_power_dbm),
                "ris_gain_db": _array_sha256(field.ris_gain_db),
            },
            "coverage_percent": field.coverage_percent,
            "dead_zone_percent": field.dead_zone_percent,
        }
    return results


def _measure_generation_focus(generation: str, repeats: int) -> dict[str, Any]:
    import numpy as np

    from airmirror_future.optimization.coherent_focus import (
        generate_coherent_target_pattern,
    )
    from airmirror_future.ris.phase import (
        common_phase_offset_candidates,
        generate_ris_only_focus_pattern,
        generate_unquantized_ris_only_focus_pattern,
    )
    from airmirror_future.scenarios.smart_space import create_smart_space_scene
    from airmirror_future.simulation.engine import SimulationEngine
    from airmirror_future.simulation.ground_truth import ControllerModel

    scene = create_smart_space_scene(generation)
    ris = scene.ris_surfaces[0]
    tx = scene.transmitter()
    rx = scene.receiver()
    engine = SimulationEngine()
    model = ControllerModel()

    ideal_timing, ideal = _timed_repeats(
        lambda: generate_unquantized_ris_only_focus_pattern(
            ris, tx, rx, scene.frequency_hz
        ),
        warmups=1,
        repeats=repeats,
    )
    if ris.phase_bits is None:
        candidate_timing = {
            "minimum_s": 0.0,
            "median_s": 0.0,
            "p95_s": 0.0,
            "maximum_s": 0.0,
            "repeat_count": 0.0,
            "warmup_count": 0.0,
        }
        candidate_count = 1
        candidate_semantics = "analytic_continuous_offset"
    else:
        candidate_timing, candidates = _timed_repeats(
            lambda: common_phase_offset_candidates(ideal, ris.phase_bits),
            warmups=1,
            repeats=repeats,
        )
        candidate_count = int(len(candidates))
        candidate_semantics = "piecewise_constant_common_offset_commands"

    pattern = generate_ris_only_focus_pattern(
        ris, tx, rx, scene.frequency_hz
    )
    channel_timing, channel = _timed_repeats(
        lambda: engine.compute_channel(
            scene,
            tx=tx,
            rx=rx,
            ris_patterns={ris.id: pattern},
            model=model,
        ),
        warmups=1,
        repeats=repeats,
    )
    baseline_timing, _ = _timed_repeats(
        lambda: engine.compute_channel(
            scene, tx=tx, rx=rx, ris_patterns={}, model=model
        ),
        warmups=1,
        repeats=repeats,
    )

    focus_repeats = 1 if generation == "Advanced" else repeats
    focus_timing, focused_pattern = _timed_repeats(
        lambda: generate_coherent_target_pattern(
            scene,
            model,
            engine=engine,
            tx=tx,
            rx=rx,
            ris=ris,
        ),
        warmups=0,
        repeats=focus_repeats,
    )
    return {
        "scenario": _scenario_record(scene),
        "candidate_semantics": candidate_semantics,
        "candidate_count": candidate_count,
        "focus_candidate_generation": candidate_timing,
        "ris_only_pattern_generation": ideal_timing,
        "channel_evaluation_with_ris": channel_timing,
        "channel_evaluation_without_ris": baseline_timing,
        "coherent_focus_total": focus_timing,
        "focus_output_size": int(np.asarray(focused_pattern).size),
        "measured_focus_evaluation_count": (
            2 if ris.phase_bits is None else candidate_count + 1
        ),
        "note": (
            "Advanced total Focus intentionally has one measured repeat because "
            "the exact finite-bit candidate sweep is expensive."
            if generation == "Advanced"
            else ""
        ),
        "sample_channel_received_power_dbm": channel.received_power_dbm,
    }


def _field_grid(
    generation: str,
    *,
    full_fast: bool,
    future_fast: bool,
) -> tuple[int, int, str]:
    if full_fast and generation in {"Current", "Advanced"}:
        return 80, 60, "fast"
    if future_fast and generation == "Future":
        return 80, 60, "fast_explicit_opt_in"
    return DEFAULT_FIELD_GRIDS[generation]


def _measure_field(
    generation: str,
    grid_width: int,
    grid_height: int,
    quality_label: str,
) -> dict[str, Any]:
    from airmirror_future.core.types import SimulationConfig
    from airmirror_future.ris.phase import generate_ris_only_focus_pattern
    from airmirror_future.scenarios.smart_space import create_smart_space_scene
    from airmirror_future.simulation.engine import SimulationEngine
    from airmirror_future.simulation.ground_truth import ControllerModel

    scene = create_smart_space_scene(generation)
    ris = scene.ris_surfaces[0]
    pattern = generate_ris_only_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    engine = SimulationEngine()
    config = SimulationConfig(grid_width, grid_height, "power")
    rss_before, peak_before = _process_memory_bytes()
    started = time.perf_counter()
    field = engine.compute_field_map(
        scene,
        config,
        {ris.id: pattern},
        ControllerModel(),
    )
    elapsed = time.perf_counter() - started
    rss_after, peak_after = _process_memory_bytes()
    result_array_bytes = sum(
        values.nbytes
        for values in (
            field.x_m,
            field.y_m,
            field.received_power_dbm,
            field.snr_db,
            field.baseline_power_dbm,
            field.ris_gain_db,
        )
    )
    return {
        "scenario": _scenario_record(scene),
        "grid_width": grid_width,
        "grid_height": grid_height,
        "point_count": grid_width * grid_height,
        "quality_label": quality_label,
        "wall_clock_s": elapsed,
        "engine_runtime_s": field.runtime_s,
        "result_array_bytes": result_array_bytes,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "peak_rss_bytes": peak_after,
        "peak_rss_delta_bytes": max(0, peak_after - peak_before),
        "coverage_percent": field.coverage_percent,
        "allocation_contract": (
            "FieldMapResult owns x/y plus four float64 grid arrays. Peak RSS "
            "also includes bounded production RIS contribution batches."
        ),
    }


def _measure_metrics(repeats: int) -> dict[str, Any]:
    import numpy as np

    from airmirror_future.simulation.metrics import (
        coverage_percent,
        outage_probability,
    )

    values = np.linspace(-20.0, 80.0, 80 * 60, dtype=float).reshape(60, 80)
    threshold = 35.0
    timing, last = _timed_repeats(
        lambda: (
            coverage_percent(values, threshold),
            outage_probability(values, threshold),
        ),
        warmups=3,
        repeats=max(10, repeats * 10),
    )
    return {
        "grid": [80, 60],
        "input_bytes": values.nbytes,
        "timing": timing,
        "coverage_percent": last[0],
        "outage_probability": last[1],
    }


def _measure_pattern_view(repeats: int) -> dict[str, Any]:
    from PySide6.QtWidgets import QApplication

    from airmirror_future.gui.pattern_view import PhasePatternView
    from airmirror_future.ris.phase import generate_ris_only_focus_pattern
    from airmirror_future.scenarios.smart_space import create_smart_space_scene

    application = QApplication.instance() or QApplication([])
    results: dict[str, Any] = {}
    for generation in DEFAULT_GENERATIONS:
        scene = create_smart_space_scene(generation)
        ris = scene.ris_surfaces[0]
        pattern = generate_ris_only_focus_pattern(
            ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
        )
        view = PhasePatternView()

        def render() -> None:
            view.set_patterns(
                pattern,
                pattern,
                ris.ny,
                ris.nx,
                phase_bits=ris.phase_bits,
                pattern_source="RIS-only Physics Focus",
            )
            application.processEvents()

        timing, _ = _timed_repeats(
            render,
            warmups=2,
            repeats=max(5, repeats * 3),
        )
        results[generation] = {
            "grid": [ris.nx, ris.ny],
            "timing": timing,
            "scope": "PhasePatternView.set_patterns plus offscreen event processing",
        }
    return results


def _measure_xr() -> dict[str, Any]:
    from airmirror_future.core.types import SimulationConfig
    from airmirror_future.experiments.xr_dynamic_room_mvp import (
        ADAPTIVE_RIS_MODE,
        _pattern_hash,
        build_trajectory,
        compute_adaptive_mvp,
    )
    from airmirror_future.gui.workers import build_xr_field_cache_key
    from airmirror_future.simulation.engine import SimulationEngine
    from airmirror_future.simulation.ground_truth import ControllerModel

    engine = SimulationEngine()
    model = ControllerModel()
    trajectory = build_trajectory()
    started = time.perf_counter()
    computation = compute_adaptive_mvp(engine=engine, model=model)
    link_precompute_s = time.perf_counter() - started
    adaptive = [
        sample for sample in computation.samples if sample.mode == ADAPTIVE_RIS_MODE
    ]
    config = SimulationConfig(80, 60, "power")
    ris = computation.scene.ris_surfaces[0]
    static_started = time.perf_counter()
    static_field = engine.compute_field_map(
        computation.scene,
        config,
        {ris.id: computation.static_pattern},
        model,
    )
    static_field_wall_clock_s = time.perf_counter() - static_started
    static_key = build_xr_field_cache_key(
        computation.scene,
        engine,
        model,
        config,
        _pattern_hash(computation.static_pattern),
    )
    # The first adaptive command is intentionally the same initial-position
    # command as Static.  Use the next trajectory sample to force a real cache
    # miss while retaining the exact command snapshot semantics.
    sample = adaptive[1] if len(adaptive) > 1 else adaptive[0]
    key_started = time.perf_counter()
    key = build_xr_field_cache_key(
        computation.scene,
        engine,
        model,
        config,
        sample.command_hash,
    )
    key_build_s = time.perf_counter() - key_started
    cache: dict[object, object] = {static_key: static_field}
    lookup_started = time.perf_counter()
    miss = cache.get(key)
    cache_miss_lookup_s = time.perf_counter() - lookup_started
    adaptive_started = time.perf_counter()
    adaptive_field = engine.compute_field_map(
        computation.scene,
        config,
        {ris.id: sample.commanded_pattern},
        model,
    )
    adaptive_field_wall_clock_s = time.perf_counter() - adaptive_started
    cache[key] = adaptive_field
    lookup_started = time.perf_counter()
    hit = cache.get(key)
    cache_hit_lookup_s = time.perf_counter() - lookup_started
    return {
        "scenario": _scenario_record(computation.scene),
        "trajectory_sample_count": len(trajectory),
        "link_result_count": len(computation.samples),
        "link_precompute_wall_clock_s": link_precompute_s,
        "link_evaluation_runtime_sum_s": sum(
            sample.evaluation_runtime_s for sample in computation.samples
        ),
        "adaptive_focus_and_overhead_s": max(
            0.0,
            link_precompute_s
            - sum(sample.evaluation_runtime_s for sample in computation.samples),
        ),
        "field_cache_key_build_s": key_build_s,
        "cache_miss_lookup_s": cache_miss_lookup_s,
        "cache_hit_lookup_s": cache_hit_lookup_s,
        "cache_miss_confirmed": miss is None,
        "cache_hit_confirmed": hit is adaptive_field,
        "static_field_wall_clock_s": static_field_wall_clock_s,
        "static_field_engine_runtime_s": static_field.runtime_s,
        "adaptive_cache_miss_field_wall_clock_s": adaptive_field_wall_clock_s,
        "adaptive_cache_miss_engine_runtime_s": adaptive_field.runtime_s,
        "cache_size_after_miss": len(cache),
        "cache_semantics": (
            "cache hits do not run physics; misses enqueue one serialized "
            "XRAdaptiveFieldWorker in the GUI"
        ),
    }


def _measure_worker_cancellation() -> dict[str, Any]:
    from PySide6.QtCore import QCoreApplication, QThreadPool

    from airmirror_future.core.types import SimulationConfig
    from airmirror_future.gui.workers import MapWorker
    from airmirror_future.ris.phase import generate_ris_only_focus_pattern
    from airmirror_future.scenarios.smart_space import create_smart_space_scene
    from airmirror_future.simulation.engine import SimulationEngine
    from airmirror_future.simulation.ground_truth import ControllerModel

    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    pattern = generate_ris_only_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )
    worker = MapWorker(
        1,
        SimulationEngine(),
        scene,
        SimulationConfig(80, 60, "power"),
        {ris.id: pattern},
        ControllerModel(),
    )
    started_event = threading.Event()
    terminated_event = threading.Event()
    original_compute = worker.engine.compute_field_map

    def observed_compute(*args: object, **kwargs: object) -> object:
        started_event.set()
        return original_compute(*args, **kwargs)

    worker.engine.compute_field_map = observed_compute  # type: ignore[method-assign]
    worker.signals.terminated.connect(
        lambda _version, _worker: terminated_event.set()
    )
    app = QCoreApplication.instance() or QCoreApplication([])
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    queued_at = time.perf_counter()
    pool.start(worker)
    if not started_event.wait(timeout=5.0):
        raise RuntimeError("worker did not enter production physics")
    physics_started_at = time.perf_counter()
    time.sleep(0.01)
    cancel_at = time.perf_counter()
    worker.cancel()
    deadline = time.perf_counter() + 30.0
    while time.perf_counter() < deadline and not terminated_event.is_set():
        app.processEvents()
        time.sleep(0.001)
    pool.waitForDone(30_000)
    app.processEvents()
    if not terminated_event.is_set():
        raise RuntimeError("worker did not terminate after cancellation")
    terminated_at = time.perf_counter()
    return {
        "worker": "MapWorker",
        "scenario": "Current Fast 80x60",
        "queue_to_physics_start_s": physics_started_at - queued_at,
        "cancel_request_after_physics_start_s": cancel_at - physics_started_at,
        "cancel_to_runnable_termination_s": terminated_at - cancel_at,
        "queue_backend": "real local QThreadPool with one worker thread",
        "cancellation_boundary": (
            "SimulationEngine.compute_field_map checks once per completed row; "
            "an in-progress point evaluation is not interrupted"
        ),
    }


def _case_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.case == "focus":
        return _measure_generation_focus(args.generation, args.repeats)
    if args.case == "field":
        return _measure_field(
            args.generation,
            args.grid_width,
            args.grid_height,
            args.quality_label,
        )
    if args.case == "metrics":
        return _measure_metrics(args.repeats)
    if args.case == "pattern_view":
        return _measure_pattern_view(args.repeats)
    if args.case == "equivalence":
        return _measure_equivalence_anchors()
    if args.case == "xr":
        return _measure_xr()
    if args.case == "worker_cancel":
        return _measure_worker_cancellation()
    raise ValueError(f"unknown case: {args.case}")


def _run_child(
    root: Path,
    arguments: list[str],
    *,
    timeout_s: float,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(THREAD_ENVIRONMENT)
    source = str(root / "src")
    environment["PYTHONPATH"] = (
        source
        if not environment.get("PYTHONPATH")
        else source + os.pathsep + environment["PYTHONPATH"]
    )
    command = [sys.executable, "-B", str(Path(__file__).resolve()), *arguments]
    completed = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_s,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "benchmark child failed: "
            + subprocess.list2cmdline(command)
            + "\n"
            + completed.stderr
        )
    return json.loads(completed.stdout)


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    root = _repository_root()
    if args.reuse_core is None:
        payload: dict[str, Any] = {
            "schema_id": "airmirror_perf_prep_01",
            "schema_version": 1,
            "task": "PERF-PREP-01",
            "measurement_started_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
            "environment": _environment(root),
            "contract": {
                "production_semantics_modified": False,
                "formal_p1a_started": False,
                "qa_ap_full_matrix_run": False,
                "blas_thread_policy": THREAD_ENVIRONMENT,
                "default_generations": list(DEFAULT_GENERATIONS),
                "default_field_grids": {
                    key: list(value) for key, value in DEFAULT_FIELD_GRIDS.items()
                },
            },
            "focus": {},
            "field_maps": {},
        }
        for generation in args.generations:
            payload["focus"][generation] = _run_child(
                root,
                [
                    "--case",
                    "focus",
                    "--generation",
                    generation,
                    "--repeats",
                    str(args.repeats),
                ],
                timeout_s=args.timeout_s,
            )
            width, height, label = _field_grid(
                generation,
                full_fast=args.full_fast,
                future_fast=args.future_fast,
            )
            payload["field_maps"][generation] = _run_child(
                root,
                [
                    "--case",
                    "field",
                    "--generation",
                    generation,
                    "--grid-width",
                    str(width),
                    "--grid-height",
                    str(height),
                    "--quality-label",
                    label,
                ],
                timeout_s=args.timeout_s,
            )
        payload["metrics"] = _run_child(
            root,
            ["--case", "metrics", "--repeats", str(args.repeats)],
            timeout_s=args.timeout_s,
        )
    else:
        source = args.reuse_core.resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("schema_id") != "airmirror_perf_prep_01":
            raise ValueError("--reuse-core must name a PERF-PREP-01 JSON file")
        environment = payload.get("environment")
        if not isinstance(environment, dict):
            raise ValueError("--reuse-core environment is missing")
        if environment.get("git_head") != _git(root, "rev-parse", "HEAD"):
            raise ValueError("--reuse-core git_head differs from current HEAD")
        payload["rerun_core_source"] = str(source)
        payload["rerun_scope"] = "reuse focus/field/metrics; remeasure XR and GUI worker"
    payload["pattern_view"] = _run_child(
        root,
        ["--case", "pattern_view", "--repeats", str(args.repeats)],
        timeout_s=args.timeout_s,
    )
    payload["numerical_equivalence_anchors"] = _run_child(
        root,
        ["--case", "equivalence"],
        timeout_s=args.timeout_s,
    )
    payload["xr"] = _run_child(
        root,
        ["--case", "xr"],
        timeout_s=args.timeout_s,
    )
    payload["gui_worker"] = _run_child(
        root,
        ["--case", "worker_cancel"],
        timeout_s=args.timeout_s,
    )
    payload["measurement_finished_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
    )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--generations",
        nargs="+",
        choices=DEFAULT_GENERATIONS,
        default=list(DEFAULT_GENERATIONS),
    )
    parser.add_argument(
        "--full-fast",
        action="store_true",
        help="run Fast 80x60 field maps for Current and Advanced",
    )
    parser.add_argument(
        "--future-fast",
        action="store_true",
        help="explicitly opt in to the expensive Future Fast 80x60 field map",
    )
    parser.add_argument("--timeout-s", type=float, default=900.0)
    parser.add_argument(
        "--reuse-core",
        type=Path,
        help="reuse same-HEAD focus/field/metrics and remeasure XR/worker only",
    )
    parser.add_argument(
        "--case",
        choices=(
            "focus",
            "field",
            "metrics",
            "pattern_view",
            "equivalence",
            "xr",
            "worker_cancel",
        ),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--generation", choices=DEFAULT_GENERATIONS)
    parser.add_argument("--grid-width", type=int, default=8)
    parser.add_argument("--grid-height", type=int, default=6)
    parser.add_argument("--quality-label", default="representative_probe")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.repeats <= 0:
        raise ValueError("repeats must be positive")
    if args.timeout_s <= 0.0:
        raise ValueError("timeout-s must be positive")
    if args.case is not None:
        print(json.dumps(_case_payload(args), ensure_ascii=False, allow_nan=False))
        return 0
    if args.output is None:
        raise ValueError("--output is required for a suite run")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"benchmark output already exists: {output}")
    payload = run_suite(args)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
