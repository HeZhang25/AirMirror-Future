"""RIS phase quantization and physics-focus pattern generation."""

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
        if bits <= 0:
            raise ValueError("bits must be positive or None")
        levels = 2**bits
        step = 2.0 * np.pi / levels
        result = np.mod(np.floor(values / step + 0.5), levels) * step
    return float(result) if result.ndim == 0 else result


def generate_focus_pattern(
    ris: RISSurface,
    tx: Transmitter | Vec3,
    rx: Receiver | Vec3,
    frequency_hz: float,
) -> np.ndarray:
    """Return the phase conjugate of TX-cell-RX propagation.

    With the convention ``exp(-j*k*L + j*phi)``, the command phase is
    ``phi = k*L mod 2*pi`` before hardware phase quantization.
    """
    tx_position = tx.position if isinstance(tx, Transmitter) else tx
    rx_position = rx.position if isinstance(rx, Receiver) else rx
    cells = ris.cell_centers()
    d1 = np.linalg.norm(cells - tx_position.as_array()[None, :], axis=1)
    d2 = np.linalg.norm(cells - rx_position.as_array()[None, :], axis=1)
    ideal = wave_number_rad_m(frequency_hz) * (d1 + d2)
    return np.asarray(quantize_phase(ideal, ris.phase_bits))

