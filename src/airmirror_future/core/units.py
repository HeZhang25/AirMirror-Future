"""Unit conversions with stable power floors."""

from __future__ import annotations

import math

import numpy as np

from airmirror_future.core.constants import MIN_POWER_W


def dbm_to_watts(power_dbm: float) -> float:
    """Convert power in dBm to watts."""
    if not math.isfinite(power_dbm):
        raise ValueError("power_dbm must be finite")
    return 10.0 ** ((power_dbm - 30.0) / 10.0)


def watts_to_dbm(power_w: float | np.ndarray) -> float | np.ndarray:
    """Convert watts to dBm after applying a numerical floor."""
    values = np.maximum(np.asarray(power_w, dtype=float), MIN_POWER_W)
    result = 10.0 * np.log10(values) + 30.0
    return float(result) if result.ndim == 0 else result


def db_to_amplitude(db: float) -> float:
    """Convert an attenuation/gain expressed in dB to a field ratio."""
    return 10.0 ** (db / 20.0)


def db_to_power_ratio(db: float) -> float:
    """Convert dB to a power ratio."""
    return 10.0 ** (db / 10.0)

