"""Built-in static Scene v1 templates for the non-release XR route editor."""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

from airmirror_future.core.types import (
    Obstacle,
    Receiver,
    Scene,
    Transmitter,
    Vec3,
    Wall,
)
from airmirror_future.core.units import dbm_to_watts
from airmirror_future.ris.generations import generation_preset
from airmirror_future.scenarios.smart_space import create_smart_space_scene


XR_EDITOR_SCENE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("complex_office", "复杂办公室 / Complex Office"),
    ("smart_space", "Current Smart Space"),
    ("future_smart_space", "Future Smart Space · exact M8 fixed field"),
    ("future_intelligent_workspace", "Future Intelligent Workspace · dual RIS demo"),
)


def _wall(
    identifier: str,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    blocks_los: bool = True,
    attenuation_db: float = 28.0,
) -> Wall:
    return Wall(
        identifier,
        Vec3(*start, 0.0),
        Vec3(*end, 0.0),
        height_m=3.2,
        attenuation_db=attenuation_db,
        reflection_magnitude=0.38,
        reflection_phase_rad=2.8,
        blocks_los=blocks_los,
    )


def create_complex_office_scene() -> Scene:
    """Create a partitioned indoor template using only existing Scene v1 types."""
    walls = [
        _wall("north", (0.0, 10.0), (14.0, 10.0), blocks_los=False, attenuation_db=80.0),
        _wall("south", (0.0, 0.0), (14.0, 0.0), blocks_los=False, attenuation_db=80.0),
        _wall("west", (0.0, 0.0), (0.0, 10.0), blocks_los=False, attenuation_db=80.0),
        _wall("east", (14.0, 0.0), (14.0, 10.0), blocks_los=False, attenuation_db=80.0),
        _wall("office-west", (4.4, 0.8), (4.4, 4.0)),
        _wall("office-east", (9.6, 0.8), (9.6, 4.0)),
        _wall("meeting-divider", (5.8, 6.2), (11.8, 6.2)),
        _wall("service-core", (7.0, 6.2), (7.0, 9.2)),
    ]
    obstacles = [
        Obstacle(
            "storage-bank",
            Vec3(1.8, 7.0, 0.0),
            Vec3(3.2, 8.8, 2.2),
            attenuation_db=18.0,
        ),
        Obstacle(
            "meeting-table",
            Vec3(8.0, 7.1, 0.0),
            Vec3(10.8, 8.5, 0.9),
            attenuation_db=8.0,
        ),
        Obstacle(
            "equipment-rack",
            Vec3(11.8, 1.4, 0.0),
            Vec3(13.0, 2.6, 2.4),
            attenuation_db=24.0,
        ),
    ]
    ris = generation_preset(
        "Current",
        identifier="ris-1",
        position=Vec3(7.0, 9.85, 1.6),
        yaw_rad=-math.pi / 2.0,
    )
    return Scene(
        name="XR Complex Office",
        room_size=Vec3(14.0, 10.0, 3.2),
        frequency_hz=5.0e9,
        bandwidth_hz=100.0e6,
        transmitters=[
            Transmitter("tx-1", Vec3(1.2, 5.2, 2.6), dbm_to_watts(20.0), 1.0)
        ],
        receivers=[Receiver("rx-1", Vec3(2.0, 2.0, 1.2), 1.0, 7.0)],
        walls=walls,
        obstacles=obstacles,
        ris_surfaces=[ris],
        z_eval_m=1.2,
        coverage_threshold_db=35.0,
        random_seed=20260901,
    )


def create_xr_editor_scene(template_id: str) -> Scene:
    """Return a fresh validated Scene for one route-editor template ID."""
    if template_id == "complex_office":
        return create_complex_office_scene()
    if template_id == "smart_space":
        scene = create_smart_space_scene("Current")
        return replace(scene, name="XR Smart Space Route Editor")
    if template_id == "future_smart_space":
        scene = create_smart_space_scene("Future")
        return replace(scene, name="XR Future Smart Space Fixed Field")
    if template_id == "future_intelligent_workspace":
        path = Path(__file__).resolve().parents[3] / "scenes" / "future_intelligent_workspace_demo.json"
        if not path.exists():
            raise FileNotFoundError(f"Future Intelligent Workspace scene asset not found: {path}")
        return Scene.load(path)
    raise ValueError(f"unknown XR editor scene template: {template_id!r}")
