from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest

from airmirror_future import (
    COMMANDED_PHASE_ATOL_RAD as TOP_LEVEL_COMMANDED_PHASE_ATOL_RAD,
)
from airmirror_future import validate_commanded_pattern as top_level_validator
from airmirror_future.core.pattern_contract import (
    COMMANDED_PHASE_ATOL_RAD,
    validate_commanded_pattern,
)
from airmirror_future.core.types import RISSurface, SimulationConfig
from airmirror_future.physics.ris_scattering import ris_channel_for_points
from airmirror_future.ris import validate_commanded_pattern as ris_validator
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation import engine as engine_module
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import GroundTruthModel


def _surface(*, phase_bits: int | None, nx: int = 4, ny: int = 1) -> RISSurface:
    source = create_smart_space_scene("Current").ris_surfaces[0]
    return replace(source, nx=nx, ny=ny, phase_bits=phase_bits)


@pytest.mark.parametrize("bits", (1, 2, 3, 4))
def test_commanded_pattern_rejects_off_grid_phase(bits: int) -> None:
    ris = _surface(phase_bits=bits)
    step = 2.0 * math.pi / (2**bits)
    pattern = np.arange(ris.cell_count, dtype=float) % (2**bits) * step
    pattern[-1] += 0.01

    with pytest.raises(ValueError, match="off-grid phase"):
        validate_commanded_pattern(ris, pattern)


def test_commanded_pattern_accepts_modulo_equivalent_states() -> None:
    ris = _surface(phase_bits=2)
    tolerance_offsets = np.array([0.0, 0.5, -0.5, 0.25]) * COMMANDED_PHASE_ATOL_RAD
    pattern = (
        np.arange(ris.cell_count, dtype=float) * (math.pi / 2.0)
        + np.array([0.0, 2.0, -1.0, 3.0]) * (2.0 * math.pi)
        + tolerance_offsets
    )

    validated = validate_commanded_pattern(ris, pattern)

    assert validated.dtype == np.float64
    assert np.array_equal(validated, pattern)
    pattern[0] = 123.0
    assert validated[0] != pattern[0]

    float32_states = (
        np.arange(ris.cell_count, dtype=np.float32) * np.float32(math.pi / 2.0)
    )
    assert np.allclose(
        validate_commanded_pattern(ris, float32_states),
        float32_states.astype(float),
        rtol=0.0,
        atol=0.0,
    )


def test_commanded_pattern_tolerance_does_not_silently_quantize() -> None:
    ris = _surface(phase_bits=4)
    pattern = np.zeros(ris.cell_count)
    pattern[0] = 2.0 * COMMANDED_PHASE_ATOL_RAD

    with pytest.raises(ValueError, match="off-grid phase"):
        validate_commanded_pattern(ris, pattern)


def test_continuous_command_accepts_finite_unwrapped_phases() -> None:
    ris = _surface(phase_bits=None)
    pattern = np.array([-8.0 * math.pi, -0.125, 7.25, 10.0 * math.pi])
    assert np.array_equal(validate_commanded_pattern(ris, pattern), pattern)


@pytest.mark.parametrize(
    "bad_pattern",
    (
        np.array([0.0, 0.0, 0.0]),
        np.zeros((1, 4)),
        np.array([0.0, 0.0, 0.0, np.nan]),
        np.array([0.0, 0.0, 0.0, np.inf]),
        np.array([0.0j, 0.0j, 0.0j, 0.0j]),
        np.array([False, False, False, False]),
        np.array(["0", "0", "0", "0"]),
    ),
)
def test_commanded_pattern_rejects_invalid_shape_or_values(
    bad_pattern: np.ndarray,
) -> None:
    with pytest.raises(ValueError):
        validate_commanded_pattern(_surface(phase_bits=None), bad_pattern)


@pytest.mark.parametrize("phase_bits", (True, 1.5))
def test_ris_phase_bits_rejects_bool_and_non_integer(phase_bits: object) -> None:
    for invalid in (phase_bits, 0, -1):
        with pytest.raises(ValueError, match="phase_bits must be a positive integer"):
            replace(_surface(phase_bits=1), phase_bits=invalid)


def test_engine_rejects_unknown_and_ambiguous_pattern_keys() -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    pattern = np.zeros(ris.cell_count)
    engine = SimulationEngine()

    with pytest.raises(ValueError, match="ris_patterns must be a mapping"):
        engine.compute_channel(scene, ris_patterns=[pattern])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not found.*missing"):
        engine.compute_channel(scene, ris_patterns={"missing": pattern})

    duplicate_scene = replace(
        scene,
        ris_surfaces=[ris, replace(ris)],
    )
    with pytest.raises(ValueError, match="not unique.*ris-1"):
        engine.compute_channel(duplicate_scene, ris_patterns={ris.id: pattern})


def test_engine_validates_command_before_ground_truth_perturbation() -> None:
    class UntouchableGroundTruth(GroundTruthModel):
        def position_delta(self, key: str) -> np.ndarray:
            raise AssertionError(f"Ground Truth was touched before validation: {key}")

    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    invalid = np.full(ris.cell_count, math.pi / 2.0)
    truth = UntouchableGroundTruth(position_error_sigma_m=1.0)

    with pytest.raises(ValueError, match="off-grid phase"):
        SimulationEngine().compute_channel(
            scene,
            ris_patterns={ris.id: invalid},
            model=truth,
        )


def test_field_map_validates_commanded_pattern_once_before_pixel_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    pattern = np.zeros(ris.cell_count)
    calls = 0
    original = engine_module.validate_commanded_pattern

    def counting_validator(surface: RISSurface, phase_rad: np.ndarray) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original(surface, phase_rad)

    monkeypatch.setattr(engine_module, "validate_commanded_pattern", counting_validator)
    SimulationEngine().compute_field_map(
        scene,
        SimulationConfig(grid_width=2, grid_height=2),
        ris_patterns={ris.id: pattern},
    )
    assert calls == 1


def test_low_level_scattering_reuses_commanded_validator() -> None:
    scene = create_smart_space_scene("Current")
    ris = scene.ris_surfaces[0]
    invalid = np.full(ris.cell_count, math.pi / 2.0)

    with pytest.raises(ValueError, match="off-grid phase"):
        ris_channel_for_points(
            scene.transmitter(),
            scene.receiver().position.as_array()[None, :],
            scene.receiver().gain_linear,
            ris,
            invalid,
            scene.frequency_hz,
        )


def test_actual_phase_error_is_not_requantized() -> None:
    class FixedPhaseErrorGroundTruth(GroundTruthModel):
        def ris_phase_offsets(self, ris: RISSurface) -> np.ndarray:
            return np.full(ris.cell_count, math.pi / 4.0)

    scene = create_smart_space_scene("Current")
    ris = replace(scene.ris_surfaces[0], nx=1, ny=1, phase_bits=1)
    scene = replace(scene, ris_surfaces=[ris])
    commanded = np.zeros(ris.cell_count)
    engine = SimulationEngine()

    nominal = engine.compute_channel(scene, ris_patterns={ris.id: commanded})
    actual = engine.compute_channel(
        scene,
        ris_patterns={ris.id: commanded},
        model=FixedPhaseErrorGroundTruth(),
    )

    phase_delta = np.angle(actual.ris_channel * np.conj(nominal.ris_channel))
    assert phase_delta == pytest.approx(math.pi / 4.0, abs=1.0e-12)


def test_a3_public_exports_are_importable() -> None:
    assert top_level_validator is validate_commanded_pattern
    assert ris_validator is validate_commanded_pattern
    assert TOP_LEVEL_COMMANDED_PHASE_ATOL_RAD == COMMANDED_PHASE_ATOL_RAD
