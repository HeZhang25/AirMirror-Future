"""Separate nominal controller and reproducible ground-truth models."""

from __future__ import annotations

from dataclasses import dataclass
import zlib

import numpy as np

from airmirror_future.core.types import RISSurface, Vec3, Wall


@dataclass(slots=True)
class ControllerModel:
    """Nominal model believed by the RIS controller."""

    name: str = "Controller Model"

    def position_delta(self, key: str) -> np.ndarray:
        return np.zeros(3)

    def ris_phase_offsets(self, ris: RISSurface) -> np.ndarray:
        return np.zeros(ris.cell_count)

    def ris_efficiency_scale(self, ris: RISSurface) -> np.ndarray:
        return np.ones(ris.cell_count)

    def wall_coefficient(self, wall: Wall) -> complex:
        return wall.reflection_coefficient


@dataclass(slots=True)
class GroundTruthModel(ControllerModel):
    """Reproducible truth model hidden from feedback optimizers."""

    seed: int = 20260901
    ris_phase_error_sigma_rad: float = 0.0
    ris_efficiency_sigma_fraction: float = 0.0
    wall_amplitude_error_sigma_fraction: float = 0.0
    wall_phase_error_sigma_rad: float = 0.0
    position_error_sigma_m: float = 0.0
    measurement_noise_sigma_db: float = 0.0
    name: str = "Ground Truth Model"

    def __post_init__(self) -> None:
        values = (
            self.ris_phase_error_sigma_rad,
            self.ris_efficiency_sigma_fraction,
            self.wall_amplitude_error_sigma_fraction,
            self.wall_phase_error_sigma_rad,
            self.position_error_sigma_m,
            self.measurement_noise_sigma_db,
        )
        if any(value < 0.0 or not np.isfinite(value) for value in values):
            raise ValueError("all model-error sigmas must be finite and non-negative")

    def _rng(self, key: str) -> np.random.Generator:
        key_seed = zlib.crc32(key.encode("utf-8")) & 0xFFFFFFFF
        return np.random.default_rng(np.random.SeedSequence([self.seed, key_seed]))

    def position_delta(self, key: str) -> np.ndarray:
        return self._rng(f"position:{key}").normal(0.0, self.position_error_sigma_m, 3)

    def ris_phase_offsets(self, ris: RISSurface) -> np.ndarray:
        return self._rng(f"phase:{ris.id}").normal(
            0.0, self.ris_phase_error_sigma_rad, ris.cell_count
        )

    def ris_efficiency_scale(self, ris: RISSurface) -> np.ndarray:
        values = self._rng(f"efficiency:{ris.id}").normal(
            1.0, self.ris_efficiency_sigma_fraction, ris.cell_count
        )
        return np.clip(values, 0.0, 1.0 / max(ris.reflection_efficiency, 1.0e-12))

    def wall_coefficient(self, wall: Wall) -> complex:
        rng = self._rng(f"wall:{wall.id}")
        magnitude = np.clip(
            wall.reflection_magnitude
            * rng.normal(1.0, self.wall_amplitude_error_sigma_fraction),
            0.0,
            1.0,
        )
        phase = wall.reflection_phase_rad + rng.normal(0.0, self.wall_phase_error_sigma_rad)
        return complex(magnitude * np.exp(1j * phase))

    def perturb(self, key: str, position: Vec3) -> Vec3:
        delta = self.position_delta(key)
        value = position.as_array() + delta
        return Vec3(float(value[0]), float(value[1]), float(value[2]))

