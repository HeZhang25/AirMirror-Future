from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool

from airmirror_future.core.types import FieldMapResult, SimulationConfig
from airmirror_future.gui import main_window as gui_main
from airmirror_future.gui.main_window import MainWindow
from airmirror_future.gui.workers import (
    XRFutureFixedFieldRequest,
    XRFuturePreparedFieldWorker,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.scenarios.xr_editor import create_xr_editor_scene


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args: object) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


class _Signals:
    def __init__(self) -> None:
        self.progress = _Signal()
        self.partial = _Signal()
        self.finished = _Signal()
        self.failed = _Signal()
        self.terminated = _Signal()


class _ManualFutureWorker:
    started = []

    def __init__(self, version, request, config) -> None:
        self.version = version
        self.request = request
        self.config = config
        self.signals = _Signals()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True


class _ManualPool:
    def start(self, worker) -> None:
        _ManualFutureWorker.started.append(worker)


def _field(config: SimulationConfig, value: float, runtime_s: float) -> FieldMapResult:
    values = np.full((config.grid_height, config.grid_width), value)
    return FieldMapResult(
        x_m=np.linspace(0.05, 9.95, config.grid_width),
        y_m=np.linspace(0.05, 7.95, config.grid_height),
        received_power_dbm=values,
        snr_db=values + 100.0,
        baseline_power_dbm=values - 3.0,
        ris_gain_db=np.full_like(values, 3.0),
        coverage_percent=75.0,
        dead_zone_percent=25.0,
        runtime_s=runtime_s,
    )


def _run_worker_with_fake_matrix(
    monkeypatch,
    request: XRFutureFixedFieldRequest,
    config: SimulationConfig | None = None,
):
    config = config or SimulationConfig(48, 36, batch_size=8)
    evaluated = []

    class _Prepared:
        coefficient_identities = tuple(
            f"sha256:grid-point-{index}"
            for index in range(config.grid_width * config.grid_height)
        )
        build_runtime_s = 12.5
        coefficient_bytes = (
            config.grid_width
            * config.grid_height
            * 3072
            * np.dtype(complex).itemsize
        )

        def evaluate(self, pattern):
            evaluated.append(np.array(pattern, copy=True))
            return _field(config, -70.0 + len(evaluated), 0.004 + len(evaluated) / 1000)

    monkeypatch.setattr(
        "airmirror_future.gui.workers.prepare_controller_field",
        lambda *args, **kwargs: _Prepared(),
    )
    worker = XRFuturePreparedFieldWorker(17, request, config)
    partial = []
    finished = []
    failed = []
    progress = []
    worker.signals.partial.connect(lambda _version, value: partial.append(value))
    worker.signals.finished.connect(lambda _version, value: finished.append(value))
    worker.signals.failed.connect(lambda _version, value: failed.append(value))
    worker.signals.progress.connect(
        lambda _version, done, total, _fraction: progress.append((done, total))
    )
    worker.run()
    assert not failed, failed[0] if failed else ""
    assert len(partial) == len(finished) == 1
    assert progress == [(0, 3), (1, 3), (2, 3), (3, 3)]
    return finished[0], evaluated


def test_future_template_is_full_future_ris() -> None:
    scene = create_xr_editor_scene("future_smart_space")
    ris = scene.ris_surfaces[0]

    assert scene.name == "XR Future Smart Space Fixed Field"
    assert ris.generation == "Future"
    assert (ris.nx, ris.ny, ris.cell_count) == (64, 48, 3072)


def test_future_worker_reuses_one_exact_matrix_for_two_commands(monkeypatch) -> None:
    scene = create_xr_editor_scene("future_smart_space")
    request = XRFutureFixedFieldRequest(
        scene=scene,
        static_position=scene.receiver().position,
        selected_position=replace(scene.receiver().position, x=7.0, y=5.0),
        selected_point_id="point-4",
        experiment_identity="sha256:experiment",
        scene_identity="sha256:scene",
        trajectory_identity="sha256:trajectory",
    )

    result, evaluated = _run_worker_with_fake_matrix(monkeypatch, request)

    assert len(evaluated) == 2
    assert not np.array_equal(evaluated[0], evaluated[1])
    assert result.mvp.scene.ris_surfaces[0].generation == "Future"
    assert {sample.mode for sample in result.mvp.samples} == {
        "No RIS",
        "Static RIS",
        "Adaptive RIS",
    }
    assert result.static_field.received_power_dbm.shape == (36, 48)
    assert result.adaptive_field.received_power_dbm.shape == (36, 48)
    assert result.static_key.coefficient_identity == result.coefficient_identity
    assert result.adaptive_key.coefficient_identity == result.coefficient_identity
    assert result.static_key.command_hash != result.adaptive_key.command_hash
    assert result.coefficient_bytes == 81 * 1024 * 1024


def test_gui_fixed_field_identity_timing_hot_modes_and_cancel(
    qapp,
    monkeypatch,
) -> None:
    window = MainWindow(create_smart_space_scene("Current"))
    assert QThreadPool.globalInstance().waitForDone(5000)
    window.scenario_combo.setCurrentIndex(
        window.scenario_combo.findData("xr_route_editor")
    )
    window.xr_template_combo.setCurrentIndex(
        window.xr_template_combo.findData("future_smart_space")
    )
    window._xr_load_template()
    window._xr_select_relative_point(-1)
    assert window.xr_future_field_button.isEnabled()
    assert window.xr_future_accuracy_combo.currentData() == "production_m8"
    assert window.xr_future_grid_combo.currentData() == (8, 6)

    window.xr_future_accuracy_combo.setCurrentIndex(
        window.xr_future_accuracy_combo.findData("preview_m1")
    )
    assert not window.xr_future_field_button.isEnabled()
    assert "backend unavailable" in window.xr_future_accuracy_status.text()
    assert window.scene_view._heatmap_item is None
    window.xr_future_accuracy_combo.setCurrentIndex(
        window.xr_future_accuracy_combo.findData("production_m8")
    )
    assert window.xr_future_field_button.isEnabled()

    _ManualFutureWorker.started = []
    window.thread_pool = _ManualPool()
    monkeypatch.setattr(gui_main, "XRFuturePreparedFieldWorker", _ManualFutureWorker)
    window._run_xr_future_fixed_field()
    manual = _ManualFutureWorker.started[-1]
    assert (manual.config.grid_width, manual.config.grid_height) == (8, 6)
    assert manual.request.selected_point_id == "point-4"
    assert window.scene_view._heatmap_item is None
    assert "not a whole-route" in window.xr_sample_label.text()

    result, _ = _run_worker_with_fake_matrix(
        monkeypatch,
        manual.request,
        manual.config,
    )
    manual.signals.partial.emit(manual.version, result.mvp)
    manual.signals.finished.emit(manual.version, result)
    manual.signals.terminated.emit(manual.version, manual)

    assert "cold 12.50 s" in window.xr_field_status.text()
    assert "hot Static 5.00 ms" in window.xr_field_status.text()
    assert "hot Adaptive 6.00 ms" in window.xr_field_status.text()
    assert "playback 2.0 fps" in window.xr_field_status.text()
    assert "coefficients 2.2 MiB" in window.xr_field_status.text()
    assert "not full-route A" in window.xr_route_status.text()
    assert len(window._xr_field_cache) == 2

    window.xr_mode_combo.setCurrentText("Adaptive RIS")
    assert window._xr_pending_field_request is None
    assert "Adaptive field hot-cached" in window.xr_field_status.text()
    assert "Small fixed grid 8×6" in window.xr_field_status.text()

    window._run_xr_future_fixed_field()
    cancelled = _ManualFutureWorker.started[-1]
    stale_result, _ = _run_worker_with_fake_matrix(
        monkeypatch,
        cancelled.request,
        cancelled.config,
    )
    window._cancel_xr_editor_run()
    assert cancelled.cancel_requested
    assert "finishes the in-flight cold build" in window.xr_field_status.text()
    cancelled.signals.finished.emit(cancelled.version, stale_result)
    assert window._xr_static_field is None
    cancelled.signals.terminated.emit(cancelled.version, cancelled)

    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
