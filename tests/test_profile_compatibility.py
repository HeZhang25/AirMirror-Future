"""FND-T13: immutable references from the pre-C1 d9ab04a baseline.

The reference was captured before modifying production code, after checking
that src/ at 9fad9b0 was identical to d9ab04a. Never regenerate it to bless a
different physical model. These are test fixtures, not experiment provenance.
"""

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.core.types import Obstacle, Receiver, Scene, Transmitter, Vec3, Wall
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


REFERENCE = Path(__file__).with_name("fixtures") / "c1_v01_components.json"
BASELINE = "d9ab04a502055af3b519a781629e6e83f0ded9d8"


def reflection_blockage_scene() -> Scene:
    """Small directed fixture: separate blockers on each reflection leg."""
    return Scene(
        "reflection-blockage-fixture", Vec3(10, 10, 3), 5e9, 20e6,
        [Transmitter("tx", Vec3(2, -1, 1.5))],
        [Receiver("rx", Vec3(2, 1, 1.5))],
        walls=[
            Wall("mirror", Vec3(0, -2, 0), Vec3(0, 2, 0), reflection_magnitude=0.5),
            Wall("before", Vec3(1, -0.8, 0), Vec3(1, -0.2, 0),
                 attenuation_db=3, reflection_magnitude=0),
            Wall("after", Vec3(1, 0.2, 0), Vec3(1, 0.8, 0),
                 attenuation_db=7, reflection_magnitude=0),
            Wall("miss", Vec3(8, 8, 0), Vec3(8, 9, 0)),
        ],
        obstacles=[
            Obstacle("incident-box", Vec3(0.4, -0.4, 1), Vec3(0.6, -0.1, 2), 2),
            Obstacle("scattered-box", Vec3(0.4, 0.1, 1), Vec3(0.6, 0.4, 2), 4),
        ],
    )


def compatibility_case(name: str, truth: bool) -> tuple[Scene, ControllerModel]:
    scene = reflection_blockage_scene() if name == "reflection" else create_smart_space_scene(name)
    model = GroundTruthModel(
        seed=2718, position_error_sigma_m=0.01,
        wall_amplitude_error_sigma_fraction=0.05, wall_phase_error_sigma_rad=0.1,
        ris_phase_error_sigma_rad=0.25, ris_efficiency_sigma_fraction=0.03,
        measurement_noise_sigma_db=0.2,
    ) if truth else ControllerModel()
    return scene, model


def component_snapshot(name: str, truth: bool) -> dict:
    scene, model = compatibility_case(name, truth)
    patterns = {
        ris.id: generate_focus_pattern(ris, scene.transmitter(), scene.receiver(), scene.frequency_hz)
        for ris in scene.ris_surfaces
    }
    result = SimulationEngine().compute_channel(scene, ris_patterns=patterns, model=model)
    components = [[value.real, value.imag] for value in (
        result.los_channel, result.wall_channel, result.ris_channel, result.total_channel
    )]
    paths = []
    for detail in result.path_details:
        item = dict(detail)
        if "point" in item:
            item["point"] = asdict(item["point"])
        if "channel" in item:
            item["channel"] = [item["channel"].real, item["channel"].imag]
        paths.append(item)
    return {"components": components, "paths": paths}


@pytest.mark.parametrize("name", ("Current", "Advanced", "Future", "reflection"))
@pytest.mark.parametrize("truth", (False, True))
def test_default_profile_components_match_v01_reference(name: str, truth: bool) -> None:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert reference["baseline"] == BASELINE
    expected = reference[f"{name}-{'truth' if truth else 'nominal'}"]
    actual = component_snapshot(name, truth)
    # Compare complex numbers, not each real/imag part's relative error.
    def complexes(values: list) -> np.ndarray:
        array = np.asarray(values)
        return array[..., 0] + 1j * array[..., 1]

    np.testing.assert_allclose(complexes(actual["components"]), complexes(expected["components"]),
                               rtol=1e-12, atol=1e-15)
    assert len(actual["paths"]) == len(expected["paths"])
    for actual_path, expected_path in zip(actual["paths"], expected["paths"], strict=True):
        assert actual_path.keys() == expected_path.keys()
        for key in actual_path:
            if key == "channel":
                np.testing.assert_allclose(complex(*actual_path[key]), complex(*expected_path[key]),
                                           rtol=1e-12, atol=1e-15)
            else:
                assert actual_path[key] == expected_path[key]
