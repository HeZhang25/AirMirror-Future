"""Area-normalized bistatic finite-aperture RIS scattering."""

from __future__ import annotations

import math

import numpy as np

from airmirror_future.core.constants import MIN_DISTANCE_M
from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import RISSurface, Transmitter, Vec3
from airmirror_future.physics.free_space import wave_number_rad_m


def _ris_channel_for_points_from_validated_pattern(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    phase: np.ndarray,
    frequency_hz: float,
    *,
    cell_phase_error_rad: np.ndarray | None = None,
    efficiency_scale: np.ndarray | float = 1.0,
) -> np.ndarray:
    """Evaluate scattering after the commanded hardware boundary."""
    if ris.active:
        raise NotImplementedError("active RIS requires an explicit power and noise model")
    if not ris.enabled:
        return np.zeros(len(receiver_points), dtype=complex)
    points = np.asarray(receiver_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("receiver_points must have shape [N, 3]")
    cells = ris.cell_centers()
    contributions = _ris_aperture_point_contributions(
        tx, points, receiver_gain_linear, ris, cells,
        np.arange(ris.cell_count, dtype=int),
        np.full(ris.cell_count, ris.cell_area_m2), phase, frequency_hz,
        cell_phase_error_rad=cell_phase_error_rad,
        efficiency_scale=efficiency_scale,
    )
    return np.sum(contributions, axis=1)


def _ris_aperture_point_contributions(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    aperture_points: np.ndarray,
    parent_control_index: np.ndarray,
    weights_m2: np.ndarray,
    phase: np.ndarray,
    frequency_hz: float,
    *,
    cell_phase_error_rad: np.ndarray | None = None,
    efficiency_scale: np.ndarray | float = 1.0,
) -> np.ndarray:
    """Return one contribution per receiver and aperture sample."""
    samples = np.asarray(aperture_points, dtype=float)
    points = np.asarray(receiver_points, dtype=float)
    parents = np.asarray(parent_control_index, dtype=int)
    weights = np.asarray(weights_m2, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("receiver_points must have shape [N, 3]")
    if samples.ndim != 2 or samples.shape[1] != 3:
        raise ValueError("aperture_points must have shape [N, 3]")
    if parents.ndim != 1 or weights.ndim != 1 or len(parents) != len(samples) or len(weights) != len(samples):
        raise ValueError("sample arrays must have matching lengths")
    if not np.all((parents >= 0) & (parents < ris.cell_count)):
        raise ValueError("parent_control_index contains an invalid control index")
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("weights_m2 must be finite and positive")
    tx_vector = tx.position.as_array()[None, :] - samples
    d1 = np.linalg.norm(tx_vector, axis=1)
    if np.any(d1 < MIN_DISTANCE_M):
        raise ValueError("transmitter is too close to a RIS cell centre/sample point")
    incoming_direction = tx_vector / d1[:, None]
    cos_in = np.maximum(incoming_direction @ ris.normal, 0.0)

    output_vector = points[:, None, :] - samples[None, :, :]
    d2 = np.linalg.norm(output_vector, axis=2)
    if np.any(d2 < MIN_DISTANCE_M):
        raise ValueError("receiver is too close to a RIS aperture sample")
    outgoing_direction = output_vector / d2[:, :, None]
    cos_out = np.maximum(np.einsum("bnk,k->bn", outgoing_direction, ris.normal), 0.0)
    direction_amplitude = np.power(cos_in[None, :] * cos_out, ris.direction_exponent / 2.0)
    errors = np.zeros(ris.cell_count, dtype=float) if cell_phase_error_rad is None else np.asarray(cell_phase_error_rad, dtype=float)
    if errors.ndim == 0:
        errors = np.full(ris.cell_count, float(errors), dtype=float)
    if errors.ndim != 1 or errors.size != ris.cell_count or not np.all(np.isfinite(errors)):
        raise ValueError("cell_phase_error_rad must be finite with one value per control cell")
    eta = np.clip(ris.reflection_efficiency * np.asarray(efficiency_scale, dtype=float), 0.0, 1.0)
    if np.ndim(eta) == 0:
        eta_sample = np.full(len(samples), math.sqrt(float(eta)), dtype=float)
    else:
        eta_values = np.asarray(eta, dtype=float).reshape(-1)
        if eta_values.size != ris.cell_count:
            raise ValueError("efficiency_scale must be scalar or one value per control cell")
        eta_sample = np.sqrt(eta_values[parents])
    amplitude = (
        math.sqrt(tx.gain_linear * receiver_gain_linear)
        * eta_sample[None, :] * weights[None, :]
        / (4.0 * math.pi * d1[None, :] * d2) * direction_amplitude
    )
    propagation_phase = -wave_number_rad_m(frequency_hz) * (d1[None, :] + d2)
    sample_phase = propagation_phase + phase[parents][None, :] + errors[parents][None, :]
    return amplitude * np.exp(1j * sample_phase)


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
    phase = validate_commanded_pattern(ris, pattern_rad)
    return _ris_channel_for_points_from_validated_pattern(
        tx,
        receiver_points,
        receiver_gain_linear,
        ris,
        phase,
        frequency_hz,
        cell_phase_error_rad=cell_phase_error_rad,
        efficiency_scale=efficiency_scale,
    )


def ris_channel(
    tx: Transmitter,
    rx_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    **kwargs: object,
) -> complex:
    phase = validate_commanded_pattern(ris, pattern_rad)
    points = rx_position.as_array()[None, :]
    return complex(
        _ris_channel_for_points_from_validated_pattern(
            tx, points, receiver_gain_linear, ris, phase, frequency_hz, **kwargs
        )[0]
    )


def _ris_channel_from_validated_pattern(
    tx: Transmitter,
    rx_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    **kwargs: object,
) -> complex:
    """Internal scalar entry for an engine-validated commanded snapshot."""
    points = rx_position.as_array()[None, :]
    return complex(
        _ris_channel_for_points_from_validated_pattern(
            tx, points, receiver_gain_linear, ris, pattern_rad, frequency_hz, **kwargs
        )[0]
    )
