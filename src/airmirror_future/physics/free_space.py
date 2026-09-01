"""Complex Friis free-space propagation."""

from __future__ import annotations

import math

import numpy as np

from airmirror_future.core.constants import MIN_DISTANCE_M, SPEED_OF_LIGHT_M_S


def wavelength_m(frequency_hz: float) -> float:
    """Return free-space wavelength ``lambda = c/f`` in metres."""
    if frequency_hz <= 0.0 or not math.isfinite(frequency_hz):
        raise ValueError("frequency_hz must be finite and positive")
    return SPEED_OF_LIGHT_M_S / frequency_hz


def wave_number_rad_m(frequency_hz: float) -> float:
    """Return the free-space wave number ``k = 2*pi/lambda`` in rad/m."""
    return 2.0 * math.pi / wavelength_m(frequency_hz)


def complex_free_space_channel(
    distance_m: float | np.ndarray,
    frequency_hz: float,
    tx_gain_linear: float = 1.0,
    rx_gain_linear: float = 1.0,
) -> complex | np.ndarray:
    """Compute the narrowband complex Friis channel.

    ``h = sqrt(Gt*Gr) * lambda/(4*pi*d) * exp(-j*k*d)``.
    Gains are linear power gains and distance is in metres.
    """
    distances = np.asarray(distance_m, dtype=float)
    if np.any(~np.isfinite(distances)) or np.any(distances < MIN_DISTANCE_M):
        raise ValueError("distance_m must be finite and greater than zero")
    if tx_gain_linear <= 0.0 or rx_gain_linear <= 0.0:
        raise ValueError("antenna gains must be positive")
    wavelength = wavelength_m(frequency_hz)
    wave_number = 2.0 * math.pi / wavelength
    channel = (
        math.sqrt(tx_gain_linear * rx_gain_linear)
        * wavelength
        / (4.0 * math.pi * distances)
        * np.exp(-1j * wave_number * distances)
    )
    return complex(channel) if channel.ndim == 0 else channel

