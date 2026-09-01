"""Versioned, explicit JSON serialization for simulation scenes."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from airmirror_future.core.types import (
    Obstacle,
    Receiver,
    RISSurface,
    Scene,
    Transmitter,
    Vec3,
    Wall,
)


def save_scene(scene: Scene, path: str | Path) -> None:
    """Save a human-readable schema-versioned scene JSON file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(asdict(scene), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _vec(data: dict[str, Any]) -> Vec3:
    return Vec3(float(data["x"]), float(data["y"]), float(data["z"]))


def load_scene(path: str | Path) -> Scene:
    """Load and validate a v1 scene JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = int(data.get("schema_version", 1))
    if version != 1:
        raise ValueError(f"unsupported scene schema_version: {version}")
    transmitters = [
        Transmitter(
            id=item["id"],
            position=_vec(item["position"]),
            power_w=float(item["power_w"]),
            gain_linear=float(item.get("gain_linear", 1.0)),
        )
        for item in data.get("transmitters", [])
    ]
    receivers = [
        Receiver(
            id=item["id"],
            position=_vec(item["position"]),
            gain_linear=float(item.get("gain_linear", 1.0)),
            noise_figure_db=float(item.get("noise_figure_db", 7.0)),
        )
        for item in data.get("receivers", [])
    ]
    walls = [
        Wall(
            id=item["id"],
            start=_vec(item["start"]),
            end=_vec(item["end"]),
            height_m=float(item.get("height_m", 3.0)),
            attenuation_db=float(item.get("attenuation_db", 30.0)),
            reflection_magnitude=float(item.get("reflection_magnitude", 0.4)),
            reflection_phase_rad=float(item.get("reflection_phase_rad", 3.141592653589793)),
            blocks_los=bool(item.get("blocks_los", True)),
        )
        for item in data.get("walls", [])
    ]
    obstacles = [
        Obstacle(
            id=item["id"],
            min_corner=_vec(item["min_corner"]),
            max_corner=_vec(item["max_corner"]),
            attenuation_db=float(item.get("attenuation_db", 20.0)),
            fully_blocking=bool(item.get("fully_blocking", False)),
        )
        for item in data.get("obstacles", [])
    ]
    ris_surfaces = [
        RISSurface(
            id=item["id"],
            position=_vec(item["position"]),
            yaw_rad=float(item["yaw_rad"]),
            width_m=float(item["width_m"]),
            height_m=float(item["height_m"]),
            nx=int(item["nx"]),
            ny=int(item["ny"]),
            phase_bits=None if item.get("phase_bits") is None else int(item["phase_bits"]),
            reflection_efficiency=float(item.get("reflection_efficiency", 0.7)),
            update_rate_hz=float(item.get("update_rate_hz", 10.0)),
            self_sensing=bool(item.get("self_sensing", False)),
            generation=str(item.get("generation", "Current")),
            enabled=bool(item.get("enabled", True)),
            active=bool(item.get("active", False)),
            direction_exponent=float(item.get("direction_exponent", 1.0)),
        )
        for item in data.get("ris_surfaces", [])
    ]
    return Scene(
        name=str(data["name"]),
        room_size=_vec(data["room_size"]),
        frequency_hz=float(data["frequency_hz"]),
        bandwidth_hz=float(data["bandwidth_hz"]),
        transmitters=transmitters,
        receivers=receivers,
        walls=walls,
        obstacles=obstacles,
        ris_surfaces=ris_surfaces,
        z_eval_m=float(data.get("z_eval_m", 1.2)),
        coverage_threshold_db=float(data.get("coverage_threshold_db", 10.0)),
        random_seed=int(data.get("random_seed", 20260901)),
        schema_version=version,
    )

