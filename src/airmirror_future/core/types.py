"""Validated public data structures for scenes, devices, and results."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np

from airmirror_future.core.units import dbm_to_watts


WALL_ENDPOINT_Z_ATOL_M = 1.0e-9


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True, slots=True)
class Vec3:
    """A three-dimensional point or vector in metres."""

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        for name, value in (("x", self.x), ("y", self.y), ("z", self.z)):
            _finite(value, name)

    def as_array(self) -> np.ndarray:
        return np.array((self.x, self.y, self.z), dtype=float)

    def distance_to(self, other: "Vec3") -> float:
        return float(np.linalg.norm(self.as_array() - other.as_array()))


@dataclass(slots=True)
class Transmitter:
    """RF transmitter. Power is the conducted transmit power in watts."""

    id: str
    position: Vec3
    power_w: float = field(default_factory=lambda: dbm_to_watts(20.0))
    gain_linear: float = 1.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("transmitter id cannot be empty")
        if self.power_w < 0.0 or not math.isfinite(self.power_w):
            raise ValueError("power_w must be finite and non-negative")
        if self.gain_linear <= 0.0 or not math.isfinite(self.gain_linear):
            raise ValueError("gain_linear must be finite and positive")


@dataclass(slots=True)
class Receiver:
    """Receiver position and receiver-side RF assumptions."""

    id: str
    position: Vec3
    gain_linear: float = 1.0
    noise_figure_db: float = 7.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("receiver id cannot be empty")
        if self.gain_linear <= 0.0 or not math.isfinite(self.gain_linear):
            raise ValueError("gain_linear must be finite and positive")
        _finite(self.noise_figure_db, "noise_figure_db")


@dataclass(slots=True)
class Wall:
    """A Scene v1 floor-anchored vertical wall segment."""

    id: str
    start: Vec3
    end: Vec3
    height_m: float = 3.0
    attenuation_db: float = 30.0
    reflection_magnitude: float = 0.4
    reflection_phase_rad: float = math.pi
    blocks_los: bool = True

    def __post_init__(self) -> None:
        for field_name, value in (("start.z", self.start.z), ("end.z", self.end.z)):
            if abs(value) > WALL_ENDPOINT_Z_ATOL_M:
                raise ValueError(
                    f"wall {self.id!r} {field_name}={value!r} m violates the Scene v1 "
                    "floor anchor; set start.z and end.z to 0 explicitly "
                    f"(absolute tolerance {WALL_ENDPOINT_Z_ATOL_M:g} m)"
                )
        if math.hypot(self.end.x - self.start.x, self.end.y - self.start.y) <= 0.0:
            raise ValueError(f"wall {self.id!r} endpoints must differ in XY")
        if self.height_m <= 0.0 or not math.isfinite(self.height_m):
            raise ValueError("height_m must be finite and positive")
        if self.attenuation_db < 0.0 or not math.isfinite(self.attenuation_db):
            raise ValueError("attenuation_db must be finite and non-negative")
        if not 0.0 <= self.reflection_magnitude <= 1.0:
            raise ValueError("reflection_magnitude must be in [0, 1]")
        _finite(self.reflection_phase_rad, "reflection_phase_rad")

    @property
    def reflection_coefficient(self) -> complex:
        return self.reflection_magnitude * np.exp(1j * self.reflection_phase_rad)


@dataclass(slots=True)
class Obstacle:
    """An axis-aligned rectangular absorbing obstacle."""

    id: str
    min_corner: Vec3
    max_corner: Vec3
    attenuation_db: float = 20.0
    fully_blocking: bool = False

    def __post_init__(self) -> None:
        if not (
            self.min_corner.x < self.max_corner.x
            and self.min_corner.y < self.max_corner.y
            and self.min_corner.z < self.max_corner.z
        ):
            raise ValueError("obstacle min_corner must be below max_corner")
        if self.attenuation_db < 0.0 or not math.isfinite(self.attenuation_db):
            raise ValueError("attenuation_db must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class RISGeneration:
    """Metadata for a representative, editable RIS technology preset."""

    name: str
    display_name_zh: str
    future_assumption: bool = False

    def __post_init__(self) -> None:
        if self.name not in {"Current", "Advanced", "Future"}:
            raise ValueError("generation name must be Current, Advanced, or Future")
        if not self.display_name_zh:
            raise ValueError("display_name_zh cannot be empty")


@dataclass(slots=True)
class RISSurface:
    """Finite, vertical rectangular RIS aperture.

    ``yaw_rad`` is the azimuth of the outward surface normal. ``active``
    denotes an externally powered active RIS and is intentionally unsupported
    by the v0.1 propagation engine.
    """

    id: str
    position: Vec3
    yaw_rad: float
    width_m: float
    height_m: float
    nx: int
    ny: int
    phase_bits: int | None = 1
    reflection_efficiency: float = 0.7
    update_rate_hz: float = 10.0
    self_sensing: bool = False
    generation: str = "Current"
    enabled: bool = True
    active: bool = False
    direction_exponent: float = 1.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("RIS id cannot be empty")
        if (
            self.width_m <= 0.0
            or self.height_m <= 0.0
            or not math.isfinite(self.width_m)
            or not math.isfinite(self.height_m)
        ):
            raise ValueError("RIS aperture dimensions must be finite and positive")
        if any(
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or value <= 0
            for value in (self.nx, self.ny)
        ):
            raise ValueError("RIS patch counts must be positive integers")
        if self.phase_bits is not None and (
            isinstance(self.phase_bits, (bool, np.bool_))
            or not isinstance(self.phase_bits, (int, np.integer))
            or self.phase_bits <= 0
        ):
            raise ValueError("phase_bits must be a positive integer or None for continuous")
        if not 0.0 <= self.reflection_efficiency <= 1.0:
            raise ValueError("passive RIS reflection_efficiency must be in [0, 1]")
        if self.update_rate_hz <= 0.0 or not math.isfinite(self.update_rate_hz):
            raise ValueError("update_rate_hz must be finite and positive")
        if self.direction_exponent < 0.0 or not math.isfinite(self.direction_exponent):
            raise ValueError("direction_exponent must be finite and non-negative")
        _finite(self.yaw_rad, "yaw_rad")

    @property
    def cell_count(self) -> int:
        return self.nx * self.ny

    @property
    def cell_area_m2(self) -> float:
        return self.width_m * self.height_m / self.cell_count

    @property
    def normal(self) -> np.ndarray:
        return np.array((math.cos(self.yaw_rad), math.sin(self.yaw_rad), 0.0))

    def cell_centers(self) -> np.ndarray:
        """Return cell centres as an ``[nx*ny, 3]`` SI-coordinate array."""
        tangent = np.array((-math.sin(self.yaw_rad), math.cos(self.yaw_rad), 0.0))
        u = ((np.arange(self.nx) + 0.5) / self.nx - 0.5) * self.width_m
        v = ((np.arange(self.ny) + 0.5) / self.ny - 0.5) * self.height_m
        uu, vv = np.meshgrid(u, v, indexing="xy")
        return (
            self.position.as_array()[None, :]
            + uu.reshape(-1, 1) * tangent[None, :]
            + vv.reshape(-1, 1) * np.array((0.0, 0.0, 1.0))[None, :]
        )


@dataclass(slots=True)
class Scene:
    """Serializable simulation scene. All values use SI units."""

    name: str
    room_size: Vec3
    frequency_hz: float
    bandwidth_hz: float
    transmitters: list[Transmitter]
    receivers: list[Receiver]
    walls: list[Wall] = field(default_factory=list)
    obstacles: list[Obstacle] = field(default_factory=list)
    ris_surfaces: list[RISSurface] = field(default_factory=list)
    z_eval_m: float = 1.2
    coverage_threshold_db: float = 10.0
    random_seed: int = 20260901
    schema_version: int = 1

    def __post_init__(self) -> None:
        if min(self.room_size.x, self.room_size.y, self.room_size.z) <= 0.0:
            raise ValueError("room dimensions must be positive")
        if self.frequency_hz <= 0.0 or not math.isfinite(self.frequency_hz):
            raise ValueError("frequency_hz must be finite and positive")
        if self.bandwidth_hz <= 0.0 or not math.isfinite(self.bandwidth_hz):
            raise ValueError("bandwidth_hz must be finite and positive")
        if not 0.0 <= self.z_eval_m <= self.room_size.z:
            raise ValueError("z_eval_m must be inside the room")

    def transmitter(self, identifier: str | None = None) -> Transmitter:
        if not self.transmitters:
            raise ValueError("scene has no transmitter")
        if identifier is None:
            return self.transmitters[0]
        return next(item for item in self.transmitters if item.id == identifier)

    def receiver(self, identifier: str | None = None) -> Receiver:
        if not self.receivers:
            raise ValueError("scene has no receiver")
        if identifier is None:
            return self.receivers[0]
        return next(item for item in self.receivers if item.id == identifier)

    def save(self, path: str | Path) -> None:
        from airmirror_future.scene.serialization import save_scene

        save_scene(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "Scene":
        from airmirror_future.scene.serialization import load_scene

        return load_scene(path)


MapQuantity = Literal["power", "snr", "ris_gain"]


@dataclass(slots=True)
class SimulationConfig:
    """Field-map resolution and display metric selection."""

    grid_width: int = 80
    grid_height: int = 60
    map_quantity: MapQuantity = "power"
    coverage_threshold_db: float | None = None
    batch_size: int = 256

    def __post_init__(self) -> None:
        if self.grid_width < 2 or self.grid_height < 2:
            raise ValueError("field-map dimensions must be at least 2x2")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")


@dataclass(slots=True)
class ChannelResult:
    """Complex channel components and receiver metrics for one link."""

    total_channel: complex
    los_channel: complex
    wall_channel: complex
    ris_channel: complex
    received_power_w: float
    received_power_dbm: float
    noise_power_dbm: float
    snr_db: float
    shannon_capacity_bps: float
    path_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FieldMapResult:
    """Regular field grid and derived link-budget maps."""

    x_m: np.ndarray
    y_m: np.ndarray
    received_power_dbm: np.ndarray
    snr_db: np.ndarray
    baseline_power_dbm: np.ndarray
    ris_gain_db: np.ndarray
    coverage_percent: float
    dead_zone_percent: float
    runtime_s: float


@dataclass(slots=True)
class OptimizationResult:
    """A reproducible RIS optimization result."""

    patterns: dict[str, np.ndarray]
    objective_db: float
    iterations: int
    runtime_s: float
    history_db: list[float]
    cancelled: bool = False
    # Foundation B metadata keeps hardware resolution distinct from the
    # optimizer's candidate search resolution.  Defaults preserve the v0.1
    # construction contract for callers that build results directly.
    algorithm: str = ""
    hardware_phase_bits: int | None = None
    search_levels: int | None = None
    pattern_source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


CancelCheck = Callable[[], bool]
