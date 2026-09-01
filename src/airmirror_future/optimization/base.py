"""Common optimizer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from airmirror_future.core.types import OptimizationResult
from airmirror_future.simulation.ground_truth import ControllerModel


ProgressCallback = Callable[[int, int, float], None]


class Optimizer(ABC):
    """Base interface for algorithms that can only observe an oracle."""

    @abstractmethod
    def optimize(
        self,
        controller_model: ControllerModel,
        measurement_oracle: Any,
        objective: str = "received_power_dbm",
        **kwargs: Any,
    ) -> OptimizationResult:
        raise NotImplementedError

