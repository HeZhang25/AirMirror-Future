"""GUI-only seam for the externally owned XR trajectory implementation.

This module deliberately contains no interpolation, trajectory validation, or
serialization.  It defines the editor's draft view state and the calls that the
independent trajectory owner must adapt to its versioned headless contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from airmirror_future.core.types import Scene, Vec3
from airmirror_future.experiments.xr_dynamic_room_mvp import TrajectorySample


EXPECTED_TRAJECTORY_INTERFACE_VERSION = "airmirror_xr_route_experiment/1"


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

    draft: RouteDraft
    snapshot: object


class TrajectoryEditorBackend(Protocol):
    """A-side adapter seam over the independent B-owned route contract.

    The B contract currently freezes the versioned route document, validation,
    sampling, and headless computation.  Construction/saving of a newly edited
    in-memory route and speed-to-arrival-time editing still need an agreed public
    adapter before this protocol can be connected in production.
    """

    @property
    def interface_version(self) -> str: ...

    def validate(self, scene: Scene, draft: RouteDraft) -> object: ...

    def sample(self, snapshot: object) -> tuple[TrajectorySample, ...]: ...

    def save(self, snapshot: object, path: str | Path) -> None: ...

    def load(self, path: str | Path, scene: Scene) -> LoadedRoute: ...

    def retime_from_previous_speed(
        self,
        draft: RouteDraft,
        index: int,
        speed_m_s: float,
    ) -> RouteDraft: ...


class TrajectoryBackendUnavailable(RuntimeError):
    """Raised when a real B-owned trajectory adapter has not been supplied."""
