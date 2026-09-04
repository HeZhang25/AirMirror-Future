"""FND-T14: Profile value types, canonical identity and finite/error contracts."""

from dataclasses import FrozenInstanceError, dataclass, replace
import hashlib
import os
import subprocess
import sys

import numpy as np
import pytest

from airmirror_future.core.constants import MIN_DISTANCE_M
from airmirror_future.core.types import Vec3
from airmirror_future.physics import reflections
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.profiles import (
    CanonicalParameters, IndoorDeterministicProfile, PropagationModifier,
    PropagationPathContext, PropagationProfile, profile_identity,
)


ROLES = ("direct", "reflection_before", "reflection_after", "ris_incident", "ris_scattered")


@dataclass(frozen=True)
class MetadataProfile:
    profile_id: str = "test_profile"
    profile_version: str = "1"
    canonical_parameters: CanonicalParameters = ()

    def environment_modifier(self, *, scene, context):
        return PropagationModifier(1 + 0j)


def context(role: str, **kwargs) -> PropagationPathContext:
    values = {"role": role, "start": Vec3(0, 0, 0), "end": Vec3(1, 0, 0)}
    if role.startswith("reflection"):
        values["reflecting_wall_id"] = "mirror"
    if role.startswith("ris"):
        values["ris_id"] = "panel"
    values.update(kwargs)
    return PropagationPathContext(**values)


def test_default_profile_is_frozen_parameterless_protocol_and_engine_snapshot() -> None:
    first, second = SimulationEngine(), SimulationEngine()
    profile = first.profile
    assert isinstance(profile, PropagationProfile)
    assert isinstance(profile, IndoorDeterministicProfile)
    assert profile is not second.profile
    assert profile.profile_id == "indoor_deterministic"
    assert profile.profile_version == "1"
    assert profile.canonical_parameters == ()
    assert first.profile_identity == second.profile_identity == profile_identity(profile)
    assert not hasattr(profile, "__dict__")
    for name, value in (("profile_id", "other"), ("profile_version", "2"),
                        ("canonical_parameters", (("x", 1),))):
        with pytest.raises(FrozenInstanceError):
            setattr(profile, name, value)
    with pytest.raises(TypeError):
        IndoorDeterministicProfile(profile_version="2")
    with pytest.raises(AttributeError):
        first.profile = second.profile
    with pytest.raises(AttributeError):
        first.profile_identity = "forged"
    injected = MetadataProfile()
    assert SimulationEngine(injected).profile is injected


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("length", (0.0, MIN_DISTANCE_M / 2, 1.0))
def test_context_does_not_own_minimum_distance(role: str, length: float) -> None:
    value = context(role, end=Vec3(length, 0, 0))
    with pytest.raises(FrozenInstanceError):
        value.role = "direct"
    assert not hasattr(value, "__dict__")
    modifier = PropagationModifier(0j)
    with pytest.raises(FrozenInstanceError):
        modifier.value = 1j


@pytest.mark.parametrize("role,changes", (
    ("unknown", {}), ("direct", {"ris_id": "panel"}),
    ("direct", {"reflecting_wall_id": "mirror"}),
    ("reflection_before", {"reflecting_wall_id": None}),
    ("reflection_after", {"ris_id": "panel"}),
    ("ris_incident", {"ris_id": None}),
    ("ris_scattered", {"reflecting_wall_id": "mirror"}),
    ("reflection_before", {"reflecting_wall_id": ""}),
    ("ris_incident", {"ris_id": ""}), ("ris_scattered", {"ris_id": 3}),
    ("direct", {"start": (0, 0, 0)}),
))
def test_context_rejects_invalid_role_identity_and_coordinate_type(role, changes) -> None:
    with pytest.raises(ValueError):
        context(role, **changes)


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -float("inf")))
@pytest.mark.parametrize("endpoint", ("start", "end"))
def test_context_rechecks_finite_vec3(endpoint: str, value: float) -> None:
    point = Vec3(0, 0, 0)
    object.__setattr__(point, "x", value)  # bypass Vec3 only to exercise the context boundary
    with pytest.raises(ValueError, match="finite Vec3"):
        context("direct", **{endpoint: point})


def test_identity_matches_literal_canonical_payload() -> None:
    profile = MetadataProfile(canonical_parameters=(
        ("a", None), ("b", True), ("c", -12), ("d", 1.5), ("e", "墙\nα"),
    ))
    payload = ('["airmirror_profile_identity",1,["str","test_profile"],["str","1"],'
               '[["a",["null",null]],["b",["bool",true]],["c",["int","-12"]],'
               '["d",["float64_hex","0x1.8000000000000p+0"]],["e",["str","墙\\nα"]]]]')
    assert profile_identity(profile) == "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_profile_identity_changes_with_version_or_parameters() -> None:
    base = MetadataProfile(canonical_parameters=(("x", 1),))
    variants = (base, replace(base, profile_id="other"), replace(base, profile_version="2"),
                replace(base, canonical_parameters=(("x", 2),)),
                replace(base, canonical_parameters=(("y", 1),)))
    assert len({profile_identity(profile) for profile in variants}) == len(variants)
    values = (None, False, True, 0, 1, 0.0, -0.0, 1.0, "1", "é", "e\u0301")
    identities = {profile_identity(replace(base, canonical_parameters=(("x", value),)))
                  for value in values}
    assert len(identities) == len(values)


@pytest.mark.parametrize("field,value", (
    ("profile_id", ""), ("profile_id", "Upper"), ("profile_id", "a b"),
    ("profile_id", "汉字"), ("profile_version", 1), ("profile_version", "1\n"),
    ("canonical_parameters", []), ("canonical_parameters", (["x", 1],)),
    ("canonical_parameters", (("x",),)), ("canonical_parameters", (("x", 1, 2),)),
    ("canonical_parameters", (("z", 1), ("a", 1))),
    ("canonical_parameters", (("x", 1), ("x", 2))),
    ("canonical_parameters", (("Upper", 1),)),
    ("canonical_parameters", (("x", float("nan")),)),
    ("canonical_parameters", (("x", float("inf")),)),
    ("canonical_parameters", (("x", 1j),)),
    ("canonical_parameters", (("x", []),)),
    ("canonical_parameters", (("x", np.int64(1)),)),
    ("canonical_parameters", (("x", "\ud800"),)),
))
def test_invalid_profile_metadata_is_rejected_at_construction(field, value) -> None:
    with pytest.raises(ValueError):
        SimulationEngine(replace(MetadataProfile(), **{field: value}))


def test_missing_profile_interface_fails_explicitly() -> None:
    with pytest.raises(ValueError):
        SimulationEngine(object())
    class NoMethod:
        profile_id = "no_method"
        profile_version = "1"
        canonical_parameters = ()
    with pytest.raises(ValueError, match="environment_modifier"):
        SimulationEngine(NoMethod())


def test_profile_identity_is_identical_across_independent_processes() -> None:
    code = """
from types import SimpleNamespace
from airmirror_future.simulation.profiles import profile_identity
p = SimpleNamespace(profile_id='test_profile', profile_version='1',
                    canonical_parameters=(('bool', True), ('float', -0.0),
                                          ('int', 1), ('text', '\\u5899')))
print(profile_identity(p))
"""
    expected = profile_identity(MetadataProfile(canonical_parameters=(
        ("bool", True), ("float", -0.0), ("int", 1), ("text", "墙"),
    )))
    for seed in ("1", "98765"):
        process = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True,
                                 text=True, env={**os.environ, "PYTHONHASHSEED": seed}, timeout=30)
        assert process.stdout.strip() == expected


def test_reflection_version_is_separate_from_profile_identity(monkeypatch) -> None:
    profile = IndoorDeterministicProfile()
    original = profile_identity(profile)
    assert reflections.reflection_model_id == "finite_wall_single_bounce_image"
    assert reflections.reflection_model_version == "1"
    monkeypatch.setattr(reflections, "reflection_model_id", "test_other_reflection")
    monkeypatch.setattr(reflections, "reflection_model_version", "2")
    assert profile_identity(profile) == original
