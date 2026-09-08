"""GUI adapter over the B-owned versioned XR route implementation.

This module contains only draft-to-contract mapping.  Interpolation, trajectory
validation, identity construction, persistence, and speed retiming stay in the
versioned headless route module.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from airmirror_future.core.types import Scene, Vec3
from airmirror_future.experiments.xr_dynamic_room_mvp import TrajectorySample
from airmirror_future.experiments.xr_route import (
    XR_ROUTE_INTERFACE_VERSION,
    RouteDefinition,
    RouteSamplingPolicy,
    RouteValidationPolicy,
    XRRouteExperiment,
    create_route_experiment,
    load_route_experiment,
    retime_route_from_previous_speed,
    save_route_experiment_bundle,
)


EXPECTED_TRAJECTORY_INTERFACE_VERSION = XR_ROUTE_INTERFACE_VERSION
DEFAULT_MAX_SAMPLES = 10_000


@dataclass(frozen=True, slots=True)
class RoutePointDraft:
    """One GUI control-point draft; not a persisted trajectory data model."""

    id: str
    position: Vec3
    time_s: float


@dataclass(frozen=True, slots=True)
class RouteDraft:
    """Editable GUI state passed to the external trajectory validator."""

    name: str
    points: tuple[RoutePointDraft, ...]
    sample_interval_s: float


@dataclass(frozen=True, slots=True)
class LoadedRoute:
    """One loaded GUI draft paired with the owner's opaque validated snapshot."""

    scene: Scene
    draft: RouteDraft
    snapshot: XRRouteExperiment


class TrajectoryEditorBackend(Protocol):
    """A-side adapter seam over the independent B-owned route contract."""

    @property
    def interface_version(self) -> str: ...

    def validate(self, scene: Scene, draft: RouteDraft) -> XRRouteExperiment: ...

    def sample(self, snapshot: XRRouteExperiment) -> tuple[TrajectorySample, ...]: ...

    def save(
        self,
        snapshot: XRRouteExperiment,
        path: str | Path,
    ) -> XRRouteExperiment: ...

    def load(self, path: str | Path) -> LoadedRoute: ...

    def retime_from_previous_speed(
        self,
        draft: RouteDraft,
        index: int,
        speed_m_s: float,
    ) -> RouteDraft: ...


class TrajectoryBackendUnavailable(RuntimeError):
    """Raised when a real B-owned trajectory adapter has not been supplied."""


class XRRouteTrajectoryBackend:
    """Production GUI adapter for ``airmirror_xr_route_experiment/1``."""

    interface_version = XR_ROUTE_INTERFACE_VERSION

    @staticmethod
    def _route_definition(draft: RouteDraft) -> RouteDefinition:
        return RouteDefinition(
            waypoints=tuple(point.position for point in draft.points),
            timing_kind="explicit_times",
            waypoint_times_s=tuple(point.time_s for point in draft.points),
        )

    def validate(self, scene: Scene, draft: RouteDraft) -> XRRouteExperiment:
        return create_route_experiment(
            scene,
            self._route_definition(draft),
            RouteSamplingPolicy(draft.sample_interval_s, DEFAULT_MAX_SAMPLES),
            RouteValidationPolicy(),
            experiment_id=draft.name,
        )

    def sample(
        self,
        snapshot: XRRouteExperiment,
    ) -> tuple[TrajectorySample, ...]:
        if not isinstance(snapshot, XRRouteExperiment):
            raise ValueError("snapshot must be an XRRouteExperiment")
        return snapshot.trajectory

    def save(
        self,
        snapshot: XRRouteExperiment,
        path: str | Path,
    ) -> XRRouteExperiment:
        return save_route_experiment_bundle(snapshot, path, overwrite=False)

    def load(self, path: str | Path) -> LoadedRoute:
        snapshot = load_route_experiment(path)
        times = snapshot.route.waypoint_times_s
        if times is None:
            resolved_times: list[float] = []
            sample_index = 0
            for waypoint in snapshot.route.waypoints:
                while (
                    sample_index < len(snapshot.trajectory)
                    and snapshot.trajectory[sample_index].position != waypoint
                ):
                    sample_index += 1
                if sample_index >= len(snapshot.trajectory):
                    raise ValueError(
                        "sampled route does not retain an exact waypoint"
                    )
                resolved_times.append(snapshot.trajectory[sample_index].time_s)
                sample_index += 1
            times = tuple(resolved_times)
        draft = RouteDraft(
            name=snapshot.experiment_id,
            points=tuple(
                RoutePointDraft(f"point-{index + 1}", position, time_s)
                for index, (position, time_s) in enumerate(
                    zip(snapshot.route.waypoints, times, strict=True)
                )
            ),
            sample_interval_s=snapshot.sampling.sample_interval_s,
        )
        return LoadedRoute(snapshot.scene, draft, snapshot)

    def retime_from_previous_speed(
        self,
        draft: RouteDraft,
        index: int,
        speed_m_s: float,
    ) -> RouteDraft:
        route = retime_route_from_previous_speed(
            self._route_definition(draft),
            index,
            speed_m_s,
        )
        if route.waypoint_times_s is None:
            raise ValueError("GUI explicit-time draft did not retain arrival times")
        points = tuple(
            replace(point, time_s=time_s)
            for point, time_s in zip(
                draft.points,
                route.waypoint_times_s,
                strict=True,
            )
        )
        return replace(draft, points=points)
