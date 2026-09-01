"""Command-line and desktop application entry point."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from airmirror_future.core.config import FIELD_QUALITY_PRESETS, field_quality_preset
from airmirror_future.core.types import Scene, SimulationConfig
from airmirror_future.ris.generations import generation_preset
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine


def _load_scene(path: str | None) -> Scene:
    return Scene.load(path) if path else create_smart_space_scene()


def run_headless(scene: Scene, generation: str, quality: str) -> int:
    original = scene.ris_surfaces[0]
    scene.ris_surfaces[0] = generation_preset(
        generation,
        identifier=original.id,
        position=original.position,
        yaw_rad=original.yaw_rad,
    )
    ris = scene.ris_surfaces[0]
    tx, rx = scene.transmitter(), scene.receiver()
    pattern = generate_focus_pattern(ris, tx, rx, scene.frequency_hz)
    engine = SimulationEngine()
    baseline = engine.compute_channel(scene, tx, rx, {})
    focused = engine.compute_channel(scene, tx, rx, {ris.id: pattern})
    quality_preset = field_quality_preset(quality)
    width, height = quality_preset.grid_width, quality_preset.grid_height
    field = engine.compute_field_map(
        scene, SimulationConfig(width, height), {ris.id: pattern}
    )
    payload = {
        "model": "System-level electromagnetic approximation",
        "generation": generation,
        "future_assumption": generation == "Future",
        "baseline_power_dbm": baseline.received_power_dbm,
        "focused_power_dbm": focused.received_power_dbm,
        "target_ris_gain_db": focused.received_power_dbm - baseline.received_power_dbm,
        "snr_db": focused.snr_db,
        "coverage_percent": field.coverage_percent,
        "dead_zone_percent": field.dead_zone_percent,
        "field_runtime_s": field.runtime_s,
        "grid": [width, height],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AirMirror Future RIS simulator")
    parser.add_argument("--headless", action="store_true", help="run the Smart Space demo without GUI")
    parser.add_argument("--scene", help="path to a scene JSON file")
    parser.add_argument(
        "--generation", choices=("Current", "Advanced", "Future"), default="Current"
    )
    parser.add_argument(
        "--quality", choices=tuple(item.key for item in FIELD_QUALITY_PRESETS), default="balanced"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scene = _load_scene(args.scene)
    if args.headless:
        return run_headless(scene, args.generation, args.quality)
    try:
        from airmirror_future.gui.main_window import run_gui
    except ImportError as exc:
        print(
            "PySide6 is required for the desktop interface. Install the project with "
            "'pip install -e .' or use --headless.\n"
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 2
    return run_gui(scene)


if __name__ == "__main__":
    raise SystemExit(main())
