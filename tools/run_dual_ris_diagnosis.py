"""Reproduce the original dual-RIS diagnosis and a complementary two-target scene.

The script uses the unchanged FAST 1x1 coefficient model and the public Scene v1
and dual-Future Controller APIs.  It never edits the original scene or manifest.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np

from airmirror_future.core.types import Obstacle, Receiver, RISSurface, Scene, Transmitter, Vec3, SimulationConfig
from airmirror_future.core.units import dbm_to_watts
from airmirror_future.optimization.dual_ris_focus import (
    evaluate_dual_ris_command,
    generate_dual_ris_coordinated_patterns,
)
from airmirror_future.physics.ris_scattering import FAST_1X1_RIS_COEFFICIENT_MODEL
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.profiles import PropagationPathContext
from airmirror_future.scene.serialization import load_scene


def _complex(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _command_json(patterns: dict[str, np.ndarray]) -> dict[str, list[float]]:
    return {identifier: [float(value) for value in values] for identifier, values in patterns.items()}


def _case(scene: Scene, engine: SimulationEngine, patterns: dict[str, np.ndarray]) -> dict[str, object]:
    result = evaluate_dual_ris_command(scene, patterns, engine=engine)
    details = {row["ris_id"]: row for row in result.path_details if row.get("kind") == "RIS"}
    h0 = result.los_channel + result.wall_channel
    command_state = {
        ris.id: {
            "enabled": bool(ris.enabled),
            "command_present": ris.id in patterns,
            "command_length": int(np.asarray(patterns[ris.id]).size) if ris.id in patterns else 0,
        }
        for ris in scene.ris_surfaces
    }
    return {
        "commands_rad": _command_json(patterns),
        "h0": _complex(h0),
        "h1": _complex(result.los_channel),
        "h2": _complex(result.wall_channel),
        # Explicit aliases retain the physical meaning for readers of older
        # manifests while the compact h0/h1/h2 names match the diagnostic table.
        "h0_baseline": _complex(h0),
        "h1_los": _complex(result.los_channel),
        "h2_wall": _complex(result.wall_channel),
        "ris_channel": _complex(result.ris_channel),
        "total_channel": _complex(result.total_channel),
        "received_power_w": float(result.received_power_w),
        "received_power_dbm": float(result.received_power_dbm),
        "snr_db": float(result.snr_db),
        "ris_path_details": {
            identifier: {
                "channel": _complex(row["channel"]),
                "blockers": list(row["blockers"]),
            }
            for identifier, row in details.items()
        },
        "command_state": command_state,
    }


def _four_cases(scene: Scene, engine: SimulationEngine) -> dict[str, object]:
    no = _case(scene, engine, {})
    ids = tuple(ris.id for ris in scene.ris_surfaces)
    singles: dict[str, object] = {}
    for identifier in ids:
        focus = generate_dual_ris_coordinated_patterns(scene, engine=engine, ris_ids=(identifier,))
        item = _case(scene, engine, focus.patterns)
        item["optimization"] = {"rounds": int(focus.rounds), "converged": bool(focus.converged)}
        singles[identifier] = item
    focus = generate_dual_ris_coordinated_patterns(scene, engine=engine, ris_ids=ids)
    dual = _case(scene, engine, focus.patterns)
    dual["optimization"] = {"rounds": int(focus.rounds), "converged": bool(focus.converged)}
    return {"no_ris": no, "single_ris": singles, "dual_ris": dual}


def _geometry_diagnostics(scene: Scene, engine: SimulationEngine) -> dict[str, object]:
    tx = scene.transmitter()
    target = scene.receiver().position
    rows = {}
    for ris in scene.ris_surfaces:
        incoming = tx.position.as_array() - ris.position.as_array()
        incoming /= np.linalg.norm(incoming)
        outgoing = target.as_array() - ris.position.as_array()
        outgoing /= np.linalg.norm(outgoing)
        before = engine._environment_modifier(
            scene, PropagationPathContext("ris_incident", tx.position, ris.position, ris_id=ris.id)
        )
        after = engine._environment_modifier(
            scene, PropagationPathContext("ris_scattered", ris.position, target, ris_id=ris.id)
        )
        rows[ris.id] = {
            "distance_tx_ris_m": tx.position.distance_to(ris.position),
            "distance_ris_rx_m": ris.position.distance_to(target),
            "cos_in": float(max(0.0, incoming @ ris.normal)),
            "cos_out": float(max(0.0, outgoing @ ris.normal)),
            "incident_modifier": _complex(before.value),
            "incident_blockers": list(before.blocker_ids),
            "scattered_modifier": _complex(after.value),
            "scattered_blockers": list(after.blocker_ids),
            "enabled": bool(ris.enabled),
            "yaw_rad": float(ris.yaw_rad),
        }
    return rows


def _bisector_yaw(position: tuple[float, float, float], tx: tuple[float, float, float], target: tuple[float, float, float]) -> float:
    a = math.atan2(tx[1] - position[1], tx[0] - position[0])
    b = math.atan2(target[1] - position[1], target[0] - position[0])
    return math.atan2(math.sin(a) + math.sin(b), math.cos(a) + math.cos(b))


def build_complementary_scene() -> Scene:
    tx_position = (1.0, 5.0, 2.4)
    target_a = (3.0, 8.0, 1.2)
    target_b = (10.0, 2.0, 1.2)
    def wall(identifier: str, start: tuple[float, float], end: tuple[float, float], blocks: bool = True) -> object:
        from airmirror_future.core.types import Wall
        return Wall(identifier, Vec3(*start, 0.0), Vec3(*end, 0.0), height_m=3.0, attenuation_db=24.0 if blocks else 80.0, reflection_magnitude=0.35 if blocks else 0.2, reflection_phase_rad=2.4 if blocks else math.pi, blocks_los=blocks)
    walls = [
        wall("north", (0.0, 10.0), (12.0, 10.0), False),
        wall("south", (0.0, 0.0), (12.0, 0.0), False),
        wall("west", (0.0, 0.0), (0.0, 10.0), False),
        wall("east", (12.0, 0.0), (12.0, 10.0), False),
        wall("mid-vertical", (6.0, 4.2), (6.0, 5.8)),
        wall("mid-horizontal", (6.0, 5.0), (10.0, 5.0)),
    ]
    ris_a_position = (3.0, 8.8, 1.5)
    ris_b_position = (9.0, 1.2, 1.5)
    ris = [
        RISSurface("ris-north", Vec3(*ris_a_position), _bisector_yaw(ris_a_position, tx_position, target_a), 3.0, 2.0, 64, 48, None, 0.95, 1000.0, True, "Future"),
        RISSurface("ris-east", Vec3(*ris_b_position), _bisector_yaw(ris_b_position, tx_position, target_b), 3.0, 2.0, 64, 48, None, 0.95, 1000.0, True, "Future"),
    ]
    return Scene(
        "Future Dual RIS Complementary Demonstration",
        Vec3(12.0, 10.0, 3.0),
        5.0e9,
        1.0e8,
        [Transmitter("tx-demo", Vec3(*tx_position), dbm_to_watts(20.0), 1.0)],
        [Receiver("rx-demo", Vec3(*target_a), 1.0, 7.0)],
        walls,
        [Obstacle("cabinet", Vec3(5.2, 7.0, 0.0), Vec3(6.2, 8.0, 2.0), attenuation_db=16.0)],
        ris,
        1.2,
        35.0,
        20260909,
    )


def build_diagnosis(original_path: Path, output_scene: Path, output_manifest: Path, grid: tuple[int, int]) -> dict[str, object]:
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    original = load_scene(original_path)
    original_cases = _four_cases(original, engine)
    original_focus = generate_dual_ris_coordinated_patterns(original, engine=engine)
    original_diag = _geometry_diagnostics(original, engine)

    complementary = build_complementary_scene()
    output_scene.parent.mkdir(parents=True, exist_ok=True)
    complementary.save(output_scene)
    target_points = {"ris-north_target": Vec3(3.0, 8.0, 1.2), "ris-east_target": Vec3(10.0, 2.0, 1.2)}
    targets: dict[str, object] = {}
    field_summaries: dict[str, object] = {}
    for name, point in target_points.items():
        target_scene = replace(complementary, receivers=[replace(complementary.receiver(), position=point)])
        cases = _four_cases(target_scene, engine)
        targets[name] = {"position_m": {"x": point.x, "y": point.y, "z": point.z}, "cases": cases, "geometry": _geometry_diagnostics(target_scene, engine)}
        fields = {}
        for label, case in (("no_ris", cases["no_ris"]), ("north", cases["single_ris"]["ris-north"]), ("east", cases["single_ris"]["ris-east"]), ("dual", cases["dual_ris"])):
            patterns = {key: np.asarray(values, dtype=float) for key, values in case["commands_rad"].items()}
            field = engine.compute_field_map(target_scene, SimulationConfig(grid[0], grid[1], batch_size=8), ris_patterns=patterns)
            fields[label] = {"grid": list(grid), "power_dbm_min": float(np.min(field.received_power_dbm)), "power_dbm_max": float(np.max(field.received_power_dbm)), "power_dbm_mean": float(np.mean(field.received_power_dbm)), "snr_db_mean": float(np.mean(field.snr_db))}
        field_summaries[name] = fields
    payload = {
        "schema": "airmirror_future_dual_ris_diagnosis/1",
        "coefficient_model": {"identity": FAST_1X1_RIS_COEFFICIENT_MODEL.identity, "quadrature_identity": FAST_1X1_RIS_COEFFICIENT_MODEL.quadrature_identity},
        "original_baseline": {"scene_file": original_path.as_posix(), "cases": original_cases, "geometry": original_diag, "dual_minus_north_db": original_cases["dual_ris"]["received_power_dbm"] - original_cases["single_ris"]["ris-north"]["received_power_dbm"], "dual_command_ids": sorted(original_focus.patterns)},
        "new_scene_file": output_scene.as_posix(),
        "verification_grid": list(grid),
        "targets": targets,
        "field_summaries": field_summaries,
    }
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", type=Path, default=Path("scenes/future_dual_ris_demo.json"))
    parser.add_argument("--scene", type=Path, default=Path("scenes/future_dual_ris_complementary.json"))
    parser.add_argument("--output", type=Path, default=Path("results/demos/future_dual_ris_diagnosis.json"))
    parser.add_argument("--grid", type=int, nargs=2, default=(8, 6))
    args = parser.parse_args()
    payload = build_diagnosis(args.original, args.scene, args.output, (int(args.grid[0]), int(args.grid[1])))
    print(json.dumps({"output": str(args.output), "scene": str(args.scene), "dual_minus_north_db": payload["original_baseline"]["dual_minus_north_db"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
