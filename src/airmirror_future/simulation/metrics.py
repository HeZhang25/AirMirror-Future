"""Reusable aggregate simulation metrics."""

from __future__ import annotations

import numpy as np


def coverage_percent(snr_db: np.ndarray, threshold_db: float) -> float:
    values = np.asarray(snr_db, dtype=float)
    if values.size == 0:
        raise ValueError("snr_db cannot be empty")
    return float(np.mean(values >= threshold_db) * 100.0)


def outage_probability(snr_db: np.ndarray, threshold_db: float) -> float:
    return 1.0 - coverage_percent(snr_db, threshold_db) / 100.0

