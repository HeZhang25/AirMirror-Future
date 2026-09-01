"""AirMirror Future public package API."""

from airmirror_future.core.types import (
    ChannelResult,
    FieldMapResult,
    Obstacle,
    OptimizationResult,
    Receiver,
    RISGeneration,
    RISSurface,
    Scene,
    SimulationConfig,
    Transmitter,
    Vec3,
    Wall,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.optimization.measurement import MeasurementOracle

__all__ = [
    "ChannelResult",
    "FieldMapResult",
    "Obstacle",
    "OptimizationResult",
    "Receiver",
    "RISGeneration",
    "RISSurface",
    "Scene",
    "SimulationConfig",
    "SimulationEngine",
    "ControllerModel",
    "GroundTruthModel",
    "MeasurementOracle",
    "Transmitter",
    "Vec3",
    "Wall",
]

__version__ = "0.1.0"
