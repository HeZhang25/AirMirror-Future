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
    WALL_ENDPOINT_Z_ATOL_M,
)
from airmirror_future.core.pattern_contract import (
    COMMANDED_PHASE_ATOL_RAD,
    validate_commanded_pattern,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.ris.phase import generate_ris_only_focus_pattern
from airmirror_future.ris.aperture import (
    EquivalentPatchDiagnostics,
    equivalent_patch_diagnostics,
)
from airmirror_future.physics.ris_scattering import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    PRODUCTION_RIS_COEFFICIENT_MODEL,
    RISCoefficientModel,
)
from airmirror_future.optimization.dual_ris_focus import (
    DualRISFocusResult,
    evaluate_dual_ris_command,
    generate_dual_ris_coordinated_patterns,
)

__all__ = [
    "ChannelResult",
    "FieldMapResult",
    "FAST_1X1_RIS_COEFFICIENT_MODEL",
    "DualRISFocusResult",
    "EquivalentPatchDiagnostics",
    "COMMANDED_PHASE_ATOL_RAD",
    "equivalent_patch_diagnostics",
    "evaluate_dual_ris_command",
    "generate_coherent_target_pattern",
    "generate_dual_ris_coordinated_patterns",
    "generate_ris_only_focus_pattern",
    "Obstacle",
    "OptimizationResult",
    "Receiver",
    "RISCoefficientModel",
    "RISGeneration",
    "RISSurface",
    "PRODUCTION_RIS_COEFFICIENT_MODEL",
    "Scene",
    "SimulationConfig",
    "SimulationEngine",
    "ControllerModel",
    "GroundTruthModel",
    "MeasurementOracle",
    "Transmitter",
    "Vec3",
    "Wall",
    "WALL_ENDPOINT_Z_ATOL_M",
    "validate_commanded_pattern",
]

__version__ = "0.1.0"
