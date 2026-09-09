"""Headless non-release XR Dynamic Room MVP vertical slice."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from collections.abc import Callable
from typing import Literal

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import CancelCheck, ChannelResult, Scene, Vec3
from airmirror_future.experiments.provenance import _build_provenance_fields
from airmirror_future.experiments.run_output import _new_run_id
from airmirror_future.optimization.coherent_focus import (
    generate_coherent_target_pattern,
)
from airmirror_future.physics.ris_scattering import (
    PRODUCTION_QUADRATURE_ORDER,
    PRODUCTION_QUADRATURE_POLICY_ID,
    PRODUCTION_QUADRATURE_POLICY_VERSION,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.coefficient_identity import controller_ris_coefficient_identity
from airmirror_future.simulation.ground_truth import ControllerModel


NO_RIS_MODE = "No RIS"
STATIC_RIS_MODE = "Static RIS"
ADAPTIVE_RIS_MODE = "Adaptive RIS"
MVP_MODES = (NO_RIS_MODE, STATIC_RIS_MODE)
ADAPTIVE_MVP_MODES = (*MVP_MODES, ADAPTIVE_RIS_MODE)

TRAJECTORY_DURATION_S = 5.0
TRAJECTORY_SAMPLE_INTERVAL_S = 0.5
TRAJECTORY_START = Vec3(8.5, 4.0, 1.2)
TRAJECTORY_VELOCITY_M_S = Vec3(-0.3, 0.3, 0.0)

_DEFAULT_OUTPUT_ROOT = Path("results") / "prototypes" / "xr_dynamic_room_mvp"
_DEFAULT_ADAPTIVE_OUTPUT_ROOT = (
    Path("results") / "prototypes" / "xr_dynamic_room_adaptive"
)
_PROTOTYPE_STATUS = "non_release_vertical_slice"
_ADAPTIVE_PROTOTYPE_STATUS = "non_release_adaptive_provisional"
_ADAPTIVE_TIME_SEMANTICS = "discrete_samples_ideal_instantaneous_reconfiguration"
_CHANNEL_BEHAVIOR = "current_center_frequency_narrowband"
_FOCUS_PATH = "generate_coherent_target_pattern"

MVP_CSV_FIELDS = (
    "sample_index",
    "time_s",
    "rx_x_m",
    "rx_y_m",
    "rx_z_m",
    "mode",
    "received_power_dbm",
    "snr_db",
    "ris_channel_abs",
    "static_pattern_hash",
    "prototype_status",
    "scenario",
    "tx_id",
    "rx_id",
    "ris_id",
    "generation",
    "frequency_hz",
    "bandwidth_hz",
    "profile_id",
    "profile_version",
    "profile_identity",
    "simulation_model",
    "focus_path",
    "channel_behavior",
    "production_quadrature",
)

_C2_PROVENANCE_FIELDS = (
    "provenance_schema_id",
    "provenance_schema_version",
    "provenance_status",
    "pending_contracts_json",
    "run_id",
    "software_version",
    "focus_mode_id",
    "focus_mode_version",
    "search_levels",
    "profile_id",
    "profile_version",
    "profile_parameters_json",
    "profile_identity",
    "reflection_model_id",
    "reflection_model_version",
    "world_model_id",
    "world_model_version",
    "world_model_parameters_json",
    "random_seed",
    "channel_frequency_model_id",
    "quadrature_policy_id",
    "quadrature_policy_version",
    "coefficient_model_identity",
)

ADAPTIVE_CSV_FIELDS = _C2_PROVENANCE_FIELDS + (
    "timestamp",
    "prototype_status",
    "adaptive_time_semantics",
    "scenario",
    "sample_index",
    "time_s",
    "mode",
    "tx_id",
    "rx_id",
    "ris_id",
    "rx_x_m",
    "rx_y_m",
    "rx_z_m",
    "frequency_hz",
    "bandwidth_hz",
    "tx_power_w",
    "rx_noise_figure_db",
    "generation",
    "ris_count",
    "ris_width_m",
    "ris_height_m",
    "nx",
    "ny",
    "phase_bits",
    "efficiency",
    "phase_error_sigma_rad",
    "algorithm",
    "focus_path",
    "simulation_model",
    "channel_behavior",
    "production_quadrature",
    "command_kind",
    "command_hash",
    "command_size",
    "command_values_json",
    "static_pattern_hash",
    "total_channel_real",
    "total_channel_imag",
    "los_channel_real",
    "los_channel_imag",
    "wall_channel_real",
    "wall_channel_imag",
    "ris_channel_real",
    "ris_channel_imag",
    "received_power_dbm",
    "ris_gain_db",
    "noise_power_dbm",
    "snr_db",
    "coverage_percent",
    "coverage_threshold_db",
    "iterations",
    "runtime_s",
)


@dataclass(frozen=True, slots=True)
class TrajectorySample:
    """One deterministic receiver position at one simulation time."""

    sample_index: int
    time_s: float
    position: Vec3


@dataclass(frozen=True, slots=True)
class DynamicLinkSample:
    """One evaluated mode at one trajectory sample."""

    trajectory: TrajectorySample
    mode: Literal["No RIS", "Static RIS", "Adaptive RIS"]
    received_power_dbm: float
    snr_db: float
    ris_channel: complex
    static_pattern_hash: str
    total_channel: complex = 0.0j
    los_channel: complex = 0.0j
    wall_channel: complex = 0.0j
    noise_power_dbm: float = 0.0
    command_kind: Literal["none", "static", "adaptive"] = "none"
    command_hash: str = ""
    commanded_pattern: np.ndarray | None = None
    evaluation_runtime_s: float = 0.0


@dataclass(frozen=True, slots=True)
class MVPArtifacts:
    """Paths and run-level facts produced by one MVP execution."""

    csv_path: Path
    png_path: Path
    static_pattern_hash: str
    runtime_s: float


@dataclass(frozen=True, slots=True)
class AdaptiveMVPArtifacts:
    """Paths and identities from one provisional three-mode execution."""

    csv_path: Path
    png_path: Path
    run_id: str
    static_pattern_hash: str
    adaptive_pattern_hashes: tuple[str, ...]
    runtime_s: float


@dataclass(frozen=True, slots=True)
class MVPComputation:
    """One complete in-memory result reused by headless and GUI frontends."""

    scene: Scene
    trajectory: tuple[TrajectorySample, ...]
    static_pattern: np.ndarray
    samples: tuple[DynamicLinkSample, ...]


def build_trajectory() -> tuple[TrajectorySample, ...]:
    """Return ``p(t) = p0 + v*t`` for the fixed MVP sampling clock."""
    sample_count = int(round(TRAJECTORY_DURATION_S / TRAJECTORY_SAMPLE_INTERVAL_S)) + 1
    return tuple(
        TrajectorySample(
            sample_index=index,
            time_s=index * TRAJECTORY_SAMPLE_INTERVAL_S,
            position=Vec3(
                TRAJECTORY_START.x + TRAJECTORY_VELOCITY_M_S.x * index * TRAJECTORY_SAMPLE_INTERVAL_S,
                TRAJECTORY_START.y + TRAJECTORY_VELOCITY_M_S.y * index * TRAJECTORY_SAMPLE_INTERVAL_S,
                TRAJECTORY_START.z + TRAJECTORY_VELOCITY_M_S.z * index * TRAJECTORY_SAMPLE_INTERVAL_S,
            ),
        )
        for index in range(sample_count)
    )


def create_mvp_scene() -> Scene:
    """Reuse the Current Smart Space scene with the MVP's initial receiver."""
    scene = create_smart_space_scene("Current")
    receiver = replace(scene.receiver(), position=TRAJECTORY_START)
    return replace(scene, name="XR Dynamic Room MVP", receivers=[receiver])


def _validate_mvp_scene(scene: Scene) -> None:
    if len(scene.transmitters) != 1 or len(scene.receivers) != 1:
        raise ValueError("XR Dynamic Room MVP requires exactly one TX and one RX")
    if len(scene.ris_surfaces) != 1 or not scene.ris_surfaces[0].enabled:
        raise ValueError("XR Dynamic Room MVP requires exactly one enabled RIS")


def _pattern_hash(pattern: np.ndarray) -> str:
    """Hash the exact validated float64 command values in control order."""
    values = np.asarray(pattern, dtype=">f8")
    return "sha256:" + hashlib.sha256(values.tobytes(order="C")).hexdigest()


def _freeze_command(ris: object, pattern: np.ndarray) -> np.ndarray:
    """Return an owned, validated, read-only commanded-pattern snapshot."""
    frozen = validate_commanded_pattern(ris, pattern)
    frozen.setflags(write=False)
    return frozen


def generate_static_pattern(
    scene: Scene,
    initial_position: Vec3,
    *,
    engine: SimulationEngine,
    model: ControllerModel,
) -> np.ndarray:
    """Focus once at the initial RX and return an immutable command snapshot."""
    _validate_mvp_scene(scene)
    ris = scene.ris_surfaces[0]
    initial_receiver = replace(scene.receiver(), position=initial_position)
    pattern = generate_coherent_target_pattern(
        scene,
        model,
        engine=engine,
        tx=scene.transmitter(),
        rx=initial_receiver,
        ris=ris,
    )
    return _freeze_command(ris, pattern)


def generate_adaptive_pattern(
    scene: Scene,
    position: Vec3,
    *,
    engine: SimulationEngine,
    model: ControllerModel,
) -> np.ndarray:
    """Generate one legal Controller command for one discrete RX sample."""
    _validate_mvp_scene(scene)
    receiver = replace(scene.receiver(), position=position)
    pattern = generate_coherent_target_pattern(
        scene,
        model,
        engine=engine,
        tx=scene.transmitter(),
        rx=receiver,
        ris=scene.ris_surfaces[0],
    )
    return _freeze_command(scene.ris_surfaces[0], pattern)


def _evaluate_link(
    scene: Scene,
    point: TrajectorySample,
    mode: Literal["No RIS", "Static RIS", "Adaptive RIS"],
    commanded_pattern: np.ndarray | None,
    *,
    engine: SimulationEngine,
    model: ControllerModel,
    static_pattern_hash: str = "",
) -> DynamicLinkSample:
    """Evaluate one real production link against one immutable command snapshot."""
    receiver = replace(scene.receiver(), position=point.position)
    ris = scene.ris_surfaces[0]
    patterns = {} if commanded_pattern is None else {ris.id: commanded_pattern}
    started = time.perf_counter()
    result: ChannelResult = engine.compute_channel(
        scene,
        tx=scene.transmitter(),
        rx=receiver,
        ris_patterns=patterns,
        model=model,
    )
    runtime_s = time.perf_counter() - started
    finite_values = (
        result.received_power_dbm,
        result.snr_db,
        result.noise_power_dbm,
        result.total_channel.real,
        result.total_channel.imag,
        result.los_channel.real,
        result.los_channel.imag,
        result.wall_channel.real,
        result.wall_channel.imag,
        result.ris_channel.real,
        result.ris_channel.imag,
        runtime_s,
    )
    if not all(math.isfinite(value) for value in finite_values):
        raise ValueError("XR Dynamic Room MVP produced a non-finite channel result")
    command_hash = "" if commanded_pattern is None else _pattern_hash(commanded_pattern)
    command_kind: Literal["none", "static", "adaptive"] = {
        NO_RIS_MODE: "none",
        STATIC_RIS_MODE: "static",
        ADAPTIVE_RIS_MODE: "adaptive",
    }[mode]
    return DynamicLinkSample(
        trajectory=point,
        mode=mode,
        received_power_dbm=result.received_power_dbm,
        snr_db=result.snr_db,
        ris_channel=result.ris_channel,
        static_pattern_hash=static_pattern_hash,
        total_channel=result.total_channel,
        los_channel=result.los_channel,
        wall_channel=result.wall_channel,
        noise_power_dbm=result.noise_power_dbm,
        command_kind=command_kind,
        command_hash=command_hash,
        commanded_pattern=commanded_pattern,
        evaluation_runtime_s=runtime_s,
    )


def evaluate_trajectory(
    scene: Scene,
    trajectory: tuple[TrajectorySample, ...],
    static_pattern: np.ndarray,
    *,
    engine: SimulationEngine,
    model: ControllerModel,
) -> tuple[DynamicLinkSample, ...]:
    """Evaluate the two comparison modes on one shared trajectory."""
    _validate_mvp_scene(scene)
    if not trajectory:
        raise ValueError("trajectory cannot be empty")
    ris = scene.ris_surfaces[0]
    frozen_pattern = _freeze_command(ris, static_pattern)
    pattern_hash = _pattern_hash(frozen_pattern)

    samples: list[DynamicLinkSample] = []
    for point in trajectory:
        for mode in MVP_MODES:
            commanded = None if mode == NO_RIS_MODE else frozen_pattern
            samples.append(
                _evaluate_link(
                    scene,
                    point,
                    mode,
                    commanded,
                    engine=engine,
                    model=model,
                    static_pattern_hash=(
                        pattern_hash if mode == STATIC_RIS_MODE else ""
                    ),
                )
            )
    return tuple(samples)


def evaluate_adaptive_trajectory(
    scene: Scene,
    trajectory: tuple[TrajectorySample, ...],
    static_pattern: np.ndarray,
    *,
    engine: SimulationEngine,
    model: ControllerModel,
    cancel_check: CancelCheck | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[DynamicLinkSample, ...]:
    """Evaluate No/Static/Adaptive with one shared deterministic configuration.

    Adaptive Focus is recomputed once per discrete RX sample.  Cancellation is
    checked between every expensive boundary; a worker may additionally inject
    an engine that checks during finite-bit Focus candidate evaluation.
    """
    _validate_mvp_scene(scene)
    if not trajectory:
        raise ValueError("trajectory cannot be empty")
    ris = scene.ris_surfaces[0]
    frozen_static = _freeze_command(ris, static_pattern)
    static_hash = _pattern_hash(frozen_static)
    samples: list[DynamicLinkSample] = []
    total = len(trajectory)
    for completed, point in enumerate(trajectory, start=1):
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("XR adaptive link calculation cancelled")
        samples.append(
            _evaluate_link(
                scene,
                point,
                NO_RIS_MODE,
                None,
                engine=engine,
                model=model,
            )
        )
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("XR adaptive link calculation cancelled")
        samples.append(
            _evaluate_link(
                scene,
                point,
                STATIC_RIS_MODE,
                frozen_static,
                engine=engine,
                model=model,
                static_pattern_hash=static_hash,
            )
        )
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("XR adaptive link calculation cancelled")
        adaptive = generate_adaptive_pattern(
            scene,
            point.position,
            engine=engine,
            model=model,
        )
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("XR adaptive link calculation cancelled")
        samples.append(
            _evaluate_link(
                scene,
                point,
                ADAPTIVE_RIS_MODE,
                adaptive,
                engine=engine,
                model=model,
            )
        )
        if progress is not None:
            progress(completed, total)
    return tuple(samples)


def _create_output_directory(output: Path | None) -> Path:
    target = _DEFAULT_OUTPUT_ROOT / _new_run_id() if output is None else Path(output)
    target.mkdir(parents=True, exist_ok=False)
    return target


def _create_adaptive_output_directory(output: Path | None) -> Path:
    target = (
        _DEFAULT_ADAPTIVE_OUTPUT_ROOT / _new_run_id()
        if output is None
        else Path(output)
    )
    target.mkdir(parents=True, exist_ok=False)
    return target


def _csv_row(
    sample: DynamicLinkSample,
    *,
    scene: Scene,
    engine: SimulationEngine,
) -> dict[str, object]:
    ris = scene.ris_surfaces[0]
    point = sample.trajectory
    return {
        "sample_index": point.sample_index,
        "time_s": point.time_s,
        "rx_x_m": point.position.x,
        "rx_y_m": point.position.y,
        "rx_z_m": point.position.z,
        "mode": sample.mode,
        "received_power_dbm": sample.received_power_dbm,
        "snr_db": sample.snr_db,
        "ris_channel_abs": abs(sample.ris_channel),
        "static_pattern_hash": sample.static_pattern_hash,
        "prototype_status": _PROTOTYPE_STATUS,
        "scenario": scene.name,
        "tx_id": scene.transmitter().id,
        "rx_id": scene.receiver().id,
        "ris_id": ris.id,
        "generation": ris.generation,
        "frequency_hz": scene.frequency_hz,
        "bandwidth_hz": scene.bandwidth_hz,
        "profile_id": engine.profile.profile_id,
        "profile_version": engine.profile.profile_version,
        "profile_identity": engine.profile_identity,
        "simulation_model": "ControllerModel",
        "focus_path": _FOCUS_PATH,
        "channel_behavior": _CHANNEL_BEHAVIOR,
        "production_quadrature": (
            f"midpoint_{PRODUCTION_QUADRATURE_ORDER}x{PRODUCTION_QUADRATURE_ORDER}_per_control_patch"
        ),
    }


def _write_csv(
    path: Path,
    samples: tuple[DynamicLinkSample, ...],
    *,
    scene: Scene,
    engine: SimulationEngine,
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=MVP_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_csv_row(sample, scene=scene, engine=engine) for sample in samples)


def _write_plot(path: Path, samples: tuple[DynamicLinkSample, ...]) -> None:
    figure = Figure(figsize=(8.0, 7.0))
    FigureCanvasAgg(figure)
    power_axis, snr_axis = figure.subplots(2, 1, sharex=True)
    colors = {NO_RIS_MODE: "#64748b", STATIC_RIS_MODE: "#7c3aed"}
    for mode in MVP_MODES:
        selected = [sample for sample in samples if sample.mode == mode]
        time_s = [sample.trajectory.time_s for sample in selected]
        power_axis.plot(
            time_s,
            [sample.received_power_dbm for sample in selected],
            marker="o",
            label=mode,
            color=colors[mode],
        )
        snr_axis.plot(
            time_s,
            [sample.snr_db for sample in selected],
            marker="o",
            label=mode,
            color=colors[mode],
        )

    power_axis.set_ylabel("Received power (dBm)")
    power_axis.set_title("XR Dynamic Room MVP — Fixed Initial-Position RIS Command")
    power_axis.grid(True, alpha=0.3)
    power_axis.legend()
    snr_axis.set_xlabel("Time (s)")
    snr_axis.set_ylabel("SNR (dB)")
    snr_axis.grid(True, alpha=0.3)
    snr_axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)


def _command_values_json(sample: DynamicLinkSample) -> str:
    if sample.commanded_pattern is None:
        return ""
    return json.dumps(
        sample.commanded_pattern.tolist(),
        allow_nan=False,
        separators=(",", ":"),
    )


def _adaptive_csv_row(
    sample: DynamicLinkSample,
    *,
    scene: Scene,
    provenance: dict[str, object],
    timestamp: str,
    baseline_received_power_dbm: float,
    engine: SimulationEngine,
) -> dict[str, object]:
    ris = scene.ris_surfaces[0]
    point = sample.trajectory
    algorithm = {
        NO_RIS_MODE: "no_ris_contribution_disabled",
        STATIC_RIS_MODE: "initial_coherent_target_focus_frozen",
        ADAPTIVE_RIS_MODE: "per_sample_coherent_target_focus",
    }[sample.mode]
    row = dict(provenance)
    if sample.mode == NO_RIS_MODE:
        row["coefficient_model_identity"] = ""
    else:
        row["coefficient_model_identity"] = controller_ris_coefficient_identity(
            scene,
            engine,
            scene.transmitter(),
            replace(scene.receiver(), position=point.position),
            ris,
        )
    row.update(
        {
            "timestamp": timestamp,
            "prototype_status": _ADAPTIVE_PROTOTYPE_STATUS,
            "adaptive_time_semantics": _ADAPTIVE_TIME_SEMANTICS,
            "scenario": scene.name,
            "sample_index": point.sample_index,
            "time_s": point.time_s,
            "mode": sample.mode,
            "tx_id": scene.transmitter().id,
            "rx_id": scene.receiver().id,
            "ris_id": ris.id,
            "rx_x_m": point.position.x,
            "rx_y_m": point.position.y,
            "rx_z_m": point.position.z,
            "frequency_hz": scene.frequency_hz,
            "bandwidth_hz": scene.bandwidth_hz,
            "tx_power_w": scene.transmitter().power_w,
            "rx_noise_figure_db": scene.receiver().noise_figure_db,
            "generation": ris.generation,
            "ris_count": len(scene.ris_surfaces),
            "ris_width_m": ris.width_m,
            "ris_height_m": ris.height_m,
            "nx": ris.nx,
            "ny": ris.ny,
            "phase_bits": "continuous" if ris.phase_bits is None else ris.phase_bits,
            "efficiency": ris.reflection_efficiency,
            "phase_error_sigma_rad": 0.0,
            "algorithm": algorithm,
            "focus_path": _FOCUS_PATH,
            "simulation_model": "ControllerModel",
            "channel_behavior": _CHANNEL_BEHAVIOR,
            "production_quadrature": (
                f"midpoint_{PRODUCTION_QUADRATURE_ORDER}x"
                f"{PRODUCTION_QUADRATURE_ORDER}_per_control_patch"
            ),
            "command_kind": sample.command_kind,
            "command_hash": sample.command_hash,
            "command_size": (
                0 if sample.commanded_pattern is None else sample.commanded_pattern.size
            ),
            "command_values_json": _command_values_json(sample),
            "static_pattern_hash": sample.static_pattern_hash,
            "total_channel_real": sample.total_channel.real,
            "total_channel_imag": sample.total_channel.imag,
            "los_channel_real": sample.los_channel.real,
            "los_channel_imag": sample.los_channel.imag,
            "wall_channel_real": sample.wall_channel.real,
            "wall_channel_imag": sample.wall_channel.imag,
            "ris_channel_real": sample.ris_channel.real,
            "ris_channel_imag": sample.ris_channel.imag,
            "received_power_dbm": sample.received_power_dbm,
            "ris_gain_db": (
                ""
                if sample.mode == NO_RIS_MODE
                else sample.received_power_dbm - baseline_received_power_dbm
            ),
            "noise_power_dbm": sample.noise_power_dbm,
            "snr_db": sample.snr_db,
            "coverage_percent": "",
            "coverage_threshold_db": scene.coverage_threshold_db,
            "iterations": 0 if sample.mode == NO_RIS_MODE else 1,
            "runtime_s": sample.evaluation_runtime_s,
        }
    )
    return row


def _write_adaptive_csv(
    path: Path,
    computation: MVPComputation,
    *,
    provenance: dict[str, object],
    timestamp: str,
    engine: SimulationEngine,
) -> None:
    baseline = {
        sample.trajectory.sample_index: sample.received_power_dbm
        for sample in computation.samples
        if sample.mode == NO_RIS_MODE
    }
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=ADAPTIVE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(
            _adaptive_csv_row(
                sample,
                scene=computation.scene,
                provenance=provenance,
                timestamp=timestamp,
                baseline_received_power_dbm=baseline[sample.trajectory.sample_index],
                engine=engine,
            )
            for sample in computation.samples
        )


def _write_adaptive_plot(
    path: Path,
    samples: tuple[DynamicLinkSample, ...],
) -> None:
    figure = Figure(figsize=(8.0, 7.0))
    FigureCanvasAgg(figure)
    power_axis, snr_axis = figure.subplots(2, 1, sharex=True)
    colors = {
        NO_RIS_MODE: "#64748b",
        STATIC_RIS_MODE: "#7c3aed",
        ADAPTIVE_RIS_MODE: "#059669",
    }
    for mode in ADAPTIVE_MVP_MODES:
        selected = [sample for sample in samples if sample.mode == mode]
        time_s = [sample.trajectory.time_s for sample in selected]
        power_axis.plot(
            time_s,
            [sample.received_power_dbm for sample in selected],
            marker="o",
            label=mode,
            color=colors[mode],
        )
        snr_axis.plot(
            time_s,
            [sample.snr_db for sample in selected],
            marker="o",
            label=mode,
            color=colors[mode],
        )
    power_axis.set_ylabel("Received power (dBm)")
    power_axis.set_title(
        "XR Dynamic Room Adaptive Prototype — Provisional Controller Results"
    )
    power_axis.grid(True, alpha=0.3)
    power_axis.legend()
    snr_axis.set_xlabel("Time (s)")
    snr_axis.set_ylabel("SNR (dB)")
    snr_axis.grid(True, alpha=0.3)
    snr_axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)


def compute_mvp(
    *,
    engine: SimulationEngine | None = None,
    model: ControllerModel | None = None,
) -> MVPComputation:
    """Compute the frozen-pattern MVP once without writing artifacts."""
    active_engine = engine or SimulationEngine()
    active_model = model or ControllerModel()
    scene = create_mvp_scene()
    trajectory = build_trajectory()
    static_pattern = generate_static_pattern(
        scene,
        trajectory[0].position,
        engine=active_engine,
        model=active_model,
    )
    samples = evaluate_trajectory(
        scene,
        trajectory,
        static_pattern,
        engine=active_engine,
        model=active_model,
    )
    evaluated_static = next(
        sample.commanded_pattern
        for sample in samples
        if sample.mode == STATIC_RIS_MODE
    )
    assert evaluated_static is not None
    return MVPComputation(scene, trajectory, evaluated_static, samples)


def compute_adaptive_mvp(
    *,
    engine: SimulationEngine | None = None,
    model: ControllerModel | None = None,
    cancel_check: CancelCheck | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> MVPComputation:
    """Compute the provisional three-mode Controller prototype in memory."""
    active_engine = engine or SimulationEngine()
    active_model = model or ControllerModel()
    scene = create_mvp_scene()
    trajectory = build_trajectory()
    if cancel_check is not None and cancel_check():
        raise SimulationCancelled("XR adaptive link calculation cancelled")
    static_pattern = generate_static_pattern(
        scene,
        trajectory[0].position,
        engine=active_engine,
        model=active_model,
    )
    samples = evaluate_adaptive_trajectory(
        scene,
        trajectory,
        static_pattern,
        engine=active_engine,
        model=active_model,
        cancel_check=cancel_check,
        progress=progress,
    )
    evaluated_static = next(
        sample.commanded_pattern
        for sample in samples
        if sample.mode == STATIC_RIS_MODE
    )
    assert evaluated_static is not None
    return MVPComputation(scene, trajectory, evaluated_static, samples)


def run(output: Path | None = None) -> MVPArtifacts:
    """Run the deterministic No RIS versus Static RIS MVP comparison."""
    started = time.perf_counter()
    output_directory = _create_output_directory(output)
    engine = SimulationEngine()
    computation = compute_mvp(engine=engine)

    csv_path = output_directory / "xr_dynamic_room_mvp.csv"
    png_path = output_directory / "xr_dynamic_room_mvp.png"
    _write_csv(csv_path, computation.samples, scene=computation.scene, engine=engine)
    _write_plot(png_path, computation.samples)
    return MVPArtifacts(
        csv_path=csv_path,
        png_path=png_path,
        static_pattern_hash=_pattern_hash(computation.static_pattern),
        runtime_s=time.perf_counter() - started,
    )


def run_adaptive(output: Path | None = None) -> AdaptiveMVPArtifacts:
    """Run the provisional No/Static/Adaptive Controller comparison."""
    started = time.perf_counter()
    output_directory = _create_adaptive_output_directory(output)
    run_id = output_directory.name
    engine = SimulationEngine()
    model = ControllerModel()
    computation = compute_adaptive_mvp(engine=engine, model=model)
    provenance = _build_provenance_fields(
        engine=engine,
        scene=computation.scene,
        focus=generate_coherent_target_pattern,
        world=model,
        run_id=run_id,
        quadrature_policy_id=PRODUCTION_QUADRATURE_POLICY_ID,
        quadrature_policy_version=PRODUCTION_QUADRATURE_POLICY_VERSION,
    )
    provenance["coefficient_model_identity"] = ""
    timestamp = datetime.now(timezone.utc).isoformat()
    csv_path = output_directory / "xr_dynamic_room_adaptive.csv"
    png_path = output_directory / "xr_dynamic_room_adaptive.png"
    _write_adaptive_csv(
        csv_path,
        computation,
        provenance=provenance,
        timestamp=timestamp,
        engine=engine,
    )
    _write_adaptive_plot(png_path, computation.samples)
    adaptive_hashes = tuple(
        sample.command_hash
        for sample in computation.samples
        if sample.mode == ADAPTIVE_RIS_MODE
    )
    return AdaptiveMVPArtifacts(
        csv_path=csv_path,
        png_path=png_path,
        run_id=run_id,
        static_pattern_hash=_pattern_hash(computation.static_pattern),
        adaptive_pattern_hashes=adaptive_hashes,
        runtime_s=time.perf_counter() - started,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="complete no-overwrite prototype run directory",
    )
    parser.add_argument(
        "--adaptive",
        action="store_true",
        help="run the provisional three-mode Adaptive RIS extension",
    )
    args = parser.parse_args(argv)
    if args.adaptive:
        adaptive = run_adaptive(args.output)
        print(f"CSV: {adaptive.csv_path}")
        print(f"PNG: {adaptive.png_path}")
        print(f"Static pattern: {adaptive.static_pattern_hash}")
        print(f"Adaptive patterns: {len(adaptive.adaptive_pattern_hashes)}")
        print("Status: non-release adaptive prototype · provisional pending QA-CC/NB")
        print(f"Runtime: {adaptive.runtime_s:.6f} s")
        return 0
    artifacts = run(args.output)
    print(f"CSV: {artifacts.csv_path}")
    print(f"PNG: {artifacts.png_path}")
    print(f"Static pattern: {artifacts.static_pattern_hash}")
    print(f"Runtime: {artifacts.runtime_s:.6f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
