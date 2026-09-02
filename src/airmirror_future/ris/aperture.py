"""Derived diagnostics for system-level equivalent RIS aperture patches."""

from __future__ import annotations

from dataclasses import dataclass
import math

from airmirror_future.core.types import RISSurface
from airmirror_future.physics.free_space import wavelength_m


EQUIVALENT_PATCH_SEMANTIC = "system-level equivalent controllable aperture patch"


@dataclass(frozen=True, slots=True)
class EquivalentPatchDiagnostics:
    """Read-only SI diagnostics for the current equivalent-patch grid.

    The pitch-to-wavelength ratios are transparency information, not physical
    meta-atom spacing checks or model-validity pass/fail criteria.
    """

    aperture_width_m: float
    aperture_height_m: float
    aperture_area_m2: float
    patch_count_x: int
    patch_count_y: int
    patch_count_total: int
    effective_pitch_x_m: float
    effective_pitch_y_m: float
    operating_frequency_hz: float
    operating_wavelength_m: float
    pitch_x_over_wavelength: float
    pitch_y_over_wavelength: float


def equivalent_patch_diagnostics(
    ris: RISSurface,
    frequency_hz: float,
) -> EquivalentPatchDiagnostics:
    """Derive aperture-patch pitch and wavelength ratios without mutation.

    ``width_m`` and ``height_m`` remain the physical aperture source of truth.
    Changing ``frequency_hz`` changes only wavelength-derived diagnostics.
    """
    wavelength = wavelength_m(frequency_hz)
    pitch_x = ris.width_m / ris.nx
    pitch_y = ris.height_m / ris.ny
    ratio_x = pitch_x / wavelength
    ratio_y = pitch_y / wavelength
    derived = (pitch_x, pitch_y, wavelength, ratio_x, ratio_y)
    if not all(math.isfinite(value) and value > 0.0 for value in derived):
        raise ValueError("derived equivalent-patch diagnostics must be finite and positive")

    return EquivalentPatchDiagnostics(
        aperture_width_m=ris.width_m,
        aperture_height_m=ris.height_m,
        aperture_area_m2=ris.width_m * ris.height_m,
        patch_count_x=ris.nx,
        patch_count_y=ris.ny,
        patch_count_total=ris.cell_count,
        effective_pitch_x_m=pitch_x,
        effective_pitch_y_m=pitch_y,
        operating_frequency_hz=float(frequency_hz),
        operating_wavelength_m=wavelength,
        pitch_x_over_wavelength=ratio_x,
        pitch_y_over_wavelength=ratio_y,
    )
