"""Deterministic environment-only modifiers and stable Profile identities.

Carrier, reflection coefficients, RIS response and world realization remain
with their existing owners. A Profile only evaluates the explicit environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Literal, Protocol, runtime_checkable

from airmirror_future.core.types import Scene, Vec3
from airmirror_future.physics.blockage import path_attenuation_amplitude


PropagationPathRole = Literal[
    "direct", "reflection_before", "reflection_after", "ris_incident", "ris_scattered"
]
CanonicalParameter = bool | int | float | str | None
CanonicalParameters = tuple[tuple[str, CanonicalParameter], ...]

_ROLES = ("direct", "reflection_before", "reflection_after", "ris_incident", "ris_scattered")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_.-]*", re.ASCII)


@dataclass(frozen=True, slots=True)
class PropagationPathContext:
    """One directed environment segment; distance validity belongs to physics."""

    role: PropagationPathRole
    start: Vec3
    end: Vec3
    reflecting_wall_id: str | None = None
    ris_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or self.role not in _ROLES:
            raise ValueError(f"unknown propagation path role: {self.role!r}")
        for name, point in (("start", self.start), ("end", self.end)):
            if not isinstance(point, Vec3):
                raise ValueError(f"{name} must be a finite Vec3")
            if not all(math.isfinite(value) for value in (point.x, point.y, point.z)):
                raise ValueError(f"{name} must be a finite Vec3")
        for name, identifier in (("reflecting_wall_id", self.reflecting_wall_id),
                                 ("ris_id", self.ris_id)):
            if identifier is not None and (not isinstance(identifier, str) or not identifier):
                raise ValueError(f"{name} must be a non-empty string or None")
        reflection = self.role in ("reflection_before", "reflection_after")
        ris = self.role in ("ris_incident", "ris_scattered")
        if reflection != (self.reflecting_wall_id is not None) or ris != (self.ris_id is not None):
            raise ValueError(f"IDs do not match propagation path role {self.role!r}")


@dataclass(frozen=True, slots=True)
class PropagationModifier:
    """Dimensionless scalar and diagnostic IDs, validated at the engine boundary."""

    value: complex
    blocker_ids: tuple[str, ...] = ()


@runtime_checkable
class PropagationProfile(Protocol):
    """Environment rule with stable metadata and no access to hidden truth."""

    @property
    def profile_id(self) -> str: ...

    @property
    def profile_version(self) -> str: ...

    @property
    def canonical_parameters(self) -> CanonicalParameters: ...

    def environment_modifier(
        self, *, scene: Scene, context: PropagationPathContext
    ) -> PropagationModifier: ...


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} must match [a-z0-9][a-z0-9_.-]*")
    return value


def _tagged_scalar(value: CanonicalParameter) -> list:
    # Exact built-in types avoid repr/custom encoder or NumPy type semantics.
    if value is None:
        return ["null", None]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float and math.isfinite(value):
        return ["float64_hex", value.hex()]
    if type(value) is str:
        return ["str", value]
    raise ValueError("canonical parameter must be None, bool, int, finite float or str")


def profile_identity(profile: PropagationProfile) -> str:
    """Return the C1 tagged-JSON SHA-256 identity, independent of process hash seeds."""
    try:
        identifier = _identifier(profile.profile_id, "profile_id")
        version = _identifier(profile.profile_version, "profile_version")
        parameters = profile.canonical_parameters
    except AttributeError as exc:
        raise ValueError("Profile must expose ID, version and canonical_parameters") from exc
    if not isinstance(parameters, tuple):
        raise ValueError("canonical_parameters must be a sorted tuple of (key, scalar) tuples")
    tagged = []
    previous = None
    for pair in parameters:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("canonical parameter must be a (key, scalar) tuple")
        key = _identifier(pair[0], "parameter key")
        if previous is not None and key <= previous:
            raise ValueError("canonical parameter keys must be sorted and unique")
        tagged.append([key, _tagged_scalar(pair[1])])
        previous = key
    payload = ["airmirror_profile_identity", 1, ["str", identifier], ["str", version], tagged]
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Profile canonical payload must be valid UTF-8 JSON") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class IndoorDeterministicProfile:
    """Immutable v0.1 wall/obstacle attenuation, including the 300 dB blocker rule."""

    profile_id: str = field(default="indoor_deterministic", init=False)
    profile_version: str = field(default="1", init=False)
    canonical_parameters: CanonicalParameters = field(default=(), init=False)

    def environment_modifier(
        self, *, scene: Scene, context: PropagationPathContext
    ) -> PropagationModifier:
        excluded = {context.reflecting_wall_id} if context.reflecting_wall_id is not None else None
        attenuation, blockers = path_attenuation_amplitude(scene, context.start, context.end, excluded)
        return PropagationModifier(complex(attenuation, 0.0), tuple(blockers))
