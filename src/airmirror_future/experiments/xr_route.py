"""Versioned XR route documents, deterministic sampling, and collision checks."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Literal

from airmirror_future.core.types import Obstacle, Scene, Vec3, Wall
from airmirror_future.experiments.xr_dynamic_room_mvp import TrajectorySample


XR_ROUTE_SCHEMA_ID = "airmirror_xr_route_experiment"
XR_ROUTE_SCHEMA_VERSION = 1
XR_ROUTE_INTERFACE_VERSION = f"{XR_ROUTE_SCHEMA_ID}/{XR_ROUTE_SCHEMA_VERSION}"
MAX_ROUTE_SAMPLE_BUDGET = 1_000_000
_GEOMETRY_EPSILON_M = 1.0e-9


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    """Ordered SI waypoints and one unambiguous timing definition."""

    waypoints: tuple[Vec3, ...]
    timing_kind: Literal["explicit_times", "speed"]
    waypoint_times_s: tuple[float, ...] | None = None
    default_speed_m_s: float | None = None
    segment_speeds_m_s: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class RouteSamplingPolicy:
    """Deterministic temporal sampling limits for one route."""

    sample_interval_s: float
    max_samples: int


@dataclass(frozen=True, slots=True)
class RouteValidationPolicy:
    """Route contact policy; exact wall and obstacle contact is illegal."""

    clearance_warning_m: float = 0.1
    touch_is_collision: bool = True


@dataclass(frozen=True, slots=True)
class RouteCollision:
    """A continuous route segment that contacts scene geometry."""

    segment_index: int
    geometry_kind: Literal["wall", "obstacle"]
    geometry_id: str
    message: str


@dataclass(frozen=True, slots=True)
class RouteWarning:
    """A non-fatal route condition useful to a future visualizer."""

    code: str
    message: str
    waypoint_index: int | None = None
    geometry_id: str | None = None


@dataclass(frozen=True, slots=True)
class RouteValidationReport:
    """Errors, warnings, and structured collisions from route validation."""

    errors: tuple[str, ...]
    warnings: tuple[RouteWarning, ...]
    collisions: tuple[RouteCollision, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


class RouteValidationError(ValueError):
    """Raised when a route cannot be evaluated against its Scene v1 geometry."""

    def __init__(self, report: RouteValidationReport) -> None:
        self.report = report
        super().__init__("; ".join(report.errors))


@dataclass(frozen=True, slots=True, init=False)
class XRRouteExperiment:
    """Opaque validated XR route snapshot created by the public factory."""

    experiment_id: str
    scene: Scene
    scene_path: Path | None
    route: RouteDefinition
    sampling: RouteSamplingPolicy
    validation: RouteValidationPolicy
    trajectory: tuple[TrajectorySample, ...]
    validation_report: RouteValidationReport
    scene_identity: str
    trajectory_identity: str
    experiment_identity: str


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _identity(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_number(value: object, name: str) -> float:
    result = _number(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    if value > MAX_ROUTE_SAMPLE_BUDGET:
        raise ValueError(
            f"{name} cannot exceed the hard limit {MAX_ROUTE_SAMPLE_BUDGET}"
        )
    return value


def _vec3(value: object, name: str) -> Vec3:
    data = _mapping(value, name)
    try:
        return Vec3(
            _number(data["x"], f"{name}.x"),
            _number(data["y"], f"{name}.y"),
            _number(data["z"], f"{name}.z"),
        )
    except KeyError as exc:
        raise ValueError(f"{name} is missing coordinate {exc.args[0]!r}") from exc


def _parse_route(data: dict[str, Any]) -> RouteDefinition:
    waypoint_items = _sequence(data.get("waypoints"), "trajectory.waypoints")
    if not waypoint_items:
        raise ValueError("trajectory.waypoints cannot be empty")
    waypoints = tuple(
        _vec3(
            _mapping(item, f"trajectory.waypoints[{index}]").get("position_m"),
            f"trajectory.waypoints[{index}].position_m",
        )
        for index, item in enumerate(waypoint_items)
    )
    timing = _mapping(data.get("timing"), "trajectory.timing")
    kind = timing.get("kind")
    if kind == "explicit_times":
        values = _sequence(
            timing.get("waypoint_times_s"),
            "trajectory.timing.waypoint_times_s",
        )
        times = tuple(
            _number(value, f"trajectory.timing.waypoint_times_s[{index}]")
            for index, value in enumerate(values)
        )
        if len(times) != len(waypoints):
            raise ValueError("waypoint_times_s must have one value per waypoint")
        return RouteDefinition(waypoints, "explicit_times", waypoint_times_s=times)
    if kind == "speed":
        has_default = "default_speed_m_s" in timing
        has_segments = "segment_speeds_m_s" in timing
        if has_default == has_segments:
            raise ValueError(
                "speed timing requires exactly one of default_speed_m_s or "
                "segment_speeds_m_s"
            )
        if has_default:
            return RouteDefinition(
                waypoints,
                "speed",
                default_speed_m_s=_positive_number(
                    timing["default_speed_m_s"],
                    "trajectory.timing.default_speed_m_s",
                ),
            )
        speed_items = _sequence(
            timing["segment_speeds_m_s"],
            "trajectory.timing.segment_speeds_m_s",
        )
        speeds = tuple(
            _positive_number(
                value, f"trajectory.timing.segment_speeds_m_s[{index}]"
            )
            for index, value in enumerate(speed_items)
        )
        if len(speeds) != max(0, len(waypoints) - 1):
            raise ValueError("segment_speeds_m_s must have one value per segment")
        return RouteDefinition(
            waypoints,
            "speed",
            segment_speeds_m_s=speeds,
        )
    raise ValueError("trajectory.timing.kind must be 'explicit_times' or 'speed'")


def _waypoint_times(route: RouteDefinition) -> tuple[float, ...]:
    if not route.waypoints:
        raise ValueError("route waypoints cannot be empty")
    if route.timing_kind == "explicit_times":
        if (
            route.waypoint_times_s is None
            or route.default_speed_m_s is not None
            or route.segment_speeds_m_s is not None
        ):
            raise ValueError("explicit_times requires only waypoint_times_s")
        if len(route.waypoint_times_s) != len(route.waypoints):
            raise ValueError("waypoint_times_s must have one value per waypoint")
        times = tuple(
            _number(value, f"waypoint_times_s[{index}]")
            for index, value in enumerate(route.waypoint_times_s)
        )
        if times[0] != 0.0:
            raise ValueError("explicit waypoint time must start at exactly 0 s")
        if any(later <= earlier for earlier, later in zip(times, times[1:])):
            raise ValueError("explicit waypoint times must be strictly increasing")
        return times

    if route.timing_kind != "speed":
        raise ValueError("timing_kind must be 'explicit_times' or 'speed'")
    if len(route.waypoints) == 1:
        if route.default_speed_m_s is not None:
            _positive_number(route.default_speed_m_s, "default_speed_m_s")
        elif route.segment_speeds_m_s not in (None, ()):
            raise ValueError("a single-point route has no segment speeds")
        return (0.0,)
    if any(
        start.distance_to(end) <= _GEOMETRY_EPSILON_M
        for start, end in zip(route.waypoints, route.waypoints[1:])
    ):
        raise ValueError(
            "zero-length speed segment is invalid; use explicit increasing times "
            "to represent a dwell"
        )
    has_default = route.default_speed_m_s is not None
    has_segments = route.segment_speeds_m_s is not None
    if has_default == has_segments:
        raise ValueError(
            "speed timing requires exactly one default speed or segment speed tuple"
        )
    if has_default:
        speed = _positive_number(route.default_speed_m_s, "default_speed_m_s")
        speeds = (speed,) * (len(route.waypoints) - 1)
    else:
        assert route.segment_speeds_m_s is not None
        if len(route.segment_speeds_m_s) != len(route.waypoints) - 1:
            raise ValueError("segment speeds must have one value per segment")
        speeds = tuple(
            _positive_number(value, f"segment_speeds_m_s[{index}]")
            for index, value in enumerate(route.segment_speeds_m_s)
        )
    times = [0.0]
    for start, end, speed in zip(route.waypoints, route.waypoints[1:], speeds):
        times.append(times[-1] + start.distance_to(end) / speed)
    if not all(math.isfinite(value) for value in times):
        raise ValueError("derived waypoint times must be finite")
    return tuple(times)


def sample_route(
    route: RouteDefinition,
    sampling: RouteSamplingPolicy,
) -> tuple[TrajectorySample, ...]:
    """Linearly sample a route, retaining every exact waypoint and endpoint."""
    interval = _positive_number(sampling.sample_interval_s, "sample_interval_s")
    max_samples = _positive_int(sampling.max_samples, "max_samples")
    times = _waypoint_times(route)
    if len(times) > max_samples:
        raise ValueError("sampling policy exceeds max_samples")
    duration = times[-1]
    if duration == 0.0:
        return (TrajectorySample(0, 0.0, route.waypoints[0]),)
    ratio = duration / interval
    if not math.isfinite(ratio):
        raise ValueError("sampling policy exceeds max_samples")
    regular_count = math.ceil(ratio)
    aligned_waypoint_count = sum(
        math.isclose(
            time_s / interval,
            round(time_s / interval),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
        for time_s in times[:-1]
    )
    sample_count = regular_count + len(times) - aligned_waypoint_count
    if sample_count > max_samples:
        raise ValueError("sampling policy exceeds max_samples")

    scheduled = list(times)
    regular_index = 0
    while regular_index * interval < duration:
        scheduled.append(regular_index * interval)
        regular_index += 1
    scheduled.append(duration)
    scheduled.sort()
    unique_times: list[float] = []
    for value in scheduled:
        if unique_times and math.isclose(
            value, unique_times[-1], rel_tol=0.0, abs_tol=1.0e-12
        ):
            if value in times:
                unique_times[-1] = value
            continue
        unique_times.append(value)
    if len(unique_times) > max_samples:
        raise ValueError("sampling policy exceeds max_samples")

    samples: list[TrajectorySample] = []
    segment_index = 0
    for sample_index, time_s in enumerate(unique_times):
        while (
            segment_index + 1 < len(times) - 1
            and time_s > times[segment_index + 1]
        ):
            segment_index += 1
        if time_s == times[-1]:
            position = route.waypoints[-1]
        elif time_s == times[segment_index]:
            position = route.waypoints[segment_index]
        elif time_s == times[segment_index + 1]:
            position = route.waypoints[segment_index + 1]
        else:
            start_time = times[segment_index]
            fraction = (time_s - start_time) / (times[segment_index + 1] - start_time)
            start = route.waypoints[segment_index]
            end = route.waypoints[segment_index + 1]
            position = Vec3(
                start.x + fraction * (end.x - start.x),
                start.y + fraction * (end.y - start.y),
                start.z + fraction * (end.z - start.z),
            )
        samples.append(TrajectorySample(sample_index, time_s, position))
    return tuple(samples)


def retime_route_from_previous_speed(
    route: RouteDefinition,
    waypoint_index: int,
    speed_m_s: float,
) -> RouteDefinition:
    """Set one incoming-segment speed while preserving later segment durations.

    ``waypoint_index`` identifies the segment from ``index - 1`` to ``index``.
    For explicit times, the selected arrival time is recomputed and the same
    delta shifts every later arrival. Thus all downstream motion and dwell
    durations remain unchanged. For speed timing, a per-segment speed tuple is
    returned with only the selected segment changed.
    """
    speed = _positive_number(speed_m_s, "speed_m_s")
    if (
        isinstance(waypoint_index, bool)
        or not isinstance(waypoint_index, int)
        or not 1 <= waypoint_index < len(route.waypoints)
    ):
        raise ValueError("waypoint_index must identify a non-initial waypoint")
    times = _waypoint_times(route)
    previous = route.waypoints[waypoint_index - 1]
    current = route.waypoints[waypoint_index]
    distance = previous.distance_to(current)
    if distance <= _GEOMETRY_EPSILON_M:
        raise ValueError(
            "cannot retime a zero-length dwell segment from speed; edit its "
            "explicit arrival time instead"
        )

    if route.timing_kind == "explicit_times":
        arrival = times[waypoint_index - 1] + distance / speed
        delta = arrival - times[waypoint_index]
        shifted = times[:waypoint_index] + tuple(
            value + delta for value in times[waypoint_index:]
        )
        result = RouteDefinition(
            route.waypoints,
            "explicit_times",
            waypoint_times_s=shifted,
        )
    else:
        if route.default_speed_m_s is not None:
            speeds = [route.default_speed_m_s] * (len(route.waypoints) - 1)
        else:
            assert route.segment_speeds_m_s is not None
            speeds = list(route.segment_speeds_m_s)
        speeds[waypoint_index - 1] = speed
        result = RouteDefinition(
            route.waypoints,
            "speed",
            segment_speeds_m_s=tuple(speeds),
        )
    _waypoint_times(result)
    return result


def _cross_2d(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _point_on_wall_xy(point: Vec3, wall: Wall) -> bool:
    wall_dx = wall.end.x - wall.start.x
    wall_dy = wall.end.y - wall.start.y
    offset = (point.x - wall.start.x, point.y - wall.start.y)
    if abs(_cross_2d(offset, (wall_dx, wall_dy))) > _GEOMETRY_EPSILON_M:
        return False
    dot = offset[0] * wall_dx + offset[1] * wall_dy
    length_sq = wall_dx * wall_dx + wall_dy * wall_dy
    return -_GEOMETRY_EPSILON_M <= dot <= length_sq + _GEOMETRY_EPSILON_M


def _segment_intersects_wall(start: Vec3, end: Vec3, wall: Wall) -> bool:
    route_xy = (end.x - start.x, end.y - start.y)
    wall_xy = (wall.end.x - wall.start.x, wall.end.y - wall.start.y)
    offset = (wall.start.x - start.x, wall.start.y - start.y)
    route_length_sq = route_xy[0] ** 2 + route_xy[1] ** 2
    denominator = _cross_2d(route_xy, wall_xy)
    if route_length_sq <= _GEOMETRY_EPSILON_M**2:
        if not _point_on_wall_xy(start, wall):
            return False
        return min(start.z, end.z) <= wall.height_m and max(start.z, end.z) >= 0.0
    if abs(denominator) > _GEOMETRY_EPSILON_M:
        t = _cross_2d(offset, wall_xy) / denominator
        u = _cross_2d(offset, route_xy) / denominator
        if not (
            -_GEOMETRY_EPSILON_M <= t <= 1.0 + _GEOMETRY_EPSILON_M
            and -_GEOMETRY_EPSILON_M <= u <= 1.0 + _GEOMETRY_EPSILON_M
        ):
            return False
        z = start.z + t * (end.z - start.z)
        return -_GEOMETRY_EPSILON_M <= z <= wall.height_m + _GEOMETRY_EPSILON_M
    if abs(_cross_2d(offset, route_xy)) > _GEOMETRY_EPSILON_M:
        return False
    t0 = (
        (wall.start.x - start.x) * route_xy[0]
        + (wall.start.y - start.y) * route_xy[1]
    ) / route_length_sq
    t1 = (
        (wall.end.x - start.x) * route_xy[0]
        + (wall.end.y - start.y) * route_xy[1]
    ) / route_length_sq
    lower = max(0.0, min(t0, t1))
    upper = min(1.0, max(t0, t1))
    if lower > upper + _GEOMETRY_EPSILON_M:
        return False
    z0 = start.z + lower * (end.z - start.z)
    z1 = start.z + upper * (end.z - start.z)
    return min(z0, z1) <= wall.height_m and max(z0, z1) >= 0.0


def _point_in_obstacle(point: Vec3, obstacle: Obstacle) -> bool:
    return all(
        minimum - _GEOMETRY_EPSILON_M
        <= value
        <= maximum + _GEOMETRY_EPSILON_M
        for value, minimum, maximum in zip(
            (point.x, point.y, point.z),
            obstacle.min_corner.as_array(),
            obstacle.max_corner.as_array(),
        )
    )


def _segment_intersects_obstacle(
    start: Vec3, end: Vec3, obstacle: Obstacle
) -> bool:
    origin = start.as_array()
    direction = end.as_array() - origin
    minimum = obstacle.min_corner.as_array()
    maximum = obstacle.max_corner.as_array()
    lower, upper = 0.0, 1.0
    for axis in range(3):
        if abs(direction[axis]) <= _GEOMETRY_EPSILON_M:
            if (
                origin[axis] < minimum[axis] - _GEOMETRY_EPSILON_M
                or origin[axis] > maximum[axis] + _GEOMETRY_EPSILON_M
            ):
                return False
            continue
        t0 = (minimum[axis] - origin[axis]) / direction[axis]
        t1 = (maximum[axis] - origin[axis]) / direction[axis]
        lower = max(lower, min(t0, t1))
        upper = min(upper, max(t0, t1))
        if lower > upper + _GEOMETRY_EPSILON_M:
            return False
    return True


def _point_segment_distance_xy(point: Vec3, wall: Wall) -> float:
    dx = wall.end.x - wall.start.x
    dy = wall.end.y - wall.start.y
    length_sq = dx * dx + dy * dy
    fraction = max(
        0.0,
        min(
            1.0,
            ((point.x - wall.start.x) * dx + (point.y - wall.start.y) * dy)
            / length_sq,
        ),
    )
    nearest_x = wall.start.x + fraction * dx
    nearest_y = wall.start.y + fraction * dy
    return math.hypot(point.x - nearest_x, point.y - nearest_y)


def _point_obstacle_distance(point: Vec3, obstacle: Obstacle) -> float:
    squared = 0.0
    for value, minimum, maximum in zip(
        (point.x, point.y, point.z),
        obstacle.min_corner.as_array(),
        obstacle.max_corner.as_array(),
    ):
        if value < minimum:
            squared += (minimum - value) ** 2
        elif value > maximum:
            squared += (value - maximum) ** 2
    return math.sqrt(squared)


def validate_route(
    scene: Scene,
    waypoints: tuple[Vec3, ...],
    policy: RouteValidationPolicy,
) -> RouteValidationReport:
    """Validate a continuous route against room, wall, and obstacle geometry."""
    if not policy.touch_is_collision:
        raise ValueError("XR route v1 requires touch_is_collision=true")
    clearance = _number(policy.clearance_warning_m, "clearance_warning_m")
    if clearance < 0.0:
        raise ValueError("clearance_warning_m must be non-negative")
    if not waypoints:
        return RouteValidationReport(("route cannot be empty",), (), ())

    errors: list[str] = []
    warnings: list[RouteWarning] = []
    collisions: list[RouteCollision] = []
    for index, point in enumerate(waypoints):
        coordinates = (point.x, point.y, point.z)
        limits = (scene.room_size.x, scene.room_size.y, scene.room_size.z)
        if any(
            value < -_GEOMETRY_EPSILON_M or value > limit + _GEOMETRY_EPSILON_M
            for value, limit in zip(coordinates, limits)
        ):
            errors.append(f"waypoint {index} is outside the room volume")
        elif clearance > 0.0 and any(
            min(value, limit - value) <= clearance
            for value, limit in zip(coordinates, limits)
        ):
            warnings.append(
                RouteWarning(
                    "room_boundary_clearance",
                    f"waypoint {index} is within {clearance:g} m of the room boundary",
                    waypoint_index=index,
                )
            )

    segments = (
        tuple(zip(waypoints, waypoints[1:]))
        if len(waypoints) > 1
        else ((waypoints[0], waypoints[0]),)
    )
    collided_entities: set[tuple[str, str]] = set()
    for segment_index, (start, end) in enumerate(segments):
        for wall in scene.walls:
            if _segment_intersects_wall(start, end, wall):
                message = f"route segment {segment_index} contacts wall {wall.id!r}"
                collisions.append(
                    RouteCollision(segment_index, "wall", wall.id, message)
                )
                errors.append(message)
                collided_entities.add(("wall", wall.id))
        for obstacle in scene.obstacles:
            if _segment_intersects_obstacle(start, end, obstacle):
                message = (
                    f"route segment {segment_index} contacts obstacle {obstacle.id!r}"
                )
                collisions.append(
                    RouteCollision(segment_index, "obstacle", obstacle.id, message)
                )
                errors.append(message)
                collided_entities.add(("obstacle", obstacle.id))

    if clearance > 0.0:
        warning_keys: set[tuple[str, int, str]] = set()
        for index, point in enumerate(waypoints):
            for wall in scene.walls:
                key = ("wall", index, wall.id)
                if (
                    ("wall", wall.id) not in collided_entities
                    and -clearance <= point.z <= wall.height_m + clearance
                    and _point_segment_distance_xy(point, wall) <= clearance
                    and key not in warning_keys
                ):
                    warnings.append(
                        RouteWarning(
                            "wall_clearance",
                            f"waypoint {index} is within {clearance:g} m of wall {wall.id!r}",
                            index,
                            wall.id,
                        )
                    )
                    warning_keys.add(key)
            for obstacle in scene.obstacles:
                key = ("obstacle", index, obstacle.id)
                if (
                    ("obstacle", obstacle.id) not in collided_entities
                    and _point_obstacle_distance(point, obstacle) <= clearance
                    and key not in warning_keys
                ):
                    warnings.append(
                        RouteWarning(
                            "obstacle_clearance",
                            f"waypoint {index} is within {clearance:g} m of obstacle {obstacle.id!r}",
                            index,
                            obstacle.id,
                        )
                    )
                    warning_keys.add(key)
    return RouteValidationReport(tuple(errors), tuple(warnings), tuple(collisions))


def _route_payload(route: RouteDefinition) -> dict[str, object]:
    timing: dict[str, object] = {"kind": route.timing_kind}
    if route.timing_kind == "explicit_times":
        assert route.waypoint_times_s is not None
        timing["waypoint_times_s"] = [float(value) for value in route.waypoint_times_s]
    elif route.default_speed_m_s is not None:
        timing["default_speed_m_s"] = float(route.default_speed_m_s)
    else:
        assert route.segment_speeds_m_s is not None
        timing["segment_speeds_m_s"] = [
            float(value) for value in route.segment_speeds_m_s
        ]
    return {
        "waypoints": [
            {
                "position_m": {
                    "x": float(point.x),
                    "y": float(point.y),
                    "z": float(point.z),
                }
            }
            for point in route.waypoints
        ],
        "timing": timing,
    }


def _sampling_payload(sampling: RouteSamplingPolicy) -> dict[str, object]:
    return {
        "sample_interval_s": float(sampling.sample_interval_s),
        "max_samples": int(sampling.max_samples),
    }


def _validation_payload(validation: RouteValidationPolicy) -> dict[str, object]:
    return {
        "clearance_warning_m": float(validation.clearance_warning_m),
        "touch_is_collision": bool(validation.touch_is_collision),
    }


def _semantic_identity_payload(
    *,
    experiment_id: str,
    scene_identity: str,
    route: RouteDefinition,
    sampling: RouteSamplingPolicy,
    validation: RouteValidationPolicy,
) -> dict[str, object]:
    return {
        "schema_id": XR_ROUTE_SCHEMA_ID,
        "schema_version": XR_ROUTE_SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "scene_identity": scene_identity,
        "trajectory": _route_payload(route),
        "sampling": _sampling_payload(sampling),
        "validation": _validation_payload(validation),
    }


def _scene_identity(scene: Scene) -> str:
    def vec(point: Vec3) -> dict[str, float]:
        return {"x": float(point.x), "y": float(point.y), "z": float(point.z)}

    payload = {
        "name": scene.name,
        "room_size": vec(scene.room_size),
        "frequency_hz": float(scene.frequency_hz),
        "bandwidth_hz": float(scene.bandwidth_hz),
        "transmitters": [
            {
                "id": item.id,
                "position": vec(item.position),
                "power_w": float(item.power_w),
                "gain_linear": float(item.gain_linear),
            }
            for item in scene.transmitters
        ],
        "receivers": [
            {
                "id": item.id,
                "position": vec(item.position),
                "gain_linear": float(item.gain_linear),
                "noise_figure_db": float(item.noise_figure_db),
            }
            for item in scene.receivers
        ],
        "walls": [
            {
                "id": item.id,
                "start": vec(item.start),
                "end": vec(item.end),
                "height_m": float(item.height_m),
                "attenuation_db": float(item.attenuation_db),
                "reflection_magnitude": float(item.reflection_magnitude),
                "reflection_phase_rad": float(item.reflection_phase_rad),
                "blocks_los": bool(item.blocks_los),
            }
            for item in scene.walls
        ],
        "obstacles": [
            {
                "id": item.id,
                "min_corner": vec(item.min_corner),
                "max_corner": vec(item.max_corner),
                "attenuation_db": float(item.attenuation_db),
                "fully_blocking": bool(item.fully_blocking),
            }
            for item in scene.obstacles
        ],
        "ris_surfaces": [
            {
                "id": item.id,
                "position": vec(item.position),
                "yaw_rad": float(item.yaw_rad),
                "width_m": float(item.width_m),
                "height_m": float(item.height_m),
                "nx": int(item.nx),
                "ny": int(item.ny),
                "phase_bits": None if item.phase_bits is None else int(item.phase_bits),
                "reflection_efficiency": float(item.reflection_efficiency),
                "update_rate_hz": float(item.update_rate_hz),
                "self_sensing": bool(item.self_sensing),
                "generation": item.generation,
                "enabled": bool(item.enabled),
                "active": bool(item.active),
                "direction_exponent": float(item.direction_exponent),
            }
            for item in scene.ris_surfaces
        ],
        "z_eval_m": float(scene.z_eval_m),
        "coverage_threshold_db": float(scene.coverage_threshold_db),
        "random_seed": int(scene.random_seed),
        "schema_version": int(scene.schema_version),
    }
    return _identity(payload)


def _trajectory_identity(
    route: RouteDefinition,
    sampling: RouteSamplingPolicy,
    trajectory: tuple[TrajectorySample, ...],
) -> str:
    return _identity(
        {
            "trajectory": _route_payload(route),
            "sampling": _sampling_payload(sampling),
            "sampled_trajectory": [
                {
                    "sample_index": sample.sample_index,
                    "time_s": float(sample.time_s),
                    "position_m": {
                        "x": float(sample.position.x),
                        "y": float(sample.position.y),
                        "z": float(sample.position.z),
                    },
                }
                for sample in trajectory
            ],
        }
    )


def _new_route_experiment(
    *,
    experiment_id: str,
    scene: Scene,
    scene_path: Path | None,
    route: RouteDefinition,
    sampling: RouteSamplingPolicy,
    validation: RouteValidationPolicy,
    trajectory: tuple[TrajectorySample, ...],
    report: RouteValidationReport,
    scene_identity: str,
    trajectory_identity: str,
    experiment_identity: str,
) -> XRRouteExperiment:
    experiment = object.__new__(XRRouteExperiment)
    for name, value in (
        ("experiment_id", experiment_id),
        ("scene", scene),
        ("scene_path", scene_path),
        ("route", route),
        ("sampling", sampling),
        ("validation", validation),
        ("trajectory", trajectory),
        ("validation_report", report),
        ("scene_identity", scene_identity),
        ("trajectory_identity", trajectory_identity),
        ("experiment_identity", experiment_identity),
    ):
        object.__setattr__(experiment, name, value)
    return experiment


def _matching_scene_path(scene: Scene, scene_path: str | Path) -> Path:
    resolved = Path(scene_path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Scene v1 snapshot does not exist: {resolved}")
    persisted = Scene.load(resolved)
    if _scene_identity(persisted) != _scene_identity(scene):
        raise ValueError(
            "scene_path does not contain the same validated Scene v1 snapshot"
        )
    return resolved


def _write_or_reuse_scene_snapshot(scene: Scene, destination: Path) -> Path:
    resolved = destination.resolve()
    if resolved.exists():
        return _matching_scene_path(scene, resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                asdict(scene),
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    return resolved


def _portable_scene_reference(
    scene: Scene,
    scene_path: Path,
    route_destination: Path,
) -> tuple[Path, str]:
    """Return a relative Scene reference, copying across Windows drives."""
    try:
        reference = os.path.relpath(scene_path, route_destination.parent)
        return scene_path, Path(reference).as_posix()
    except ValueError:
        portable_path = route_destination.with_name(
            route_destination.stem + ".scene.json"
        )
        persisted = _write_or_reuse_scene_snapshot(scene, portable_path)
        reference = os.path.relpath(persisted, route_destination.parent)
        return persisted, Path(reference).as_posix()


def _validated_scene_copy(scene: Scene) -> Scene:
    if not isinstance(scene, Scene) or scene.schema_version != 1:
        raise ValueError("XR route v1 requires an in-memory Scene v1")
    snapshot = copy.deepcopy(scene)
    entity_groups = (
        (snapshot.transmitters, "transmitters"),
        (snapshot.receivers, "receivers"),
        (snapshot.walls, "walls"),
        (snapshot.obstacles, "obstacles"),
        (snapshot.ris_surfaces, "ris_surfaces"),
    )
    for entities, name in entity_groups:
        if not isinstance(entities, list):
            raise ValueError(f"Scene v1 {name} must be a list")
        for entity in entities:
            validator = getattr(entity, "__post_init__", None)
            if not callable(validator):
                raise ValueError(f"Scene v1 {name} contains an invalid entity")
            validator()
    snapshot.__post_init__()
    return snapshot


def create_route_experiment(
    scene: Scene,
    route: RouteDefinition,
    sampling: RouteSamplingPolicy,
    validation: RouteValidationPolicy,
    *,
    experiment_id: str,
    scene_path: str | Path | None = None,
) -> XRRouteExperiment:
    """Create one internally consistent route snapshot from in-memory inputs.

    Inputs are deep-copied before sampling, collision validation, and identity
    construction. If ``scene_path`` is supplied, it must already contain the
    same validated Scene v1 semantics. An in-memory-only snapshot is runnable
    but route-only saving rejects until a Scene snapshot is bound or the
    controlled bundle saver is used.
    """
    if not isinstance(experiment_id, str) or not experiment_id:
        raise ValueError("experiment_id must be a non-empty string")
    if not isinstance(route, RouteDefinition):
        raise ValueError("route must be a RouteDefinition")
    if not isinstance(sampling, RouteSamplingPolicy):
        raise ValueError("sampling must be a RouteSamplingPolicy")
    if not isinstance(validation, RouteValidationPolicy):
        raise ValueError("validation must be a RouteValidationPolicy")

    scene_snapshot = _validated_scene_copy(scene)
    route_snapshot = copy.deepcopy(route)
    sampling_snapshot = copy.deepcopy(sampling)
    validation_snapshot = copy.deepcopy(validation)
    trajectory = sample_route(route_snapshot, sampling_snapshot)
    report = validate_route(
        scene_snapshot,
        route_snapshot.waypoints,
        validation_snapshot,
    )
    if not report.is_valid:
        raise RouteValidationError(report)
    scene_identity = _scene_identity(scene_snapshot)
    trajectory_identity = _trajectory_identity(
        route_snapshot,
        sampling_snapshot,
        trajectory,
    )
    experiment_identity = _identity(
        _semantic_identity_payload(
            experiment_id=experiment_id,
            scene_identity=scene_identity,
            route=route_snapshot,
            sampling=sampling_snapshot,
            validation=validation_snapshot,
        )
    )
    bound_scene_path = (
        None
        if scene_path is None
        else _matching_scene_path(scene_snapshot, scene_path)
    )
    return _new_route_experiment(
        experiment_id=experiment_id,
        scene=scene_snapshot,
        scene_path=bound_scene_path,
        route=route_snapshot,
        sampling=sampling_snapshot,
        validation=validation_snapshot,
        trajectory=trajectory,
        report=report,
        scene_identity=scene_identity,
        trajectory_identity=trajectory_identity,
        experiment_identity=experiment_identity,
    )


def _assert_route_experiment_consistent(experiment: XRRouteExperiment) -> None:
    if not isinstance(experiment, XRRouteExperiment):
        raise ValueError("experiment must be an XRRouteExperiment")
    trajectory = sample_route(experiment.route, experiment.sampling)
    report = validate_route(
        experiment.scene,
        experiment.route.waypoints,
        experiment.validation,
    )
    scene_identity = _scene_identity(experiment.scene)
    trajectory_identity = _trajectory_identity(
        experiment.route,
        experiment.sampling,
        trajectory,
    )
    experiment_identity = _identity(
        _semantic_identity_payload(
            experiment_id=experiment.experiment_id,
            scene_identity=scene_identity,
            route=experiment.route,
            sampling=experiment.sampling,
            validation=experiment.validation,
        )
    )
    if (
        not report.is_valid
        or trajectory != experiment.trajectory
        or report != experiment.validation_report
        or scene_identity != experiment.scene_identity
        or trajectory_identity != experiment.trajectory_identity
        or experiment_identity != experiment.experiment_identity
    ):
        raise ValueError("XR route experiment snapshot was mutated or is inconsistent")


def load_route_experiment(path: str | Path) -> XRRouteExperiment:
    """Load, validate, identify, and sample one XR route v1 JSON document."""
    source = Path(path).resolve()
    data = _mapping(json.loads(source.read_text(encoding="utf-8")), "document")
    schema_id = data.get("schema_id")
    schema_version = data.get("schema_version")
    if schema_id != XR_ROUTE_SCHEMA_ID:
        raise ValueError(f"unsupported XR route schema_id: {schema_id!r}")
    if isinstance(schema_version, bool) or schema_version != XR_ROUTE_SCHEMA_VERSION:
        raise ValueError(f"unsupported XR route schema_version: {schema_version!r}")
    experiment_id = data.get("experiment_id")
    if not isinstance(experiment_id, str) or not experiment_id:
        raise ValueError("experiment_id must be a non-empty string")

    scene_source = _mapping(data.get("scene"), "scene")
    if scene_source.get("kind") != "scene_v1_reference":
        raise ValueError("XR route v1 scene.kind must be 'scene_v1_reference'")
    reference = scene_source.get("path")
    if not isinstance(reference, str) or not reference:
        raise ValueError("scene.path must be a non-empty relative path")
    if Path(reference).is_absolute():
        raise ValueError("scene.path must be relative to the XR route document")
    scene_path = (source.parent / Path(reference)).resolve()
    scene = Scene.load(scene_path)
    if scene.schema_version != 1:
        raise ValueError("XR route v1 requires a supported Scene v1 snapshot")

    route = _parse_route(_mapping(data.get("trajectory"), "trajectory"))
    sampling_data = _mapping(data.get("sampling"), "sampling")
    sampling = RouteSamplingPolicy(
        _positive_number(
            sampling_data.get("sample_interval_s"), "sampling.sample_interval_s"
        ),
        _positive_int(sampling_data.get("max_samples"), "sampling.max_samples"),
    )
    validation_data = _mapping(data.get("validation"), "validation")
    touch_is_collision = validation_data.get("touch_is_collision", True)
    if not isinstance(touch_is_collision, bool):
        raise ValueError("validation.touch_is_collision must be boolean")
    validation = RouteValidationPolicy(
        _number(
            validation_data.get("clearance_warning_m", 0.1),
            "validation.clearance_warning_m",
        ),
        touch_is_collision,
    )
    return create_route_experiment(
        scene,
        route,
        sampling,
        validation,
        experiment_id=experiment_id,
        scene_path=scene_path,
    )


def save_route_experiment(
    experiment: XRRouteExperiment,
    path: str | Path,
    *,
    overwrite: bool = False,
) -> None:
    """Save a route document while preserving the referenced Scene v1 identity."""
    _assert_route_experiment_consistent(experiment)
    if experiment.scene_path is None:
        raise ValueError(
            "route-only save requires a matching persisted Scene v1 snapshot; "
            "use save_route_experiment_bundle for an in-memory Scene"
        )
    scene_path = _matching_scene_path(experiment.scene, experiment.scene_path)
    destination = Path(path).resolve()
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _, reference = _portable_scene_reference(
        experiment.scene,
        scene_path,
        destination,
    )
    document = {
        "schema_id": XR_ROUTE_SCHEMA_ID,
        "schema_version": XR_ROUTE_SCHEMA_VERSION,
        "experiment_id": experiment.experiment_id,
        "scene": {
            "kind": "scene_v1_reference",
            "path": reference,
        },
        "trajectory": _route_payload(experiment.route),
        "sampling": _sampling_payload(experiment.sampling),
        "validation": _validation_payload(experiment.validation),
    }
    destination.write_text(
        json.dumps(document, allow_nan=False, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_route_experiment_bundle(
    experiment: XRRouteExperiment,
    path: str | Path,
    *,
    scene_path: str | Path | None = None,
    overwrite: bool = False,
) -> XRRouteExperiment:
    """Persist an in-memory Scene v1 snapshot and its referencing route.

    With no explicit ``scene_path``, an unbound experiment writes
    ``<route-stem>.scene.json`` beside the route. Existing Scene files are
    reused only when their validated identity matches; they are never silently
    overwritten. The returned snapshot is bound to the persisted Scene path.
    """
    _assert_route_experiment_consistent(experiment)
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    if scene_path is None:
        candidate = experiment.scene_path
        if candidate is None:
            candidate = destination.with_name(destination.stem + ".scene.json")
    else:
        candidate = Path(scene_path)
        if not candidate.is_absolute():
            candidate = destination.parent / candidate
    scene_destination = Path(candidate).resolve()
    route_destination = destination.resolve()
    if scene_destination == route_destination:
        raise ValueError("route and Scene snapshot paths must differ")
    try:
        os.path.relpath(scene_destination, route_destination.parent)
    except ValueError:
        scene_destination = route_destination.with_name(
            route_destination.stem + ".scene.json"
        )

    scene_destination = _write_or_reuse_scene_snapshot(
        experiment.scene,
        scene_destination,
    )
    bound = create_route_experiment(
        experiment.scene,
        experiment.route,
        experiment.sampling,
        experiment.validation,
        experiment_id=experiment.experiment_id,
        scene_path=scene_destination,
    )
    save_route_experiment(bound, route_destination, overwrite=overwrite)
    return bound


__all__ = [
    "MAX_ROUTE_SAMPLE_BUDGET",
    "RouteCollision",
    "RouteDefinition",
    "RouteSamplingPolicy",
    "RouteValidationError",
    "RouteValidationPolicy",
    "RouteValidationReport",
    "RouteWarning",
    "XRRouteExperiment",
    "XR_ROUTE_INTERFACE_VERSION",
    "XR_ROUTE_SCHEMA_ID",
    "XR_ROUTE_SCHEMA_VERSION",
    "create_route_experiment",
    "load_route_experiment",
    "retime_route_from_previous_speed",
    "sample_route",
    "save_route_experiment",
    "save_route_experiment_bundle",
    "validate_route",
]
