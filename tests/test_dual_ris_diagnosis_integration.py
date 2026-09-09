from __future__ import annotations

import json
from pathlib import Path

from tools.run_dual_ris_diagnosis import build_diagnosis


def test_dual_ris_diagnosis_replays_original_and_complementary_scene(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    scene_output = tmp_path / "future_dual_ris_complementary.json"
    manifest_output = tmp_path / "future_dual_ris_diagnosis.json"
    payload = build_diagnosis(
        root / "scenes" / "future_dual_ris_demo.json",
        scene_output,
        manifest_output,
        (8, 6),
    )

    assert payload["coefficient_model"] == {
        "identity": "control_patch_center_bistatic_coefficients/1",
        "quadrature_identity": "midpoint_1x1_per_control_patch/1",
    }
    assert payload["verification_grid"] == [8, 6]
    original = payload["original_baseline"]
    assert original["dual_command_ids"] == ["ris-east", "ris-north"]
    assert abs(original["dual_minus_north_db"] - 0.6351601072889537) < 1e-12

    targets = payload["targets"]
    north = targets["ris-north_target"]["cases"]
    east = targets["ris-east_target"]["cases"]
    assert (
        north["single_ris"]["ris-north"]["received_power_dbm"]
        > north["single_ris"]["ris-east"]["received_power_dbm"]
    )
    assert (
        east["single_ris"]["ris-east"]["received_power_dbm"]
        > east["single_ris"]["ris-north"]["received_power_dbm"]
    )
    assert scene_output.is_file() and manifest_output.is_file()
    replayed = json.loads(manifest_output.read_text(encoding="utf-8"))
    assert replayed["original_baseline"]["dual_command_ids"] == [
        "ris-east",
        "ris-north",
    ]


def test_checked_diagnosis_assets_do_not_replace_the_original_baseline() -> None:
    root = Path(__file__).parents[1]
    original_scene = root / "scenes" / "future_dual_ris_demo.json"
    original_manifest = root / "results" / "demos" / "future_dual_ris_demo_1x1.json"
    diagnosis_manifest = root / "results" / "demos" / "future_dual_ris_diagnosis.json"
    complementary_scene = root / "scenes" / "future_dual_ris_complementary.json"

    assert original_scene.is_file() and original_manifest.is_file()
    assert diagnosis_manifest.is_file() and complementary_scene.is_file()
    payload = json.loads(diagnosis_manifest.read_text(encoding="utf-8"))
    assert payload["original_baseline"]["scene_file"].endswith(
        "scenes/future_dual_ris_demo.json"
    )
    assert payload["new_scene_file"].endswith(
        "scenes/future_dual_ris_complementary.json"
    )
