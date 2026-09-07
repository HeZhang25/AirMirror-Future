from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QThreadPool

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
    SmartSpaceRefreshResult,
    SmartSpaceRefreshWorker,
)
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
    for identifier, position in moves.items():
        item = window.scene_view._entity_items[identifier]
        item.setPos(window.scene_view._point(position))
        label = window.scene_view._entity_labels[identifier]
        expected_offset = (
            QPointF(8, 8) if identifier == "ris-1" else QPointF(10, -18)
        )
        assert label.pos() == item.pos() + expected_offset

    assert active.cancelled is True
    assert calls == {"focus": 0, "channel": 0, "field": 0}
    assert window._version == start_version + len(moves)
    assert window._debounced_action == "smart_space_refresh"
    assert window._debounce.isActive()
    assert window.latest_field is None
    assert window.scene_view._heatmap_item is None
    assert window.scene_view._coverage_item is None
    assert window.pattern_view.isHidden()
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
            (expected.x, expected.y, expected.z)
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
