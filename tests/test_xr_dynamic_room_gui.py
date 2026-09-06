from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, Qt

from airmirror_future.experiments import xr_dynamic_room_mvp as mvp
from airmirror_future.gui.main_window import MainWindow
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine


@pytest.fixture
def xr_window(qapp):
    window = MainWindow(create_smart_space_scene("Current"))
    yield window
    window._debounce.stop()
    window._xr_playback_timer.stop()
    window.close()
    for worker in window._workers:
        worker.cancel()
    assert QThreadPool.globalInstance().waitForDone(5000)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _enter_xr(window: MainWindow, qtbot) -> None:
    index = window.scenario_combo.findData("xr_dynamic_room_mvp")
    assert index >= 0
    assert "XR Dynamic Room MVP" in window.scenario_combo.itemText(index)
    window.scenario_combo.setCurrentIndex(index)
    qtbot.waitUntil(lambda: window._xr_result is not None, timeout=5000)


def test_xr_entry_uses_real_mvp_result_and_draws_frozen_trajectory(
    xr_window: MainWindow,
    qtbot,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None

    assert result.trajectory == mvp.build_trajectory()
    assert len(result.trajectory) == 11
    assert len(result.samples) == 22
    assert len(xr_window.scene_view._trajectory_markers) == 11
    assert xr_window.scene_view._trajectory_path is not None
    assert xr_window.scene_view._entities_draggable is False
    assert all(
        sample.ris_channel == 0.0j
        for sample in result.samples
        if sample.mode == mvp.NO_RIS_MODE
    )
    assert {
        sample.static_pattern_hash
        for sample in result.samples
        if sample.mode == mvp.STATIC_RIS_MODE
    } == {mvp._pattern_hash(result.static_pattern)}
    assert "Power:" in xr_window.power_metric.text()
    assert "SNR:" in xr_window.snr_metric.text()
    assert "Mode: No RIS" == xr_window.gain_metric.text()


def test_play_pause_reset_and_mode_switch_are_result_only(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_pattern_calls = 0
    real_generate_static_pattern = mvp.generate_static_pattern

    def counted_static_pattern(*args, **kwargs):
        nonlocal static_pattern_calls
        static_pattern_calls += 1
        return real_generate_static_pattern(*args, **kwargs)

    monkeypatch.setattr(mvp, "generate_static_pattern", counted_static_pattern)
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    assert static_pattern_calls == 1
    original_trajectory = result.trajectory
    original_pattern = np.array(result.static_pattern, copy=True)

    def unexpected_channel(*args, **kwargs):
        raise AssertionError("playback must not recompute channel physics")

    def unexpected_field(*args, **kwargs):
        raise AssertionError("XR playback must not compute a field map")

    monkeypatch.setattr(SimulationEngine, "compute_channel", unexpected_channel)
    monkeypatch.setattr(SimulationEngine, "compute_field_map", unexpected_field)

    xr_window._xr_playback_timer.setInterval(10)
    qtbot.mouseClick(xr_window.xr_play_button, Qt.MouseButton.LeftButton)
    assert xr_window._xr_playback_timer.isActive()
    assert xr_window.xr_play_button.isEnabled() is False
    assert xr_window.xr_pause_button.isEnabled() is True
    qtbot.waitUntil(lambda: xr_window._xr_sample_index >= 1, timeout=1000)

    qtbot.mouseClick(xr_window.xr_pause_button, Qt.MouseButton.LeftButton)
    paused_index = xr_window._xr_sample_index
    assert xr_window._xr_playback_timer.isActive() is False
    qtbot.wait(40)
    assert xr_window._xr_sample_index == paused_index

    xr_window.xr_mode_combo.setCurrentText(mvp.STATIC_RIS_MODE)
    xr_window.xr_timeline.setValue(7)
    assert xr_window._xr_sample_index == 7
    selected = next(
        sample
        for sample in result.samples
        if sample.trajectory.sample_index == 7
        and sample.mode == mvp.STATIC_RIS_MODE
    )
    assert xr_window.power_metric.text() == (
        f"Power: {selected.received_power_dbm:.2f} dBm"
    )
    assert xr_window.snr_metric.text() == f"SNR: {selected.snr_db:.2f} dB"
    assert xr_window.gain_metric.text() == "Mode: Static RIS"

    qtbot.mouseClick(xr_window.xr_reset_button, Qt.MouseButton.LeftButton)
    assert xr_window._xr_sample_index == 0
    assert xr_window.xr_timeline.value() == 0
    assert result.trajectory == original_trajectory
    assert np.array_equal(result.static_pattern, original_pattern)
    assert result.static_pattern.flags.writeable is False
    assert static_pattern_calls == 1


def test_scene_view_moves_only_rx_visual_during_playback(
    xr_window: MainWindow,
    qtbot,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    demo_scene_rx = result.scene.receiver().position

    xr_window.xr_timeline.setValue(10)

    rx_item = xr_window.scene_view._entity_items[result.scene.receiver().id]
    expected_point = xr_window.scene_view._point(result.trajectory[10].position)
    assert rx_item.pos() == expected_point
    assert result.scene.receiver().position == demo_scene_rx
    assert result.trajectory == mvp.build_trajectory()


def test_leaving_xr_restores_ordinary_smart_space_state(
    xr_window: MainWindow,
    qtbot,
) -> None:
    ordinary_scene = xr_window.scene_model
    ordinary_patterns = {
        identifier: np.array(pattern, copy=True)
        for identifier, pattern in xr_window.patterns.items()
    }
    ordinary_controls = (
        xr_window.frequency.value(),
        xr_window.bandwidth.value(),
        xr_window.generation_combo.currentText(),
    )
    ordinary_metrics = tuple(
        widget.text()
        for widget in (
            xr_window.power_metric,
            xr_window.snr_metric,
            xr_window.gain_metric,
            xr_window.coverage_metric,
            xr_window.dead_zone_metric,
            xr_window.runtime_metric,
        )
    )
    _enter_xr(xr_window, qtbot)
    xr_window.xr_mode_combo.setCurrentText(mvp.STATIC_RIS_MODE)
    xr_window.xr_timeline.setValue(10)

    xr_window.scenario_combo.setCurrentIndex(
        xr_window.scenario_combo.findData("smart_space")
    )

    assert xr_window._xr_demo_active is False
    assert xr_window._xr_result is None
    assert xr_window.scene_model is ordinary_scene
    assert xr_window.scene_view.model_scene is ordinary_scene
    assert xr_window.scene_view._entities_draggable is True
    assert xr_window.xr_controls.isVisible() is False
    assert xr_window.right_panel.isEnabled() is True
    assert (
        xr_window.frequency.value(),
        xr_window.bandwidth.value(),
        xr_window.generation_combo.currentText(),
    ) == ordinary_controls
    assert all(
        np.array_equal(xr_window.patterns[identifier], pattern)
        for identifier, pattern in ordinary_patterns.items()
    )
    assert tuple(
        widget.text()
        for widget in (
            xr_window.power_metric,
            xr_window.snr_metric,
            xr_window.gain_metric,
            xr_window.coverage_metric,
            xr_window.dead_zone_metric,
            xr_window.runtime_metric,
        )
    ) == ordinary_metrics
