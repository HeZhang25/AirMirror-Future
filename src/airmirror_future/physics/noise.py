"""Thermal noise, SNR, and Shannon upper-bound calculations."""

from __future__ import annotations

import math


def noise_power_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    """Return ``-174 + 10log10(B) + NF`` in dBm."""
    if bandwidth_hz <= 0.0 or not math.isfinite(bandwidth_hz):
        raise ValueError("bandwidth_hz must be finite and positive")
    if not math.isfinite(noise_figure_db):
        raise ValueError("noise_figure_db must be finite")
    return -174.0 + 10.0 * math.log10(bandwidth_hz) + noise_figure_db


def snr_db(received_power_dbm: float, noise_dbm: float) -> float:
    return received_power_dbm - noise_dbm


def shannon_capacity_bps(bandwidth_hz: float, snr_db_value: float) -> float:
    """Return Shannon's theoretical upper bound, not real throughput."""
    snr_linear = 10.0 ** (snr_db_value / 10.0)
    return bandwidth_hz * math.log2(1.0 + snr_linear)

