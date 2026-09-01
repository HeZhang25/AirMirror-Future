import numpy as np

from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.physics_guided import PhysicsGuidedFeedbackOptimizer
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


def test_physics_guided_feedback_returns_valid_pattern() -> None:
    scene = create_smart_space_scene()
    truth = GroundTruthModel(seed=7, ris_phase_error_sigma_rad=0.2)
    oracle = MeasurementOracle(scene, SimulationEngine(), truth)
    result = PhysicsGuidedFeedbackOptimizer(tile_height=8, tile_width=8).optimize(
        ControllerModel(), oracle
    )
    ris = scene.ris_surfaces[0]
    assert result.patterns[ris.id].shape == (ris.cell_count,)
    assert np.isfinite(result.objective_db)
    assert result.iterations > 1

