"""Run a versioned XR route through the existing production three-mode path."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import tempfile
import time
from collections.abc import Callable

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from airmirror_future.core.types import CancelCheck
from airmirror_future.experiments.fnd_qa_ap_01 import (
    QUADRATURE_POLICY_ID,
    QUADRATURE_POLICY_VERSION,
)
from airmirror_future.experiments.provenance import _build_provenance_fields
from airmirror_future.experiments.run_output import _new_run_id
from airmirror_future.experiments.xr_dynamic_room_mvp import (
    ADAPTIVE_CSV_FIELDS,
    ADAPTIVE_RIS_MODE,
    MVPComputation,
    STATIC_RIS_MODE,
    _adaptive_csv_row,
    _pattern_hash,
    evaluate_adaptive_trajectory,
    generate_static_pattern,
)
from airmirror_future.experiments.xr_route import (
    XRRouteExperiment,
    load_route_experiment,
)
from airmirror_future.optimization.coherent_focus import (
    generate_coherent_target_pattern,
)
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


XR_ROUTE_RESULT_SCHEMA_ID = "airmirror_xr_route_result"
XR_ROUTE_RESULT_SCHEMA_VERSION = 1
_ROUTE_PROTOTYPE_STATUS = "non_release_xr_route_provisional"
_DEFAULT_OUTPUT_ROOT = (
    Path(tempfile.gettempdir()) / "airmirror-future" / "xr-route"
)

ROUTE_CSV_FIELDS = (
    "xr_route_schema_id",
    "xr_route_schema_version",
    "experiment_id",
    "experiment_identity",
    "scene_identity",
    "trajectory_identity",
    "route_source",
) + ADAPTIVE_CSV_FIELDS


@dataclass(frozen=True, slots=True)
class XRRouteArtifacts:
    """Exclusive artifact paths and stable identities from one route run."""

    output_directory: Path
    csv_path: Path
    png_path: Path
    metadata_path: Path
    run_id: str
    experiment_identity: str
    scene_identity: str
    trajectory_identity: str
    static_pattern_hash: str
    adaptive_pattern_hashes: tuple[str, ...]
    sample_count: int
    runtime_s: float


def compute_route_experiment(
    experiment: XRRouteExperiment,
    *,
    engine: SimulationEngine | None = None,
    model: ControllerModel | None = None,
    cancel_check: CancelCheck | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> MVPComputation:
    """Evaluate the loaded route with production No/Static/Adaptive semantics."""
    if not experiment.trajectory:
        raise ValueError("XR route experiment has no trajectory samples")
    active_engine = engine or SimulationEngine()
    active_model = model or ControllerModel()
    if cancel_check is not None and cancel_check():
        raise SimulationCancelled("XR route calculation cancelled")
    static_pattern = generate_static_pattern(
        experiment.scene,
        experiment.trajectory[0].position,
        engine=active_engine,
        model=active_model,
    )
    samples = evaluate_adaptive_trajectory(
        experiment.scene,
        experiment.trajectory,
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
    return MVPComputation(
        experiment.scene,
        experiment.trajectory,
        evaluated_static,
        samples,
    )


def _create_output_directory(output: Path | None) -> tuple[Path, str]:
    run_id = _new_run_id()
    target = _DEFAULT_OUTPUT_ROOT / run_id if output is None else Path(output)
    target.mkdir(parents=True, exist_ok=False)
    return target.resolve(), run_id if output is None else target.name


def _write_route_csv(
    path: Path,
    computation: MVPComputation,
    experiment: XRRouteExperiment,
    *,
    provenance: dict[str, object],
    timestamp: str,
    route_source: Path,
) -> None:
    baseline = {
        sample.trajectory.sample_index: sample.received_power_dbm
        for sample in computation.samples
        if sample.command_kind == "none"
    }
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROUTE_CSV_FIELDS)
        writer.writeheader()
        for sample in computation.samples:
            row = {
                "xr_route_schema_id": XR_ROUTE_RESULT_SCHEMA_ID,
                "xr_route_schema_version": XR_ROUTE_RESULT_SCHEMA_VERSION,
                "experiment_id": experiment.experiment_id,
                "experiment_identity": experiment.experiment_identity,
                "scene_identity": experiment.scene_identity,
                "trajectory_identity": experiment.trajectory_identity,
                "route_source": str(route_source),
            }
            row.update(
                _adaptive_csv_row(
                    sample,
                    scene=computation.scene,
                    provenance=provenance,
                    timestamp=timestamp,
                    baseline_received_power_dbm=baseline[
                        sample.trajectory.sample_index
                    ],
                )
            )
            row["prototype_status"] = _ROUTE_PROTOTYPE_STATUS
            writer.writerow(row)


def _write_route_plot(path: Path, computation: MVPComputation) -> None:
    figure = Figure(figsize=(8.0, 7.0))
    FigureCanvasAgg(figure)
    power_axis, snr_axis = figure.subplots(2, 1, sharex=True)
    colors = {
        "No RIS": "#64748b",
        "Static RIS": "#7c3aed",
        "Adaptive RIS": "#059669",
    }
    for mode, color in colors.items():
        selected = [sample for sample in computation.samples if sample.mode == mode]
        time_s = [sample.trajectory.time_s for sample in selected]
        power_axis.plot(
            time_s,
            [sample.received_power_dbm for sample in selected],
            marker="o",
            label=mode,
            color=color,
        )
        snr_axis.plot(
            time_s,
            [sample.snr_db for sample in selected],
            marker="o",
            label=mode,
            color=color,
        )
    power_axis.set_ylabel("Received power (dBm)")
    power_axis.set_title("XR Custom Route - Production Three-Mode Comparison")
    power_axis.grid(True, alpha=0.3)
    power_axis.legend()
    snr_axis.set_xlabel("Time (s)")
    snr_axis.set_ylabel("SNR (dB)")
    snr_axis.grid(True, alpha=0.3)
    snr_axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)


def _metadata_payload(
    *,
    experiment: XRRouteExperiment,
    computation: MVPComputation,
    provenance: dict[str, object],
    route_source: Path,
    run_id: str,
    timestamp: str,
    runtime_s: float,
) -> dict[str, object]:
    static_hash = _pattern_hash(computation.static_pattern)
    adaptive_hashes = [
        sample.command_hash
        for sample in computation.samples
        if sample.mode == ADAPTIVE_RIS_MODE
    ]
    return {
        "schema_id": XR_ROUTE_RESULT_SCHEMA_ID,
        "schema_version": XR_ROUTE_RESULT_SCHEMA_VERSION,
        "prototype_status": _ROUTE_PROTOTYPE_STATUS,
        "run_id": run_id,
        "timestamp": timestamp,
        "route_source": str(route_source),
        "scene_source": str(experiment.scene_path),
        "experiment_id": experiment.experiment_id,
        "experiment_identity": experiment.experiment_identity,
        "scene_identity": experiment.scene_identity,
        "trajectory_identity": experiment.trajectory_identity,
        "sample_count": len(experiment.trajectory),
        "mode_count": 3,
        "static_pattern_hash": static_hash,
        "adaptive_pattern_hashes": adaptive_hashes,
        "warnings": [asdict(item) for item in experiment.validation_report.warnings],
        "runtime_s": runtime_s,
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "provenance": provenance,
    }


def run_route_experiment(
    route_path: str | Path,
    output: Path | None = None,
    *,
    engine: SimulationEngine | None = None,
    model: ControllerModel | None = None,
) -> XRRouteArtifacts:
    """Load and run one route into a unique, exclusive result directory."""
    started = time.perf_counter()
    route_source = Path(route_path).resolve()
    experiment = load_route_experiment(route_source)
    output_directory, run_id = _create_output_directory(output)
    active_engine = engine or SimulationEngine()
    active_model = model or ControllerModel()
    computation = compute_route_experiment(
        experiment,
        engine=active_engine,
        model=active_model,
    )
    provenance = _build_provenance_fields(
        engine=active_engine,
        scene=computation.scene,
        focus=generate_coherent_target_pattern,
        world=active_model,
        run_id=run_id,
        quadrature_policy_id=QUADRATURE_POLICY_ID,
        quadrature_policy_version=QUADRATURE_POLICY_VERSION,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    csv_path = output_directory / "xr_route_three_mode.csv"
    png_path = output_directory / "xr_route_three_mode.png"
    metadata_path = output_directory / "xr_route_run.json"
    _write_route_csv(
        csv_path,
        computation,
        experiment,
        provenance=provenance,
        timestamp=timestamp,
        route_source=route_source,
    )
    _write_route_plot(png_path, computation)
    elapsed = time.perf_counter() - started
    metadata = _metadata_payload(
        experiment=experiment,
        computation=computation,
        provenance=provenance,
        route_source=route_source,
        run_id=run_id,
        timestamp=timestamp,
        runtime_s=elapsed,
    )
    metadata_path.write_text(
        json.dumps(metadata, allow_nan=False, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return XRRouteArtifacts(
        output_directory,
        csv_path,
        png_path,
        metadata_path,
        run_id,
        experiment.experiment_identity,
        experiment.scene_identity,
        experiment.trajectory_identity,
        _pattern_hash(computation.static_pattern),
        tuple(metadata["adaptive_pattern_hashes"]),
        len(experiment.trajectory),
        elapsed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", type=Path, help="XR route experiment JSON")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="complete exclusive result directory; defaults outside the repository",
    )
    args = parser.parse_args(argv)
    artifacts = run_route_experiment(args.route, args.output)
    print(f"Output: {artifacts.output_directory}")
    print(f"CSV: {artifacts.csv_path}")
    print(f"PNG: {artifacts.png_path}")
    print(f"Metadata: {artifacts.metadata_path}")
    print(f"Samples: {artifacts.sample_count}")
    print(f"Trajectory identity: {artifacts.trajectory_identity}")
    print("Status: non-release XR route prototype; provisional partial provenance")
    print(f"Runtime: {artifacts.runtime_s:.6f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
