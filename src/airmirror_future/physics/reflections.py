"""Single-bounce image-method wall reflections."""

from __future__ import annotations

from dataclasses import dataclass

from airmirror_future.core.geometry import reflect_point_across_wall, segment_intersection_2d
from airmirror_future.core.types import Receiver, Scene, Transmitter, Vec3, Wall
from airmirror_future.physics.free_space import complex_free_space_channel


reflection_model_id = "finite_wall_single_bounce_image"
reflection_model_version = "1"


@dataclass(frozen=True, slots=True)
class WallReflectionPath:
    """Geometry and a single total-length Friis carrier, without wall/environment factors."""

    point: Vec3
    total_distance_m: float
    carrier: complex


def reflection_point(tx: Vec3, rx: Vec3, wall: Wall) -> Vec3 | None:
    """Return the valid specular point on a finite vertical wall, if present."""
    image = reflect_point_across_wall(tx, wall)
    hit = segment_intersection_2d(
        image.as_array(), rx.as_array(), wall.start.as_array(), wall.end.as_array()
    )
    if hit is None:
        return None
    t, _ = hit
    point = image.as_array() + t * (rx.as_array() - image.as_array())
    if not 0.0 <= point[2] <= wall.height_m:
        return None
    return Vec3(float(point[0]), float(point[1]), float(point[2]))


def single_wall_reflection_path(
    scene: Scene,
    tx: Transmitter,
    rx: Receiver,
    wall: Wall,
) -> WallReflectionPath | None:
    """Find one finite-wall path and carrier; coefficient/blockage belong to callers."""
    point = reflection_point(tx.position, rx.position, wall)
    if point is None:
        return None
    distance = tx.position.distance_to(point) + point.distance_to(rx.position)
    carrier = complex_free_space_channel(
        distance, scene.frequency_hz, tx.gain_linear, rx.gain_linear
    )
    return WallReflectionPath(point, distance, carrier)
