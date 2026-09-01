import math

import pytest

from airmirror_future.core.types import Receiver, Scene, Transmitter, Vec3, Wall
from airmirror_future.physics.reflections import reflection_point
from airmirror_future.simulation.engine import SimulationEngine


def _scene(blocks: bool) -> Scene:
    wall = Wall(
        "wall",
        Vec3(5.0, 0.0, 0.0),
        Vec3(5.0, 10.0, 0.0),
        attenuation_db=30.0,
        reflection_magnitude=0.0,
        blocks_los=blocks,
    )
    return Scene(
        "blockage",
        Vec3(10, 10, 3),
        5.0e9,
        20.0e6,
        [Transmitter("tx", Vec3(2, 5, 1.5))],
        [Receiver("rx", Vec3(8, 5, 1.5))],
        walls=[wall],
    )


def test_complete_los_path_applies_wall_attenuation() -> None:
    blocked = SimulationEngine().compute_channel(_scene(True))
    clear = SimulationEngine().compute_channel(_scene(False))
    ratio_db = 20.0 * math.log10(abs(blocked.los_channel) / abs(clear.los_channel))
    assert ratio_db == pytest.approx(-30.0, abs=0.01)


def test_image_method_finds_specular_point_on_finite_wall() -> None:
    wall = Wall("mirror", Vec3(0, -2, 0), Vec3(0, 2, 0), reflection_magnitude=0.5)
    point = reflection_point(Vec3(2, -1, 1.5), Vec3(2, 1, 1.5), wall)
    assert point is not None
    assert point.x == pytest.approx(0.0)
    assert point.y == pytest.approx(0.0)

