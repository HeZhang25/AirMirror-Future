"""Geometric primitives used by blockage and image-method reflections."""

from __future__ import annotations

import numpy as np

from airmirror_future.core.constants import MIN_DISTANCE_M
from airmirror_future.core.types import Obstacle, Vec3, Wall


def safe_distance(a: Vec3 | np.ndarray, b: Vec3 | np.ndarray) -> float:
    """Return Euclidean distance, rejecting coincident propagation points."""
    aa = a.as_array() if isinstance(a, Vec3) else np.asarray(a, dtype=float)
    bb = b.as_array() if isinstance(b, Vec3) else np.asarray(b, dtype=float)
    distance = float(np.linalg.norm(aa - bb))
    if distance < MIN_DISTANCE_M:
        raise ValueError("propagation distance is too close to zero")
    return distance


def segment_intersection_2d(
    p0: np.ndarray, p1: np.ndarray, q0: np.ndarray, q1: np.ndarray
) -> tuple[float, float] | None:
    """Return segment parameters ``(t, u)`` for a proper 2-D intersection."""
    r = p1[:2] - p0[:2]
    s = q1[:2] - q0[:2]
    cross = r[0] * s[1] - r[1] * s[0]
    if abs(cross) < 1.0e-12:
        return None
    delta = q0[:2] - p0[:2]
    t = (delta[0] * s[1] - delta[1] * s[0]) / cross
    u = (delta[0] * r[1] - delta[1] * r[0]) / cross
    if 1.0e-8 < t < 1.0 - 1.0e-8 and -1.0e-8 <= u <= 1.0 + 1.0e-8:
        return float(t), float(u)
    return None


def path_intersects_wall(start: Vec3, end: Vec3, wall: Wall) -> bool:
    intersection = segment_intersection_2d(
        start.as_array(), end.as_array(), wall.start.as_array(), wall.end.as_array()
    )
    if intersection is None:
        return False
    t, _ = intersection
    z_at_wall = start.z + t * (end.z - start.z)
    return 0.0 <= z_at_wall <= wall.height_m


def path_intersects_obstacle(start: Vec3, end: Vec3, obstacle: Obstacle) -> bool:
    """Use the slab algorithm for a segment/AABB intersection."""
    origin = start.as_array()
    direction = end.as_array() - origin
    minimum = obstacle.min_corner.as_array()
    maximum = obstacle.max_corner.as_array()
    t_min, t_max = 0.0, 1.0
    for axis in range(3):
        if abs(direction[axis]) < 1.0e-12:
            if origin[axis] < minimum[axis] or origin[axis] > maximum[axis]:
                return False
            continue
        t0 = (minimum[axis] - origin[axis]) / direction[axis]
        t1 = (maximum[axis] - origin[axis]) / direction[axis]
        if t0 > t1:
            t0, t1 = t1, t0
        t_min = max(t_min, t0)
        t_max = min(t_max, t1)
        if t_min > t_max:
            return False
    return t_max > 1.0e-8 and t_min < 1.0 - 1.0e-8


def reflect_point_across_wall(point: Vec3, wall: Wall) -> Vec3:
    """Reflect a point across the wall's infinite vertical plane."""
    a = wall.start.as_array()[:2]
    b = wall.end.as_array()[:2]
    p = point.as_array()[:2]
    tangent = b - a
    tangent /= np.linalg.norm(tangent)
    projection = a + tangent * np.dot(p - a, tangent)
    reflected = 2.0 * projection - p
    return Vec3(float(reflected[0]), float(reflected[1]), point.z)

