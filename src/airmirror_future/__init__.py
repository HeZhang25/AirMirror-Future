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
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.ris.phase import generate_ris_only_focus_pattern

__all__ = [
    "ChannelResult",
    "FieldMapResult",
    "generate_coherent_target_pattern",
    "generate_ris_only_focus_pattern",
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
