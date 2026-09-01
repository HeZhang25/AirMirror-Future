import math

import numpy as np
import pytest

from airmirror_future.physics.free_space import (
    complex_free_space_channel,
    wave_number_rad_m,
    wavelength_m,
)
from airmirror_future.physics.noise import noise_power_dbm, shannon_capacity_bps


def test_distance_doubled_drops_power_by_about_six_db() -> None:
    h1 = complex_free_space_channel(10.0, 5.0e9)
    h2 = complex_free_space_channel(20.0, 5.0e9)
    delta_db = 10.0 * math.log10(abs(h2) ** 2 / abs(h1) ** 2)
    assert delta_db == pytest.approx(-6.0206, abs=0.01)


def test_one_wavelength_adds_two_pi_propagation_phase() -> None:
    frequency = 5.0e9
    assert wave_number_rad_m(frequency) * wavelength_m(frequency) == pytest.approx(
        2.0 * math.pi
    )


def test_complex_field_interference() -> None:
    path = 1.2 - 0.4j
    assert abs(path + path) == pytest.approx(2.0 * abs(path))
    assert abs(path + path * np.exp(1j * math.pi)) < 1.0e-12


def test_noise_and_shannon_upper_bound_are_finite() -> None:
    noise = noise_power_dbm(100.0e6, 7.0)
    assert noise == pytest.approx(-87.0)
    assert shannon_capacity_bps(100.0e6, 10.0) > 0.0


@pytest.mark.parametrize("distance", [0.0, -1.0, float("nan")])
def test_invalid_distance_is_rejected(distance: float) -> None:
    with pytest.raises(ValueError):
        complex_free_space_channel(distance, 5.0e9)

