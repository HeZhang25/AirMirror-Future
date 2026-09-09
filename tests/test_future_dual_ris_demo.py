from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from airmirror_future import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    SimulationEngine,
    evaluate_dual_ris_command,
)
from airmirror_future.scene.serialization import load_scene
from tools.run_future_dual_ris_demo import build_demo


def test_demo_scene_manifest_replays_all_legal_cases() -> None:
    root = Path(__file__).parents[1]
    scene_path = root / "scenes" / "future_dual_ris_demo.json"
    payload = build_demo(scene_path)
    scene = load_scene(scene_path)
    assert payload["schema"] == "airmirror_future_dual_ris_demo/1"
    assert payload["coefficient_model"]["identity"] == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    assert [row["id"] for row in payload["ris"]] == ["ris-north", "ris-east"]

    engine = SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)
    cases = payload["cases"]
    assert cases["no_ris"]["commands_rad"] == {}
    for result in cases["single_ris"].values():
        commands = result["commands_rad"]
        assert len(commands) == 1
        identifier, values = next(iter(commands.items()))
        assert identifier in {"ris-north", "ris-east"}
        assert len(values) == scene.ris_surfaces[0].cell_count
        replay = evaluate_dual_ris_command(
            scene,
            {identifier: np.asarray(values, dtype=float)},
            engine=engine,
        )
        assert replay.total_channel.real == result["total_channel"]["real"]
        assert replay.total_channel.imag == result["total_channel"]["imag"]

    dual_commands = {
        identifier: np.asarray(values, dtype=float)
        for identifier, values in cases["dual_ris"]["commands_rad"].items()
    }
    assert set(dual_commands) == {"ris-north", "ris-east"}
    replay = evaluate_dual_ris_command(scene, dual_commands, engine=engine)
    assert replay.received_power_dbm == cases["dual_ris"]["received_power_dbm"]


def test_checked_manifest_is_json_and_matches_generated_geometry() -> None:
    root = Path(__file__).parents[1]
    manifest = root / "results" / "demos" / "future_dual_ris_demo_1x1.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["scene_file"] == "scenes/future_dual_ris_demo.json"
    assert payload["target"]["rx_position_m"] == {"x": 8.5, "y": 4.0, "z": 1.2}
    assert payload["cases"]["dual_ris"]["focus_converged"] is True
