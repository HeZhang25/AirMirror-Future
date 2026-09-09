from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from airmirror_future import FAST_1X1_RIS_COEFFICIENT_MODEL
from airmirror_future.experiments.xr_route import load_route_experiment
from airmirror_future.scene.serialization import load_scene
from tools.run_future_intelligent_workspace_demo import build_demo


def test_future_intelligent_workspace_scene_route_and_four_cases() -> None:
    root = Path(__file__).parents[1]
    scene_path = root / "scenes" / "future_intelligent_workspace_demo.json"
    route_path = root / "scenes" / "future_intelligent_workspace_route.json"
    scene = load_scene(scene_path)
    route = load_route_experiment(route_path)
    assert scene.name == "Future Intelligent Workspace"
    assert scene.room_size.x == 12.0 and scene.room_size.y == 9.0
    assert len(scene.walls) == 7
    assert len(scene.obstacles) == 5
    assert [(ris.width_m, ris.height_m, ris.nx, ris.ny, ris.phase_bits) for ris in scene.ris_surfaces] == [
        (3.0, 2.0, 64, 48, None),
        (3.0, 2.0, 64, 48, None),
    ]
    assert all(ris.generation == "Future" and ris.enabled for ris in scene.ris_surfaces)
    assert len(route.route.waypoints) == 8
    assert len(route.trajectory) == 27
    assert route.validation_report.collisions == ()
    payload = build_demo(scene_path, route_path)
    assert payload["coefficient_model"]["identity"] == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    targets = payload["representative_targets"]
    assert set(targets) == {"point-2", "point-4", "point-5", "point-8"}
    cases = targets["point-8"]["cases"]
    assert set(cases) == {"no_ris", "single_first_ris", "single_second_ris", "dual_ris"}
    assert cases["no_ris"]["engine"]["commands"] == {}
    assert cases["dual_ris"]["prepared"]["used"] is True
    assert cases["dual_ris"]["prepared"]["direct_engine_delta_abs"] < 1e-12
    field = payload["prepared_dual_ris_field_8x6"]
    assert field["grid"] == [8, 6]
    assert field["model"] == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    assert field["coefficient_bytes"] == 8 * 6 * 64 * 48 * 16 * 2


def test_manifest_is_replayable_and_does_not_touch_original_demo() -> None:
    root = Path(__file__).parents[1]
    output = root / "results" / "demos" / "future_intelligent_workspace_dual_ris_1x1.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scene_file"] == "scenes/future_intelligent_workspace_demo.json"
    assert payload["route_file"] == "scenes/future_intelligent_workspace_route.json"
    original = root / "scenes" / "future_dual_ris_demo.json"
    assert original.exists()
    assert (root / "results" / "demos" / "future_dual_ris_demo_1x1.json").exists()
