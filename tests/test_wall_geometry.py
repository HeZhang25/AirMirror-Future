from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import airmirror_future.simulation.engine as engine_module
from airmirror_future import WALL_ENDPOINT_Z_ATOL_M
from airmirror_future.core.types import Receiver, Scene, Transmitter, Vec3, Wall
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel
from airmirror_future.simulation.profiles import IndoorDeterministicProfile


ROOT = Path(__file__).resolve().parents[1]


def _reflection_scene(wall: Wall | None = None) -> Scene:
    return Scene(
        "wall-geometry",
        Vec3(10.0, 10.0, 3.0),
        5.0e9,
        20.0e6,
        [Transmitter("tx", Vec3(2.0, -1.0, 1.5))],
        [Receiver("rx", Vec3(2.0, 1.0, 1.5))],
        walls=[
            wall
            or Wall(
                "mirror",
                Vec3(0.0, -2.0, 0.0),
                Vec3(0.0, 2.0, 0.0),
                reflection_magnitude=0.5,
            )
        ],
    )


@pytest.mark.parametrize(
    ("field_name", "start_z", "end_z"),
    (("start.z", 2.0 * WALL_ENDPOINT_Z_ATOL_M, 0.0), ("end.z", 0.0, -0.25)),
)
def test_floor_anchored_wall_rejects_nonzero_endpoint_z(
    field_name: str, start_z: float, end_z: float
) -> None:
    with pytest.raises(ValueError) as error:
        Wall(
            "raised-wall",
            Vec3(0.0, 0.0, start_z),
            Vec3(1.0, 0.0, end_z),
        )

    message = str(error.value)
    assert "raised-wall" in message
    assert field_name in message
    assert "Scene v1 floor anchor" in message
    assert "set start.z and end.z to 0 explicitly" in message


def test_floor_anchor_tolerance_is_preserved_by_scene_round_trip(tmp_path: Path) -> None:
    wall = Wall(
        "round-trip-wall",
        Vec3(0.0, 0.0, WALL_ENDPOINT_Z_ATOL_M),
        Vec3(1.0, 0.0, -WALL_ENDPOINT_Z_ATOL_M),
    )
    scene = _reflection_scene(wall)
    destination = tmp_path / "scene.json"

    scene.save(destination)
    loaded_wall = Scene.load(destination).walls[0]

    assert loaded_wall.start.z == WALL_ENDPOINT_Z_ATOL_M
    assert loaded_wall.end.z == -WALL_ENDPOINT_Z_ATOL_M


def test_floor_anchored_wall_endpoints_must_differ_in_xy() -> None:
    with pytest.raises(ValueError, match=r"flat-wall.*endpoints must differ in XY"):
        Wall(
            "flat-wall",
            Vec3(1.0, 2.0, WALL_ENDPOINT_Z_ATOL_M),
            Vec3(1.0, 2.0, -WALL_ENDPOINT_Z_ATOL_M),
        )


def test_scene_v1_loader_reports_wall_id_field_and_migration(tmp_path: Path) -> None:
    data = json.loads((ROOT / "scenes" / "smart_room.json").read_text(encoding="utf-8"))
    data["walls"][0]["end"]["z"] = 0.5
    source = tmp_path / "raised-wall.json"
    source.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        Scene.load(source)

    message = str(error.value)
    assert "north" in message
    assert "end.z" in message
    assert "0.5" in message
    assert "set start.z and end.z to 0 explicitly" in message


def test_ground_truth_wall_uses_reproducible_rigid_xy_delta() -> None:
    scene = _reflection_scene()
    model_a = GroundTruthModel(seed=2718, position_error_sigma_m=0.2)
    model_b = GroundTruthModel(seed=2718, position_error_sigma_m=0.2)
    engine = SimulationEngine()

    working_a, _, _ = engine._working_scene(
        scene, scene.transmitter(), scene.receiver(), model_a
    )
    working_b, _, _ = engine._working_scene(
        scene, scene.transmitter(), scene.receiver(), model_b
    )
    original = scene.walls[0]
    perturbed = working_a.walls[0]
    delta = model_a.position_delta("wall:mirror")

    assert working_a.walls == working_b.walls
    np.testing.assert_allclose(
        perturbed.start.as_array()[:2], original.start.as_array()[:2] + delta[:2]
    )
    np.testing.assert_allclose(
        perturbed.end.as_array()[:2], original.end.as_array()[:2] + delta[:2]
    )
    np.testing.assert_allclose(
        perturbed.end.as_array()[:2] - perturbed.start.as_array()[:2],
        original.end.as_array()[:2] - original.start.as_array()[:2],
    )
    assert perturbed.start.z == original.start.z
    assert perturbed.end.z == original.end.z
    assert perturbed.height_m == original.height_m


def test_engine_shares_perturbed_wall_between_blockage_and_reflection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedWallDeltaGroundTruth(GroundTruthModel):
        def __init__(self) -> None:
            super().__init__(position_error_sigma_m=1.0)
            self.wall_delta_calls = 0

        def position_delta(self, key: str) -> np.ndarray:
            if key == "wall:mirror":
                self.wall_delta_calls += 1
                return np.array((0.25, -0.5, 99.0))
            return np.zeros(3)

    observed: dict[str, Wall] = {}

    class RecordingProfile(IndoorDeterministicProfile):
        def environment_modifier(self, *, scene, context):
            observed.setdefault("blockage", scene.walls[0])
            return super().environment_modifier(scene=scene, context=context)

    original_reflection = engine_module.single_wall_reflection_path

    def fake_reflection(
        scene: Scene,
        tx: Transmitter,
        rx: Receiver,
        wall: Wall,
    ):
        if scene.name == "wall-geometry":
            observed["reflection_scene"] = scene.walls[0]
            observed["reflection_argument"] = wall
        return original_reflection(scene, tx, rx, wall)

    monkeypatch.setattr(engine_module, "single_wall_reflection_path", fake_reflection)
    model = FixedWallDeltaGroundTruth()

    SimulationEngine(RecordingProfile()).compute_channel(_reflection_scene(), model=model)

    shared_wall = observed["blockage"]
    assert shared_wall is observed["reflection_scene"]
    assert shared_wall is observed["reflection_argument"]
    assert shared_wall.start == Vec3(0.25, -2.5, 0.0)
    assert shared_wall.end == Vec3(0.25, 1.5, 0.0)
    assert model.wall_delta_calls == 1
