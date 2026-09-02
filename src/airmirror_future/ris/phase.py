"""Pure helpers for RIS phase quantization and phase-conjugate focus."""

from __future__ import annotations

import numpy as np

from airmirror_future.core.types import RISSurface, Transmitter, Receiver, Vec3
from airmirror_future.physics.free_space import wave_number_rad_m


def quantize_phase(phi_rad: float | np.ndarray, bits: int | None) -> float | np.ndarray:
    """Quantize wrapped phase to ``2**bits`` uniform states.

    ``bits=None`` represents continuous phase control.
    """
    values = np.mod(np.asarray(phi_rad, dtype=float), 2.0 * np.pi)
    if bits is None:
        result = values
    else:
        if (
            isinstance(bits, (bool, np.bool_))
            or not isinstance(bits, (int, np.integer))
            or bits <= 0
        ):
            raise ValueError("bits must be positive or None")
        bits = int(bits)
        levels = 2**bits
        step = 2.0 * np.pi / levels
        result = np.mod(np.floor(values / step + 0.5), levels) * step
    return float(result) if result.ndim == 0 else result


def generate_unquantized_ris_only_focus_pattern(
    ris: RISSurface,
    tx: Transmitter | Vec3,
    rx: Receiver | Vec3,
    frequency_hz: float,
) -> np.ndarray:
    """Return continuous phase conjugates for the TX-patch-RX paths.

    With the convention ``exp(-j*k*L + j*phi)``, the command phase is
    ``phi = k*L mod 2*pi``.  This helper does not read or align with the
    non-RIS baseline channel.
    """
    tx_position = tx.position if isinstance(tx, Transmitter) else tx
    rx_position = rx.position if isinstance(rx, Receiver) else rx
    cells = ris.cell_centers()
    d1 = np.linalg.norm(cells - tx_position.as_array()[None, :], axis=1)
    d2 = np.linalg.norm(cells - rx_position.as_array()[None, :], axis=1)
    ideal = wave_number_rad_m(frequency_hz) * (d1 + d2)
    return np.mod(ideal, 2.0 * np.pi)


def apply_common_phase_offset(
    phase_rad: np.ndarray,
    common_phase_offset_rad: float,
    bits: int | None,
) -> np.ndarray:
    """Add one common offset before applying the hardware quantizer."""
    values = np.asarray(phase_rad, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("phase_rad must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(values)):
        raise ValueError("phase_rad must contain only finite values")
    if not np.isfinite(common_phase_offset_rad):
        raise ValueError("common_phase_offset_rad must be finite")
    return np.asarray(quantize_phase(values + common_phase_offset_rad, bits))


def common_phase_offset_candidates(
    phase_rad: np.ndarray,
    bits: int,
) -> np.ndarray:
    """Return deterministic offsets covering all finite-bit quantized patterns.

    The quantized pattern is piecewise constant as a common offset traverses
    ``[0, 2*pi)``.  One midpoint from every interval between quantizer
    transitions is returned.  Exact ``0.0`` is always the first candidate so
    stable tie-breaking preserves the unshifted RIS-only command.
    """
    values = np.asarray(phase_rad, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("phase_rad must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(values)):
        raise ValueError("phase_rad must contain only finite values")
    if (
        isinstance(bits, (bool, np.bool_))
        or not isinstance(bits, (int, np.integer))
        or bits <= 0
    ):
        raise ValueError("bits must be positive")
    bits = int(bits)

    period = 2.0 * np.pi
    levels = 2**bits
    step = period / levels
    boundaries = np.mod(
        (np.arange(levels, dtype=float) + 0.5)[:, None] * step
        - np.mod(values, period)[None, :],
        period,
    )
    boundaries = np.unique(boundaries.reshape(-1))
    following = np.roll(boundaries, -1)
    following[-1] += period
    midpoints = np.mod(boundaries + 0.5 * (following - boundaries), period)
    midpoints.sort()
    nonzero = midpoints[midpoints != 0.0]
    return np.concatenate((np.array([0.0]), nonzero))


def generate_ris_only_focus_pattern(
    ris: RISSurface,
    tx: Transmitter | Vec3,
    rx: Receiver | Vec3,
    frequency_hz: float,
) -> np.ndarray:
    """Return the legacy RIS-only phase-conjugate command.

    The command makes nominal RIS patches mutually coherent at ``rx`` but
    deliberately ignores the direct and reflected baseline field.
    """
    ideal = generate_unquantized_ris_only_focus_pattern(ris, tx, rx, frequency_hz)
    return apply_common_phase_offset(ideal, 0.0, ris.phase_bits)


def generate_focus_pattern(
    ris: RISSurface,
    tx: Transmitter | Vec3,
    rx: Receiver | Vec3,
    frequency_hz: float,
) -> np.ndarray:
    """Backward-compatible alias for :func:`generate_ris_only_focus_pattern`.

    Foundation A1 intentionally preserves this function's v0.1 semantics.
    New total-channel objectives must call the explicitly named coherent
    strategy from :mod:`airmirror_future.optimization.coherent_focus`.
    """
    return generate_ris_only_focus_pattern(ris, tx, rx, frequency_hz)
