"""Ground-truth measurement oracle hidden from feedback controllers."""

from __future__ import annotations

import numpy as np

from airmirror_future.core.types import Scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel


class MeasurementOracle:
    """Expose measured target power without exposing truth-model parameters."""

    def __init__(
        self,
        scene: Scene,
        engine: SimulationEngine,
        ground_truth: GroundTruthModel,
        *,
        tx_id: str | None = None,
        rx_id: str | None = None,
    ) -> None:
        self.scene = scene
        self.engine = engine
        self.ground_truth = ground_truth
        self.tx_id = tx_id
        self.rx_id = rx_id
        self._rng = np.random.default_rng(ground_truth.seed + 7919)
        self.measurements = 0

    def measure(self, patterns: dict[str, np.ndarray]) -> float:
        """Return a noisy dBm measurement using the hidden truth model."""
        result = self.engine.compute_channel(
            self.scene, self.tx_id, self.rx_id, patterns, self.ground_truth
        )
        self.measurements += 1
        noise = self._rng.normal(0.0, self.ground_truth.measurement_noise_sigma_db)
        return float(result.received_power_dbm + noise)

