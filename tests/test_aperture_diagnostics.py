from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from airmirror_future import EquivalentPatchDiagnostics, equivalent_patch_diagnostics
from airmirror_future.core.constants import SPEED_OF_LIGHT_M_S
from airmirror_future.core.types import RISSurface, Vec3
from airmirror_future.ris import EQUIVALENT_PATCH_SEMANTIC
from airmirror_future.ris.generations import generation_preset


def _surface() -> RISSurface:
    return RISSurface(
        id="ris",
        position=Vec3(0.0, 0.0, 1.5),
        yaw_rad=0.0,
        width_m=1.6,
        height_m=1.2,
        nx=8,
        ny=6,
    )


def test_effective_pitch_changes_without_resizing_aperture() -> None:
    ris = _surface()
    refined = replace(ris, nx=16, ny=12)
    base = equivalent_patch_diagnostics(ris, 5.0e9)
    refined_grid = equivalent_patch_diagnostics(refined, 5.0e9)
    higher_frequency = equivalent_patch_diagnostics(ris, 10.0e9)

    assert refined_grid.aperture_width_m == base.aperture_width_m
    assert refined_grid.aperture_height_m == base.aperture_height_m
    assert refined_grid.aperture_area_m2 == base.aperture_area_m2
    assert refined_grid.effective_pitch_x_m == pytest.approx(
        base.effective_pitch_x_m / 2.0
    )
    assert refined_grid.effective_pitch_y_m == pytest.approx(
        base.effective_pitch_y_m / 2.0
    )

    assert higher_frequency.aperture_width_m == base.aperture_width_m
    assert higher_frequency.aperture_height_m == base.aperture_height_m
    assert higher_frequency.effective_pitch_x_m == base.effective_pitch_x_m
    assert higher_frequency.effective_pitch_y_m == base.effective_pitch_y_m
    assert higher_frequency.operating_wavelength_m == pytest.approx(
        base.operating_wavelength_m / 2.0
    )
    assert higher_frequency.pitch_x_over_wavelength == pytest.approx(
        base.pitch_x_over_wavelength * 2.0
    )
    assert higher_frequency.pitch_y_over_wavelength == pytest.approx(
        base.pitch_y_over_wavelength * 2.0
    )


def test_equivalent_patch_diagnostics_report_exact_si_values() -> None:
    ris = _surface()
    frequency_hz = 5.0e9
    result = equivalent_patch_diagnostics(ris, frequency_hz)
    expected_wavelength = SPEED_OF_LIGHT_M_S / frequency_hz

    assert isinstance(result, EquivalentPatchDiagnostics)
    assert result.aperture_area_m2 == pytest.approx(1.92)
    assert result.patch_count_x == 8
    assert result.patch_count_y == 6
    assert result.patch_count_total == 48
    assert result.effective_pitch_x_m == pytest.approx(0.2)
    assert result.effective_pitch_y_m == pytest.approx(0.2)
    assert result.operating_wavelength_m == pytest.approx(expected_wavelength)
    assert result.pitch_x_over_wavelength == pytest.approx(0.2 / expected_wavelength)
    assert result.pitch_y_over_wavelength == pytest.approx(0.2 / expected_wavelength)
    assert EQUIVALENT_PATCH_SEMANTIC == (
        "system-level equivalent controllable aperture patch"
    )


@pytest.mark.parametrize("frequency_hz", (0.0, -1.0, np.nan, np.inf))
def test_equivalent_patch_diagnostics_reject_invalid_frequency(
    frequency_hz: float,
) -> None:
    with pytest.raises(ValueError, match="frequency_hz must be finite and positive"):
        equivalent_patch_diagnostics(_surface(), frequency_hz)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("width_m", np.nan),
        ("height_m", np.inf),
        ("nx", 1.5),
        ("ny", True),
    ),
)
def test_ris_surface_rejects_invalid_patch_geometry(
    field_name: str,
    value: float,
) -> None:
    with pytest.raises(ValueError):
        replace(_surface(), **{field_name: value})


@pytest.mark.parametrize("generation", ("Current", "Advanced", "Future"))
def test_generation_diagnostics_are_finite_and_positive(generation: str) -> None:
    result = equivalent_patch_diagnostics(generation_preset(generation), 5.0e9)
    numeric_values = (
        result.aperture_width_m,
        result.aperture_height_m,
        result.aperture_area_m2,
        result.effective_pitch_x_m,
        result.effective_pitch_y_m,
        result.operating_frequency_hz,
        result.operating_wavelength_m,
        result.pitch_x_over_wavelength,
        result.pitch_y_over_wavelength,
    )
    assert all(np.isfinite(value) and value > 0.0 for value in numeric_values)
