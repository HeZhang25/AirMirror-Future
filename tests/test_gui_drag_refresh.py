from __future__ import annotations

from dataclasses import replace
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QThreadPool, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from airmirror_future.core.types import (
    ChannelResult,
    FieldMapResult,
    SimulationConfig,
    Vec3,
)
from airmirror_future.gui import main_window as gui_main
from airmirror_future.gui import workers as gui_workers
from airmirror_future.gui.main_window import MainWindow
from airmirror_future.gui.workers import (
    MapWorker,
    SmartSpaceRefreshResult,
    SmartSpaceRefreshWorker,
)
from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


def _channel(power_dbm: float) -> ChannelResult:
    return ChannelResult(
        total_channel=1.0 + 0.0j,
        los_channel=1.0 + 0.0j,
        wall_channel=0.0j,
        ris_channel=0.0j,
        received_power_w=1.0,
        received_power_dbm=power_dbm,
        noise_power_dbm=-100.0,
        snr_db=power_dbm + 100.0,
        shannon_capacity_bps=1.0,
    )


def _field() -> FieldMapResult:
    values = np.array([[-80.0, -79.0], [-78.0, -77.0]])
    return FieldMapResult(
        x_m=np.array([0.0, 1.0]),
        y_m=np.array([0.0, 1.0]),
        received_power_dbm=values,
        snr_db=values + 100.0,
        baseline_power_dbm=values - 3.0,
        ris_gain_db=np.full_like(values, 3.0),
        coverage_percent=75.0,
        dead_zone_percent=25.0,
        runtime_s=0.25,
    )


def _refresh_result(scene, *, power_dbm: float = -60.0) -> SmartSpaceRefreshResult:
    ris = scene.ris_surfaces[0]
    pattern = np.zeros(ris.cell_count)
    return SmartSpaceRefreshResult(
        scene=scene,
        patterns={ris.id: pattern},
        pattern_source="Coherent Target Focus",
        focused=_channel(power_dbm),
        baseline=_channel(power_dbm - 5.0),
        field_map=_field(),
    )


@pytest.fixture
def light_window(qapp, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        gui_main,
        "generate_coherent_target_pattern",
        lambda scene, model, *, engine, ris=None: np.zeros(
            (scene.ris_surfaces[0] if ris is None else ris).cell_count
        ),
    )
    monkeypatch.setattr(
        SimulationEngine,
        "compute_channel",
        lambda *_args, **_kwargs: _channel(-70.0),
    )
    window = MainWindow(create_smart_space_scene("Current"))
    window._debounce.stop()
    yield window
    window._debounce.stop()
    window.close()
    for worker in window._workers:
        worker.cancel()
    assert QThreadPool.globalInstance().waitForDone(5000)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_drag_burst_updates_all_entities_without_synchronous_physics(
    light_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp,
) -> None:
    window = light_window
    calls = {"focus": 0, "channel": 0, "field": 0}

    def unexpected(name: str):
        def fail(*_args, **_kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} physics ran in the drag callback")

        return fail

    monkeypatch.setattr(
        gui_workers,
        "generate_coherent_target_pattern",
        unexpected("focus"),
    )
    monkeypatch.setattr(SimulationEngine, "compute_channel", unexpected("channel"))
    monkeypatch.setattr(SimulationEngine, "compute_field_map", unexpected("field"))

    class ActiveWorker:
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    active = ActiveWorker()
    window._active_worker = active
    window.latest_field = _field()
    window.scene_view.set_field_map(window.latest_field, "接收功率")
    window.scene_view.set_coverage_map(window.latest_field, 0.0, True)
    assert window.scene_view._heatmap_item is not None
    assert window.scene_view._coverage_item is not None
    start_version = window._version
    tx = window.scene_model.transmitter()
    rx = window.scene_model.receiver()
    ris = window.scene_model.ris_surfaces[0]
    moves = {
        tx.id: Vec3(1.1, 2.1, tx.position.z),
        rx.id: Vec3(8.1, 5.2, rx.position.z),
        ris.id: Vec3(6.0, 4.1, ris.position.z),
    }
    window.show()
    qapp.processEvents()
    for identifier, position in moves.items():
        item = window.scene_view._entity_items[identifier]
        start = window.scene_view.mapFromScene(item.scenePos())
        target = window.scene_view.mapFromScene(window.scene_view._point(position))
        QTest.mousePress(
            window.scene_view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=start,
        )
        QTest.mouseMove(window.scene_view.viewport(), target, delay=1)
        QTest.mouseRelease(
            window.scene_view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=target,
        )
        qapp.processEvents()
        label = window.scene_view._entity_labels[identifier]
        expected_offset = (
            QPointF(8, 8) if identifier == "ris-1" else QPointF(10, -18)
        )
        assert label.pos() == item.pos() + expected_offset

    assert active.cancelled is True
    assert calls == {"focus": 0, "channel": 0, "field": 0}
    assert window._version == start_version + 2 * len(moves)
    assert window._debounced_action == "smart_space_refresh"
    assert window._debounce.isActive()
    assert window.latest_field is None
    assert window.scene_view._heatmap_item is None
    assert window.scene_view._coverage_item is None
    assert window.pattern_view.isHidden() is False
    assert "Pattern 生成中" in window.pattern_view.commanded.text()
    assert "calculating" in window.power_metric.text()
    actual_positions = {
        window.scene_model.transmitter().id: window.scene_model.transmitter().position,
        window.scene_model.receiver().id: window.scene_model.receiver().position,
        window.scene_model.ris_surfaces[0].id: (
            window.scene_model.ris_surfaces[0].position
        ),
    }
    for identifier, expected in moves.items():
        actual = actual_positions[identifier]
        assert (actual.x, actual.y, actual.z) == pytest.approx(
            (expected.x, expected.y, expected.z),
            abs=0.02,
        )


def test_drag_debounce_starts_one_worker_with_latest_deep_copied_snapshot(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    rx = window.scene_model.receiver()
    first = Vec3(rx.position.x - 0.1, rx.position.y, rx.position.z)
    latest = Vec3(rx.position.x - 0.2, rx.position.y + 0.1, rx.position.z)
    window._entity_moved(rx.id, first)
    window._entity_moved(rx.id, latest)
    window._debounce.stop()
    window._run_debounced_action()

    assert len(started) == 1
    worker = started[0]
    assert isinstance(worker, SmartSpaceRefreshWorker)
    assert worker.scene is not window.scene_model
    assert worker.scene.receiver().position == latest
    assert worker.version == window._version


def test_finite_bit_ris_geometry_change_invalidates_old_command(
    light_window: MainWindow,
) -> None:
    window = light_window
    assert window.scene_model.ris_surfaces[0].phase_bits is not None
    assert window._current_patterns() is not None
    ris = window.scene_model.ris_surfaces[0]

    window._entity_moved(
        ris.id,
        replace(ris.position, x=ris.position.x + 0.35),
    )

    window._debounce.stop()
    assert window._current_patterns() is None
    assert "Pattern 生成中" in window.pattern_view.commanded.text()


def test_applied_input_changes_and_explicit_coherent_focus_stay_off_thread(
    light_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = light_window
    calls = {"focus": 0, "channel": 0, "field": 0}

    def unexpected(name: str):
        def fail(*_args, **_kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} physics ran on the GUI thread")

        return fail

    monkeypatch.setattr(
        gui_main,
        "generate_coherent_target_pattern",
        unexpected("focus"),
    )
    monkeypatch.setattr(SimulationEngine, "compute_channel", unexpected("channel"))
    monkeypatch.setattr(SimulationEngine, "compute_field_map", unexpected("field"))

    window.generation_combo.setCurrentText("Advanced")
    assert window.scene_model.ris_surfaces[0].generation == "Advanced"
    assert window._debounced_action == "smart_space_refresh"
    window._debounce.stop()

    window.tx_power.setValue(window.tx_power.value() + 1.0)
    window._apply_parameters()
    assert window._pending is False
    assert window._debounced_action == "smart_space_refresh"
    window._debounce.stop()

    window.algorithm.setCurrentText("Coherent Target Focus")
    window._optimize()
    assert window.patterns == {}
    assert window._debounced_action == "smart_space_refresh"
    assert calls == {"focus": 0, "channel": 0, "field": 0}


def test_smart_refresh_worker_uses_one_snapshot_and_pattern_for_all_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    truth = GroundTruthModel(seed=scene.random_seed)
    pattern = np.zeros(scene.ris_surfaces[0].cell_count)
    focused = _channel(-60.0)
    baseline = _channel(-65.0)
    field = _field()
    observed = {"focus": [], "channels": [], "fields": []}

    def focus(active_scene, model, *, engine, ris):
        observed["focus"].append((active_scene, model, engine, ris))
        return pattern

    def channel(_engine, active_scene, *, ris_patterns, model):
        observed["channels"].append((active_scene, ris_patterns, model))
        return focused if ris_patterns else baseline

    def field_map(
        _engine,
        active_scene,
        config,
        ris_patterns,
        model,
        *,
        cancel_check,
    ):
        observed["fields"].append(
            (active_scene, config, ris_patterns, model, cancel_check)
        )
        return field

    monkeypatch.setattr(gui_workers, "generate_coherent_target_pattern", focus)
    monkeypatch.setattr(SimulationEngine, "compute_channel", channel)
    monkeypatch.setattr(SimulationEngine, "compute_field_map", field_map)
    worker = SmartSpaceRefreshWorker(7, scene, SimulationConfig(80, 60), truth)
    finished = []
    worker.signals.finished.connect(lambda *args: finished.append(args))
    worker.run()

    assert len(finished) == 1
    version, result = finished[0]
    assert version == 7
    assert isinstance(result, SmartSpaceRefreshResult)
    assert result.scene is scene
    assert result.patterns[scene.ris_surfaces[0].id] is pattern
    assert result.focused is focused
    assert result.baseline is baseline
    assert result.field_map is field
    assert len(observed["focus"]) == 1
    assert len(observed["channels"]) == 2
    assert len(observed["fields"]) == 1
    assert all(call[0] is scene for call in observed["channels"])
    assert observed["fields"][0][0] is scene
    assert observed["fields"][0][2][scene.ris_surfaces[0].id] is pattern
    assert observed["channels"][0][1][scene.ris_surfaces[0].id] is pattern
    assert observed["channels"][0][2] is truth
    assert observed["channels"][1][2] is truth
    assert observed["fields"][0][3] is truth
    assert isinstance(observed["focus"][0][1], ControllerModel)
    assert callable(observed["fields"][0][4])


def test_smart_refresh_cancels_focus_before_its_next_channel_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_smart_space_scene("Current")
    worker = SmartSpaceRefreshWorker(
        3,
        scene,
        SimulationConfig(80, 60),
        GroundTruthModel(seed=scene.random_seed),
    )
    channel_calls = 0
    field_calls = 0

    def channel(_engine, *_args, **_kwargs):
        nonlocal channel_calls
        channel_calls += 1
        worker.cancel()
        return _channel(-65.0)

    def field_map(*_args, **_kwargs):
        nonlocal field_calls
        field_calls += 1
        return _field()

    monkeypatch.setattr(SimulationEngine, "compute_channel", channel)
    monkeypatch.setattr(SimulationEngine, "compute_field_map", field_map)
    finished = []
    failed = []
    worker.signals.finished.connect(lambda *args: finished.append(args))
    worker.signals.failed.connect(lambda *args: failed.append(args))
    worker.run()

    assert channel_calls == 1
    assert field_calls == 0
    assert finished == []
    assert failed == []


def test_only_current_smart_refresh_result_is_applied(
    light_window: MainWindow,
) -> None:
    window = light_window
    scene = create_smart_space_scene("Current")
    pattern = np.zeros(scene.ris_surfaces[0].cell_count)
    result = SmartSpaceRefreshResult(
        scene=scene,
        patterns={scene.ris_surfaces[0].id: pattern},
        pattern_source="Coherent Target Focus",
        focused=_channel(-60.0),
        baseline=_channel(-65.0),
        field_map=_field(),
    )
    original_patterns = window.patterns
    current_version = window._version

    window._smart_space_refresh_ready(current_version - 1, result)
    assert window.patterns is original_patterns
    assert window.latest_field is None

    window._smart_space_refresh_ready(current_version, result)
    assert window.patterns is result.patterns
    assert window.latest_field is result.field_map
    assert window.power_metric.text() == "Power: -60.00 dBm"
    assert window.snr_metric.text() == "SNR: 40.00 dB"
    assert window.gain_metric.text() == "RIS Gain: +5.00 dB"
    assert window.scene_view._heatmap_item is not None
    assert window._active_worker is None


def test_cancel_stops_pending_debounce_before_worker_start(
    light_window: MainWindow,
) -> None:
    window = light_window
    rx = window.scene_model.receiver()
    window._entity_moved(
        rx.id,
        Vec3(rx.position.x + 0.1, rx.position.y, rx.position.z),
    )
    assert window._debounce.isActive()

    window._cancel_work()

    assert window._debounce.isActive() is False
    assert window._debounced_action is None
    assert window._smart_space_refresh_pending is False


def test_xr_round_trip_resumes_an_interrupted_smart_refresh(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    rx = window.scene_model.receiver()
    latest = Vec3(rx.position.x + 0.1, rx.position.y, rx.position.z)
    window._entity_moved(rx.id, latest)
    assert window._smart_space_refresh_pending is True

    window._enter_xr_demo()
    assert window._xr_resume_smart_space_refresh is True
    assert window._smart_space_refresh_pending is True
    window._leave_xr_demo()

    assert window._xr_demo_active is False
    assert window.scene_model.receiver().position == latest
    assert window._xr_resume_smart_space_refresh is False
    assert window._smart_space_refresh_pending is True
    assert window._debounced_action == "smart_space_refresh"


def test_generation_change_then_immediate_field_request_uses_new_legal_command(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    window.generation_combo.setCurrentText("Advanced")
    window.start_field_map()

    assert len(started) == 1
    worker = started[0]
    assert isinstance(worker, SmartSpaceRefreshWorker)
    assert worker.scene.ris_surfaces[0].cell_count == 576
    assert worker.patterns is None
    assert not any(isinstance(item, MapWorker) for item in started)

    result = _refresh_result(worker.scene)
    worker.signals.finished.emit(worker.version, result)
    worker.signals.terminated.emit(worker.version, worker)

    ris = window.scene_model.ris_surfaces[0]
    assert ris.nx == ris.ny == 24 and ris.phase_bits == 3
    assert window.patterns[ris.id].size == 576
    assert np.array_equal(
        validate_commanded_pattern(ris, window.patterns[ris.id]),
        window.patterns[ris.id],
    )
    assert "Grid: 24×24" in window.pattern_view.metadata.text()


def test_rapid_generation_changes_apply_only_latest_scene_result(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    window.generation_combo.setCurrentText("Advanced")
    advanced_version = window._version
    advanced_result = _refresh_result(create_smart_space_scene("Advanced"))
    window.generation_combo.setCurrentText("Future")
    future_version = window._version
    future_result = _refresh_result(create_smart_space_scene("Future"))
    window.generation_combo.setCurrentText("Current")
    window._debounce.stop()
    window._run_debounced_action()

    assert len(started) == 1
    current_worker = started[0]
    assert current_worker.scene.ris_surfaces[0].generation == "Current"
    window._smart_space_refresh_ready(advanced_version, advanced_result)
    window._smart_space_refresh_ready(future_version, future_result)
    assert window.scene_model.ris_surfaces[0].generation == "Current"
    assert window.latest_field is None

    current_worker.signals.finished.emit(
        current_worker.version,
        _refresh_result(current_worker.scene),
    )
    assert window.patterns["ris-1"].size == 64
    assert "Grid: 8×8" in window.pattern_view.metadata.text()


def test_apply_grid_and_phase_bits_never_reuses_incompatible_command(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    old_pattern = window.patterns["ris-1"].copy()
    window.thread_pool = Pool()
    window.ris_nx.setValue(12)
    window.ris_ny.setValue(10)
    window.phase_bits.setCurrentIndex(window.phase_bits.findData(3))
    window._apply_parameters()
    window.start_field_map()

    worker = started[-1]
    assert isinstance(worker, SmartSpaceRefreshWorker)
    assert worker.scene.ris_surfaces[0].cell_count == 120
    assert worker.scene.ris_surfaces[0].phase_bits == 3
    assert worker.patterns is None
    assert old_pattern.size == 64


def test_pending_full_refresh_absorbs_manual_field_request(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    rx = window.scene_model.receiver()
    window._entity_moved(
        rx.id,
        Vec3(rx.position.x + 0.25, rx.position.y, rx.position.z),
    )
    window.start_field_map()

    assert len(started) == 1
    assert isinstance(started[0], SmartSpaceRefreshWorker)
    assert not any(isinstance(item, MapWorker) for item in started)
    assert started[0].patterns is None


def test_refresh_failure_cancel_retry_preserves_pattern_visibility_preference(
    light_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    monkeypatch.setattr(QMessageBox, "critical", lambda *_args: None)
    window.thread_pool = Pool()
    window.generation_combo.setCurrentText("Advanced")
    window.start_field_map()
    failed = started[-1]
    window._worker_failed(failed.version, "boom")

    assert window.show_pattern.isChecked() is True
    assert window.pattern_view.isHidden() is False
    assert "失败" in window.pattern_view.commanded.text()

    window.start_field_map()
    assert failed.cancel_requested is True
    assert len(started) == 1
    failed.signals.terminated.emit(failed.version, failed)
    assert len(started) == 2
    retry = started[-1]
    assert isinstance(retry, SmartSpaceRefreshWorker)

    window._cancel_work()
    assert retry.cancel_requested is True
    assert window.pattern_view.isHidden() is False
    assert "取消" in window.pattern_view.commanded.text()

    window.show_pattern.setChecked(False)
    window.start_field_map()
    retry.signals.terminated.emit(retry.version, retry)
    assert window.pattern_view.isHidden() is True


def test_old_worker_callbacks_cannot_overwrite_new_generation(
    light_window: MainWindow,
) -> None:
    window = light_window
    old_version = window._version
    old_result = _refresh_result(create_smart_space_scene("Current"), power_dbm=-20.0)
    window.generation_combo.setCurrentText("Advanced")
    pending_text = window.pattern_view.metadata.text()

    window._smart_space_refresh_ready(old_version, old_result)
    window._field_ready(old_version, _field())

    assert window.scene_model.ris_surfaces[0].generation == "Advanced"
    assert window.latest_field is None
    assert window.pattern_view.metadata.text() == pending_text
    assert window.patterns.get("ris-1", np.empty(0)).size != 576


def test_scene_change_that_preserves_command_semantics_reuses_legal_pattern(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    original = window.patterns["ris-1"].copy()
    window.thread_pool = Pool()
    window.tx_power.setValue(window.tx_power.value() + 3.0)
    window.bandwidth.setValue(window.bandwidth.value() + 5.0)
    window._apply_parameters()
    window.start_field_map()

    worker = started[-1]
    assert isinstance(worker, SmartSpaceRefreshWorker)
    assert worker.patterns is not None
    assert np.array_equal(worker.patterns["ris-1"], original)
    assert window.pattern_view.isHidden() is False
    assert "仍与已应用 Scene 兼容" in window.pattern_view.metadata.text()


def test_apply_efficiency_invalidates_finite_bit_coherent_command(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    old_pattern = window.patterns["ris-1"].copy()
    window.efficiency.setValue(window.efficiency.value() + 0.05)
    window._apply_parameters()
    window.start_field_map()

    worker = started[-1]
    assert isinstance(worker, SmartSpaceRefreshWorker)
    assert worker.patterns is None
    assert old_pattern.size == 64
    assert window._current_patterns() is None


def test_apply_link_metric_changes_reuses_finite_bit_coherent_command(
    light_window: MainWindow,
) -> None:
    window = light_window
    started = []

    class Pool:
        def start(self, worker) -> None:
            started.append(worker)

    window.thread_pool = Pool()
    original = window.patterns["ris-1"].copy()
    window.bandwidth.setValue(window.bandwidth.value() + 5.0)
    window.noise_figure.setValue(window.noise_figure.value() + 1.0)
    window._apply_parameters()
    window.start_field_map()

    worker = started[-1]
    assert isinstance(worker, SmartSpaceRefreshWorker)
    assert worker.patterns is not None
    assert np.array_equal(worker.patterns["ris-1"], original)
    assert window._current_patterns() is not None
