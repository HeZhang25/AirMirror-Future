from __future__ import annotations

import copy
from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QThreadPool

from airmirror_future.core.types import FieldMapResult, SimulationConfig, Vec3
from airmirror_future.experiments.xr_dynamic_room_mvp import (
    ADAPTIVE_RIS_MODE,
    NO_RIS_MODE,
    STATIC_RIS_MODE,
    TrajectorySample,
)
from airmirror_future.gui import main_window as gui_main
from airmirror_future.gui.main_window import MainWindow
from airmirror_future.gui.workers import XRDynamicRoomWorker
from airmirror_future.gui.xr_trajectory_seam import (
    EXPECTED_TRAJECTORY_INTERFACE_VERSION,
    LoadedRoute,
    RouteDraft,
    RoutePointDraft,
    XRRouteTrajectoryBackend,
)
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.scenarios.xr_editor import create_xr_editor_scene
from airmirror_future.simulation.engine import SimulationEngine


class _FakeTrajectoryBackend:
    """Test-only substitute; production GUI intentionally ships no B backend."""

    interface_version = "fake_trajectory/1"

    def __init__(self) -> None:
        self.validated: list[tuple[object, RouteDraft]] = []
        self.saved: list[tuple[object, Path]] = []
        self.loaded: LoadedRoute | Exception | None = None
        self.retimed: list[tuple[int, float]] = []

    def validate(self, scene, draft: RouteDraft) -> object:
        if len(draft.points) < 2:
            raise ValueError("requires two points")
        if draft.points[0].time_s != 0.0:
            raise ValueError("first time must be zero")
        if any(
            right.time_s <= left.time_s
            for left, right in zip(draft.points, draft.points[1:])
        ):
            raise ValueError("times must be increasing")
        room = scene.room_size
        if any(
            not (
                0.0 <= point.position.x <= room.x
                and 0.0 <= point.position.y <= room.y
                and 0.0 <= point.position.z <= room.z
            )
            for point in draft.points
        ):
            raise ValueError("point outside room")
        snapshot = SimpleNamespace(
            scene=copy.deepcopy(scene),
            draft=copy.deepcopy(draft),
            experiment_identity="fake:experiment",
        )
        self.validated.append((scene, draft))
        return snapshot

    def sample(self, snapshot: object) -> tuple[TrajectorySample, ...]:
        draft = snapshot.draft
        return tuple(
            TrajectorySample(index, point.time_s, point.position)
            for index, point in enumerate(draft.points)
        )

    def save(self, snapshot: object, path: str | Path) -> object:
        self.saved.append((snapshot, Path(path)))
        return snapshot

    def load(self, path: str | Path) -> LoadedRoute:
        if isinstance(self.loaded, Exception):
            raise self.loaded
        if self.loaded is None:
            raise ValueError("no fake route configured")
        return self.loaded

    def retime_from_previous_speed(
        self,
        draft: RouteDraft,
        index: int,
        speed_m_s: float,
    ) -> RouteDraft:
        previous = draft.points[index - 1]
        current = draft.points[index]
        new_time = previous.time_s + previous.position.distance_to(current.position) / speed_m_s
        shift = new_time - current.time_s
        points = tuple(
            point if point_index < index else replace(point, time_s=point.time_s + shift)
            for point_index, point in enumerate(draft.points)
        )
        self.retimed.append((index, speed_m_s))
        return replace(draft, points=points)


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


class _WorkerSignals:
    def __init__(self) -> None:
        self.progress = _Signal()
        self.partial = _Signal()
        self.finished = _Signal()
        self.failed = _Signal()
        self.terminated = _Signal()


class _ManualXRWorker:
    def __init__(self, version, route_experiment=None) -> None:
        self.version = version
        self.route_experiment = route_experiment
        self.signals = _WorkerSignals()
        self.cancel_requested = False

    def cancel(self) -> None:
        self.cancel_requested = True


class _ManualPool:
    def __init__(self) -> None:
        self.started: list[_ManualXRWorker] = []

    def start(self, worker) -> None:
        self.started.append(worker)


@pytest.fixture
def windows(qapp):
    created: list[MainWindow] = []

    def factory(backend=None) -> MainWindow:
        window = MainWindow(
            create_smart_space_scene("Current"),
            trajectory_backend=backend,
        )
        created.append(window)
        index = window.scenario_combo.findData("xr_route_editor")
        window.scenario_combo.setCurrentIndex(index)
        assert window._xr_editor_active
        return window

    yield factory
    for window in created:
        window._debounce.stop()
        window._xr_playback_timer.stop()
        window._xr_field_debounce.stop()
        window.close()
        for worker in window._workers:
            worker.cancel()
    assert QThreadPool.globalInstance().waitForDone(5000)
    for window in created:
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _field(scene, config: SimulationConfig | None = None) -> FieldMapResult:
    width = 2 if config is None else config.grid_width
    height = 2 if config is None else config.grid_height
    values = np.full((height, width), -80.0)
    return FieldMapResult(
        x_m=np.linspace(0.0, scene.room_size.x, width),
        y_m=np.linspace(0.0, scene.room_size.y, height),
        received_power_dbm=values,
        snr_db=values + 90.0,
        baseline_power_dbm=values - 3.0,
        ris_gain_db=np.full_like(values, 3.0),
        coverage_percent=75.0,
        dead_zone_percent=25.0,
        runtime_s=0.01,
    )


def test_editor_loads_complex_scene_with_real_b_backend_ready(windows) -> None:
    window = windows()

    assert window._xr_editor_scene is not None
    assert window._xr_editor_scene.name == "XR Complex Office"
    assert len(window._xr_editor_scene.walls) == 8
    assert len(window._xr_editor_scene.obstacles) == 3
    assert len(window.scene_view._route_point_items) == 4
    assert window.xr_run_button.isEnabled()
    assert window.xr_save_route_button.isEnabled()
    assert window.xr_load_route_button.isEnabled()
    assert EXPECTED_TRAJECTORY_INTERFACE_VERSION in window.xr_route_status.text()
    assert "Route valid" in window.xr_route_status.text()
    assert window.scene_view._heatmap_item is None

    window.xr_template_combo.setCurrentIndex(
        window.xr_template_combo.findData("smart_space")
    )
    window._xr_load_template()
    assert window._xr_editor_scene.name == "XR Smart Space Route Editor"
    assert len(window.scene_view._route_point_items) == 4


def test_editor_loads_an_external_scene_v1(
    windows,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = windows()
    scene_path = tmp_path / "scene.json"
    scene = create_smart_space_scene("Advanced")
    scene.name = "Imported Scene v1"
    scene.save(scene_path)
    monkeypatch.setattr(
        gui_main.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(scene_path), "JSON (*.json)"),
    )

    window._xr_load_scene()

    assert window._xr_editor_scene.name == "Imported Scene v1"
    assert window.scene_view.model_scene is window._xr_editor_scene
    assert len(window.scene_view._route_point_items) == 4
    assert window.scene_view._heatmap_item is None


def test_route_editing_supports_select_drag_add_insert_delete_and_form(windows) -> None:
    backend = _FakeTrajectoryBackend()
    window = windows(backend)
    assert window._xr_trajectory is not None

    original_count = len(window._xr_trajectory.points)
    window._xr_select_relative_point(1)
    assert window._xr_selected_waypoint_index == 1
    window._xr_insert_route_point()
    assert len(window._xr_trajectory.points) == original_count + 1
    window._xr_add_route_point()
    assert len(window._xr_trajectory.points) == original_count + 2
    window._xr_delete_route_point()
    assert len(window._xr_trajectory.points) == original_count + 1

    window._xr_route_point_selected(1)
    path_before = window.scene_view._trajectory_path.path()
    item = window.scene_view._route_point_items[1]
    item.setPos(item.pos() + QPointF(14.0, -7.0))
    assert window.scene_view._trajectory_path.path() != path_before
    dragged = window._xr_trajectory.points[1]

    window.xr_point_x.setValue(dragged.position.x + 0.1)
    window.xr_point_time.setValue(dragged.time_s + 0.2)
    window._xr_apply_route_point()
    assert window._xr_trajectory.points[1].position.x == pytest.approx(
        dragged.position.x + 0.1
    )
    assert window._xr_trajectory.points[1].time_s == pytest.approx(
        dragged.time_s + 0.2
    )

    window.xr_timing_mode.setCurrentIndex(
        window.xr_timing_mode.findData("speed")
    )
    window.xr_point_speed.setValue(1.5)
    window._xr_apply_route_point()
    assert backend.retimed[-1] == (1, 1.5)
    assert window.xr_run_button.isEnabled()


def test_route_drag_through_wall_keeps_invalid_draft_and_recovers(
    windows,
    qapp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = windows(XRRouteTrajectoryBackend())
    assert window._xr_trajectory is not None
    window._xr_result = object()
    old_snapshot_draft = copy.deepcopy(window._xr_trajectory)
    item = window.scene_view._route_point_items[1]

    item.setSelected(True)
    item.setPos(window.scene_view._point(Vec3(4.48, 7.5, 1.2)))
    qapp.processEvents()

    assert item is window.scene_view._route_point_items[1]
    assert window._xr_trajectory.points[1].position == Vec3(4.48, 7.5, 1.2)
    assert "Route invalid" in window.xr_route_status.text()
    assert "meeting-divider" in window.xr_route_status.text()
    assert not window.xr_run_button.isEnabled()
    assert not window.scene_view._editable_route_valid
    assert window._xr_result is None
    assert old_snapshot_draft.points[1].position == Vec3(4.48, 5.0, 1.2)

    errors: list[str] = []
    monkeypatch.setattr(
        gui_main.QMessageBox,
        "critical",
        lambda _parent, _title, message: errors.append(message),
    )
    window._run_xr_editor()
    assert "meeting-divider" in errors[-1]
    assert not window._xr_demo_start_pending

    item.setPos(window.scene_view._point(Vec3(4.48, 5.0, 1.2)))
    qapp.processEvents()

    assert item is window.scene_view._route_point_items[1]
    assert window._xr_trajectory.points[1].position == Vec3(4.48, 5.0, 1.2)
    assert "Route valid" in window.xr_route_status.text()
    assert window.xr_run_button.isEnabled()
    assert window.scene_view._editable_route_valid


def test_continuous_route_drag_coalesces_and_clamps_with_form_sync(
    windows,
    qapp,
) -> None:
    backend = _FakeTrajectoryBackend()
    window = windows(backend)
    item = window.scene_view._route_point_items[2]
    original_item_ids = tuple(map(id, window.scene_view._route_point_items))
    validation_count = len(backend.validated)

    item.setSelected(True)
    item.setPos(QPointF(-100.0, 10_000.0))
    item.setPos(QPointF(-50.0, 9_000.0))
    assert len(backend.validated) == validation_count
    qapp.processEvents()

    assert tuple(map(id, window.scene_view._route_point_items)) == original_item_ids
    assert window._xr_selected_waypoint_index == 2
    assert window._xr_trajectory.points[2].position.x == 0.0
    assert window._xr_trajectory.points[2].position.y == 0.0
    assert item.pos() == window.scene_view._point(Vec3(0.0, 0.0, 1.2))
    assert window.xr_point_x.value() == 0.0
    assert window.xr_point_y.value() == 0.0
    assert len(backend.validated) == validation_count + 1


def test_pending_drag_is_isolated_from_route_rebuild_and_editor_exit(
    windows,
    qapp,
) -> None:
    backend = _FakeTrajectoryBackend()
    window = windows(backend)
    old_draft = window._xr_trajectory
    old_item = window.scene_view._route_point_items[1]

    old_item.setPos(old_item.pos() + QPointF(20.0, 0.0))
    window.xr_template_combo.setCurrentIndex(
        window.xr_template_combo.findData("smart_space")
    )
    window._xr_load_template()
    template_draft = window._xr_trajectory
    qapp.processEvents()

    assert template_draft is window._xr_trajectory
    assert window._xr_trajectory is not old_draft
    assert old_item not in window.scene_view._route_point_items

    current_item = window.scene_view._route_point_items[1]
    current_item.setPos(current_item.pos() + QPointF(20.0, 0.0))
    window.scenario_combo.setCurrentIndex(
        window.scenario_combo.findData("smart_space")
    )
    qapp.processEvents()

    assert not window._xr_editor_active
    assert window.scene_view._route_point_items == []


def test_route_save_load_and_invalid_form_delegate_to_backend(
    windows,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = _FakeTrajectoryBackend()
    window = windows(backend)
    assert window._xr_trajectory is not None
    saved_draft = window._xr_trajectory
    save_path = tmp_path / "route.json"
    monkeypatch.setattr(
        gui_main.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(save_path), "JSON (*.json)"),
    )
    window._xr_save_route()
    assert backend.saved[-1][1] == save_path

    loaded_draft = replace(
        saved_draft,
        name="loaded route",
        points=tuple(reversed(saved_draft.points)),
    )
    loaded_draft = replace(
        loaded_draft,
        points=tuple(
            replace(point, time_s=float(index))
            for index, point in enumerate(loaded_draft.points)
        ),
    )
    assert window._xr_editor_scene is not None
    backend.loaded = LoadedRoute(window._xr_editor_scene, loaded_draft, object())
    monkeypatch.setattr(
        gui_main.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(save_path), "JSON (*.json)"),
    )
    window._xr_load_route()
    assert window._xr_trajectory.name == "loaded route"

    errors: list[str] = []
    monkeypatch.setattr(
        gui_main.QMessageBox,
        "critical",
        lambda _parent, _title, message: errors.append(message),
    )
    window._xr_route_point_selected(1)
    before = window._xr_trajectory
    window.xr_timing_mode.setCurrentIndex(
        window.xr_timing_mode.findData("time")
    )
    window.xr_point_time.setValue(0.0)
    window._xr_apply_route_point()
    assert window._xr_trajectory is before
    assert "times must be increasing" in errors[-1]

    backend.loaded = ValueError("invalid trajectory payload")
    window._xr_load_route()
    assert window._xr_trajectory is before
    assert errors[-1] == "invalid trajectory payload"


def test_edit_invalidates_all_old_results_and_preserves_pattern_visibility(windows) -> None:
    backend = _FakeTrajectoryBackend()
    window = windows(backend)
    scene = window._xr_editor_scene
    assert scene is not None
    window._xr_result = object()
    window._xr_static_field = _field(scene)
    window._xr_no_ris_field = _field(scene)
    window._xr_field_cache = {object(): window._xr_static_field}
    window.scene_view.set_field_map(window._xr_static_field, "接收功率")
    window.show_pattern.setChecked(False)
    window._xr_playback_waiting_for_field = True
    window._xr_playback_timer.start()
    old_version = window._version

    window._xr_add_route_point()

    assert window._version > old_version
    assert window._xr_result is None
    assert not window._xr_playback_timer.isActive()
    assert window._xr_playback_waiting_for_field is False
    assert window._xr_static_field is None
    assert window._xr_no_ris_field is None
    assert not window._xr_field_cache
    assert window.scene_view._heatmap_item is None
    assert "pending" in window.xr_command_status.text().lower()
    assert "no stale field" in window.xr_field_status.text()
    assert not window.pattern_view.isVisible()


def test_latest_run_uses_copied_scene_and_waits_for_actual_termination(
    windows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeTrajectoryBackend()
    window = windows(backend)
    pool = _ManualPool()
    window.thread_pool = pool
    monkeypatch.setattr(gui_main, "XRDynamicRoomWorker", _ManualXRWorker)

    window._run_xr_editor()
    first = pool.started[-1]
    first_scene = first.route_experiment.scene
    first_draft = first.route_experiment.draft
    assert first_scene is not window._xr_editor_scene
    first_scene_name = first_scene.name

    window._xr_route_point_moved(1, Vec3(3.0, 3.0, 1.2))
    assert first.cancel_requested
    window._run_xr_editor()
    assert window._xr_demo_start_pending
    assert len(pool.started) == 1

    first.signals.terminated.emit(first.version, first)
    assert len(pool.started) == 2
    second = pool.started[-1]
    assert second is window._xr_active_worker
    second_scene = second.route_experiment.scene
    second_draft = second.route_experiment.draft
    assert second_scene.name == first_scene_name
    assert second_draft != first_draft

    window._xr_playback_waiting_for_field = True
    window._xr_playback_timer.start()
    window._cancel_xr_editor_run()
    assert not window._xr_playback_timer.isActive()
    assert window._xr_playback_waiting_for_field is False
    assert "waiting for worker termination" in window.xr_sample_label.text()
    assert "not terminated" in window.statusBar().currentMessage()
    second.signals.terminated.emit(second.version, second)
    assert "worker terminated" in window.xr_sample_label.text()


def test_custom_worker_runs_real_three_mode_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = create_xr_editor_scene("smart_space")
    draft = RouteDraft(
        "worker-route",
        (
            RoutePointDraft("point-1", Vec3(2.0, 1.0, 1.2), 0.0),
            RoutePointDraft("point-2", Vec3(2.6, 1.0, 1.2), 1.0),
        ),
        1.0,
    )
    experiment = XRRouteTrajectoryBackend().validate(scene, draft)
    trajectory = experiment.trajectory
    monkeypatch.setattr(
        SimulationEngine,
        "compute_field_map",
        lambda _self, active_scene, config, *_args, **_kwargs: _field(
            active_scene,
            config,
        ),
    )
    partial = []
    finished = []
    terminated = []
    worker = XRDynamicRoomWorker(7, route_experiment=experiment)
    worker.signals.partial.connect(lambda version, result: partial.append((version, result)))
    worker.signals.finished.connect(lambda version, result: finished.append((version, result)))
    worker.signals.terminated.connect(lambda version, value: terminated.append((version, value)))

    worker.run()

    assert len(partial) == len(finished) == len(terminated) == 1
    computation = partial[0][1]
    assert computation.trajectory == trajectory
    assert len(computation.samples) == 6
    lookup = {
        (sample.trajectory.sample_index, sample.mode): sample
        for sample in computation.samples
    }
    static_zero = lookup[(0, STATIC_RIS_MODE)]
    adaptive_zero = lookup[(0, ADAPTIVE_RIS_MODE)]
    assert lookup[(0, NO_RIS_MODE)].commanded_pattern is None
    assert static_zero.command_hash == adaptive_zero.command_hash
    assert static_zero.received_power_dbm == adaptive_zero.received_power_dbm
    assert np.array_equal(
        static_zero.commanded_pattern,
        adaptive_zero.commanded_pattern,
    )
    static_hashes = {
        lookup[(index, STATIC_RIS_MODE)].command_hash for index in (0, 1)
    }
    assert len(static_hashes) == 1
    assert not computation.static_pattern.flags.writeable


def test_real_backend_save_load_round_trip_preserves_all_identities(
    tmp_path: Path,
) -> None:
    backend = XRRouteTrajectoryBackend()
    scene = create_xr_editor_scene("smart_space")
    draft = RouteDraft(
        "gui-round-trip",
        (
            RoutePointDraft("point-1", Vec3(1.5, 1.0, 1.2), 0.0),
            RoutePointDraft("point-2", Vec3(3.5, 1.0, 1.2), 2.0),
        ),
        0.5,
    )
    snapshot = backend.validate(scene, draft)
    route_path = tmp_path / "route.json"

    bound = backend.save(snapshot, route_path)
    loaded = backend.load(route_path)

    assert route_path.is_file()
    assert (tmp_path / "route.scene.json").is_file()
    assert loaded.draft == draft
    assert loaded.scene == bound.scene
    assert loaded.snapshot.scene_identity == snapshot.scene_identity
    assert loaded.snapshot.trajectory_identity == snapshot.trajectory_identity
    assert loaded.snapshot.experiment_identity == snapshot.experiment_identity
    assert loaded.snapshot.trajectory == snapshot.trajectory
    with pytest.raises(FileExistsError):
        backend.save(snapshot, route_path)


def test_real_backend_retimes_speed_and_supports_single_point_and_dwell() -> None:
    backend = XRRouteTrajectoryBackend()
    scene = create_xr_editor_scene("smart_space")
    draft = RouteDraft(
        "speed-route",
        (
            RoutePointDraft("point-1", Vec3(1.0, 1.0, 1.2), 0.0),
            RoutePointDraft("point-2", Vec3(3.0, 1.0, 1.2), 3.0),
            RoutePointDraft("point-3", Vec3(4.0, 1.0, 1.2), 5.0),
        ),
        0.5,
    )

    retimed = backend.retime_from_previous_speed(draft, 1, 2.0)
    assert tuple(point.time_s for point in retimed.points) == (0.0, 1.0, 3.0)
    backend.validate(scene, retimed)

    single = replace(draft, points=(draft.points[0],))
    assert backend.sample(backend.validate(scene, single)) == (
        TrajectorySample(0, 0.0, draft.points[0].position),
    )

    dwell = replace(
        draft,
        points=(
            draft.points[0],
            replace(draft.points[1], position=draft.points[0].position, time_s=1.0),
            replace(draft.points[2], time_s=3.0),
        ),
    )
    backend.validate(scene, dwell)
    with pytest.raises(ValueError, match="zero-length dwell"):
        backend.retime_from_previous_speed(dwell, 1, 1.0)


def test_real_bundle_load_to_worker_end_to_end_preserves_snapshot(
    tmp_path: Path,
) -> None:
    backend = XRRouteTrajectoryBackend()
    scene = create_xr_editor_scene("smart_space")
    draft = RouteDraft(
        "gui-real-e2e",
        (RoutePointDraft("point-1", Vec3(2.0, 1.0, 1.2), 0.0),),
        0.5,
    )
    created = backend.validate(scene, draft)
    backend.save(created, tmp_path / "route.json")
    loaded = backend.load(tmp_path / "route.json")
    partial = []
    finished = []
    worker = XRDynamicRoomWorker(11, route_experiment=loaded.snapshot)
    worker.signals.partial.connect(lambda _version, result: partial.append(result))
    worker.signals.finished.connect(lambda _version, result: finished.append(result))

    worker.run()

    assert len(partial) == len(finished) == 1
    computation = finished[0].mvp
    assert loaded.snapshot.experiment_identity == created.experiment_identity
    assert loaded.snapshot.scene_identity == created.scene_identity
    assert loaded.snapshot.trajectory_identity == created.trajectory_identity
    assert computation.scene == loaded.snapshot.scene
    assert computation.trajectory == loaded.snapshot.trajectory
    assert len(computation.samples) == 3
    assert {sample.mode for sample in computation.samples} == {
        NO_RIS_MODE,
        STATIC_RIS_MODE,
        ADAPTIVE_RIS_MODE,
    }
    assert finished[0].field_map.received_power_dbm.shape == (60, 80)
