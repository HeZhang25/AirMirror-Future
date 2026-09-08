"""Stable identity for production Controller RIS transfer coefficients."""

from __future__ import annotations

import hashlib
import json
import math

from airmirror_future.core.types import RISSurface, Scene, Transmitter, Receiver
from airmirror_future.physics.ris_scattering import (
    PRODUCTION_QUADRATURE_POLICY_ID,
    PRODUCTION_QUADRATURE_POLICY_VERSION,
)
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


def controller_ris_coefficient_identity(
    scene: Scene,
    engine: object,
    tx: Transmitter,
    rx: Receiver,
    ris: RISSurface,
) -> str:
    """Return a cross-process identity for nominal RIS ``a^C``.

    Relevant blockers are projected for the built-in Profile; environment
    entities are conservatively included for custom Profile safety.
    Command state, efficiency, phase bits, Pt, B/NF, coverage, and RNG are excluded.
    """
    if isinstance(engine.profile, IndoorDeterministicProfile):
        before = engine._environment_modifier(
            scene, PropagationPathContext("ris_incident", tx.position, ris.position, ris_id=ris.id)
        )
        after = engine._environment_modifier(
            scene, PropagationPathContext("ris_scattered", ris.position, rx.position, ris_id=ris.id)
        )
        relevant_ids = set(before.blocker_ids + after.blocker_ids)
        walls = [w for w in scene.walls if w.id in relevant_ids]
        obstacles = [o for o in scene.obstacles if o.id in relevant_ids]
        modifiers = [[before.value.real, before.value.imag, list(before.blocker_ids)],
                     [after.value.real, after.value.imag, list(after.blocker_ids)]]
    else:
        walls = scene.walls
        obstacles = scene.obstacles
        modifiers = None
    wall_rows = []
    for wall in walls:
        row = [wall.id, wall.start.x, wall.start.y, wall.start.z,
               wall.end.x, wall.end.y, wall.end.z, wall.height_m,
               wall.attenuation_db, wall.blocks_los]
        if not isinstance(engine.profile, IndoorDeterministicProfile):
            row.extend([wall.reflection_magnitude, wall.reflection_phase_rad])
        wall_rows.append(row)
    payload = {
        "schema": "airmirror_controller_ris_coefficient/1",
        "frequency_model": "narrowband_center_frequency_flat_v1",
        "frequency_hz": scene.frequency_hz,
        "profile_identity": profile_identity(engine.profile),
        "quadrature": [PRODUCTION_QUADRATURE_POLICY_ID, PRODUCTION_QUADRATURE_POLICY_VERSION],
        "tx": [tx.position.x, tx.position.y, tx.position.z, tx.gain_linear],
        "rx": [rx.position.x, rx.position.y, rx.position.z, rx.gain_linear],
        "ris": [ris.id, ris.position.x, ris.position.y, ris.position.z, ris.yaw_rad,
                ris.width_m, ris.height_m, ris.nx, ris.ny, ris.direction_exponent],
        "path_modifiers": modifiers,
        "walls": wall_rows,
        "obstacles": [[o.id, o.min_corner.x, o.min_corner.y, o.min_corner.z,
                       o.max_corner.x, o.max_corner.y, o.max_corner.z,
                       o.attenuation_db, o.fully_blocking] for o in obstacles],
    }
    encoded = json.dumps(_canonical(payload), ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = ["controller_ris_coefficient_identity"]
