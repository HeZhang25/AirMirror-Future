"""Reproduce the Future Intelligent Workspace dual-RIS demonstration.

This asset intentionally uses only the checked-in Scene v1 models, the
Controller-only dual-RIS Focus helper, SimulationEngine, and the prepared
dual-RIS link/field APIs.  It does not introduce a second physics path.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from airmirror_future import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    SimulationEngine,
    evaluate_dual_ris_command,
    generate_dual_ris_coordinated_patterns,
    prepare_controller_dual_ris_field,
    prepare_controller_dual_ris_link,
)
from airmirror_future.core.types import Scene, SimulationConfig, Vec3
from airmirror_future.experiments.xr_route import load_route_experiment
from airmirror_future.scene.serialization import load_scene


DEFAULT_SCENE = Path("scenes/future_intelligent_workspace_demo.json")
DEFAULT_ROUTE = Path("scenes/future_intelligent_workspace_route.json")
DEFAULT_OUTPUT = Path(
    "results/demos/future_intelligent_workspace_dual_ris_1x1.json"
)


def _complex(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _hash_pattern(pattern: np.ndarray) -> str:
    values = np.ascontiguousarray(pattern, dtype=np.float64)
    return "sha256:" + hashlib.sha256(values.tobytes()).hexdigest()


def _pattern_summary(patterns: dict[str, np.ndarray]) -> dict[str, object]:
    return {
        identifier: {
            "cell_count": int(values.size),
            "phase_min_rad": float(np.min(values)),
            "phase_max_rad": float(np.max(values)),
            "sha256": _hash_pattern(values),
            "commands_rad": [float(value) for value in values],
        }
        for identifier, values in patterns.items()
    }


def _channel_summary(result: object, patterns: dict[str, np.ndarray]) -> dict[str, object]:
    ris_blockers = {
        str(detail["ris_id"]): list(detail.get("blockers", ()))
        for detail in result.path_details
        if detail.get("kind") == "RIS"
    }
    return {
        "commands": _pattern_summary(patterns),
        "los_channel": _complex(result.los_channel),
        "wall_channel": _complex(result.wall_channel),
        "ris_channel": _complex(result.ris_channel),
        "total_channel": _complex(result.total_channel),
        "received_power_w": float(result.received_power_w),
        "received_power_dbm": float(result.received_power_dbm),
        "snr_db": float(result.snr_db),
        "ris_path_blockers": ris_blockers,
    }


def _point_scene(scene: Scene, position: Vec3) -> Scene:
    return replace(scene, receivers=[replace(scene.receiver(), position=position)])


def _focus_case(
    scene: Scene,
    engine: SimulationEngine,
    ris_ids: tuple[str, ...],
) -> tuple[dict[str, np.ndarray], object]:
    if not ris_ids:
        patterns: dict[str, np.ndarray] = {}
    else:
        patterns = generate_dual_ris_coordinated_patterns(
            scene, engine=engine, ris_ids=ris_ids
        ).patterns
    return patterns, evaluate_dual_ris_command(scene, patterns, engine=engine)


def _prepared_case(
    scene: Scene,
    engine: SimulationEngine,
    ris_ids: tuple[str, ...],
    patterns: dict[str, np.ndarray],
) -> dict[str, object]:
    if not ris_ids:
        return {"used": False, "reason": "No RIS uses the direct Engine baseline"}
    started = time.perf_counter()
    prepared = prepare_controller_dual_ris_link(
        scene, engine=engine, ris_ids=ris_ids
    )
    result = prepared.evaluate(patterns)
    return {
        "used": True,
        "build_runtime_s": float(time.perf_counter() - started),
        "coefficient_model_identity": prepared.coefficient_model_identity,
        "ris_ids": list(ris_ids),
        "coefficient_identities": list(prepared.coefficient_identities),
        "total_channel": _complex(result.total_channel),
        "received_power_dbm": float(result.received_power_dbm),
        "snr_db": float(result.snr_db),
        "direct_engine_delta_abs": float(
            abs(result.total_channel - evaluate_dual_ris_command(
                scene, patterns, engine=engine
            ).total_channel)
        ),
    }


def _target_cases(scene: Scene, engine: SimulationEngine, position: Vec3) -> dict[str, object]:
    point_scene = _point_scene(scene, position)
    ris_ids = tuple(ris.id for ris in point_scene.ris_surfaces)
    cases: dict[str, object] = {}
    definitions = (
        ("no_ris", ()),
        ("single_first_ris", (ris_ids[0],)),
        ("single_second_ris", (ris_ids[1],)),
        ("dual_ris", ris_ids),
    )
    for name, selected in definitions:
        patterns, result = _focus_case(point_scene, engine, selected)
        cases[name] = {
            "engine": _channel_summary(result, patterns),
            "prepared": _prepared_case(point_scene, engine, selected, patterns),
        }
    return cases


def _orientation_checks(scene: Scene, target_points: dict[str, Vec3]) -> list[dict[str, object]]:
    """Record the signed front-face cosines used by the existing RIS model."""
    checks: list[dict[str, object]] = []
    tx = scene.transmitter().position
    for ris in scene.ris_surfaces:
        incident = tx.as_array() - ris.position.as_array()
        incident /= np.linalg.norm(incident)
        checks.append(
            {
                "ris_id": ris.id,
                "normal": [float(value) for value in ris.normal],
                "incident_cos_to_tx": float(np.dot(incident, ris.normal)),
                "target_cos_by_point": {
                    identifier: float(
                        np.dot(
                            (position.as_array() - ris.position.as_array())
                            / np.linalg.norm(position.as_array() - ris.position.as_array()),
                            ris.normal,
                        )
                    )
                    for identifier, position in target_points.items()
                },
            }
        )
    return checks


def _field_summary(scene: Scene, engine: SimulationEngine, patterns: dict[str, np.ndarray]) -> dict[str, object]:
    config = SimulationConfig(8, 6, "power", batch_size=8)
    started = time.perf_counter()
    prepared = prepare_controller_dual_ris_field(
        scene,
        config,
        engine=engine,
        ris_ids=tuple(ris.id for ris in scene.ris_surfaces),
        receiver_batch_size=8,
    )
    field = prepared.evaluate(patterns)
    return {
        "grid": [8, 6],
        "model": prepared.coefficient_model_identity,
        "build_runtime_s": float(prepared.build_runtime_s),
        "wall_clock_s": float(time.perf_counter() - started),
        "coefficient_bytes": int(prepared.coefficient_bytes),
        "coefficient_identities": [list(row) for row in prepared.coefficient_identities],
        "coverage_percent": float(field.coverage_percent),
        "dead_zone_percent": float(field.dead_zone_percent),
        "power_min_dbm": float(np.min(field.received_power_dbm)),
        "power_max_dbm": float(np.max(field.received_power_dbm)),
        "snr_min_db": float(np.min(field.snr_db)),
        "snr_max_db": float(np.max(field.snr_db)),
        "ris_gain_min_db": float(np.min(field.ris_gain_db)),
        "ris_gain_max_db": float(np.max(field.ris_gain_db)),
    }


def build_demo(scene_path: Path = DEFAULT_SCENE, route_path: Path = DEFAULT_ROUTE) -> dict[str, object]:
    scene = load_scene(scene_path)
    route = load_route_experiment(route_path)
    if route.scene_identity != _scene_identity(scene):
        raise ValueError("route does not reference the supplied Scene v1 identity")
    if len(scene.ris_surfaces) != 2 or any(
        ris.generation != "Future" or not ris.enabled for ris in scene.ris_surfaces
    ):
        raise ValueError("demo requires exactly two enabled Future RIS surfaces")
    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    ids = tuple(ris.id for ris in scene.ris_surfaces)
    target_indices = (1, 3, 4, 7)
    target_points = {
        f"point-{index + 1}": {
            "position_m": {
                "x": float(route.route.waypoints[index].x),
                "y": float(route.route.waypoints[index].y),
                "z": float(route.route.waypoints[index].z),
            },
            "role": (
                "direct TX service zone"
                if index == 1
                else "partition transition edge"
                if index == 3
                else "central weak-coverage corridor"
                if index == 4
                else "east RIS service zone"
            ),
            "cases": _target_cases(scene, engine, route.route.waypoints[index]),
        }
        for index in target_indices
    }
    target_positions = {
        identifier: Vec3(
            values["position_m"]["x"],
            values["position_m"]["y"],
            values["position_m"]["z"],
        )
        for identifier, values in target_points.items()
    }
    dual_target_patterns, _ = _focus_case(
        _point_scene(scene, route.route.waypoints[-1]), engine, ids
    )
    started = time.perf_counter()
    field = _field_summary(_point_scene(scene, route.route.waypoints[-1]), engine, dual_target_patterns)
    return {
        "schema": "airmirror_future_intelligent_workspace_dual_ris_demo/1",
        "scene_file": scene_path.as_posix(),
        "route_file": route_path.as_posix(),
        "scene_identity": _scene_identity(scene),
        "route_identity": route.experiment_identity,
        "route_validation": {
            "waypoint_count": len(route.route.waypoints),
            "sample_count": len(route.trajectory),
            "duration_s": float(route.trajectory[-1].time_s),
            "collisions": [collision.message for collision in route.validation_report.collisions],
            "warnings": [warning.message for warning in route.validation_report.warnings],
            "clearance_warning_m": float(route.validation.clearance_warning_m),
        },
        "scene_summary": {
            "name": scene.name,
            "room_size_m": [scene.room_size.x, scene.room_size.y, scene.room_size.z],
            "frequency_hz": scene.frequency_hz,
            "bandwidth_hz": scene.bandwidth_hz,
            "wall_count": len(scene.walls),
            "obstacle_count": len(scene.obstacles),
            "ris_ids": list(ids),
            "ris": [
                {
                    "id": ris.id,
                    "generation": ris.generation,
                    "enabled": ris.enabled,
                    "position_m": [ris.position.x, ris.position.y, ris.position.z],
                    "yaw_rad": ris.yaw_rad,
                    "normal": ris.normal.tolist(),
                    "aperture_m": [ris.width_m, ris.height_m],
                    "control_grid": [ris.nx, ris.ny],
                    "phase_bits": ris.phase_bits,
                    "reflection_efficiency": ris.reflection_efficiency,
                }
                for ris in scene.ris_surfaces
            ],
            "orientation_checks": _orientation_checks(scene, target_positions),
        },
        "coefficient_model": {
            "identity": FAST_1X1_RIS_COEFFICIENT_MODEL.identity,
            "quadrature_identity": FAST_1X1_RIS_COEFFICIENT_MODEL.quadrature_identity,
        },
        "representative_targets": target_points,
        "prepared_dual_ris_field_8x6": field,
        "runtime_s": float(time.perf_counter() - started),
        "runtime_scope": "FAST 1x1 focus, direct Engine cases, prepared dual-RIS link and 8x6 field only",
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
        },
    }


def _scene_identity(scene: Scene) -> str:
    """Use the route owner's canonical identity without duplicating its algorithm."""
    from airmirror_future.experiments.xr_route import _scene_identity as route_scene_identity

    return route_scene_identity(scene)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--route", type=Path, default=DEFAULT_ROUTE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_demo(args.scene, args.route)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "runtime_s": payload["runtime_s"]}))


if __name__ == "__main__":
    main()
