"""Exercise the integrated preview through the native Windows Qt GUI.

This is a bounded acceptance check: FAST 1x1 coefficients, an 8x6 field,
the versioned intelligent-workspace route, and no Production M8 benchmark.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import time

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsItem

from airmirror_future.experiments.xr_dynamic_room_mvp import (
    ADAPTIVE_RIS_MODE,
    NO_RIS_MODE,
    STATIC_RIS_MODE,
)
from airmirror_future.gui.main_window import MainWindow, configure_application_font
from airmirror_future.scenarios.smart_space import create_smart_space_scene


def _wait(app: QApplication, predicate: object, description: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError(f"timed out waiting for {description}")


def _save_window(window: MainWindow, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(path)):
        raise RuntimeError(f"failed to save GUI screenshot: {path}")


def _drag_ris(window: MainWindow, app: QApplication, ris_id: str) -> tuple[object, object]:
    scene = window._xr_editor_scene
    if scene is None:
        raise RuntimeError("XR editor scene is unavailable")
    before = next(ris.position for ris in scene.ris_surfaces if ris.id == ris_id)
    item = window.scene_view._entity_items[ris_id]
    movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    if not bool(item.flags() & movable):
        raise RuntimeError(f"RIS item is not draggable: {ris_id}")
    start = window.scene_view.mapFromScene(item.sceneBoundingRect().center())
    end = start + QPoint(36, 18)
    viewport = window.scene_view.viewport()
    QTest.mouseMove(viewport, start, 20)
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start, delay=20)
    QTest.mouseMove(viewport, end, 120)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=end, delay=20)
    _wait(
        app,
        lambda: next(ris.position for ris in scene.ris_surfaces if ris.id == ris_id) != before,
        f"native drag commit for {ris_id}",
        timeout_s=5.0,
    )
    after = next(ris.position for ris in scene.ris_surfaces if ris.id == ris_id)
    return before, after


def verify(
    route_path: Path,
    screenshot_path: Path,
    disabled_screenshot_path: Path,
) -> dict[str, object]:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AirMirror Future Local Preview Verification")
    configure_application_font(app)
    if QGuiApplication.platformName().lower() != "windows":
        raise RuntimeError(
            "native preview verification requires the Qt windows platform; "
            f"got {QGuiApplication.platformName()!r}"
        )

    window = MainWindow(create_smart_space_scene("Current"))
    window.resize(1460, 900)
    window.show()
    window.raise_()
    window.activateWindow()
    app.processEvents()
    try:
        route_editor_index = window.scenario_combo.findData("xr_route_editor")
        window.scenario_combo.setCurrentIndex(route_editor_index)
        app.processEvents()
        template_index = window.xr_template_combo.findData(
            "future_intelligent_workspace"
        )
        window.xr_template_combo.setCurrentIndex(template_index)
        window._xr_load_template()
        if (
            window._xr_editor_scene is None
            or window._xr_editor_scene.name != "Future Intelligent Workspace"
        ):
            raise RuntimeError("complex intelligent-workspace template did not load")

        loaded = window.trajectory_backend.load(route_path)
        window._xr_editor_scene = copy.deepcopy(loaded.scene)
        window._xr_trajectory = loaded.draft
        window._xr_selected_waypoint_index = 0
        window._xr_selected_ris_id = loaded.scene.ris_surfaces[0].id
        window._xr_editor_inputs_changed("native preview route loaded")
        app.processEvents()
        route_snapshot = window.trajectory_backend.validate(
            window._xr_editor_scene, window._xr_trajectory
        )
        trajectory = window.trajectory_backend.sample(route_snapshot)
        if len(trajectory) != 27:
            raise RuntimeError(f"expected 27 route samples, got {len(trajectory)}")

        window.xr_future_accuracy_combo.setCurrentIndex(
            window.xr_future_accuracy_combo.findData("preview_m1")
        )
        window.xr_future_grid_combo.setCurrentIndex(0)
        window._run_xr_future_fixed_field()
        _wait(
            app,
            lambda: window._xr_static_field is not None
            and window._xr_result is not None
            and window._xr_active_worker is None,
            "dual-RIS FAST 1x1 8x6 field",
        )

        ris_ids = tuple(ris.id for ris in window._xr_result.scene.ris_surfaces)
        if len(ris_ids) != 2:
            raise RuntimeError(f"expected two RIS surfaces, got {ris_ids}")
        final_index = len(window._xr_result.trajectory) - 1
        final_adaptive = window._xr_sample_lookup[
            (final_index, ADAPTIVE_RIS_MODE)
        ]
        final_patterns = window._xr_full_command_patterns[
            final_adaptive.command_hash
        ]
        if set(final_patterns) != set(ris_ids):
            raise RuntimeError("adaptive result lost the complete RIS-id mapping")
        if np.array_equal(final_patterns[ris_ids[0]], final_patterns[ris_ids[1]]):
            raise RuntimeError("the two independent RIS commands were unexpectedly identical")

        mode_checks: dict[str, dict[str, object]] = {}
        for mode in (NO_RIS_MODE, STATIC_RIS_MODE, ADAPTIVE_RIS_MODE):
            window.xr_mode_combo.setCurrentText(mode)
            window._set_xr_sample(final_index)
            app.processEvents()
            mode_checks[mode] = {
                "heatmap_visible": window.scene_view._heatmap_item is not None,
                "power_text": window.power_metric.text(),
                "snr_text": window.snr_metric.text(),
            }
            if window.scene_view._heatmap_item is None:
                raise RuntimeError(f"{mode} did not publish its current field")

        phase_checks: dict[str, dict[str, object]] = {}
        window.xr_mode_combo.setCurrentText(ADAPTIVE_RIS_MODE)
        window._set_xr_sample(final_index)
        for ris_id in ris_ids:
            index = window.xr_ris_combo.findData(ris_id)
            window.xr_ris_combo.setCurrentIndex(index)
            app.processEvents()
            metadata = window.pattern_view.metadata.text()
            pixmap = window.pattern_view.commanded.pixmap()
            if ris_id not in metadata or pixmap is None or pixmap.isNull():
                raise RuntimeError(f"phase view did not publish {ris_id}")
            phase_checks[ris_id] = {
                "metadata": metadata,
                "pixmap_cache_key": int(pixmap.cacheKey()),
            }
        if len({item["pixmap_cache_key"] for item in phase_checks.values()}) != 2:
            raise RuntimeError("selected RIS phase images were incorrectly reused")

        adaptive_cache_hits = 0
        for sample_index in range(len(window._xr_result.trajectory)):
            sample = window._xr_sample_lookup[(sample_index, ADAPTIVE_RIS_MODE)]
            key = window._xr_field_key_for_sample(sample)
            if key in window._xr_field_cache:
                adaptive_cache_hits += 1
        if adaptive_cache_hits != len(window._xr_result.trajectory):
            raise RuntimeError("not every sampled-time Adaptive field is cached")

        window.xr_ris_combo.setCurrentIndex(window.xr_ris_combo.findData(ris_ids[1]))
        window._set_xr_sample(final_index, update_receiver_position=False)
        app.processEvents()
        _save_window(window, screenshot_path)

        cached_before_drag = len(window._xr_field_cache)
        drag_before, drag_after = _drag_ris(window, app, ris_ids[1])
        if window._xr_result is not None or window._xr_field_cache:
            raise RuntimeError("RIS drag did not invalidate old commands and fields")
        if "no stale field" not in window.xr_field_status.text().lower():
            raise RuntimeError("RIS drag retained a stale field publication")

        window.xr_ris_combo.setCurrentIndex(window.xr_ris_combo.findData(ris_ids[1]))
        window.xr_ris_enabled.setChecked(False)
        window._xr_apply_ris()
        if sum(ris.enabled for ris in window._xr_editor_scene.ris_surfaces) != 1:
            raise RuntimeError("RIS disable did not produce a one-enabled-RIS scene")
        window._run_xr_future_fixed_field()
        _wait(
            app,
            lambda: window._xr_static_field is not None
            and window._xr_result is not None
            and window._xr_active_worker is None,
            "disabled-RIS FAST 1x1 degradation field",
        )
        enabled_ids = tuple(
            ris.id for ris in window._xr_result.scene.ris_surfaces if ris.enabled
        )
        if len(enabled_ids) != 1:
            raise RuntimeError("disabled-RIS calculation did not degrade to one command")
        window.xr_ris_combo.setCurrentIndex(window.xr_ris_combo.findData(ris_ids[1]))
        window.xr_mode_combo.setCurrentText(ADAPTIVE_RIS_MODE)
        window._set_xr_sample(len(window._xr_result.trajectory) - 1)
        app.processEvents()
        if "RIS disabled" not in window.pattern_view.metadata.text():
            raise RuntimeError("disabled RIS phase view did not show the disabled state")
        _save_window(window, disabled_screenshot_path)

        single_cache_count = len(window._xr_field_cache)
        window.xr_future_grid_combo.setCurrentIndex(1)
        app.processEvents()
        # Route/link samples remain reusable; grid-dependent fields, command
        # publication and their cache identity must be invalidated.
        if window._xr_static_field is not None or window._xr_field_cache:
            raise RuntimeError("grid identity change did not invalidate field cache")
        if "invalidated" not in window.xr_field_status.text().lower():
            raise RuntimeError("grid identity change did not publish invalidation")
        window.xr_future_grid_combo.setCurrentIndex(0)

        return {
            "qt_platform": QGuiApplication.platformName(),
            "scene": "Future Intelligent Workspace",
            "route_samples": len(trajectory),
            "model": "control_patch_center_bistatic_coefficients/1",
            "grid": [8, 6],
            "ris_ids": list(ris_ids),
            "mode_checks": mode_checks,
            "phase_checks": phase_checks,
            "adaptive_cache_hits": adaptive_cache_hits,
            "cached_fields_before_drag": cached_before_drag,
            "drag": {
                "ris_id": ris_ids[1],
                "before": [drag_before.x, drag_before.y, drag_before.z],
                "after": [drag_after.x, drag_after.y, drag_after.z],
                "invalidated": True,
            },
            "disabled_degradation": {
                "enabled_ris_ids": list(enabled_ids),
                "disabled_ris_id": ris_ids[1],
                "cached_fields": single_cache_count,
                "disabled_phase_state_visible": True,
            },
            "grid_change_invalidated": True,
            "screenshots": [
                screenshot_path.as_posix(),
                disabled_screenshot_path.as_posix(),
            ],
        }
    finally:
        window.close()
        app.processEvents()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--route",
        type=Path,
        default=Path("scenes/future_intelligent_workspace_route.json"),
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=Path("results/prototypes/local_preview_integrated_dual_ris.png"),
    )
    parser.add_argument(
        "--disabled-screenshot",
        type=Path,
        default=Path("results/prototypes/local_preview_integrated_disabled_ris.png"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/demos/local_preview_gui_verification.json"),
    )
    args = parser.parse_args()
    result = verify(args.route, args.screenshot, args.disabled_screenshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
