from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, Qt
from PySide6.QtWidgets import QMessageBox

from airmirror_future.core.types import FieldMapResult, SimulationConfig
from airmirror_future.experiments import xr_dynamic_room_mvp as mvp
from airmirror_future.gui import main_window as gui_main
from airmirror_future.gui import workers as gui_workers
from airmirror_future.gui.main_window import MainWindow
from airmirror_future.gui.workers import (
    XRAdaptiveFieldResult,
    XRAdaptiveFieldWorker,
    XRDynamicRoomResult,
    XRDynamicRoomWorker,
    build_xr_field_cache_key,
)
from airmirror_future.physics.noise import noise_power_dbm
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


class _ManualSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self._callbacks):
            callback(*args)


class _ManualWorkerSignals:
    def __init__(self) -> None:
        self.finished = _ManualSignal()
        self.failed = _ManualSignal()
        self.terminated = _ManualSignal()


class _ManualAdaptiveFieldWorker:
    started = []

    def __init__(
        self,
        version,
        sample_index,
        _scene,
        _config,
        _commanded,
        _hash,
        key,
    ):
        self.version = version
        self.sample_index = sample_index
        self.expected_key = key
        self.signals = _ManualWorkerSignals()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True


class _ManualPool:
    def start(self, worker) -> None:
        _ManualAdaptiveFieldWorker.started.append(worker)


@pytest.fixture
def xr_field_calls(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def field_map(
        _engine,
        scene,
        config,
        ris_patterns=None,
        model=None,
        cancel_check=None,
    ):
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("cancelled")
        x_m = np.linspace(0.05, scene.room_size.x - 0.05, config.grid_width)
        y_m = np.linspace(0.05, scene.room_size.y - 0.05, config.grid_height)
        x_grid, y_grid = np.meshgrid(x_m, y_m)
        baseline = -92.0 + 0.3 * x_grid - 0.2 * y_grid
        gain = 4.0 + 0.1 * x_grid
        power = baseline + gain
        noise_dbm = noise_power_dbm(
            scene.bandwidth_hz,
            scene.receiver().noise_figure_db,
        )
        calls.append((scene, config, ris_patterns, model, cancel_check))
        return FieldMapResult(
            x_m=x_m,
            y_m=y_m,
            received_power_dbm=power,
            snr_db=power - noise_dbm,
            baseline_power_dbm=baseline,
            ris_gain_db=gain,
            coverage_percent=75.0,
            dead_zone_percent=25.0,
            runtime_s=0.125,
        )

    monkeypatch.setattr(SimulationEngine, "compute_field_map", field_map)
    return calls


@pytest.fixture
def xr_window(qapp, xr_field_calls, xr_adaptive_computation, monkeypatch):
    monkeypatch.setattr(
        gui_workers,
        "compute_adaptive_mvp",
        lambda **_kwargs: xr_adaptive_computation,
    )
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


@pytest.fixture(scope="module")
def xr_adaptive_computation() -> mvp.MVPComputation:
    return mvp.compute_adaptive_mvp()


def _enter_xr(window: MainWindow, qtbot) -> None:
    index = window.scenario_combo.findData("xr_dynamic_room_mvp")
    assert index >= 0
    assert "XR Dynamic Room MVP" in window.scenario_combo.itemText(index)
    window.scenario_combo.setCurrentIndex(index)
    qtbot.waitUntil(lambda: window._xr_static_field is not None, timeout=5000)


def test_xr_trajectory_is_visible_while_field_map_is_pending(
    xr_window: MainWindow,
    qtbot,
) -> None:
    index = xr_window.scenario_combo.findData("xr_dynamic_room_mvp")
    xr_window.scenario_combo.setCurrentIndex(index)

    assert len(xr_window.scene_view._trajectory_markers) == 11
    assert xr_window.scene_view._heatmap_item is None
    assert "Field map calculating" in xr_window.xr_field_status.text()
    assert "Production M8" in xr_window.xr_field_status.text()
    assert "Fast grid 80×60" in xr_window.xr_field_status.text()
    assert xr_window.isEnabled()
    qtbot.waitUntil(lambda: xr_window._xr_static_field is not None, timeout=5000)


def test_xr_entry_uses_real_mvp_result_and_draws_frozen_trajectory(
    xr_window: MainWindow,
    qtbot,
    xr_field_calls,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None

    assert result.trajectory == mvp.build_trajectory()
    assert len(result.trajectory) == 11
    assert len(result.samples) == 33
    assert len(xr_window.scene_view._trajectory_markers) == 11
    assert xr_window.scene_view._trajectory_path is not None
    assert (
        xr_window.scene_view._trajectory_path.zValue()
        > xr_window.scene_view._heatmap_item.zValue()
    )
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
    assert "RIS Gain: N/A · Mode: No RIS" == xr_window.gain_metric.text()
    xr_calls = [
        call for call in xr_field_calls if call[0].name == "XR Dynamic Room MVP"
    ]
    assert len(xr_calls) == 1
    _, config, patterns, model, cancel_check = xr_calls[0]
    assert (config.grid_width, config.grid_height) == (80, 60)
    assert patterns[result.scene.ris_surfaces[0].id] is result.static_pattern
    assert isinstance(model, ControllerModel)
    assert callable(cancel_check)


def test_cached_field_modes_use_baseline_noise_semantics_and_shared_scales(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    static = xr_window._xr_static_field
    no_ris = xr_window._xr_no_ris_field
    result = xr_window._xr_result
    assert static is not None and no_ris is not None and result is not None

    noise_dbm = noise_power_dbm(
        result.scene.bandwidth_hz,
        result.scene.receiver().noise_figure_db,
    )
    assert no_ris.received_power_dbm is static.baseline_power_dbm
    assert np.array_equal(no_ris.snr_db, static.baseline_power_dbm - noise_dbm)

    power_range = xr_window._xr_field_scales["接收功率"]
    assert power_range == xr_window.scene_view.field_value_range(
        static.baseline_power_dbm,
        static.received_power_dbm,
    )
    assert xr_window.scene_view._field_value_range == power_range
    assert "shared No RIS / Static RIS scale" in xr_window.scene_view._field_legend_text

    draws = []
    real_set_field_map = xr_window.scene_view.set_field_map

    def record_field_map(field, quantity, *, value_range=None):
        draws.append((field, quantity, value_range))
        real_set_field_map(field, quantity, value_range=value_range)

    monkeypatch.setattr(xr_window.scene_view, "set_field_map", record_field_map)
    xr_window.xr_mode_combo.setCurrentText(mvp.STATIC_RIS_MODE)
    assert draws[-1][0] is static
    assert draws[-1][1:] == ("接收功率", power_range)
    assert xr_window.scene_view._field_value_range == power_range

    xr_window.xr_quantity_combo.setCurrentText("SNR")
    snr_range = xr_window._xr_field_scales["SNR"]
    assert draws[-1][0] is static
    assert draws[-1][1:] == ("SNR", snr_range)
    assert xr_window.scene_view._field_value_range == snr_range
    xr_window.xr_mode_combo.setCurrentText(mvp.NO_RIS_MODE)
    assert draws[-1][0] is no_ris
    assert draws[-1][1:] == ("SNR", snr_range)
    assert xr_window.scene_view._field_value_range == snr_range

    xr_window.xr_quantity_combo.setCurrentText("RIS 增益")
    assert xr_window.scene_view._heatmap_item.isVisible() is False
    assert "N/A for No RIS" in xr_window.xr_field_status.text()
    xr_window.xr_mode_combo.setCurrentText(mvp.STATIC_RIS_MODE)
    assert xr_window.scene_view._heatmap_item.isVisible() is True
    assert xr_window.scene_view._gain_legend_gmax_db is not None


def test_play_pause_reset_and_mode_switch_are_result_only(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
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
    assert "Mode: Static RIS" in xr_window.gain_metric.text()

    qtbot.mouseClick(xr_window.xr_reset_button, Qt.MouseButton.LeftButton)
    assert xr_window._xr_sample_index == 0
    assert xr_window.xr_timeline.value() == 0
    assert result.trajectory == original_trajectory
    assert np.array_equal(result.static_pattern, original_pattern)
    assert result.static_pattern.flags.writeable is False


def test_field_worker_cancellation_and_stale_version_are_isolated(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    mvp_result = xr_window._xr_result
    static_field = xr_window._xr_static_field
    assert mvp_result is not None and static_field is not None

    worker = XRDynamicRoomWorker(41)
    cancel_checks = []
    finished = []
    failed = []
    monkeypatch.setattr(
        gui_workers,
        "compute_adaptive_mvp",
        lambda **_kwargs: mvp_result,
    )

    def cancel_during_field(
        _engine,
        _scene,
        _config,
        _patterns,
        _model,
        *,
        cancel_check,
    ):
        cancel_checks.append(cancel_check)
        worker.cancel()
        if cancel_check():
            raise SimulationCancelled("cancelled")
        raise AssertionError("cancel_check did not observe worker cancellation")

    monkeypatch.setattr(SimulationEngine, "compute_field_map", cancel_during_field)
    worker.signals.finished.connect(lambda *args: finished.append(args))
    worker.signals.failed.connect(lambda *args: failed.append(args))
    worker.run()
    assert len(cancel_checks) == 1
    assert finished == []
    assert failed == []

    stale_version = xr_window._version
    xr_window.scenario_combo.setCurrentIndex(
        xr_window.scenario_combo.findData("smart_space")
    )
    xr_window._xr_demo_ready(
        stale_version,
        XRDynamicRoomResult(mvp=mvp_result, field_map=static_field),
    )
    assert xr_window._xr_demo_active is False
    assert xr_window._xr_static_field is None
    assert xr_window.scene_view.model_scene is xr_window.scene_model


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


def test_adaptive_field_is_real_on_demand_and_cached_by_exact_command(
    xr_window: MainWindow,
    qtbot,
    xr_field_calls,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    initial_calls = [
        call for call in xr_field_calls if call[0].name == "XR Dynamic Room MVP"
    ]
    assert len(initial_calls) == 1
    assert len(xr_window._xr_field_cache) == 1

    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    assert len(xr_field_calls) == 1
    assert "provisional" in xr_window.pattern_view.metadata.text()
    assert xr_window.scene_view._heatmap_item.isVisible() is True

    target = next(
        sample
        for sample in result.samples
        if sample.mode == mvp.ADAPTIVE_RIS_MODE
        and sample.command_hash != mvp._pattern_hash(result.static_pattern)
    )
    xr_window.xr_timeline.setValue(target.trajectory.sample_index)
    assert xr_window.scene_view._heatmap_item.isVisible() is False
    assert "Adaptive field queued" in xr_window.xr_field_status.text()
    qtbot.waitUntil(lambda: len(xr_field_calls) == 2, timeout=3000)
    qtbot.waitUntil(lambda: xr_window._active_worker is None, timeout=3000)

    _, config, patterns, model, cancel_check = xr_field_calls[-1]
    assert (config.grid_width, config.grid_height) == (80, 60)
    assert isinstance(model, ControllerModel)
    assert callable(cancel_check)
    assert target.commanded_pattern is not None
    assert np.array_equal(
        patterns[result.scene.ris_surfaces[0].id],
        target.commanded_pattern,
    )
    assert len(xr_window._xr_field_cache) == 2
    assert xr_window.scene_view._heatmap_item.isVisible() is True
    assert xr_window.scene_view._field_value_range == xr_window._xr_field_scales[
        "接收功率"
    ]
    assert "Adaptive uses same bounds" in xr_window.scene_view._field_legend_text

    before = len(xr_field_calls)
    xr_window.xr_quantity_combo.setCurrentText("SNR")
    assert xr_window.scene_view._field_value_range == xr_window._xr_field_scales["SNR"]
    xr_window.xr_quantity_combo.setCurrentText("RIS 增益")
    xr_window.xr_mode_combo.setCurrentText(mvp.NO_RIS_MODE)
    assert "N/A for No RIS" in xr_window.xr_field_status.text()
    xr_window.xr_mode_combo.setCurrentText(mvp.STATIC_RIS_MODE)
    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    qtbot.wait(750)
    assert len(xr_field_calls) == before


def test_cached_adaptive_selection_replaces_older_pending_request(
    xr_window: MainWindow,
    qtbot,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    adaptive = [
        sample for sample in result.samples if sample.mode == mvp.ADAPTIVE_RIS_MODE
    ]
    cached = adaptive[0]
    queued = next(sample for sample in adaptive if sample.command_hash != cached.command_hash)

    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    xr_window.xr_timeline.setValue(queued.trajectory.sample_index)
    assert xr_window._xr_field_debounce.isActive()
    assert xr_window._xr_pending_field_request is not None

    xr_window.xr_timeline.setValue(cached.trajectory.sample_index)

    assert xr_window._xr_field_debounce.isActive() is False
    assert xr_window._xr_pending_field_request is None


def test_adaptive_cold_cache_playback_buffers_current_sample(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    _ManualAdaptiveFieldWorker.started = []
    original_pool = xr_window.thread_pool
    xr_window.thread_pool = _ManualPool()
    monkeypatch.setattr(gui_main, "XRAdaptiveFieldWorker", _ManualAdaptiveFieldWorker)
    try:
        xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
        xr_window.xr_timeline.setValue(1)
        xr_window._xr_field_debounce.stop()
        xr_window._play_xr_demo()

        assert xr_window._xr_playback_waiting_for_field is True
        assert xr_window._xr_playback_timer.isActive() is False
        assert len(_ManualAdaptiveFieldWorker.started) == 1
        assert _ManualAdaptiveFieldWorker.started[0].sample_index == 1
        assert any(
            phrase in xr_window.xr_field_status.text().lower()
            for phrase in ("buffering", "calculating")
        )
    finally:
        xr_window._xr_playback_timer.stop()
        xr_window._xr_active_worker = None
        xr_window._active_worker = None
        xr_window.thread_pool = original_pool


def test_adaptive_ready_field_resumes_buffered_playback(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    field = xr_window._xr_static_field
    assert result is not None and field is not None
    sample = next(
        item
        for item in result.samples
        if item.mode == mvp.ADAPTIVE_RIS_MODE
        and item.trajectory.sample_index == 1
    )
    key = xr_window._xr_field_key_for_sample(sample)
    assert key is not None
    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    xr_window.xr_timeline.setValue(1)
    xr_window._xr_playback_timer.start()
    xr_window._xr_playback_timer.stop()
    xr_window._xr_playback_waiting_for_field = True
    xr_window._xr_adaptive_field_ready(
        xr_window._version,
        XRAdaptiveFieldResult(
            sample_index=1,
            command_hash=sample.command_hash,
            key=key,
            field_map=field,
        ),
    )
    assert xr_window._xr_playback_waiting_for_field is False
    assert xr_window._xr_playback_timer.isActive()
    xr_window._pause_xr_demo()


def test_cancelled_xr_worker_stays_active_until_termination_then_runs_latest(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    adaptive = [
        sample for sample in result.samples if sample.mode == mvp.ADAPTIVE_RIS_MODE
    ]
    first, latest = adaptive[1], adaptive[2]
    _ManualAdaptiveFieldWorker.started = []
    original_pool = xr_window.thread_pool
    xr_window.thread_pool = _ManualPool()
    monkeypatch.setattr(gui_main, "XRAdaptiveFieldWorker", _ManualAdaptiveFieldWorker)
    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    xr_window.xr_timeline.setValue(first.trajectory.sample_index)
    xr_window._xr_field_debounce.stop()
    xr_window._start_pending_xr_field()
    old = _ManualAdaptiveFieldWorker.started[-1]
    try:
        xr_window._cancel_active()
        xr_window.xr_timeline.setValue(latest.trajectory.sample_index)
        xr_window._xr_field_debounce.stop()
        xr_window._start_pending_xr_field()

        assert old.cancel_requested is True
        assert xr_window._xr_active_worker is old
        assert len(_ManualAdaptiveFieldWorker.started) == 1
        assert xr_window._xr_pending_field_request is not None
        assert xr_window._xr_pending_field_request[0] == latest.trajectory.sample_index

        old.signals.terminated.emit(old.version, old)
        qtbot.waitUntil(lambda: len(_ManualAdaptiveFieldWorker.started) == 2)
        assert (
            _ManualAdaptiveFieldWorker.started[-1].sample_index
            == latest.trajectory.sample_index
        )
    finally:
        xr_window._xr_active_worker = None
        xr_window._active_worker = None
        xr_window.thread_pool = original_pool


def test_cancel_then_reselect_same_sample_waits_for_old_worker_termination(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    sample = next(
        item
        for item in result.samples
        if item.mode == mvp.ADAPTIVE_RIS_MODE
        and item.command_hash != mvp._pattern_hash(result.static_pattern)
    )
    _ManualAdaptiveFieldWorker.started = []
    original_pool = xr_window.thread_pool
    xr_window.thread_pool = _ManualPool()
    monkeypatch.setattr(gui_main, "XRAdaptiveFieldWorker", _ManualAdaptiveFieldWorker)
    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    xr_window.xr_timeline.setValue(sample.trajectory.sample_index)
    xr_window._xr_field_debounce.stop()
    xr_window._start_pending_xr_field()
    old = _ManualAdaptiveFieldWorker.started[-1]
    try:
        xr_window._cancel_active()
        xr_window._redraw_xr_field()
        xr_window._xr_field_debounce.stop()

        assert old.cancel_requested is True
        assert xr_window._xr_pending_field_request is not None
        assert len(_ManualAdaptiveFieldWorker.started) == 1

        old.signals.terminated.emit(old.version, old)
        qtbot.waitUntil(lambda: len(_ManualAdaptiveFieldWorker.started) == 2)
        assert (
            _ManualAdaptiveFieldWorker.started[-1].sample_index
            == sample.trajectory.sample_index
        )
    finally:
        xr_window._xr_active_worker = None
        xr_window._active_worker = None
        xr_window.thread_pool = original_pool


def test_failed_xr_worker_keeps_pending_until_termination(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    adaptive = [
        sample for sample in result.samples if sample.mode == mvp.ADAPTIVE_RIS_MODE
    ]
    worker = XRAdaptiveFieldWorker(
        xr_window._version,
        adaptive[1].trajectory.sample_index,
        result.scene,
        xr_window._xr_fast_config(),
        adaptive[1].commanded_pattern,
        adaptive[1].command_hash,
        xr_window._xr_field_key_for_sample(adaptive[1]),
    )
    xr_window._xr_active_worker = worker
    xr_window._active_worker = worker
    xr_window._xr_field_inflight_key = worker.expected_key
    latest_key = xr_window._xr_field_key_for_sample(adaptive[2])
    assert latest_key is not None
    xr_window._xr_pending_field_request = (
        adaptive[2].trajectory.sample_index,
        adaptive[2],
        latest_key,
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: None)

    xr_window._worker_failed(xr_window._version, "boom")

    assert xr_window._xr_active_worker is worker
    assert xr_window._xr_pending_field_request is not None
    xr_window._xr_worker_terminated(xr_window._version, worker)
    assert xr_window._xr_active_worker is not worker


def test_closed_window_ignores_old_xr_termination_and_result(
    xr_window: MainWindow,
    qtbot,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    field = xr_window._xr_static_field
    assert result is not None and field is not None
    sample = next(
        item
        for item in result.samples
        if item.mode == mvp.ADAPTIVE_RIS_MODE
        and item.command_hash != mvp._pattern_hash(result.static_pattern)
    )
    key = xr_window._xr_field_key_for_sample(sample)
    assert key is not None
    worker = XRAdaptiveFieldWorker(
        xr_window._version,
        sample.trajectory.sample_index,
        result.scene,
        xr_window._xr_fast_config(),
        sample.commanded_pattern,
        sample.command_hash,
        key,
    )
    xr_window._xr_active_worker = worker
    xr_window._active_worker = worker
    xr_window.close()
    qtbot.wait(10)

    xr_window._xr_adaptive_field_ready(
        xr_window._version,
        XRAdaptiveFieldResult(
            sample_index=sample.trajectory.sample_index,
            command_hash=sample.command_hash,
            key=key,
            field_map=field,
        ),
    )
    xr_window._xr_worker_terminated(xr_window._version, worker)

    assert key not in xr_window._xr_field_cache
    assert xr_window._xr_active_worker is None
    assert xr_window._xr_pending_field_request is None


def test_adaptive_playback_does_not_launch_field_physics_per_frame(
    xr_window: MainWindow,
    qtbot,
    xr_field_calls,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    assert result is not None
    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    xr_window.xr_timeline.setValue(1)

    def unexpected_channel(*_args, **_kwargs):
        raise AssertionError("Adaptive playback must use precomputed link states")

    monkeypatch.setattr(SimulationEngine, "compute_channel", unexpected_channel)
    xr_window._xr_playback_timer.setInterval(10)
    qtbot.mouseClick(xr_window.xr_play_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: len(xr_field_calls) >= 2, timeout=3000)
    xr_window._pause_xr_demo()
    qtbot.waitUntil(lambda: xr_window._active_worker is None, timeout=3000)
    assert xr_window._xr_sample_index >= 1
    assert len(xr_field_calls) >= 2
    latest = next(
        sample
        for sample in result.samples
        if sample.mode == mvp.ADAPTIVE_RIS_MODE
        and sample.trajectory.sample_index == xr_window._xr_sample_index
    )
    assert latest.commanded_pattern is not None
    assert np.array_equal(
        xr_field_calls[-1][2][result.scene.ris_surfaces[0].id],
        latest.commanded_pattern,
    )


def test_adaptive_field_worker_honors_cancel_and_exact_request_identity(
    xr_adaptive_computation: mvp.MVPComputation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = xr_adaptive_computation.scene
    sample = next(
        item
        for item in xr_adaptive_computation.samples
        if item.mode == mvp.ADAPTIVE_RIS_MODE
        and item.command_hash != mvp._pattern_hash(xr_adaptive_computation.static_pattern)
    )
    assert sample.commanded_pattern is not None
    config = SimulationConfig(80, 60, "power")
    key = build_xr_field_cache_key(
        scene,
        SimulationEngine(),
        ControllerModel(),
        config,
        sample.command_hash,
    )
    worker = XRAdaptiveFieldWorker(
        73,
        sample.trajectory.sample_index,
        scene,
        config,
        sample.commanded_pattern,
        sample.command_hash,
        key,
    )
    finished = []
    failed = []

    def cancel_during_field(
        _engine,
        _scene,
        _config,
        _patterns,
        _model,
        *,
        cancel_check,
    ):
        worker.cancel()
        assert cancel_check()
        raise SimulationCancelled("cancelled")

    monkeypatch.setattr(SimulationEngine, "compute_field_map", cancel_during_field)
    worker.signals.finished.connect(lambda *args: finished.append(args))
    worker.signals.failed.connect(lambda *args: failed.append(args))
    worker.run()

    assert finished == []
    assert failed == []


def test_adaptive_field_cache_key_covers_real_scene_command_and_grid_identity(
    xr_adaptive_computation: mvp.MVPComputation,
) -> None:
    scene = xr_adaptive_computation.scene
    engine = SimulationEngine()
    model = ControllerModel()
    command_hash = mvp._pattern_hash(xr_adaptive_computation.static_pattern)
    key = build_xr_field_cache_key(
        scene,
        engine,
        model,
        SimulationConfig(80, 60, "power"),
        command_hash,
    )

    assert key.profile_identity == engine.profile_identity
    assert key.world_model_identity == "controller_nominal/1"
    assert key.command_hash == command_hash
    assert (key.grid_width, key.grid_height) == (80, 60)
    assert key.production_quadrature_order == 8
    assert key != build_xr_field_cache_key(
        scene,
        engine,
        model,
        SimulationConfig(81, 60, "power"),
        command_hash,
    )
    assert key != build_xr_field_cache_key(
        scene,
        engine,
        model,
        SimulationConfig(80, 60, "power"),
        "sha256:" + "0" * 64,
    )


def test_late_adaptive_field_is_cached_but_never_applied_to_wrong_snapshot(
    xr_window: MainWindow,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enter_xr(xr_window, qtbot)
    result = xr_window._xr_result
    field = xr_window._xr_static_field
    assert result is not None and field is not None
    adaptive = [
        sample for sample in result.samples if sample.mode == mvp.ADAPTIVE_RIS_MODE
    ]
    source = adaptive[1]
    current = adaptive[2]
    source_key = xr_window._xr_field_key_for_sample(source)
    assert source_key is not None
    xr_window.xr_mode_combo.setCurrentText(mvp.ADAPTIVE_RIS_MODE)
    xr_window.xr_timeline.setValue(current.trajectory.sample_index)
    xr_window._xr_field_debounce.stop()
    xr_window._xr_pending_field_request = None
    draws = []
    monkeypatch.setattr(
        xr_window.scene_view,
        "set_field_map",
        lambda *args, **kwargs: draws.append((args, kwargs)),
    )

    xr_window._xr_adaptive_field_ready(
        xr_window._version,
        XRAdaptiveFieldResult(
            sample_index=source.trajectory.sample_index,
            command_hash=source.command_hash,
            key=source_key,
            field_map=field,
        ),
    )
    assert source_key in xr_window._xr_field_cache
    assert draws == []

    stale_version = xr_window._version
    xr_window.scenario_combo.setCurrentIndex(
        xr_window.scenario_combo.findData("smart_space")
    )
    assert xr_window._xr_field_cache == {}
    xr_window._xr_adaptive_field_ready(
        stale_version,
        XRAdaptiveFieldResult(
            sample_index=source.trajectory.sample_index,
            command_hash=source.command_hash,
            key=source_key,
            field_map=field,
        ),
    )
    assert xr_window._xr_field_cache == {}
