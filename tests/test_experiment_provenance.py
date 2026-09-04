from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import pytest

import airmirror_future
from airmirror_future.experiments.provenance import _build_provenance_fields
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.physics import reflections
from airmirror_future.ris.phase import (
    generate_focus_pattern,
    generate_ris_only_focus_pattern,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.profiles import (
    CanonicalParameters,
    IndoorDeterministicProfile,
    PropagationModifier,
    PropagationPathContext,
    profile_identity,
)


@dataclass(frozen=True, slots=True)
class _MetadataProfile:
    profile_id: str = "test_profile"
    profile_version: str = "2"
    canonical_parameters: CanonicalParameters = (
        ("enabled", True),
        ("gain", 0.25),
        ("label", "室内"),
        ("limit", None),
        ("order", 3),
    )

    def environment_modifier(
        self, *, scene: object, context: PropagationPathContext
    ) -> PropagationModifier:
        return PropagationModifier(1.0 + 0.0j)


def _build(**overrides: object) -> dict[str, object]:
    scene = create_smart_space_scene("Advanced")
    values: dict[str, object] = {
        "engine": SimulationEngine(),
        "scene": scene,
        "focus": generate_focus_pattern,
        "world": ControllerModel(),
        "search_levels": None,
        "run_id": "20260904T010203.123456Z-1a2b3c4d",
    }
    values.update(overrides)
    return _build_provenance_fields(**values)


def test_builds_default_partial_provenance_from_actual_inputs() -> None:
    fields = _build()

    assert fields == {
        "provenance_schema_id": "airmirror_experiment_provenance",
        "provenance_schema_version": 1,
        "provenance_status": "partial",
        "pending_contracts_json": '["FND-PHY-NB","FND-QA-AP","FND-QA-CC"]',
        "run_id": "20260904T010203.123456Z-1a2b3c4d",
        "software_version": airmirror_future.__version__,
        "focus_mode_id": "ris_only_phase_conjugate",
        "focus_mode_version": "1",
        "search_levels": None,
        "profile_id": "indoor_deterministic",
        "profile_version": "1",
        "profile_parameters_json": "[]",
        "profile_identity": profile_identity(IndoorDeterministicProfile()),
        "reflection_model_id": reflections.reflection_model_id,
        "reflection_model_version": reflections.reflection_model_version,
        "world_model_id": "controller_nominal",
        "world_model_version": "1",
        "world_model_parameters_json": "{}",
        "random_seed": 20260901,
        "channel_frequency_model_id": "",
        "quadrature_policy_id": "",
        "quadrature_policy_version": "",
        "coefficient_model_identity": "",
    }


@pytest.mark.parametrize(
    ("focus", "expected"),
    [
        (generate_focus_pattern, "ris_only_phase_conjugate"),
        (generate_ris_only_focus_pattern, "ris_only_phase_conjugate"),
        (generate_coherent_target_pattern, "coherent_target"),
    ],
)
def test_focus_metadata_comes_from_known_actual_callable(
    focus: object, expected: str
) -> None:
    fields = _build(focus=focus)

    assert fields["focus_mode_id"] == expected
    assert fields["focus_mode_version"] == "1"


def test_profile_parameters_are_the_c1_tagged_canonical_array() -> None:
    profile = _MetadataProfile()
    fields = _build(engine=SimulationEngine(profile))
    expected = (
        '[["enabled",["bool",true]],["gain",["float64_hex","0x1.0000000000000p-2"]],'
        '["label",["str","室内"]],["limit",["null",null]],["order",["int","3"]]]'
    )

    assert fields["profile_parameters_json"] == expected
    assert fields["profile_identity"] == profile_identity(profile)
    assert json.loads(str(fields["profile_parameters_json"]))[1][1][0] == "float64_hex"


def test_ground_truth_records_all_six_sigmas_and_its_actual_seed() -> None:
    model = GroundTruthModel(
        seed=0,
        ris_phase_error_sigma_rad=0.1,
        ris_efficiency_sigma_fraction=0.2,
        wall_amplitude_error_sigma_fraction=0.3,
        wall_phase_error_sigma_rad=0.4,
        position_error_sigma_m=0.5,
        measurement_noise_sigma_db=0.6,
    )
    fields = _build(world=model)

    assert fields["world_model_id"] == "ground_truth_stochastic"
    assert fields["world_model_version"] == "1"
    assert fields["random_seed"] == 0
    assert fields["world_model_parameters_json"] == (
        '{"measurement_noise_sigma_db":0.6,"position_error_sigma_m":0.5,'
        '"ris_efficiency_sigma_fraction":0.2,"ris_phase_error_sigma_rad":0.1,'
        '"wall_amplitude_error_sigma_fraction":0.3,"wall_phase_error_sigma_rad":0.4}'
    )


def test_candidate_owner_metadata_stays_partial_while_owners_are_pending() -> None:
    fields = _build(
        channel_frequency_model_id="candidate_narrowband_v1",
        quadrature_policy_id="candidate_midpoint",
        quadrature_policy_version="7",
        coefficient_model_identity="candidate:abc",
    )

    assert fields["provenance_status"] == "partial"
    assert fields["pending_contracts_json"] == (
        '["FND-PHY-NB","FND-QA-AP","FND-QA-CC"]'
    )


def test_world_is_required_at_the_internal_seam() -> None:
    scene = create_smart_space_scene("Advanced")
    with pytest.raises(TypeError, match="world"):
        _build_provenance_fields(
            engine=SimulationEngine(),
            scene=scene,
            focus=generate_focus_pattern,
            run_id="20260904T010203.123456Z-1a2b3c4d",
        )
    with pytest.raises(ValueError, match="world"):
        _build(world=None)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"run_id": ""}, "run_id"),
        ({"run_id": "parent/child"}, "run_id"),
        ({"focus": lambda: None}, "supported actual Focus"),
        ({"search_levels": 0}, "search_levels"),
        ({"search_levels": True}, "search_levels"),
        ({"quadrature_policy_id": "candidate", "quadrature_policy_version": None},
         "quadrature policy id and version"),
    ],
)
def test_rejects_invalid_contract_inputs(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _build(**overrides)


def test_rejects_profile_metadata_mutated_after_engine_construction() -> None:
    @dataclass(slots=True)
    class MutableProfile:
        profile_id: str = "mutable"
        profile_version: str = "1"
        canonical_parameters: CanonicalParameters = ()

        def environment_modifier(
            self, *, scene: object, context: PropagationPathContext
        ) -> PropagationModifier:
            return PropagationModifier(1.0 + 0.0j)

    profile = MutableProfile()
    engine = SimulationEngine(profile)
    profile.profile_version = "2"

    with pytest.raises(ValueError, match="changed after engine construction"):
        _build(engine=engine)


def test_rejects_non_finite_ground_truth_mutation() -> None:
    model = GroundTruthModel()
    model.position_error_sigma_m = float("nan")

    with pytest.raises(ValueError, match="world model parameters"):
        _build(world=model)


def test_profile_parameter_json_and_identity_share_the_same_payload() -> None:
    profile = _MetadataProfile()
    fields = _build(engine=SimulationEngine(profile))
    tagged = json.loads(str(fields["profile_parameters_json"]))
    payload = [
        "airmirror_profile_identity",
        1,
        ["str", profile.profile_id],
        ["str", profile.profile_version],
        tagged,
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")

    assert fields["profile_identity"] == "sha256:" + hashlib.sha256(encoded).hexdigest()
