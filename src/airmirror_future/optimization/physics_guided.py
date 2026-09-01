"""Physics-prior initialization followed by measurement-only refinement."""

from __future__ import annotations

from typing import Callable

from airmirror_future.core.types import OptimizationResult
from airmirror_future.optimization.base import Optimizer, ProgressCallback
from airmirror_future.optimization.greedy import FeedbackGreedyOptimizer
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.simulation.ground_truth import ControllerModel


class PhysicsGuidedFeedbackOptimizer(Optimizer):
    """Use nominal geometry as a prior, then compensate via real feedback."""

    def __init__(self, tile_height: int = 4, tile_width: int = 4, max_passes: int = 1):
        self.greedy = FeedbackGreedyOptimizer(tile_height, tile_width, max_passes)

    def optimize(
        self,
        controller_model: ControllerModel,
        measurement_oracle: MeasurementOracle,
        objective: str = "received_power_dbm",
        *,
        cancel_check: Callable[[], bool] | None = None,
        progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        scene = measurement_oracle.scene
        ris = scene.ris_surfaces[0]
        initial = generate_focus_pattern(
            ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
        )
        return self.greedy.optimize(
            controller_model,
            measurement_oracle,
            objective,
            initial_patterns={ris.id: initial},
            cancel_check=cancel_check,
            progress=progress,
        )

