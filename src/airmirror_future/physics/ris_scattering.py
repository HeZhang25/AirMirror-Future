"""Area-normalized bistatic finite-aperture RIS scattering."""

from __future__ import annotations

import math

import numpy as np

from airmirror_future.core.constants import MIN_DISTANCE_M
from airmirror_future.core.types import RISSurface, Transmitter, Vec3
from airmirror_future.physics.free_space import wave_number_rad_m


def ris_channel_for_points(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    *,
    cell_phase_error_rad: np.ndarray | None = None,
    efficiency_scale: np.ndarray | float = 1.0,
) -> np.ndarray:
    """Return RIS complex channel for receiver points.

    Each cell contribution is

    ``sqrt(Gt*Gr*eta_n) * A_cell/(4*pi*d1*d2) * D * exp(-jk(d1+d2)+j*phi_n)``.

    The cell-area-linear amplitude makes a fixed physical aperture converge as
    it is subdivided, instead of creating energy merely by increasing cell
    count. ``D`` is the square root of a cosine power pattern because the
    directional quantity is treated as a power gain.
    """
    if ris.active:
        raise NotImplementedError("active RIS requires an explicit power and noise model")
    if not ris.enabled:
        return np.zeros(len(receiver_points), dtype=complex)
    points = np.asarray(receiver_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("receiver_points must have shape [N, 3]")
    phase = np.asarray(pattern_rad, dtype=float).reshape(-1)
    if phase.size != ris.cell_count:
        raise ValueError(f"pattern has {phase.size} phases, expected {ris.cell_count}")
    cells = ris.cell_centers()
    tx_vector = tx.position.as_array()[None, :] - cells
    d1 = np.linalg.norm(tx_vector, axis=1)
    if np.any(d1 < MIN_DISTANCE_M):
        raise ValueError("transmitter is too close to a RIS cell centre")
    incoming_direction = tx_vector / d1[:, None]
    cos_in = np.maximum(incoming_direction @ ris.normal, 0.0)

    output_vector = points[:, None, :] - cells[None, :, :]
    d2 = np.linalg.norm(output_vector, axis=2)
    if np.any(d2 < MIN_DISTANCE_M):
        raise ValueError("receiver is too close to a RIS cell centre")
    outgoing_direction = output_vector / d2[:, :, None]
    cos_out = np.maximum(np.einsum("bnk,k->bn", outgoing_direction, ris.normal), 0.0)
    direction_amplitude = np.power(cos_in[None, :] * cos_out, ris.direction_exponent / 2.0)

    errors = 0.0 if cell_phase_error_rad is None else np.asarray(cell_phase_error_rad)
    eta = np.clip(ris.reflection_efficiency * np.asarray(efficiency_scale), 0.0, 1.0)
    if np.ndim(eta) == 0:
        eta_amplitude = math.sqrt(float(eta))
    else:
        eta_amplitude = np.sqrt(np.asarray(eta).reshape(1, -1))
    amplitude = (
        math.sqrt(tx.gain_linear * receiver_gain_linear)
        * eta_amplitude
        * ris.cell_area_m2
        / (4.0 * math.pi * d1[None, :] * d2)
        * direction_amplitude
    )
    propagation_phase = -wave_number_rad_m(frequency_hz) * (d1[None, :] + d2)
    cell_phase = propagation_phase + phase[None, :] + errors
    return np.sum(amplitude * np.exp(1j * cell_phase), axis=1)


def ris_channel(
    tx: Transmitter,
    rx_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    **kwargs: object,
) -> complex:
    points = rx_position.as_array()[None, :]
    return complex(
        ris_channel_for_points(
            tx, points, receiver_gain_linear, ris, pattern_rad, frequency_hz, **kwargs
        )[0]
    )

