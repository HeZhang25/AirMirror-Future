"""The v0.1 Future Smart Space vertical-slice scenario."""

from __future__ import annotations

import math

from airmirror_future.core.types import Obstacle, Receiver, Scene, Transmitter, Vec3, Wall
from airmirror_future.core.units import dbm_to_watts
from airmirror_future.ris.generations import generation_preset


def create_smart_space_scene(generation: str = "Current") -> Scene:
    """Create the documented 10 x 8 x 3 metre smart-room scenario."""
    outer_wall = {
        "height_m": 3.0,
        "attenuation_db": 80.0,
        "reflection_magnitude": 0.35,
        "reflection_phase_rad": math.pi,
        "blocks_los": False,
    }
    walls = [
        Wall("north", Vec3(0, 8, 0), Vec3(10, 8, 0), **outer_wall),
        Wall("south", Vec3(0, 0, 0), Vec3(10, 0, 0), **outer_wall),
        Wall("west", Vec3(0, 0, 0), Vec3(0, 8, 0), **outer_wall),
        Wall("east", Vec3(10, 0, 0), Vec3(10, 8, 0), **outer_wall),
        Wall(
            "partition",
            Vec3(5, 2, 0),
            Vec3(5, 6, 0),
            height_m=3.0,
            attenuation_db=30.0,
            reflection_magnitude=0.45,
            reflection_phase_rad=2.6,
            blocks_los=True,
        ),
    ]
    return Scene(
        name="Future Smart Space",
        room_size=Vec3(10.0, 8.0, 3.0),
        frequency_hz=5.0e9,
        bandwidth_hz=100.0e6,
        transmitters=[
            Transmitter("tx-1", Vec3(1.0, 4.0, 2.4), dbm_to_watts(20.0), 1.0)
        ],
        receivers=[Receiver("rx-1", Vec3(8.5, 4.0, 1.2), 1.0, 7.0)],
        walls=walls,
        obstacles=[
            Obstacle(
                "cabinet",
                Vec3(7.0, 1.5, 0.0),
                Vec3(8.0, 2.5, 2.2),
                attenuation_db=20.0,
            )
        ],
        ris_surfaces=[generation_preset(generation)],
        z_eval_m=1.2,
        coverage_threshold_db=35.0,
        random_seed=20260901,
    )
