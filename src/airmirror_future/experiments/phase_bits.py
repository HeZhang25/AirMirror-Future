"""Phase-resolution sweep with fixed aperture and deterministic output."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import time

import matplotlib.pyplot as plt

from airmirror_future.core.config import field_quality_preset
from airmirror_future.core.types import SimulationConfig
from airmirror_future.experiments.provenance import _build_provenance_fields
from airmirror_future.experiments.result_classification import _classify_result_directory
from airmirror_future.experiments.run_output import _create_run_directory
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


PHASE_BITS_RESULT_FIELDS = (
    "provenance_schema_id",
    "provenance_schema_version",
    "provenance_status",
    "pending_contracts_json",
    "run_id",
    "software_version",
    "timestamp",
    "scenario",
    "frequency_hz",
    "bandwidth_hz",
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
    "rx_x_m",
    "rx_y_m",
    "rx_z_m",
    "received_power_dbm",
    "ris_gain_db",
    "snr_db",
    "coverage_percent",
    "coverage_threshold_db",
    "iterations",
    "runtime_s",
    "random_seed",
    "channel_frequency_model_id",
    "quadrature_policy_id",
    "quadrature_policy_version",
    "coefficient_model_identity",
)


def run(output: Path | None = None) -> tuple[Path, Path]:
    """Run the fixed-aperture 1/2/3/4/continuous phase sweep."""
    run_directory = _create_run_directory(output)
    output = run_directory.path

    # The experiment deliberately uses one explicit nominal controller model for
    # every channel/field-map calculation and for provenance.  This keeps the
    # selected world realization identical across baseline and focused results.
    scene = create_smart_space_scene("Advanced")
    original = scene.ris_surfaces[0]
    world = ControllerModel()
    engine = SimulationEngine()
    baseline = engine.compute_channel(scene, ris_patterns={}, model=world)
    quality = field_quality_preset("fast")
    rows: list[dict[str, object]] = []
    for bits in (1, 2, 3, 4, None):
        started = time.perf_counter()
        ris = replace(original, phase_bits=bits)
        scene.ris_surfaces[0] = ris
        pattern = generate_focus_pattern(
            ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
        )
        result = engine.compute_channel(
            scene, ris_patterns={ris.id: pattern}, model=world
        )
        field = engine.compute_field_map(
            scene,
            SimulationConfig(
                grid_width=quality.grid_width,
                grid_height=quality.grid_height,
            ),
            {ris.id: pattern},
            model=world,
        )
        rows.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scenario": scene.name,
                "frequency_hz": scene.frequency_hz,
                "bandwidth_hz": scene.bandwidth_hz,
                "generation": ris.generation,
                "ris_count": len(scene.ris_surfaces),
                "ris_width_m": ris.width_m,
                "ris_height_m": ris.height_m,
                "nx": ris.nx,
                "ny": ris.ny,
                "phase_bits": "continuous" if bits is None else bits,
                "efficiency": ris.reflection_efficiency,
                "phase_error_sigma_rad": 0.0,
                "algorithm": "Physics Focus",
                "rx_x_m": scene.receiver().position.x,
                "rx_y_m": scene.receiver().position.y,
                "rx_z_m": scene.receiver().position.z,
                "received_power_dbm": result.received_power_dbm,
                "ris_gain_db": result.received_power_dbm - baseline.received_power_dbm,
                "snr_db": result.snr_db,
                "coverage_percent": field.coverage_percent,
                "coverage_threshold_db": scene.coverage_threshold_db,
                "iterations": 1,
                "runtime_s": time.perf_counter() - started,
                "random_seed": scene.random_seed,
            }
        )

    # Provenance is generated only after the actual simulation calls complete,
    # then copied into every row as run-level metadata.
    provenance = _build_provenance_fields(
        engine=engine,
        scene=scene,
        focus=generate_focus_pattern,
        world=world,
        search_levels=None,
        run_id=run_directory.run_id,
    )
    rows = [{**row, **provenance} for row in rows]
    csv_path = output / "phase_bits.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PHASE_BITS_RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    png_path = output / "phase_bits.png"
    labels = [str(row["phase_bits"]) for row in rows]
    gains = [float(row["ris_gain_db"]) for row in rows]
    figure, axis = plt.subplots(figsize=(7, 4.2))
    axis.plot(labels, gains, marker="o", color="#7c3aed")
    axis.set_xlabel("Phase resolution")
    axis.set_ylabel("Target RIS gain (dB)")
    axis.set_title("AirMirror Future — Phase Resolution")
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    figure.savefig(png_path, dpi=160)
    plt.close(figure)

    classification = _classify_result_directory(output, expected_foundation=True)
    if classification != "foundation_partial":
        raise ValueError(
            "C2 Foundation Phase Resolution run classified unexpectedly: "
            f"{classification}"
        )
    return csv_path, png_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="complete Foundation run directory (created exclusively)",
    )
    args = parser.parse_args(argv)
    csv_path, png_path = run(args.output)
    print(f"CSV: {csv_path}")
    print(f"PNG: {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
