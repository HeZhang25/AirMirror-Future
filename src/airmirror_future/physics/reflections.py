"""Single-bounce image-method wall reflections."""

from __future__ import annotations

import numpy as np

from airmirror_future.core.geometry import reflect_point_across_wall, segment_intersection_2d
from airmirror_future.core.types import Receiver, Scene, Transmitter, Vec3, Wall
from airmirror_future.physics.blockage import path_attenuation_amplitude
from airmirror_future.physics.free_space import complex_free_space_channel


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


def single_wall_reflection(
    scene: Scene,
    tx: Transmitter,
    rx: Receiver,
    wall: Wall,
    reflection_coefficient: complex | None = None,
) -> tuple[complex, Vec3 | None]:
    """Compute one image-method path using total reflected path length."""
    point = reflection_point(tx.position, rx.position, wall)
    if point is None or wall.reflection_magnitude == 0.0:
        return 0.0j, None
    distance = tx.position.distance_to(point) + point.distance_to(rx.position)
    before, _ = path_attenuation_amplitude(scene, tx.position, point, {wall.id})
    after, _ = path_attenuation_amplitude(scene, point, rx.position, {wall.id})
    coefficient = wall.reflection_coefficient if reflection_coefficient is None else reflection_coefficient
    channel = complex_free_space_channel(
        distance, scene.frequency_hz, tx.gain_linear, rx.gain_linear
    )
    return channel * coefficient * before * after, point

