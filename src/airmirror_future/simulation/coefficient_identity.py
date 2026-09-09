"""Stable identity for production Controller RIS transfer coefficients."""

from __future__ import annotations

import hashlib
import json
import math

from airmirror_future.core.types import RISSurface, Scene, Transmitter, Receiver
from airmirror_future.physics.ris_scattering import (
    PRODUCTION_QUADRATURE_POLICY_ID,
    PRODUCTION_QUADRATURE_POLICY_VERSION,
    _production_quadrature_spec,
)
from airmirror_future.ris.quadrature import QuadratureSpec
from airmirror_future.simulation.profiles import (
    IndoorDeterministicProfile,
    PropagationPathContext,
    profile_identity,
)


def _canonical(value: object) -> object:
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("coefficient identity values must be finite")
        return ["float64_hex", value.hex()]
    if type(value) in (str, int, bool) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    raise ValueError(f"unsupported coefficient identity value: {type(value).__name__}")


def _quadrature_array_identity(spec: QuadratureSpec) -> str:
    """Hash the exact custom quadrature arrays with the canonical JSON rules."""
    payload = {
        "schema": "airmirror_quadrature_arrays/1",
        "sample_coordinates": spec.sample_coordinates.tolist(),
        "weights": spec.weights.tolist(),
        "parent_control_index": spec.parent_control_index.tolist(),
    }
    encoded = json.dumps(
        _canonical(payload), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _canonical(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _quadrature_canonical_json(
    spec: QuadratureSpec,
    policy_id: str,
    policy_version: str,
    *,
    array_identity: str | None = None,
) -> bytes:
    """Return C's exact canonical quadrature subdocument for safe reuse."""
    return _canonical_json_bytes(
        {
            "policy_id": policy_id,
            "policy_version": policy_version,
            "rule": spec.rule,
            "order_x": spec.order_x,
            "order_y": spec.order_y,
            "flatten_order": "ris_cell_centers_meshgrid_xy_c_v1",
            "parent_control_index": spec.parent_control_index.tolist(),
            "array_identity": (
                _quadrature_array_identity(spec)
                if array_identity is None
                else array_identity
            ),
        }
    )


def controller_ris_coefficient_identity(
    scene: Scene,
    engine: object,
    tx: Transmitter,
    rx: Receiver,
    ris: RISSurface,
    *,
    quadrature_spec: QuadratureSpec | None = None,
    quadrature_policy_id: str | None = None,
    quadrature_policy_version: str | None = None,
    _quadrature_json: bytes | None = None,
) -> str:
    """Return a cross-process identity for nominal RIS ``a^C``.

    Relevant blockers are projected for the built-in Profile; environment
    entities are conservatively included for custom Profile safety.
    Command state, efficiency, phase bits, Pt, B/NF, coverage, and RNG are excluded.
    """
    if quadrature_spec is None:
        coefficient_model = getattr(engine, "coefficient_model", None)
        if coefficient_model is None or (
            coefficient_model.quadrature_policy_id == PRODUCTION_QUADRATURE_POLICY_ID
            and coefficient_model.quadrature_policy_version
            == PRODUCTION_QUADRATURE_POLICY_VERSION
        ):
            spec = _production_quadrature_spec(ris)
            policy_id = PRODUCTION_QUADRATURE_POLICY_ID
            policy_version = PRODUCTION_QUADRATURE_POLICY_VERSION
            model_identity = None
            array_identity = "derived_by_signed_production_policy"
        else:
            spec = coefficient_model.quadrature_spec(ris)
            policy_id = coefficient_model.quadrature_policy_id
            policy_version = coefficient_model.quadrature_policy_version
            model_identity = coefficient_model.identity
            array_identity = "derived_by_named_coefficient_model"
        if quadrature_policy_id not in (None, policy_id) or quadrature_policy_version not in (
            None,
            policy_version,
        ):
            raise ValueError("production quadrature identity does not accept another policy")
    else:
        spec = quadrature_spec
        if spec.control_count != ris.cell_count:
            raise ValueError("quadrature must have one parent group per control patch")
        if not isinstance(quadrature_policy_id, str) or not quadrature_policy_id:
            raise ValueError("custom quadrature identity requires a non-empty policy id")
        if not isinstance(quadrature_policy_version, str) or not quadrature_policy_version:
            raise ValueError("custom quadrature identity requires a non-empty policy version")
        policy_id = quadrature_policy_id
        policy_version = quadrature_policy_version
        model_identity = "custom_quadrature_research_evaluation/1"
        array_identity = (
            None if _quadrature_json is not None else _quadrature_array_identity(spec)
        )

    before_context = PropagationPathContext(
        "ris_incident", tx.position, ris.position, ris_id=ris.id
    )
    after_context = PropagationPathContext(
        "ris_scattered", ris.position, rx.position, ris_id=ris.id
    )
    before = engine._environment_modifier(scene, before_context)
    after = engine._environment_modifier(scene, after_context)
    modifiers = [
        [before.value.real, before.value.imag, list(before.blocker_ids)],
        [after.value.real, after.value.imag, list(after.blocker_ids)],
    ]

    if isinstance(engine.profile, IndoorDeterministicProfile):
        relevant_ids = set(before.blocker_ids + after.blocker_ids)
        walls = [w for w in scene.walls if w.id in relevant_ids]
        obstacles = [o for o in scene.obstacles if o.id in relevant_ids]
        custom_environment = None
    else:
        walls = scene.walls
        obstacles = scene.obstacles
        # A custom Profile receives the complete Scene object.  In addition to
        # recording its two actual outputs above, retain the complete canonical
        # environment collection because it has no declared dependency
        # projection comparable to IndoorDeterministicProfile.
        custom_environment = {
            "room_size": [scene.room_size.x, scene.room_size.y, scene.room_size.z],
            "z_eval_m": scene.z_eval_m,
            "schema_version": scene.schema_version,
        }
    wall_rows = []
    for wall in walls:
        row = [wall.id, wall.start.x, wall.start.y, wall.start.z,
               wall.end.x, wall.end.y, wall.end.z, wall.height_m,
               wall.attenuation_db, wall.blocks_los]
        if not isinstance(engine.profile, IndoorDeterministicProfile):
            row.extend([wall.reflection_magnitude, wall.reflection_phase_rad])
        wall_rows.append(row)
    quadrature_payload = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "rule": spec.rule,
        "order_x": spec.order_x,
        "order_y": spec.order_y,
        "flatten_order": "ris_cell_centers_meshgrid_xy_c_v1",
        "parent_control_index": spec.parent_control_index.tolist(),
        "array_identity": array_identity,
    }
    if model_identity is not None:
        quadrature_payload["coefficient_model_identity"] = model_identity
    payload = {
        "schema": "airmirror_controller_ris_coefficient/1",
        "frequency_model": "narrowband_center_frequency_flat_v1",
        "frequency_hz": scene.frequency_hz,
        "profile_identity": profile_identity(engine.profile),
        "quadrature": quadrature_payload,
        "tx": [tx.position.x, tx.position.y, tx.position.z, tx.gain_linear],
        "rx": [rx.position.x, rx.position.y, rx.position.z, rx.gain_linear],
        "ris": [ris.id, ris.position.x, ris.position.y, ris.position.z, ris.yaw_rad,
                ris.width_m, ris.height_m, ris.nx, ris.ny, ris.direction_exponent],
        "path_modifiers": modifiers,
        "custom_environment": custom_environment,
        "walls": wall_rows,
        "obstacles": [[o.id, o.min_corner.x, o.min_corner.y, o.min_corner.z,
                       o.max_corner.x, o.max_corner.y, o.max_corner.z,
                       o.attenuation_db, o.fully_blocking] for o in obstacles],
    }
    if _quadrature_json is None:
        encoded = _canonical_json_bytes(payload)
        return "sha256:" + hashlib.sha256(encoded).hexdigest()
    if not isinstance(_quadrature_json, bytes):
        raise ValueError("cached quadrature JSON must be bytes")
    digest = hashlib.sha256()
    digest.update(b"{")
    for index, key in enumerate(sorted(payload)):
        if index:
            digest.update(b",")
        digest.update(_canonical_json_bytes(key))
        digest.update(b":")
        digest.update(
            _quadrature_json
            if key == "quadrature"
            else _canonical_json_bytes(payload[key])
        )
    digest.update(b"}")
    return "sha256:" + digest.hexdigest()


__all__ = ["controller_ris_coefficient_identity"]
