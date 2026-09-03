import numpy as np

from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.physics_guided import PhysicsGuidedFeedbackOptimizer
from airmirror_future.optimization.greedy import FeedbackGreedyOptimizer
from airmirror_future.ris.phase import generate_focus_pattern
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


def test_search_levels_are_distinct_from_hardware_bits() -> None:
    scene = create_smart_space_scene("Future")
    truth = GroundTruthModel(seed=11)
    oracle = MeasurementOracle(scene, SimulationEngine(), truth)
    result = FeedbackGreedyOptimizer(
        tile_height=48, tile_width=64, search_levels=5
    ).optimize(ControllerModel(), oracle)
    assert result.hardware_phase_bits is None
    assert result.search_levels == 5
    assert result.metadata["candidate_levels"] == 5
    assert result.metadata["search_levels_applies"] is True
    # A continuous initial/final pattern may retain non-search-grid values;
    # the optimizer must not silently quantize it as hardware.
    assert result.pattern_source == "Feedback Greedy"


def test_finite_bit_candidates_are_hardware_states_even_with_search_override() -> None:
    scene = create_smart_space_scene("Current")
    truth = GroundTruthModel(seed=12)
    oracle = MeasurementOracle(scene, SimulationEngine(), truth)
    ris = scene.ris_surfaces[0]
    result = FeedbackGreedyOptimizer(
        tile_height=4, tile_width=4, search_levels=17
    ).optimize(ControllerModel(), oracle)
    assert result.hardware_phase_bits == ris.phase_bits
    assert result.search_levels is None
    assert result.metadata["candidate_levels"] == 2 ** ris.phase_bits
    assert result.metadata["search_levels_applies"] is False
    step = 2 * np.pi / (2 ** ris.phase_bits)
    values = np.mod(result.patterns[ris.id], step)
    assert np.all(np.minimum(values, step - values) < 1e-9)


def test_continuous_physics_guided_preserves_initial_when_search_does_not_improve() -> None:
    scene = create_smart_space_scene("Future")
    ris = scene.ris_surfaces[0]
    initial = generate_focus_pattern(
        ris, scene.transmitter(), scene.receiver(), scene.frequency_hz
    )

    class ConstantOracle:
        def __init__(self) -> None:
            self.scene = scene

        def measure(self, patterns: dict[str, np.ndarray]) -> float:
            return -50.0

    result = PhysicsGuidedFeedbackOptimizer(
        tile_height=ris.ny,
        tile_width=ris.nx,
        search_levels=5,
    ).optimize(ControllerModel(), ConstantOracle())
    np.testing.assert_array_equal(result.patterns[ris.id], initial)
    assert result.hardware_phase_bits is None
    assert result.search_levels == 5


def test_feedback_optimizer_is_reproducible_for_fixed_seed_and_options() -> None:
    scene = create_smart_space_scene("Current")

    def run_once() -> object:
        truth = GroundTruthModel(seed=21, measurement_noise_sigma_db=0.1)
        oracle = MeasurementOracle(scene, SimulationEngine(), truth)
        return FeedbackGreedyOptimizer(tile_height=8, tile_width=8).optimize(
            ControllerModel(), oracle
        )

    first = run_once()
    second = run_once()
    np.testing.assert_array_equal(first.patterns[scene.ris_surfaces[0].id], second.patterns[scene.ris_surfaces[0].id])
    assert first.objective_db == second.objective_db
    assert first.history_db == second.history_db
    assert first.iterations == second.iterations
