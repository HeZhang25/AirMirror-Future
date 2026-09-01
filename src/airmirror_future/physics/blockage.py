"""First-order attenuation caused by walls and rectangular obstacles."""

from __future__ import annotations

from airmirror_future.core.geometry import path_intersects_obstacle, path_intersects_wall
from airmirror_future.core.types import Scene, Vec3
from airmirror_future.core.units import db_to_amplitude


def path_attenuation_amplitude(
    scene: Scene,
    start: Vec3,
    end: Vec3,
    exclude_wall_ids: set[str] | None = None,
) -> tuple[float, list[str]]:
    """Return cumulative field attenuation and blocking object identifiers."""
    excluded = exclude_wall_ids or set()
    attenuation_db = 0.0
    blockers: list[str] = []
    for wall in scene.walls:
        if wall.id in excluded or not wall.blocks_los:
            continue
        if path_intersects_wall(start, end, wall):
            attenuation_db += wall.attenuation_db
            blockers.append(wall.id)
    for obstacle in scene.obstacles:
        if path_intersects_obstacle(start, end, obstacle):
            attenuation_db += 300.0 if obstacle.fully_blocking else obstacle.attenuation_db
            blockers.append(obstacle.id)
    return db_to_amplitude(-attenuation_db), blockers

