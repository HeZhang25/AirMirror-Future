"""Headless non-release XR Dynamic Room MVP vertical slice."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path
import time
from typing import Literal

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import Scene, Vec3
from airmirror_future.experiments.run_output import _new_run_id
from airmirror_future.optimization.coherent_focus import (
    generate_coherent_target_pattern,
)
from airmirror_future.physics.ris_scattering import PRODUCTION_QUADRATURE_ORDER
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


NO_RIS_MODE = "No RIS"
STATIC_RIS_MODE = "Static RIS"
MVP_MODES = (NO_RIS_MODE, STATIC_RIS_MODE)

TRAJECTORY_DURATION_S = 5.0
TRAJECTORY_SAMPLE_INTERVAL_S = 0.5
TRAJECTORY_START = Vec3(8.5, 4.0, 1.2)
TRAJECTORY_VELOCITY_M_S = Vec3(-0.3, 0.3, 0.0)

_DEFAULT_OUTPUT_ROOT = Path("results") / "prototypes" / "xr_dynamic_room_mvp"
_PROTOTYPE_STATUS = "non_release_vertical_slice"
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
    mode: Literal["No RIS", "Static RIS"]
    received_power_dbm: float
    snr_db: float
    ris_channel: complex
    static_pattern_hash: str


@dataclass(frozen=True, slots=True)
class MVPArtifacts:
    """Paths and run-level facts produced by one MVP execution."""

    csv_path: Path
    png_path: Path
    static_pattern_hash: str
    runtime_s: float


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
    frozen = validate_commanded_pattern(ris, pattern)
    frozen.setflags(write=False)
    return frozen


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
    frozen_pattern = validate_commanded_pattern(ris, static_pattern)
    frozen_pattern.setflags(write=False)
    pattern_hash = _pattern_hash(frozen_pattern)

    samples: list[DynamicLinkSample] = []
    for point in trajectory:
        receiver = replace(scene.receiver(), position=point.position)
        for mode in MVP_MODES:
            patterns = {} if mode == NO_RIS_MODE else {ris.id: frozen_pattern}
            result = engine.compute_channel(
                scene,
                tx=scene.transmitter(),
                rx=receiver,
                ris_patterns=patterns,
                model=model,
            )
            if not all(
                math.isfinite(value)
                for value in (
                    result.received_power_dbm,
                    result.snr_db,
                    result.ris_channel.real,
                    result.ris_channel.imag,
                )
            ):
                raise ValueError("XR Dynamic Room MVP produced a non-finite channel result")
            samples.append(
                DynamicLinkSample(
                    trajectory=point,
                    mode=mode,
                    received_power_dbm=result.received_power_dbm,
                    snr_db=result.snr_db,
                    ris_channel=result.ris_channel,
                    static_pattern_hash=pattern_hash if mode == STATIC_RIS_MODE else "",
                )
            )
    return tuple(samples)


def _create_output_directory(output: Path | None) -> Path:
    target = _DEFAULT_OUTPUT_ROOT / _new_run_id() if output is None else Path(output)
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


def run(output: Path | None = None) -> MVPArtifacts:
    """Run the deterministic No RIS versus Static RIS MVP comparison."""
    started = time.perf_counter()
    output_directory = _create_output_directory(output)
    scene = create_mvp_scene()
    trajectory = build_trajectory()
    engine = SimulationEngine()
    model = ControllerModel()
    static_pattern = generate_static_pattern(
        scene,
        trajectory[0].position,
        engine=engine,
        model=model,
    )
    samples = evaluate_trajectory(
        scene,
        trajectory,
        static_pattern,
        engine=engine,
        model=model,
    )

    csv_path = output_directory / "xr_dynamic_room_mvp.csv"
    png_path = output_directory / "xr_dynamic_room_mvp.png"
    _write_csv(csv_path, samples, scene=scene, engine=engine)
    _write_plot(png_path, samples)
    return MVPArtifacts(
        csv_path=csv_path,
        png_path=png_path,
        static_pattern_hash=_pattern_hash(static_pattern),
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
    args = parser.parse_args(argv)
    artifacts = run(args.output)
    print(f"CSV: {artifacts.csv_path}")
    print(f"PNG: {artifacts.png_path}")
    print(f"Static pattern: {artifacts.static_pattern_hash}")
    print(f"Runtime: {artifacts.runtime_s:.6f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
