"""Pure validation for commanded RIS hardware phase states."""

from __future__ import annotations

import math

import numpy as np

from airmirror_future.core.types import RISSurface


COMMANDED_PHASE_ATOL_RAD = 1.0e-6
"""Absolute circular tolerance for finite-bit commanded states, in radians."""


def validate_commanded_pattern(
    ris: RISSurface,
    phase_rad: np.ndarray,
) -> np.ndarray:
    """Return a validated float64 snapshot of one RIS commanded pattern.

    Discrete commands must lie within :data:`COMMANDED_PHASE_ATOL_RAD` of a
    hardware state modulo ``2*pi``. Accepted values are copied without
    wrapping, snapping, or quantization. Continuous hardware accepts any
    finite real phase representation.
    """
    raw = np.asarray(phase_rad)
    if raw.ndim != 1:
        raise ValueError(
            f"commanded pattern for RIS {ris.id!r} must be one-dimensional"
        )
    if raw.size != ris.cell_count:
        raise ValueError(
            f"commanded pattern for RIS {ris.id!r} has {raw.size} phases, "
            f"expected {ris.cell_count}"
        )
    if not np.issubdtype(raw.dtype, np.number) or np.issubdtype(
        raw.dtype, np.complexfloating
    ):
        raise ValueError(
            f"commanded pattern for RIS {ris.id!r} must contain real phases"
        )
    try:
        phase = np.array(raw, dtype=float, copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            f"commanded pattern for RIS {ris.id!r} must contain real phases"
        ) from error
    if not np.all(np.isfinite(phase)):
        raise ValueError(
            f"commanded pattern for RIS {ris.id!r} must contain only finite phases"
        )

    if ris.phase_bits is None:
        return phase

    step = math.ldexp(2.0 * math.pi, -int(ris.phase_bits))
    if step == 0.0:
        raise ValueError(f"phase_bits for RIS {ris.id!r} is too large to validate")
    wrapped = np.mod(phase, 2.0 * math.pi)
    nearest_state = np.rint(wrapped / step) * step
    distance = np.abs(wrapped - nearest_state)
    invalid = np.flatnonzero(distance > COMMANDED_PHASE_ATOL_RAD)
    if invalid.size:
        index = int(invalid[0])
        raise ValueError(
            f"commanded pattern for RIS {ris.id!r} contains an off-grid phase "
            f"at index {index}: {phase[index]!r} rad"
        )
    return phase


__all__ = ["COMMANDED_PHASE_ATOL_RAD", "validate_commanded_pattern"]
