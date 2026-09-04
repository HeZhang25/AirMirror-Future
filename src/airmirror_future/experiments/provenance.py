"""Minimum Foundation experiment provenance construction.

This module owns only run-level metadata.  It deliberately does not write files
or infer future physics identities: the experiment runner supplies the returned
fields to its CSV writer, while the respective future owners sign their own
identity fields.
"""

from __future__ import annotations

import json
import math
import re
import airmirror_future
from airmirror_future.physics import reflections
from airmirror_future.ris.phase import (
    generate_focus_pattern,
    generate_ris_only_focus_pattern,
)
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.profiles import (
    PropagationProfile,
    _tagged_scalar,
    profile_identity,
)


PROVENANCE_SCHEMA_ID = "airmirror_experiment_provenance"
PROVENANCE_SCHEMA_VERSION = 1
DEFAULT_PENDING_CONTRACTS = ("FND-PHY-NB", "FND-QA-AP", "FND-QA-CC")

_RUN_ID_SAFE = re.compile(r"^[^\\/\x00]+$")
_FOCUS_MODES: dict[object, tuple[str, str]] = {
    generate_focus_pattern: ("ris_only_phase_conjugate", "1"),
    generate_ris_only_focus_pattern: ("ris_only_phase_conjugate", "1"),
    generate_coherent_target_pattern: ("coherent_target", "1"),
}
_GROUND_TRUTH_KEYS = (
    "ris_phase_error_sigma_rad",
    "ris_efficiency_sigma_fraction",
    "wall_amplitude_error_sigma_fraction",
    "wall_phase_error_sigma_rad",
    "position_error_sigma_m",
    "measurement_noise_sigma_db",
)


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: object, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or empty")
    return value


def _validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or not run_id or not _RUN_ID_SAFE.fullmatch(run_id):
        raise ValueError("run_id must be a non-empty run-directory basename")
    if run_id in {".", ".."}:
        raise ValueError("run_id must be a non-empty run-directory basename")
    return run_id


def _canonical_profile_parameters(profile: PropagationProfile) -> str:
    """Serialize C1 tagged parameters with the identity's canonical JSON rules."""
    parameters = profile.canonical_parameters
    if not isinstance(parameters, tuple):
        raise ValueError("Profile canonical_parameters must be a sorted tuple")
    tagged: list[list[object]] = []
    previous: str | None = None
    for pair in parameters:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("Profile canonical parameter must be a (key, scalar) tuple")
        key, value = pair
        if not isinstance(key, str) or not key:
            raise ValueError("Profile canonical parameter key must be non-empty")
        if previous is not None and key <= previous:
            raise ValueError("Profile canonical parameter keys must be sorted and unique")
        tagged.append([key, _tagged_scalar(value)])
        previous = key
    try:
        return json.dumps(
            tagged,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Profile canonical parameters must be JSON serializable") from exc


def _focus_mode(focus: object) -> tuple[str, str]:
    try:
        return _FOCUS_MODES[focus]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "focus must be one of the supported actual Focus callables"
        ) from exc


def _world_metadata(
    scene: object,
    world: ControllerModel | GroundTruthModel,
) -> tuple[str, str, str, int]:
    if isinstance(world, GroundTruthModel):
        values: dict[str, float] = {}
        for key in _GROUND_TRUTH_KEYS:
            value = getattr(world, key, None)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"world model parameters {key} must be finite numbers")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"world model parameters {key} must be finite and non-negative")
            values[key] = float(value)
        seed = getattr(world, "seed", None)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("Ground Truth seed must be an integer")
        parameters = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return "ground_truth_stochastic", "1", parameters, seed
    if isinstance(world, ControllerModel):
        seed = getattr(scene, "random_seed", None)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("scene random_seed must be an integer")
        return "controller_nominal", "1", "{}", seed
    raise ValueError("world must be a ControllerModel or GroundTruthModel")


def _validate_optional_owner_fields(
    *,
    channel_frequency_model_id: object,
    quadrature_policy_id: object,
    quadrature_policy_version: object,
    coefficient_model_identity: object,
) -> tuple[str, str, str, str]:
    channel = _optional_string(channel_frequency_model_id, "channel_frequency_model_id")
    quadrature_id = _optional_string(quadrature_policy_id, "quadrature_policy_id")
    quadrature_version = _optional_string(
        quadrature_policy_version, "quadrature_policy_version"
    )
    coefficient = _optional_string(coefficient_model_identity, "coefficient_model_identity")
    if bool(quadrature_id) != bool(quadrature_version):
        raise ValueError("quadrature policy id and version must both be empty or non-empty")
    return channel, quadrature_id, quadrature_version, coefficient


def _build_provenance_fields(
    engine: object,
    scene: object,
    focus: object,
    world: ControllerModel | GroundTruthModel,
    search_levels: int | None = None,
    run_id: str | None = None,
    *,
    channel_frequency_model_id: str | None = None,
    quadrature_policy_id: str | None = None,
    quadrature_policy_version: str | None = None,
    coefficient_model_identity: str | None = None,
) -> dict[str, object]:
    """Build C2 schema metadata from actual run objects.

    ``world`` is the actual model used by the run.  It is intentionally required:
    provenance must never infer a nominal Controller model when a caller forgets
    to pass the selected world.
    """
    if run_id is None:
        raise ValueError("run_id is required")
    validated_run_id = _validate_run_id(run_id)
    focus_id, focus_version = _focus_mode(focus)
    if search_levels is not None and (
        isinstance(search_levels, bool)
        or not isinstance(search_levels, int)
        or search_levels <= 0
    ):
        raise ValueError("search_levels must be a positive integer or None")

    world_id, world_version, world_parameters, random_seed = _world_metadata(scene, world)

    try:
        profile = engine.profile
    except AttributeError as exc:
        raise ValueError("engine must expose the actual PropagationProfile") from exc
    if not isinstance(profile, PropagationProfile):
        raise ValueError("engine must expose the actual PropagationProfile")
    identity = profile_identity(profile)
    engine_identity = getattr(engine, "profile_identity", identity)
    if engine_identity != identity:
        raise ValueError("Profile identity changed after engine construction")
    parameters_json = _canonical_profile_parameters(profile)

    channel, quadrature_id, quadrature_version, coefficient = _validate_optional_owner_fields(
        channel_frequency_model_id=channel_frequency_model_id,
        quadrature_policy_id=quadrature_policy_id,
        quadrature_policy_version=quadrature_policy_version,
        coefficient_model_identity=coefficient_model_identity,
    )
    # C2 is intentionally partial until the three future owner Work Items sign
    # their contracts.  Candidate IDs may be recorded above, but callers cannot
    # remove these mandatory pending owners or manufacture a complete result.
    pending = DEFAULT_PENDING_CONTRACTS

    return {
        "provenance_schema_id": PROVENANCE_SCHEMA_ID,
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "provenance_status": "partial",
        "pending_contracts_json": json.dumps(pending, separators=(",", ":")),
        "run_id": validated_run_id,
        "software_version": _non_empty_string(airmirror_future.__version__, "software_version"),
        "focus_mode_id": focus_id,
        "focus_mode_version": focus_version,
        "search_levels": search_levels,
        "profile_id": _non_empty_string(profile.profile_id, "profile_id"),
        "profile_version": _non_empty_string(profile.profile_version, "profile_version"),
        "profile_parameters_json": parameters_json,
        "profile_identity": identity,
        "reflection_model_id": _non_empty_string(
            reflections.reflection_model_id, "reflection_model_id"
        ),
        "reflection_model_version": _non_empty_string(
            reflections.reflection_model_version, "reflection_model_version"
        ),
        "world_model_id": world_id,
        "world_model_version": world_version,
        "world_model_parameters_json": world_parameters,
        "random_seed": random_seed,
        "channel_frequency_model_id": channel,
        "quadrature_policy_id": quadrature_id,
        "quadrature_policy_version": quadrature_version,
        "coefficient_model_identity": coefficient,
    }


__all__ = [
    "DEFAULT_PENDING_CONTRACTS",
    "PROVENANCE_SCHEMA_ID",
    "PROVENANCE_SCHEMA_VERSION",
    "_build_provenance_fields",
]
