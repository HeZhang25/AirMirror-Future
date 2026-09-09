from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool

from airmirror_future import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    PRODUCTION_RIS_COEFFICIENT_MODEL,
)
from airmirror_future.core.types import FieldMapResult, SimulationConfig
from airmirror_future.experiments.xr_dynamic_room_mvp import TrajectorySample
from airmirror_future.gui import main_window as gui_main
from airmirror_future.gui.main_window import MainWindow
from airmirror_future.gui.workers import (
    XRFutureFixedFieldRequest,
    XRFuturePreparedFieldWorker,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.scenarios.xr_editor import create_xr_editor_scene
from airmirror_future.simulation.engine import SimulationCancelled


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
        coefficient_model_identity = request.coefficient_model_identity
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
            return _field(
                config,
                -69.0 if len(evaluated) == 1 else -68.0,
                0.005 if len(evaluated) == 1 else 0.006,
            )

    def _prepare(*args, **kwargs):
        engine = kwargs.get("engine")
        assert engine.coefficient_model.identity == request.coefficient_model_identity
        progress = kwargs.get("progress")
        cancel_check = kwargs.get("cancel_check")
        assert callable(cancel_check)
        assert not cancel_check()
        if progress is not None:
            total = config.grid_width * config.grid_height
            progress(0, total)
            progress(total, total)
        return _Prepared()

    monkeypatch.setattr(
        "airmirror_future.gui.workers.prepare_controller_field",
        _prepare,
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
    assert not partial
    assert len(finished) == 1
    receiver_total = config.grid_width * config.grid_height
    adaptive_count = len(finished[0].adaptive_fields)
    total = receiver_total + 1 + adaptive_count
    assert progress == [
        (0, total),
        (receiver_total, total),
        *((receiver_total + index, total) for index in range(1, adaptive_count + 2)),
    ]
    return finished[0], evaluated


def test_future_template_is_full_future_ris() -> None:
    scene = create_xr_editor_scene("future_smart_space")
    ris = scene.ris_surfaces[0]

    assert scene.name == "XR Future Smart Space Fixed Field"
    assert ris.generation == "Future"
    assert (ris.nx, ris.ny, ris.cell_count) == (64, 48, 3072)


def test_future_worker_reuses_one_explicit_fast_matrix_for_two_commands(monkeypatch) -> None:
    scene = create_xr_editor_scene("future_smart_space")
    request = XRFutureFixedFieldRequest(
        scene=scene,
        static_position=scene.receiver().position,
        selected_position=replace(scene.receiver().position, x=7.0, y=5.0),
        selected_point_id="point-4",
        experiment_identity="sha256:experiment",
        scene_identity="sha256:scene",
        trajectory_identity="sha256:trajectory",
        coefficient_model_identity=FAST_1X1_RIS_COEFFICIENT_MODEL.identity,
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
    assert (
        result.coefficient_model_identity
        == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    )
    assert (
        result.static_key.coefficient_model_identity
        == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    )
    assert result.static_key.production_quadrature_order == 8
    assert result.static_key.quadrature_order_x == 1
    assert result.static_key.quadrature_order_y == 1
    assert result.static_key.command_hash != result.adaptive_key.command_hash
    assert result.coefficient_bytes == 81 * 1024 * 1024
    static_ris_id = result.mvp.scene.ris_surfaces[0].id
    assert not result.static_patterns[static_ris_id].flags.writeable
    with pytest.raises(TypeError):
        result.static_patterns["replacement"] = np.zeros(1)


def test_future_worker_evaluates_and_reports_every_sampled_time(monkeypatch) -> None:
    scene = create_xr_editor_scene("future_smart_space")
    route = tuple(
        TrajectorySample(
            sample_index=index,
            time_s=float(index),
            position=replace(scene.receiver().position, x=6.0 + index, y=3.0 + index),
        )
        for index in range(3)
    )
    request = XRFutureFixedFieldRequest(
        scene=scene,
        static_position=route[0].position,
        selected_position=route[1].position,
        selected_point_id="point-2",
        experiment_identity="sha256:route-experiment",
        scene_identity="sha256:route-scene",
        trajectory_identity="sha256:route-trajectory",
        coefficient_model_identity=FAST_1X1_RIS_COEFFICIENT_MODEL.identity,
        trajectory=route,
    )

    result, evaluated = _run_worker_with_fake_matrix(
        monkeypatch,
        request,
        SimulationConfig(8, 6, batch_size=8),
    )

    adaptive_samples = [
        sample for sample in result.mvp.samples if sample.mode == "Adaptive RIS"
    ]
    assert len(adaptive_samples) == len(route)
    assert len(result.adaptive_fields) == len(route)
    assert len(evaluated) == 1 + len(route)
    cached_hashes = {key.command_hash for key, _field in result.adaptive_fields}
    assert {sample.command_hash for sample in adaptive_samples} == cached_hashes


def test_future_worker_keeps_explicit_production_m8_option(monkeypatch) -> None:
    scene = create_xr_editor_scene("future_smart_space")
    request = XRFutureFixedFieldRequest(
        scene=scene,
        static_position=scene.receiver().position,
        selected_position=replace(scene.receiver().position, x=7.0, y=5.0),
        selected_point_id="point-4",
        experiment_identity="sha256:experiment",
        scene_identity="sha256:scene",
        trajectory_identity="sha256:trajectory",
        coefficient_model_identity=PRODUCTION_RIS_COEFFICIENT_MODEL.identity,
    )

    result, _evaluated = _run_worker_with_fake_matrix(
        monkeypatch,
        request,
        SimulationConfig(8, 6, batch_size=8),
    )

    assert result.coefficient_model_identity == PRODUCTION_RIS_COEFFICIENT_MODEL.identity
    assert result.static_key.coefficient_model_identity == result.coefficient_model_identity
    assert result.static_key.production_quadrature_order == 8
    assert result.static_key.quadrature_order_x == 8
    assert result.static_key.quadrature_order_y == 8
    assert result.quadrature_identity == "midpoint_8x8_per_control_patch/1"


def test_future_worker_cancel_emits_no_partial_or_finished(monkeypatch) -> None:
    scene = create_xr_editor_scene("future_smart_space")
    request = XRFutureFixedFieldRequest(
        scene=scene,
        static_position=scene.receiver().position,
        selected_position=replace(scene.receiver().position, x=7.0, y=5.0),
        selected_point_id="point-4",
        experiment_identity="sha256:experiment",
        scene_identity="sha256:scene",
        trajectory_identity="sha256:trajectory",
        coefficient_model_identity=FAST_1X1_RIS_COEFFICIENT_MODEL.identity,
    )
    config = SimulationConfig(8, 6, batch_size=8)

    def _cancelled_prepare(*_args, **kwargs):
        progress = kwargs["progress"]
        cancel_check = kwargs["cancel_check"]
        progress(0, 48)
        progress(8, 48)
        assert cancel_check()
        raise SimulationCancelled("cancelled by focused GUI regression")

    monkeypatch.setattr(
        "airmirror_future.gui.workers.prepare_controller_field",
        _cancelled_prepare,
    )
    worker = XRFuturePreparedFieldWorker(21, request, config)
    partial = []
    finished = []
    failed = []
    terminated = []
    worker.signals.partial.connect(lambda *_args: partial.append(True))
    worker.signals.finished.connect(lambda *_args: finished.append(True))
    worker.signals.failed.connect(lambda *_args: failed.append(True))
    worker.signals.terminated.connect(lambda *_args: terminated.append(True))

    def _cancel_after_first_batch(
        _version: int,
        done: int,
        _total: int,
        _fraction: float,
    ) -> None:
        if done == 8:
            worker.cancel()

    worker.signals.progress.connect(_cancel_after_first_batch)
    worker.run()

    assert not partial
    assert not finished
    assert not failed
    assert terminated == [True]


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
    assert window.xr_future_accuracy_combo.currentData() == "preview_m1"
    assert window.xr_future_grid_combo.currentData() == (8, 6)
    assert "Fast 1×1 selected" in window.xr_future_accuracy_status.text()
    assert "real prepared field" in window.xr_future_accuracy_status.text()

    window.xr_future_accuracy_combo.setCurrentIndex(
        window.xr_future_accuracy_combo.findData("production_m8")
    )
    assert window.xr_future_field_button.isEnabled()
    assert "Production M8" in window.xr_future_accuracy_status.text()
    assert window.scene_view._heatmap_item is None
    window.xr_future_accuracy_combo.setCurrentIndex(
        window.xr_future_accuracy_combo.findData("preview_m1")
    )
    assert window.xr_future_field_button.isEnabled()

    _ManualFutureWorker.started = []
    window.thread_pool = _ManualPool()
    monkeypatch.setattr(gui_main, "XRFuturePreparedFieldWorker", _ManualFutureWorker)
    window._run_xr_future_fixed_field()
    manual = _ManualFutureWorker.started[-1]
    assert (manual.config.grid_width, manual.config.grid_height) == (8, 6)
    assert manual.request.selected_point_id == "point-4"
    assert (
        manual.request.coefficient_model_identity
        == FAST_1X1_RIS_COEFFICIENT_MODEL.identity
    )
    assert len(manual.request.trajectory) > 1
    assert window.scene_view._heatmap_item is None
    assert "19 sampled-time fields" in window.xr_sample_label.text()

    result, _ = _run_worker_with_fake_matrix(
        monkeypatch,
        manual.request,
        manual.config,
    )
    manual.signals.finished.emit(manual.version, result)
    manual.signals.terminated.emit(manual.version, manual)

    assert window.xr_mode_combo.currentText() == "Adaptive RIS"
    for sample_index in range(len(result.mvp.trajectory)):
        sample = window._xr_sample_lookup[(sample_index, "Adaptive RIS")]
        key = window._xr_field_key_for_sample(sample)
        assert key in window._xr_field_cache
    window._set_xr_sample(len(result.mvp.trajectory) - 1)
    assert "Adaptive field hot-cached" in window.xr_field_status.text()
    assert "cold 12.50 s" in window.xr_field_status.text()
    assert "hot Static 5.00 ms" in window.xr_field_status.text()
    assert "hot Adaptive 6.00 ms" in window.xr_field_status.text()
    assert "playback 2.0 fps" in window.xr_field_status.text()
    assert "coefficients 2.2 MiB" in window.xr_field_status.text()
    assert "Fast 1×1" in window.xr_field_status.text()
    assert "every time is cached" in window.xr_route_status.text()
    assert len(window._xr_field_cache) == len(result.adaptive_fields)

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
    assert "receiver-batch boundary" in window.xr_field_status.text()
    cancelled.signals.finished.emit(cancelled.version, stale_result)
    assert window._xr_static_field is None
    cancelled.signals.terminated.emit(cancelled.version, cancelled)

    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
