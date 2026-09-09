"""Functional Chinese desktop UI for the Smart Space vertical slice."""

from __future__ import annotations

import copy
from dataclasses import replace
import math
from pathlib import Path
import sys
import time

import numpy as np
from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from airmirror_future.core.config import FIELD_QUALITY_PRESETS, field_quality_preset
from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import FieldMapResult, Scene, SimulationConfig, Vec3
from airmirror_future.core.units import dbm_to_watts, watts_to_dbm
from airmirror_future.gui.pattern_view import PhasePatternView
from airmirror_future.gui.scene_view import SceneView
from airmirror_future.gui.workers import (
    MapWorker,
    OptimizationWorker,
    SmartSpaceRefreshResult,
    SmartSpaceRefreshWorker,
    XRAdaptiveFieldResult,
    XRAdaptiveFieldWorker,
    XRDynamicRoomWorker,
    XRDynamicRoomResult,
    XRFieldCacheKey,
    XRFutureFixedFieldRequest,
    XRFuturePreparedFieldResult,
    XRFuturePreparedFieldWorker,
    build_xr_field_cache_key,
)
from airmirror_future.experiments.xr_dynamic_room_mvp import (
    ADAPTIVE_MVP_MODES,
    ADAPTIVE_RIS_MODE,
    DynamicLinkSample,
    MVPComputation,
    NO_RIS_MODE,
    STATIC_RIS_MODE,
    TrajectorySample,
    _pattern_hash,
    build_trajectory,
    create_mvp_scene,
)
from airmirror_future.gui.xr_trajectory_seam import (
    EXPECTED_TRAJECTORY_INTERFACE_VERSION,
    RouteDraft,
    RoutePointDraft,
    TrajectoryBackendUnavailable,
    TrajectoryEditorBackend,
    XRRouteTrajectoryBackend,
)
from airmirror_future.ris.generations import generation_preset
from airmirror_future.ris.aperture import equivalent_patch_diagnostics
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.physics.noise import noise_power_dbm
from airmirror_future.physics.ris_scattering import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    PRODUCTION_QUADRATURE_ORDER,
    PRODUCTION_RIS_COEFFICIENT_MODEL,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.scenarios.xr_editor import (
    XR_EDITOR_SCENE_TEMPLATES,
    create_xr_editor_scene,
)


XR_FUTURE_FAST_M1 = "preview_m1"
XR_FUTURE_EXACT_M8 = "production_m8"


class MainWindow(QMainWindow):
    """AirMirror Future v0.1 Smart Space desktop application."""

    def __init__(
        self,
        scene: Scene,
        *,
        trajectory_backend: TrajectoryEditorBackend | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("AirMirror Future · 可编程电磁空间仿真平台")
        self.resize(1460, 900)
        self.scene_model = scene
        self.engine = SimulationEngine()
        self.controller_model = ControllerModel()
        self.trajectory_backend = (
            trajectory_backend
            if trajectory_backend is not None
            else XRRouteTrajectoryBackend()
        )
        self.ground_truth = GroundTruthModel(seed=scene.random_seed)
        self.patterns: dict[str, np.ndarray] = {}
        self.latest_field: FieldMapResult | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: list[object] = []
        self._version = 0
        self._active_worker: object | None = None
        self._smart_space_active_worker: (
            MapWorker | OptimizationWorker | SmartSpaceRefreshWorker | None
        ) = None
        self._xr_active_worker: (
            XRDynamicRoomWorker
            | XRAdaptiveFieldWorker
            | XRFuturePreparedFieldWorker
            | None
        ) = None
        self._updating_controls = False
        self._pending = False
        self._pattern_source = "Coherent Target Focus"
        self._pattern_context: tuple[object, ...] | None = None
        self._xr_demo_active = False
        self._xr_playback_waiting_for_field = False
        self._xr_editor_active = False
        self._xr_editor_scene: Scene | None = None
        self._xr_trajectory: RouteDraft | None = None
        self._xr_selected_waypoint_index = 0
        self._xr_selected_ris_id: str | None = None
        self._xr_ris_command_states: dict[str, str] = {}
        self._xr_route_valid = False
        self._xr_pending_run_request: object | None = None
        self._xr_cancel_waiting_for_termination = False
        self._xr_result: MVPComputation | None = None
        self._xr_static_field: FieldMapResult | None = None
        self._xr_no_ris_field: FieldMapResult | None = None
        self._xr_field_scales: dict[str, tuple[float, float]] = {}
        self._xr_field_runtime_summary = ""
        self._xr_field_cache: dict[XRFieldCacheKey, FieldMapResult] = {}
        self._xr_static_field_key: XRFieldCacheKey | None = None
        self._xr_pending_field_request: (
            tuple[int, DynamicLinkSample, XRFieldCacheKey] | None
        ) = None
        self._xr_field_inflight_key: XRFieldCacheKey | None = None
        self._xr_field_cache_limit = len(build_trajectory()) + 1
        self._xr_demo_start_pending = False
        self._xr_future_started_at: float | None = None
        self._closing = False
        self._xr_sample_index = 0
        self._xr_sample_lookup: dict[tuple[int, str], DynamicLinkSample] = {}
        self._smart_metric_texts: tuple[str, ...] = ()
        self._smart_space_refresh_pending = False
        self._xr_resume_smart_space_refresh = False
        self._debounced_action: str | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self._run_debounced_action)
        self._xr_playback_timer = QTimer(self)
        self._xr_playback_timer.setInterval(500)
        self._xr_playback_timer.timeout.connect(self._advance_xr_sample)
        self._xr_field_debounce = QTimer(self)
        self._xr_field_debounce.setSingleShot(True)
        self._xr_field_debounce.setInterval(650)
        self._xr_field_debounce.timeout.connect(self._start_pending_xr_field)
        self._xr_future_elapsed_timer = QTimer(self)
        self._xr_future_elapsed_timer.setInterval(500)
        self._xr_future_elapsed_timer.timeout.connect(
            self._update_xr_future_elapsed
        )

        self.scene_view = SceneView()
        self.scene_view.on_entity_moved = self._entity_moved
        self.scene_view.on_route_point_moved = self._xr_route_point_moved
        self.scene_view.on_route_point_selected = self._xr_route_point_selected
        self.pattern_view = PhasePatternView()
        self._build_ui()
        self._set_pending(False)
        self._set_focus_pattern()
        self._refresh_all(recompute_map=False)
        self._schedule_field_map()

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel = self._build_left_panel()
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.scene_view)
        self.right_panel = self._build_right_panel()
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([280, 860, 320])

        central = QWidget()
        layout = QVBoxLayout(central)
        title_row = QHBoxLayout()
        title = QLabel("<h2>AirMirror Future</h2><span>物理约束的系统级 RIS 数字孪生</span>")
        self.future_badge = QLabel("")
        self.future_badge.setStyleSheet("color:#f59e0b;font-weight:600")
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.future_badge)
        layout.addLayout(title_row)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_metrics_bar())
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("System-level electromagnetic approximation")

    def _build_left_panel(self) -> QWidget:
        container = QScrollArea()
        container.setWidgetResizable(True)
        container.setMinimumWidth(260)
        panel = QWidget()
        panel.setMinimumWidth(240)
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>场景 / Scenario</b>"))
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItem("Future Smart Space", "smart_space")
        self.scenario_combo.addItem(
            "XR Dynamic Room MVP · Prototype",
            "xr_dynamic_room_mvp",
        )
        self.scenario_combo.addItem(
            "XR Scene & Route Editor · Prototype",
            "xr_route_editor",
        )
        self.scenario_combo.currentIndexChanged.connect(self._scenario_changed)
        layout.addWidget(self.scenario_combo)
        roadmap = QLabel(
            "XR Dynamic Room：non-release playback / route editor\n"
            "Smart Factory · Future City：尚未实现"
        )
        roadmap.setWordWrap(True)
        roadmap.setStyleSheet("color:#64748b")
        layout.addWidget(roadmap)

        self.xr_controls = QGroupBox("XR Playback / Editor")
        xr_layout = QVBoxLayout(self.xr_controls)

        self.xr_editor_group = QGroupBox(
            f"Scene & Route · {EXPECTED_TRAJECTORY_INTERFACE_VERSION} pending"
        )
        editor_layout = QVBoxLayout(self.xr_editor_group)
        self.xr_template_combo = QComboBox()
        for template_id, display_name in XR_EDITOR_SCENE_TEMPLATES:
            self.xr_template_combo.addItem(display_name, template_id)
        editor_layout.addWidget(self.xr_template_combo)
        scene_buttons = QHBoxLayout()
        self.xr_load_template_button = QPushButton("Load Template")
        self.xr_load_scene_button = QPushButton("Load Scene")
        self.xr_load_template_button.clicked.connect(self._xr_load_template)
        self.xr_load_scene_button.clicked.connect(self._xr_load_scene)
        scene_buttons.addWidget(self.xr_load_template_button)
        scene_buttons.addWidget(self.xr_load_scene_button)
        editor_layout.addLayout(scene_buttons)

        ris_editor = QGroupBox("RIS instances · isolated dual-RIS editor")
        ris_layout = QVBoxLayout(ris_editor)
        ris_select = QHBoxLayout()
        self.xr_ris_combo = QComboBox()
        self.xr_ris_combo.currentIndexChanged.connect(self._xr_ris_selected)
        self.xr_add_ris_button = QPushButton("Create second RIS")
        self.xr_add_ris_button.clicked.connect(self._xr_add_ris)
        ris_select.addWidget(self.xr_ris_combo)
        ris_select.addWidget(self.xr_add_ris_button)
        ris_layout.addLayout(ris_select)
        ris_form = QFormLayout()
        self.xr_ris_x = self._double_spin(0.0, 1000.0, 0.0, 0.1, " m")
        self.xr_ris_y = self._double_spin(0.0, 1000.0, 0.0, 0.1, " m")
        self.xr_ris_z = self._double_spin(0.0, 1000.0, 1.5, 0.1, " m")
        self.xr_ris_enabled = QCheckBox("Enabled")
        self.xr_ris_enabled.setChecked(True)
        ris_form.addRow("X", self.xr_ris_x)
        ris_form.addRow("Y", self.xr_ris_y)
        ris_form.addRow("Z", self.xr_ris_z)
        ris_form.addRow("State", self.xr_ris_enabled)
        ris_layout.addLayout(ris_form)
        self.xr_apply_ris_button = QPushButton("Apply selected RIS")
        self.xr_apply_ris_button.clicked.connect(self._xr_apply_ris)
        ris_layout.addWidget(self.xr_apply_ris_button)
        self.xr_ris_state_status = QLabel("RIS state: pending")
        self.xr_ris_state_status.setWordWrap(True)
        self.xr_ris_state_status.setStyleSheet("color:#475569")
        ris_layout.addWidget(self.xr_ris_state_status)
        editor_layout.addWidget(ris_editor)

        select_buttons = QHBoxLayout()
        self.xr_previous_point_button = QPushButton("◀ Point")
        self.xr_next_point_button = QPushButton("Point ▶")
        self.xr_previous_point_button.clicked.connect(
            lambda: self._xr_select_relative_point(-1)
        )
        self.xr_next_point_button.clicked.connect(
            lambda: self._xr_select_relative_point(1)
        )
        select_buttons.addWidget(self.xr_previous_point_button)
        select_buttons.addWidget(self.xr_next_point_button)
        editor_layout.addLayout(select_buttons)

        point_actions = QHBoxLayout()
        self.xr_add_point_button = QPushButton("Add")
        self.xr_insert_point_button = QPushButton("Insert")
        self.xr_delete_point_button = QPushButton("Delete")
        self.xr_add_point_button.clicked.connect(self._xr_add_route_point)
        self.xr_insert_point_button.clicked.connect(self._xr_insert_route_point)
        self.xr_delete_point_button.clicked.connect(self._xr_delete_route_point)
        point_actions.addWidget(self.xr_add_point_button)
        point_actions.addWidget(self.xr_insert_point_button)
        point_actions.addWidget(self.xr_delete_point_button)
        editor_layout.addLayout(point_actions)

        self.xr_point_label = QLabel("Point: —")
        editor_layout.addWidget(self.xr_point_label)
        point_form = QFormLayout()
        self.xr_point_x = self._double_spin(0.0, 1000.0, 0.0, 0.1, " m")
        self.xr_point_y = self._double_spin(0.0, 1000.0, 0.0, 0.1, " m")
        self.xr_point_z = self._double_spin(0.0, 1000.0, 1.2, 0.1, " m")
        self.xr_point_time = self._double_spin(0.0, 86400.0, 0.0, 0.5, " s")
        self.xr_timing_mode = QComboBox()
        self.xr_timing_mode.addItem("Arrival time", "time")
        self.xr_timing_mode.addItem("Speed from previous", "speed")
        self.xr_point_speed = self._double_spin(0.01, 100.0, 1.0, 0.1, " m/s")
        self.xr_timing_mode.currentIndexChanged.connect(
            self._xr_update_timing_controls
        )
        point_form.addRow("X", self.xr_point_x)
        point_form.addRow("Y", self.xr_point_y)
        point_form.addRow("Z", self.xr_point_z)
        point_form.addRow("Timing", self.xr_timing_mode)
        point_form.addRow("Arrival", self.xr_point_time)
        point_form.addRow("Speed", self.xr_point_speed)
        editor_layout.addLayout(point_form)
        self.xr_apply_point_button = QPushButton("Apply Point")
        self.xr_apply_point_button.clicked.connect(self._xr_apply_route_point)
        editor_layout.addWidget(self.xr_apply_point_button)

        route_files = QHBoxLayout()
        self.xr_load_route_button = QPushButton("Load Route")
        self.xr_save_route_button = QPushButton("Save Route")
        self.xr_load_route_button.clicked.connect(self._xr_load_route)
        self.xr_save_route_button.clicked.connect(self._xr_save_route)
        route_files.addWidget(self.xr_load_route_button)
        route_files.addWidget(self.xr_save_route_button)
        editor_layout.addLayout(route_files)
        self.xr_route_status = QLabel("Route: pending")
        self.xr_route_status.setWordWrap(True)
        self.xr_route_status.setStyleSheet("color:#b45309")
        editor_layout.addWidget(self.xr_route_status)

        run_buttons = QHBoxLayout()
        self.xr_run_button = QPushButton("Run 3 Modes")
        self.xr_cancel_button = QPushButton("Cancel")
        self.xr_cancel_button.setEnabled(False)
        self.xr_run_button.clicked.connect(self._run_xr_editor)
        self.xr_cancel_button.clicked.connect(self._cancel_xr_editor_run)
        run_buttons.addWidget(self.xr_run_button)
        run_buttons.addWidget(self.xr_cancel_button)
        editor_layout.addLayout(run_buttons)
        self.xr_future_field_button = QPushButton(
            "Build selected point · exact M8 8×6"
        )
        self.xr_future_field_button.setToolTip(
            "Build one fixed-grid coefficient matrix, then evaluate Static and "
            "selected-point Adaptive commands. This is not a whole-route matrix."
        )
        self.xr_future_field_button.clicked.connect(
            self._run_xr_future_fixed_field
        )
        self.xr_future_field_button.setEnabled(False)
        editor_layout.addWidget(self.xr_future_field_button)
        future_options = QFormLayout()
        self.xr_future_accuracy_combo = QComboBox()
        self.xr_future_accuracy_combo.addItem(
            "高速 1×1 · prepared",
            XR_FUTURE_FAST_M1,
        )
        self.xr_future_accuracy_combo.addItem(
            "精确 M8 · production",
            XR_FUTURE_EXACT_M8,
        )
        self.xr_future_accuracy_combo.setCurrentIndex(
            self.xr_future_accuracy_combo.findData(XR_FUTURE_FAST_M1)
        )
        self.xr_future_grid_combo = QComboBox()
        self.xr_future_grid_combo.addItem("8×6 · quick Windows gate", (8, 6))
        self.xr_future_grid_combo.addItem("16×12", (16, 12))
        self.xr_future_grid_combo.addItem("48×36 · full fixed field", (48, 36))
        self.xr_future_accuracy_combo.currentIndexChanged.connect(
            self._xr_future_options_changed
        )
        self.xr_future_grid_combo.currentIndexChanged.connect(
            self._xr_future_options_changed
        )
        future_options.addRow("Model accuracy", self.xr_future_accuracy_combo)
        future_options.addRow("Map grid", self.xr_future_grid_combo)
        editor_layout.addLayout(future_options)
        self.xr_future_accuracy_status = QLabel(
            "Production M8 selected · real prepared field · 64×48 controls unchanged"
        )
        self.xr_future_accuracy_status.setWordWrap(True)
        self.xr_future_accuracy_status.setStyleSheet("color:#475569")
        editor_layout.addWidget(self.xr_future_accuracy_status)
        self.xr_command_status = QLabel("Command: pending")
        self.xr_command_status.setWordWrap(True)
        self.xr_command_status.setStyleSheet("color:#64748b")
        editor_layout.addWidget(self.xr_command_status)
        self.xr_editor_group.setVisible(False)
        xr_layout.addWidget(self.xr_editor_group)

        self.xr_mode_combo = QComboBox()
        self.xr_mode_combo.addItems(ADAPTIVE_MVP_MODES)
        self.xr_mode_combo.currentTextChanged.connect(self._xr_mode_changed)
        xr_layout.addWidget(self.xr_mode_combo)
        self.xr_quantity_combo = QComboBox()
        self.xr_quantity_combo.addItems(("接收功率", "SNR", "RIS 增益"))
        self.xr_quantity_combo.currentTextChanged.connect(self._redraw_xr_field)
        xr_layout.addWidget(self.xr_quantity_combo)
        buttons = QHBoxLayout()
        self.xr_play_button = QPushButton("Play")
        self.xr_pause_button = QPushButton("Pause")
        self.xr_reset_button = QPushButton("Reset")
        self.xr_play_button.clicked.connect(self._play_xr_demo)
        self.xr_pause_button.clicked.connect(self._pause_xr_demo)
        self.xr_reset_button.clicked.connect(self._reset_xr_demo)
        for button in (
            self.xr_play_button,
            self.xr_pause_button,
            self.xr_reset_button,
        ):
            buttons.addWidget(button)
        xr_layout.addLayout(buttons)
        self.xr_timeline = QSlider(Qt.Orientation.Horizontal)
        self.xr_timeline.setRange(0, len(build_trajectory()) - 1)
        self.xr_timeline.valueChanged.connect(self._set_xr_sample)
        xr_layout.addWidget(self.xr_timeline)
        self.xr_sample_label = QLabel("Sample: —")
        xr_layout.addWidget(self.xr_sample_label)
        self.xr_field_status = QLabel("Field map: —")
        self.xr_field_status.setWordWrap(True)
        self.xr_field_status.setStyleSheet("color:#64748b")
        xr_layout.addWidget(self.xr_field_status)
        self.xr_command_status = QLabel("Command: —")
        self.xr_command_status.setWordWrap(True)
        self.xr_command_status.setStyleSheet("color:#64748b")
        xr_layout.addWidget(self.xr_command_status)
        self.xr_controls.setVisible(False)
        self._set_xr_controls_ready(False)
        layout.addWidget(self.xr_controls)

        self.files_group = QGroupBox("场景文件")
        files_layout = QVBoxLayout(self.files_group)
        load_button = QPushButton("加载场景 / Load")
        save_button = QPushButton("保存场景 / Save")
        load_button.clicked.connect(self._load_scene)
        save_button.clicked.connect(self._save_scene)
        files_layout.addWidget(load_button)
        files_layout.addWidget(save_button)
        layout.addWidget(self.files_group)

        self.layers_group = QGroupBox("显示层")
        layers_layout = QVBoxLayout(self.layers_group)
        self.show_field = QCheckBox("Show Field")
        self.show_field.setChecked(True)
        self.show_rays = QCheckBox("Show Rays")
        self.show_rays.setChecked(True)
        self.show_pattern = QCheckBox("Show RIS Pattern")
        self.show_pattern.setChecked(True)
        self.show_coverage = QCheckBox("Show Coverage")
        self.show_coverage.setChecked(False)
        self.show_labels = QCheckBox("Show Labels")
        self.show_labels.setChecked(True)
        for checkbox in (
            self.show_field,
            self.show_rays,
            self.show_pattern,
            self.show_coverage,
            self.show_labels,
        ):
            layers_layout.addWidget(checkbox)
        self.show_field.toggled.connect(self._field_visibility_changed)
        self.show_rays.toggled.connect(self._display_options_changed)
        self.show_labels.toggled.connect(self._display_options_changed)
        self.show_pattern.toggled.connect(self.pattern_view.setVisible)
        self.show_coverage.toggled.connect(self._coverage_visibility_changed)
        layout.addWidget(self.layers_group)

        info = QPushButton("模型说明 / Model Info")
        info.clicked.connect(self._show_model_info)
        layout.addWidget(info)
        layout.addStretch()
        container.setWidget(panel)
        return container

    @staticmethod
    def _double_spin(minimum: float, maximum: float, value: float, step: float, suffix: str) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(3)
        widget.setSingleStep(step)
        widget.setValue(value)
        widget.setSuffix(suffix)
        return widget

    def _build_right_panel(self) -> QWidget:
        container = QScrollArea()
        container.setWidgetResizable(True)
        panel = QWidget()
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)

        generation_group = QGroupBox("技术代际 / Generation")
        generation_layout = QVBoxLayout(generation_group)
        self.generation_combo = QComboBox()
        self.generation_combo.addItems(("Current", "Advanced", "Future"))
        current_generation = self.scene_model.ris_surfaces[0].generation
        self.generation_combo.setCurrentText(current_generation)
        self.generation_combo.currentTextChanged.connect(self._generation_changed)
        generation_layout.addWidget(self.generation_combo)
        self.generation_status = QLabel("Current")
        self.generation_status.setStyleSheet("color:#64748b")
        generation_layout.addWidget(self.generation_status)
        generation_layout.addWidget(QLabel("代际参数是代表性仿真假设，可继续编辑。"))
        layout.addWidget(generation_group)

        rf_group = QGroupBox("RF 参数")
        rf_form = QFormLayout(rf_group)
        tx = self.scene_model.transmitter()
        rx = self.scene_model.receiver()
        self.frequency = self._double_spin(0.1, 300.0, self.scene_model.frequency_hz / 1e9, 0.1, " GHz")
        self.tx_power = self._double_spin(-30, 80, float(watts_to_dbm(tx.power_w)), 1, " dBm")
        self.bandwidth = self._double_spin(0.001, 5000, self.scene_model.bandwidth_hz / 1e6, 10, " MHz")
        self.noise_figure = self._double_spin(0, 30, rx.noise_figure_db, 0.5, " dB")
        self.coverage_threshold = self._double_spin(
            -30, 100, self.scene_model.coverage_threshold_db, 1, " dB"
        )
        rf_form.addRow("Frequency", self.frequency)
        rf_form.addRow("TX Power", self.tx_power)
        rf_form.addRow("Bandwidth", self.bandwidth)
        rf_form.addRow("Noise Figure", self.noise_figure)
        rf_form.addRow("Coverage SNR ≥", self.coverage_threshold)
        layout.addWidget(rf_group)

        ris = self.scene_model.ris_surfaces[0]
        ris_group = QGroupBox("RIS 参数")
        ris_form = QFormLayout(ris_group)
        self.ris_width = self._double_spin(0.05, 20, ris.width_m, 0.1, " m")
        self.ris_height = self._double_spin(0.05, 20, ris.height_m, 0.1, " m")
        self.ris_nx = QSpinBox()
        self.ris_ny = QSpinBox()
        for widget, value in ((self.ris_nx, ris.nx), (self.ris_ny, ris.ny)):
            widget.setRange(1, 256)
            widget.setValue(value)
        self.phase_bits = QComboBox()
        for label, value in (("1-bit", 1), ("2-bit", 2), ("3-bit", 3), ("4-bit", 4), ("continuous", None)):
            self.phase_bits.addItem(label, value)
        self.phase_bits.setCurrentIndex(self.phase_bits.findData(ris.phase_bits))
        self.efficiency = self._double_spin(0, 1, ris.reflection_efficiency, 0.05, "")
        self.update_rate = self._double_spin(0.1, 1e6, ris.update_rate_hz, 10, " Hz")
        self.self_sensing = QCheckBox("Enabled")
        self.self_sensing.setChecked(ris.self_sensing)
        ris_form.addRow("Width", self.ris_width)
        ris_form.addRow("Height", self.ris_height)
        ris_form.addRow("Nx", self.ris_nx)
        ris_form.addRow("Ny", self.ris_ny)
        ris_form.addRow("Phase Bits", self.phase_bits)
        ris_form.addRow("Efficiency η", self.efficiency)
        ris_form.addRow("Update Rate", self.update_rate)
        ris_form.addRow("Self Sensing", self.self_sensing)
        layout.addWidget(ris_group)

        error_group = QGroupBox("Ground Truth 误差")
        error_form = QFormLayout(error_group)
        self.phase_error = self._double_spin(0, 180, 0, 1, "°")
        self.measurement_noise = self._double_spin(0, 20, 0, 0.1, " dB")
        self.position_error = self._double_spin(0, 2, 0, 0.01, " m")
        self.phase_error.setToolTip("Ground Truth phase error is added after commanded-state validation; Actual is not requantized.")
        self.measurement_noise.setToolTip("Only MeasurementOracle feedback readings include this noise; direct simulation metrics do not.")
        self.position_error.setToolTip(
            "TX/RX/RIS/obstacle use their 3D model. v1 floor-anchored walls use one rigid XY delta for both endpoints; no vertical wall error."
        )
        error_form.addRow("Phase Error σ / 相位误差 σ", self.phase_error)
        error_form.addRow("Feedback Measurement Noise σ / 反馈测量噪声 σ", self.measurement_noise)
        error_form.addRow("Geometry Position Error σ / 几何位置误差 σ", self.position_error)
        layout.addWidget(error_group)

        self.apply_button = QPushButton("应用参数 / Apply")
        self.apply_button.clicked.connect(self._apply_parameters)
        layout.addWidget(self.apply_button)
        self.pending_label = QLabel("状态：已应用 / Applied")
        self.pending_label.setStyleSheet("color:#64748b")
        layout.addWidget(self.pending_label)

        optimization = QGroupBox("优化 / Optimize")
        optimization_layout = QVBoxLayout(optimization)
        self.algorithm = QComboBox()
        self.algorithm.addItems(
            (
                "Coherent Target Focus",
                "RIS-only Physics Focus",
                "Feedback Greedy",
                "Physics-Guided Feedback",
            )
        )
        self.search_levels = QSpinBox()
        self.search_levels.setRange(1, 256)
        self.search_levels.setValue(8)
        self.search_levels.setToolTip(
            "Continuous hardware 的有限候选搜索级数；不改变硬件 Allowed States。"
        )
        optimization_layout.addWidget(QLabel("Search Levels / 搜索级数"))
        optimization_layout.addWidget(self.search_levels)
        self.optimize_button = QPushButton("Optimize")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.optimize_button.clicked.connect(self._optimize)
        self.cancel_button.clicked.connect(self._cancel_work)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        optimization_layout.addWidget(self.algorithm)
        optimization_layout.addWidget(self.optimize_button)
        optimization_layout.addWidget(self.cancel_button)
        optimization_layout.addWidget(self.progress)
        layout.addWidget(optimization)

        display = QGroupBox("场图")
        display_layout = QFormLayout(display)
        self.quantity = QComboBox()
        self.quantity.addItems(("接收功率", "SNR", "RIS 增益"))
        self.quantity.currentTextChanged.connect(self._redraw_latest_map)
        self.quality = QComboBox()
        for preset in FIELD_QUALITY_PRESETS:
            self.quality.addItem(
                f"{preset.display_name} {preset.grid_width}×{preset.grid_height}",
                preset.key,
            )
        self.quality.setCurrentIndex(0)
        refresh = QPushButton("重新计算场图")
        refresh.clicked.connect(self.start_field_map)
        display_layout.addRow("Map", self.quantity)
        display_layout.addRow("Quality", self.quality)
        display_layout.addRow(refresh)
        layout.addWidget(display)

        layout.addWidget(QLabel("<b>RIS Pattern</b>"))
        layout.addWidget(self.pattern_view)
        layout.addStretch()
        container.setWidget(panel)
        self._connect_edit_signals()
        self._update_search_levels_state()
        return container

    def _connect_edit_signals(self) -> None:
        """Mark ordinary parameter edits pending without mutating the applied scene."""
        for widget in (
            self.frequency,
            self.tx_power,
            self.bandwidth,
            self.noise_figure,
            self.coverage_threshold,
            self.ris_width,
            self.ris_height,
            self.ris_nx,
            self.ris_ny,
            self.phase_bits,
            self.efficiency,
            self.update_rate,
            self.self_sensing,
            self.phase_error,
            self.measurement_noise,
            self.position_error,
        ):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._mark_pending)
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self._mark_pending)
            else:
                widget.valueChanged.connect(self._mark_pending)
        self.phase_bits.currentIndexChanged.connect(self._update_search_levels_state)

    def _mark_pending(self, *_args: object) -> None:
        if self._updating_controls:
            return
        self._set_pending(True)

    def _set_pending(self, pending: bool) -> None:
        self._pending = bool(pending)
        self.apply_button.setEnabled(self._pending)
        self.optimize_button.setEnabled(not self._pending)
        if self._pending:
            self.pending_label.setText(
                "状态：待应用 / Pending · 请先 Apply；指标与 Pattern 仍来自已应用模型"
            )
            self.pending_label.setStyleSheet("color:#b45309;font-weight:600")
        else:
            self.pending_label.setText("状态：已应用 / Applied")
            self.pending_label.setStyleSheet("color:#64748b")

    def _update_search_levels_state(self, *_args: object) -> None:
        continuous = self.phase_bits.currentData() is None
        self.search_levels.setEnabled(continuous)
        self.search_levels.setToolTip(
            "Continuous hardware：有限候选搜索级数，不是硬件状态数。"
            if continuous
            else "Finite-bit hardware：候选固定为 2^phase_bits 个合法硬件状态。"
        )

    def _build_metrics_bar(self) -> QWidget:
        panel = QGroupBox("实时指标")
        layout = QHBoxLayout(panel)
        self.power_metric = QLabel("Power: —")
        self.snr_metric = QLabel("SNR: —")
        self.gain_metric = QLabel("RIS Gain: —")
        self.coverage_metric = QLabel("Coverage: —")
        self.dead_zone_metric = QLabel("Dead Zone: —")
        self.runtime_metric = QLabel("Runtime: —")
        for widget in (
            self.power_metric,
            self.snr_metric,
            self.gain_metric,
            self.coverage_metric,
            self.dead_zone_metric,
            self.runtime_metric,
        ):
            layout.addWidget(widget)
        return panel

    def _set_xr_controls_ready(self, ready: bool) -> None:
        self.xr_mode_combo.setEnabled(ready)
        self.xr_quantity_combo.setEnabled(ready)
        self.xr_play_button.setEnabled(ready and not self._xr_playback_timer.isActive())
        self.xr_pause_button.setEnabled(ready and self._xr_playback_timer.isActive())
        self.xr_reset_button.setEnabled(ready)
        self.xr_timeline.setEnabled(ready)
        if self._xr_editor_active:
            backend_ready = self.trajectory_backend is not None
            self.xr_run_button.setEnabled(
                backend_ready
                and self._xr_trajectory is not None
                and self._xr_route_valid
                and not self._xr_demo_start_pending
            )
            self.xr_cancel_button.setEnabled(
                self._xr_demo_start_pending or self._xr_active_worker is not None
            )
            self.xr_load_route_button.setEnabled(backend_ready)
            self.xr_save_route_button.setEnabled(backend_ready)
            self.xr_future_field_button.setEnabled(
                backend_ready
                and self._xr_trajectory is not None
                and self._xr_route_valid
                and self._xr_is_full_future_scene()
                and self._xr_future_backend_ready()
                and not self._xr_demo_start_pending
                and self._xr_active_worker is None
            )

    def _set_smart_space_widgets_enabled(self, enabled: bool) -> None:
        self.files_group.setEnabled(enabled)
        self.layers_group.setEnabled(enabled)
        self.right_panel.setEnabled(enabled)

    @staticmethod
    def _default_xr_editor_trajectory(scene: Scene) -> RouteDraft:
        """Build GUI draft control points; B's sampler owns interpolation."""
        width = scene.room_size.x
        height = scene.room_size.y
        z = scene.z_eval_m
        if scene.name == "XR Complex Office":
            positions = (
                Vec3(0.14 * width, 0.50 * height, z),
                Vec3(0.32 * width, 0.50 * height, z),
                Vec3(0.63 * width, 0.50 * height, z),
                Vec3(0.86 * width, 0.50 * height, z),
            )
        else:
            positions = (
                Vec3(0.14 * width, 0.12 * height, z),
                Vec3(0.34 * width, 0.12 * height, z),
                Vec3(0.62 * width, 0.12 * height, z),
                Vec3(0.86 * width, 0.12 * height, z),
            )
        return RouteDraft(
            name=f"{scene.name} route",
            points=tuple(
                RoutePointDraft(
                    id=f"point-{index + 1}",
                    time_s=float(index * 3),
                    position=position,
                )
                for index, position in enumerate(positions)
            ),
            sample_interval_s=0.5,
        )

    @staticmethod
    def _validate_xr_editor_scene(scene: Scene) -> None:
        if len(scene.transmitters) != 1 or len(scene.receivers) != 1:
            raise ValueError("XR Route Editor requires exactly one TX and one RX")
        if not 1 <= len(scene.ris_surfaces) <= 2:
            raise ValueError("XR Route Editor supports one or two RIS instances")
        identifiers = [ris.id for ris in scene.ris_surfaces]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("XR Route Editor requires unique RIS ids")

    @staticmethod
    def _xr_joint_ris_backend_pending(scene: Scene) -> bool:
        enabled = [ris for ris in scene.ris_surfaces if ris.enabled]
        return len(scene.ris_surfaces) == 2 or len(enabled) != 1

    def _xr_is_full_future_scene(self) -> bool:
        if self._xr_editor_scene is None:
            return False
        enabled = [ris for ris in self._xr_editor_scene.ris_surfaces if ris.enabled]
        return len(enabled) == 1 and enabled[0].generation == "Future"

    def _xr_future_backend_ready(self) -> bool:
        """Accept only the two implemented explicit prepared model choices."""
        return self.xr_future_accuracy_combo.currentData() in {
            XR_FUTURE_FAST_M1,
            XR_FUTURE_EXACT_M8,
        }

    def _xr_future_coefficient_model(self):
        accuracy = self.xr_future_accuracy_combo.currentData()
        if accuracy == XR_FUTURE_FAST_M1:
            return FAST_1X1_RIS_COEFFICIENT_MODEL
        if accuracy == XR_FUTURE_EXACT_M8:
            return PRODUCTION_RIS_COEFFICIENT_MODEL
        raise RuntimeError(f"unsupported XR Future accuracy selection: {accuracy}")

    @staticmethod
    def _xr_future_model_label(identity: str) -> str:
        if identity == FAST_1X1_RIS_COEFFICIENT_MODEL.identity:
            return "Fast 1×1"
        if identity == PRODUCTION_RIS_COEFFICIENT_MODEL.identity:
            return f"Production M{PRODUCTION_QUADRATURE_ORDER}"
        return f"Unknown model {identity}"

    def _xr_future_grid(self) -> tuple[int, int]:
        grid = self.xr_future_grid_combo.currentData()
        if not isinstance(grid, (tuple, list)) or len(grid) != 2:
            raise RuntimeError("XR Future map grid selection is invalid")
        return int(grid[0]), int(grid[1])

    def _xr_future_options_changed(self, *_args: object) -> None:
        """Invalidate fields when model accuracy or map-grid identity changes."""
        if not hasattr(self, "xr_future_field_button"):
            return
        width, height = self._xr_future_grid()
        exact = self.xr_future_accuracy_combo.currentData() == XR_FUTURE_EXACT_M8
        self.xr_future_field_button.setText(
            f"Build selected point · {'exact M8' if exact else 'fast 1×1'} "
            f"{width}×{height}"
        )
        if exact:
            self.xr_future_accuracy_status.setText(
                "Production M8 selected · real prepared field · "
                "Future 3×2 m / 64×48 controls unchanged"
            )
            self.xr_future_accuracy_status.setStyleSheet("color:#475569")
        else:
            self.xr_future_accuracy_status.setText(
                "Fast 1×1 selected · real prepared field · "
                "Future 3×2 m / 64×48 controls unchanged"
            )
            self.xr_future_accuracy_status.setStyleSheet("color:#475569")
        if not self._xr_editor_active:
            return
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        self._xr_field_debounce.stop()
        self._version += 1
        self._xr_demo_start_pending = False
        self._xr_pending_run_request = None
        self._xr_pending_field_request = None
        self._cancel_active()
        self._xr_static_field = None
        self._xr_no_ris_field = None
        self._xr_field_scales = {}
        self._xr_field_runtime_summary = ""
        self._xr_field_cache = {}
        self._xr_static_field_key = None
        self._xr_field_inflight_key = None
        self.scene_view.clear_field_overlays()
        self.xr_field_status.setText(
            "Field map invalidated · model accuracy or map grid changed"
        )
        self._set_xr_controls_ready(self._xr_result is not None)

    def _render_xr_editor_inputs(self) -> None:
        if (
            not self._xr_editor_active
            or self._xr_editor_scene is None
            or self._xr_trajectory is None
        ):
            return
        self.scene_view.load_scene(self._xr_editor_scene)
        self.scene_view.set_entities_draggable(False)
        self.scene_view.set_draggable_entity_ids(
            {ris.id for ris in self._xr_editor_scene.ris_surfaces}
        )
        self.scene_view.show_editable_route(
            [waypoint.position for waypoint in self._xr_trajectory.points],
            selected_index=self._xr_selected_waypoint_index,
        )
        self._sync_xr_point_form()
        self._sync_xr_ris_controls()

    def _sync_xr_ris_controls(self) -> None:
        scene = self._xr_editor_scene
        if scene is None:
            return
        identifiers = [ris.id for ris in scene.ris_surfaces]
        selected = self._xr_selected_ris_id
        if selected not in identifiers:
            selected = identifiers[0]
        self._xr_selected_ris_id = selected
        self.xr_ris_combo.blockSignals(True)
        try:
            self.xr_ris_combo.clear()
            for ris in scene.ris_surfaces:
                state = "enabled" if ris.enabled else "disabled"
                self.xr_ris_combo.addItem(f"{ris.id} · {state}", ris.id)
            self.xr_ris_combo.setCurrentIndex(identifiers.index(selected))
        finally:
            self.xr_ris_combo.blockSignals(False)
        ris = next(item for item in scene.ris_surfaces if item.id == selected)
        self.xr_ris_x.setRange(0.0, scene.room_size.x)
        self.xr_ris_y.setRange(0.0, scene.room_size.y)
        self.xr_ris_z.setRange(0.0, scene.room_size.z)
        for widget in (
            self.xr_ris_x,
            self.xr_ris_y,
            self.xr_ris_z,
            self.xr_ris_enabled,
        ):
            widget.blockSignals(True)
        try:
            self.xr_ris_x.setValue(ris.position.x)
            self.xr_ris_y.setValue(ris.position.y)
            self.xr_ris_z.setValue(ris.position.z)
            self.xr_ris_enabled.setChecked(ris.enabled)
        finally:
            for widget in (
                self.xr_ris_x,
                self.xr_ris_y,
                self.xr_ris_z,
                self.xr_ris_enabled,
            ):
                widget.blockSignals(False)
        self.xr_add_ris_button.setEnabled(len(scene.ris_surfaces) < 2)
        states = []
        for item in scene.ris_surfaces:
            command = self._xr_ris_command_states.get(
                item.id,
                "disabled" if not item.enabled else "command pending",
            )
            states.append(
                f"{item.id}: {'enabled' if item.enabled else 'disabled'} · {command}"
            )
        self.xr_ris_state_status.setText("RIS states · " + " | ".join(states))

    def _xr_ris_selected(self, _index: int) -> None:
        identifier = self.xr_ris_combo.currentData()
        if isinstance(identifier, str) and identifier:
            self._xr_selected_ris_id = identifier
            self._sync_xr_ris_controls()

    @staticmethod
    def _next_xr_ris_id(scene: Scene) -> str:
        existing = {ris.id for ris in scene.ris_surfaces}
        number = 2
        while f"ris-{number}" in existing:
            number += 1
        return f"ris-{number}"

    def _xr_add_ris(self) -> None:
        scene = self._xr_editor_scene
        if scene is None or len(scene.ris_surfaces) >= 2:
            return
        source = scene.ris_surfaces[0]
        identifier = self._next_xr_ris_id(scene)
        candidate_x = min(
            scene.room_size.x,
            max(0.0, source.position.x + 0.75),
        )
        if math.isclose(candidate_x, source.position.x):
            candidate_x = max(0.0, source.position.x - 0.75)
        second = replace(
            source,
            id=identifier,
            position=replace(source.position, x=candidate_x),
            enabled=True,
        )
        scene.ris_surfaces = [*scene.ris_surfaces, second]
        self._xr_selected_ris_id = identifier
        self._xr_ris_command_states = {
            ris.id: (
                "disabled" if not ris.enabled else "joint command pending backend"
            )
            for ris in scene.ris_surfaces
        }
        self._xr_editor_inputs_changed("second RIS created")

    def _xr_apply_ris(self) -> None:
        scene = self._xr_editor_scene
        identifier = self._xr_selected_ris_id
        if scene is None or identifier is None:
            return
        position = Vec3(
            self.xr_ris_x.value(),
            self.xr_ris_y.value(),
            self.xr_ris_z.value(),
        )
        found = False
        updated = []
        for ris in scene.ris_surfaces:
            if ris.id == identifier:
                found = True
                updated.append(
                    replace(
                        ris,
                        position=position,
                        enabled=self.xr_ris_enabled.isChecked(),
                    )
                )
            else:
                updated.append(ris)
        if not found:
            raise RuntimeError(f"selected XR RIS no longer exists: {identifier}")
        scene.ris_surfaces = updated
        self._xr_editor_inputs_changed("selected RIS changed")

    def _sync_xr_point_form(self) -> None:
        if self._xr_trajectory is None or self._xr_editor_scene is None:
            return
        index = max(
            0,
            min(self._xr_selected_waypoint_index, len(self._xr_trajectory.points) - 1),
        )
        self._xr_selected_waypoint_index = index
        waypoint = self._xr_trajectory.points[index]
        self.xr_point_x.setRange(0.0, self._xr_editor_scene.room_size.x)
        self.xr_point_y.setRange(0.0, self._xr_editor_scene.room_size.y)
        self.xr_point_z.setRange(0.0, self._xr_editor_scene.room_size.z)
        for widget in (
            self.xr_point_x,
            self.xr_point_y,
            self.xr_point_z,
            self.xr_point_time,
            self.xr_point_speed,
        ):
            widget.blockSignals(True)
        try:
            self.xr_point_x.setValue(waypoint.position.x)
            self.xr_point_y.setValue(waypoint.position.y)
            self.xr_point_z.setValue(waypoint.position.z)
            self.xr_point_time.setValue(waypoint.time_s)
            if index > 0:
                previous = self._xr_trajectory.points[index - 1]
                distance = waypoint.position.distance_to(previous.position)
                duration = waypoint.time_s - previous.time_s
                self.xr_point_speed.setValue(distance / duration)
        finally:
            for widget in (
                self.xr_point_x,
                self.xr_point_y,
                self.xr_point_z,
                self.xr_point_time,
                self.xr_point_speed,
            ):
                widget.blockSignals(False)
        self.xr_point_label.setText(
            f"Point {index + 1}/{len(self._xr_trajectory.points)} · {waypoint.id}"
        )
        self.scene_view.select_route_point(index)
        self._xr_update_timing_controls()

    def _xr_update_timing_controls(self, *_args: object) -> None:
        use_speed = self.xr_timing_mode.currentData() == "speed"
        first = self._xr_selected_waypoint_index == 0
        self.xr_point_time.setEnabled(not use_speed and not first)
        self.xr_point_speed.setEnabled(
            use_speed and not first and self.trajectory_backend is not None
        )

    def _xr_route_point_selected(self, index: int) -> None:
        if not self._xr_editor_active or self._xr_trajectory is None:
            return
        if not 0 <= index < len(self._xr_trajectory.points):
            return
        self._xr_selected_waypoint_index = index
        self._sync_xr_point_form()

    def _xr_select_relative_point(self, offset: int) -> None:
        if self._xr_trajectory is None:
            return
        count = len(self._xr_trajectory.points)
        self._xr_selected_waypoint_index = (
            self._xr_selected_waypoint_index + offset
        ) % count
        self._sync_xr_point_form()

    def _xr_route_point_moved(self, index: int, position: Vec3) -> None:
        if not self._xr_editor_active or self._xr_trajectory is None:
            return
        waypoints = list(self._xr_trajectory.points)
        waypoints[index] = replace(waypoints[index], position=position)
        self._xr_trajectory = replace(self._xr_trajectory, points=tuple(waypoints))
        self._xr_selected_waypoint_index = index
        self._xr_editor_inputs_changed("route point moved", render=False)

    def _next_xr_waypoint_id(self) -> str:
        assert self._xr_trajectory is not None
        used = {waypoint.id for waypoint in self._xr_trajectory.points}
        number = 1
        while f"point-{number}" in used:
            number += 1
        return f"point-{number}"

    def _xr_add_route_point(self) -> None:
        if self._xr_trajectory is None or self._xr_editor_scene is None:
            return
        last = self._xr_trajectory.points[-1]
        dx = max(self._xr_editor_scene.room_size.x * 0.08, 0.1)
        dy = max(self._xr_editor_scene.room_size.y * 0.05, 0.1)
        x = last.position.x + dx
        if x > self._xr_editor_scene.room_size.x:
            x = max(0.0, last.position.x - dx)
        y = last.position.y + dy
        if y > self._xr_editor_scene.room_size.y:
            y = max(0.0, last.position.y - dy)
        waypoint = RoutePointDraft(
            id=self._next_xr_waypoint_id(),
            time_s=last.time_s + max(1.0, self._xr_trajectory.sample_interval_s),
            position=Vec3(x, y, last.position.z),
        )
        self._xr_trajectory = replace(
            self._xr_trajectory,
            points=(*self._xr_trajectory.points, waypoint),
        )
        self._xr_selected_waypoint_index = len(self._xr_trajectory.points) - 1
        self._xr_editor_inputs_changed("route point added")

    def _xr_insert_route_point(self) -> None:
        if self._xr_trajectory is None:
            return
        index = self._xr_selected_waypoint_index
        if index >= len(self._xr_trajectory.points) - 1:
            self._xr_add_route_point()
            return
        before = self._xr_trajectory.points[index]
        after = self._xr_trajectory.points[index + 1]
        waypoint = RoutePointDraft(
            id=self._next_xr_waypoint_id(),
            time_s=(before.time_s + after.time_s) / 2.0,
            position=Vec3(
                (before.position.x + after.position.x) / 2.0,
                (before.position.y + after.position.y) / 2.0,
                (before.position.z + after.position.z) / 2.0,
            ),
        )
        waypoints = list(self._xr_trajectory.points)
        waypoints.insert(index + 1, waypoint)
        self._xr_trajectory = replace(self._xr_trajectory, points=tuple(waypoints))
        self._xr_selected_waypoint_index = index + 1
        self._xr_editor_inputs_changed("route point inserted")

    def _xr_delete_route_point(self) -> None:
        if self._xr_trajectory is None:
            return
        if len(self._xr_trajectory.points) <= 1:
            QMessageBox.warning(
                self,
                "Cannot delete point",
                "A trajectory requires at least one route point.",
            )
            return
        waypoints = list(self._xr_trajectory.points)
        del waypoints[self._xr_selected_waypoint_index]
        self._xr_trajectory = replace(self._xr_trajectory, points=tuple(waypoints))
        self._xr_selected_waypoint_index = min(
            self._xr_selected_waypoint_index,
            len(waypoints) - 1,
        )
        self._xr_editor_inputs_changed("route point deleted")

    def _xr_apply_route_point(self) -> None:
        if self._xr_trajectory is None or self._xr_editor_scene is None:
            return
        index = self._xr_selected_waypoint_index
        try:
            old = self._xr_trajectory.points[index]
            time_s = 0.0 if index == 0 else self.xr_point_time.value()
            updated = replace(
                old,
                position=Vec3(
                    self.xr_point_x.value(),
                    self.xr_point_y.value(),
                    self.xr_point_z.value(),
                ),
                time_s=time_s,
            )
            waypoints = list(self._xr_trajectory.points)
            waypoints[index] = updated
            candidate = replace(self._xr_trajectory, points=tuple(waypoints))
            if self.xr_timing_mode.currentData() == "speed" and index > 0:
                if self.trajectory_backend is None:
                    raise TrajectoryBackendUnavailable(
                        "speed retiming waits for the external B trajectory backend"
                    )
                candidate = self.trajectory_backend.retime_from_previous_speed(
                    candidate, index, self.xr_point_speed.value()
                )
            if self.trajectory_backend is not None:
                self.trajectory_backend.validate(self._xr_editor_scene, candidate)
        except Exception as exc:
            QMessageBox.critical(self, "Invalid route point", str(exc))
            self.xr_route_status.setText(f"Route invalid: {exc}")
            self.xr_route_status.setStyleSheet("color:#b91c1c;font-weight:600")
            return
        self._xr_trajectory = candidate
        self._xr_editor_inputs_changed("route point form applied")

    def _xr_editor_inputs_changed(self, reason: str, *, render: bool = True) -> None:
        if not self._xr_editor_active:
            return
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        self._xr_field_debounce.stop()
        self._debounce.stop()
        self._version += 1
        self._xr_demo_start_pending = False
        self._xr_pending_run_request = None
        self._xr_pending_field_request = None
        self._cancel_active()
        self._xr_result = None
        self._xr_static_field = None
        self._xr_no_ris_field = None
        self._xr_field_scales = {}
        self._xr_field_runtime_summary = ""
        self._xr_field_cache = {}
        self._xr_static_field_key = None
        self._xr_field_inflight_key = None
        self._xr_sample_lookup = {}
        if self._xr_editor_scene is not None:
            pending = (
                "joint command pending backend"
                if len(self._xr_editor_scene.ris_surfaces) == 2
                else "command pending"
            )
            self._xr_ris_command_states = {
                ris.id: ("disabled" if not ris.enabled else pending)
                for ris in self._xr_editor_scene.ris_surfaces
            }
        self.scene_view.clear_field_overlays()
        self.pattern_view.set_status(
            "Command pending",
            "Scene/route changed; old commands and fields were invalidated. Run three modes again.",
        )
        self.pattern_view.setVisible(self.show_pattern.isChecked())
        self.power_metric.setText("Power: pending")
        self.snr_metric.setText("SNR: pending")
        self.gain_metric.setText("RIS Gain: pending")
        self.coverage_metric.setText("Time: —")
        self.dead_zone_metric.setText("RX: —")
        self.runtime_metric.setText("Sample: —")
        self.xr_command_status.setText("Command: pending · no stale command displayed")
        self.xr_field_status.setText("Field map: pending · no stale field displayed")
        route_valid = False
        route_error: str | None = None
        try:
            if self._xr_editor_scene is None or self._xr_trajectory is None:
                raise ValueError("XR editor inputs are unavailable")
            if self._xr_joint_ris_backend_pending(self._xr_editor_scene):
                enabled_count = sum(
                    ris.enabled for ris in self._xr_editor_scene.ris_surfaces
                )
                route_error = (
                    "joint dual-RIS complex-channel backend pending C/D"
                    if len(self._xr_editor_scene.ris_surfaces) == 2
                    else "exactly one RIS must be enabled for the current backend"
                )
                self.xr_route_status.setText(
                    "RIS editing ready · run blocked · "
                    f"{len(self._xr_editor_scene.ris_surfaces)} instances / "
                    f"{enabled_count} enabled · {route_error}"
                )
                self.xr_route_status.setStyleSheet(
                    "color:#b45309;font-weight:600"
                )
            elif self.trajectory_backend is None:
                raise TrajectoryBackendUnavailable(
                    f"{EXPECTED_TRAJECTORY_INTERFACE_VERSION} adapter is not connected"
                )
            else:
                snapshot = self.trajectory_backend.validate(
                    self._xr_editor_scene,
                    self._xr_trajectory,
                )
                samples = self.trajectory_backend.sample(snapshot)
                self.xr_route_status.setText(
                    f"Route valid · {self.trajectory_backend.interface_version} · "
                    f"{len(self._xr_trajectory.points)} points · {len(samples)} samples"
                )
                self.xr_route_status.setStyleSheet("color:#15803d")
                route_valid = True
        except TrajectoryBackendUnavailable as exc:
            self.xr_route_status.setText(
                f"Route draft editable · pending B interface: {exc}"
            )
            self.xr_route_status.setStyleSheet("color:#b45309;font-weight:600")
            route_error = str(exc)
        except Exception as exc:
            self.xr_route_status.setText(f"Route invalid: {exc}")
            self.xr_route_status.setStyleSheet("color:#b91c1c;font-weight:600")
            route_error = str(exc)
        self._xr_route_valid = route_valid
        self.xr_sample_label.setText(f"Pending run · {reason}")
        self._set_xr_controls_ready(False)
        self.xr_run_button.setEnabled(route_valid)
        self.xr_future_field_button.setEnabled(
            route_valid
            and self._xr_is_full_future_scene()
            and self._xr_future_backend_ready()
        )
        if render:
            self._render_xr_editor_inputs()
        else:
            self._sync_xr_point_form()
            self._sync_xr_ris_controls()
        self.scene_view.set_editable_route_validity(route_valid, route_error)
        self.statusBar().showMessage(
            f"XR editor input changed ({reason}) · previous result invalidated"
        )

    def _xr_load_template(self) -> None:
        try:
            scene = create_xr_editor_scene(str(self.xr_template_combo.currentData()))
            self._validate_xr_editor_scene(scene)
            trajectory = self._default_xr_editor_trajectory(scene)
            if self.trajectory_backend is not None:
                self.trajectory_backend.validate(scene, trajectory)
        except Exception as exc:
            QMessageBox.critical(self, "Template load failed", str(exc))
            return
        self._xr_editor_scene = scene
        self._xr_trajectory = trajectory
        self._xr_selected_waypoint_index = 0
        self._xr_selected_ris_id = scene.ris_surfaces[0].id
        self._xr_editor_inputs_changed("scene template loaded")

    def _xr_load_scene(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load XR Scene v1",
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            scene = Scene.load(path)
            self._validate_xr_editor_scene(scene)
            trajectory = self._xr_trajectory
            if trajectory is None:
                trajectory = self._default_xr_editor_trajectory(scene)
            if self._xr_joint_ris_backend_pending(scene):
                trajectory = self._default_xr_editor_trajectory(scene)
            elif self.trajectory_backend is None:
                trajectory = self._default_xr_editor_trajectory(scene)
            else:
                try:
                    self.trajectory_backend.validate(scene, trajectory)
                except ValueError:
                    trajectory = self._default_xr_editor_trajectory(scene)
                self.trajectory_backend.validate(scene, trajectory)
        except Exception as exc:
            QMessageBox.critical(self, "Scene load failed", str(exc))
            return
        self._xr_editor_scene = scene
        self._xr_trajectory = trajectory
        self._xr_selected_waypoint_index = 0
        self._xr_selected_ris_id = scene.ris_surfaces[0].id
        self._xr_editor_inputs_changed("Scene v1 loaded")

    def _xr_save_route(self) -> None:
        if self._xr_trajectory is None or self._xr_editor_scene is None:
            return
        try:
            if self.trajectory_backend is None:
                raise TrajectoryBackendUnavailable(
                    "route save waits for the external B trajectory backend"
                )
            snapshot = self.trajectory_backend.validate(
                self._xr_editor_scene,
                self._xr_trajectory,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Route save failed", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {self.trajectory_backend.interface_version}",
            "xr_route.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            bound = self.trajectory_backend.save(snapshot, path)
            self.statusBar().showMessage(
                f"{self.trajectory_backend.interface_version} saved: {path} · "
                f"identity {bound.experiment_identity}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Route save failed", str(exc))

    def _xr_load_route(self) -> None:
        if self._xr_editor_scene is None:
            return
        if self.trajectory_backend is None:
            QMessageBox.information(
                self,
                "Trajectory backend pending",
                "Route loading waits for the external B trajectory backend.",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Load {self.trajectory_backend.interface_version}",
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            loaded = self.trajectory_backend.load(path)
            self._validate_xr_editor_scene(loaded.scene)
        except Exception as exc:
            QMessageBox.critical(self, "Route load failed", str(exc))
            return
        self._xr_editor_scene = copy.deepcopy(loaded.scene)
        self._xr_trajectory = loaded.draft
        self._xr_selected_waypoint_index = 0
        self._xr_editor_inputs_changed("versioned trajectory loaded")

    def _run_xr_future_fixed_field(self) -> None:
        """Queue one selected-point exact M8 field batch, never a route-wide A."""
        if self._xr_editor_scene is None or self._xr_trajectory is None:
            return
        try:
            if self.trajectory_backend is None:
                raise TrajectoryBackendUnavailable(
                    "Future fixed field requires the versioned route backend"
                )
            snapshot = self.trajectory_backend.validate(
                self._xr_editor_scene,
                self._xr_trajectory,
            )
            if not self._xr_is_full_future_scene():
                raise ValueError(
                    "Select the full Future Smart Space template before building"
                )
            if not self._xr_future_backend_ready():
                raise ValueError(
                    "Select a supported XR Future coefficient model"
                )
            coefficient_model = self._xr_future_coefficient_model()
            trajectory = self.trajectory_backend.sample(snapshot)
            if not trajectory:
                raise ValueError("trajectory backend returned no samples")
            first = self._xr_trajectory.points[0]
            selected = self._xr_trajectory.points[
                self._xr_selected_waypoint_index
            ]
            request = XRFutureFixedFieldRequest(
                scene=copy.deepcopy(snapshot.scene),
                static_position=first.position,
                selected_position=selected.position,
                selected_point_id=selected.id,
                experiment_identity=snapshot.experiment_identity,
                scene_identity=snapshot.scene_identity,
                trajectory_identity=snapshot.trajectory_identity,
                coefficient_model_identity=coefficient_model.identity,
                trajectory=tuple(trajectory),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Cannot build Future fixed field", str(exc))
            return

        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        self._xr_field_debounce.stop()
        self._version += 1
        self._cancel_active()
        self._xr_pending_run_request = request
        self._xr_demo_start_pending = True
        self._xr_cancel_waiting_for_termination = False
        self._xr_result = None
        self._xr_static_field = None
        self._xr_no_ris_field = None
        self._xr_field_scales = {}
        self._xr_field_runtime_summary = ""
        self._xr_field_cache = {}
        self._xr_static_field_key = None
        self._xr_pending_field_request = None
        self._xr_field_inflight_key = None
        self._xr_sample_lookup = {}
        self.scene_view.clear_field_overlays()
        self.pattern_view.set_status(
            "Future command batch pending",
            "Static focuses route point 1; Adaptive focuses the selected point.",
        )
        self.xr_command_status.setText(
            f"Commands: preparing exact M8 · selected {selected.id}"
        )
        self.xr_field_status.setText(
            "Future fixed field queued · Production M8 · "
            f"Fixed grid {self._xr_future_grid()[0]}×{self._xr_future_grid()[1]} · "
            "no stale field displayed"
        )
        self.xr_sample_label.setText(
            "Fixed-grid batch only · not a whole-route coefficient matrix"
        )
        self._set_xr_controls_ready(False)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("XR Future exact M8 fixed field queued…")
        self._start_xr_demo_worker()

    def _run_xr_editor(self) -> None:
        if self._xr_editor_scene is None or self._xr_trajectory is None:
            return
        try:
            if self.trajectory_backend is None:
                raise TrajectoryBackendUnavailable(
                    "three-mode run waits for the external B trajectory backend"
                )
            snapshot = self.trajectory_backend.validate(
                self._xr_editor_scene,
                self._xr_trajectory,
            )
            trajectory = self.trajectory_backend.sample(snapshot)
            if not trajectory:
                raise ValueError("trajectory backend returned no samples")
        except Exception as exc:
            QMessageBox.critical(self, "Cannot run trajectory", str(exc))
            return
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        self._xr_field_debounce.stop()
        self._version += 1
        self._cancel_active()
        self._xr_pending_run_request = snapshot
        self._xr_demo_start_pending = True
        self._xr_cancel_waiting_for_termination = False
        self._xr_result = None
        self._xr_static_field = None
        self._xr_no_ris_field = None
        self._xr_field_scales = {}
        self._xr_field_runtime_summary = ""
        self._xr_field_cache = {}
        self._xr_static_field_key = None
        self._xr_pending_field_request = None
        self._xr_field_inflight_key = None
        self._xr_sample_lookup = {}
        self.scene_view.clear_field_overlays()
        self.pattern_view.set_status(
            "Command calculating…",
            "Worker owns the validated immutable XR route experiment snapshot.",
        )
        self.xr_command_status.setText("Command: calculating from run snapshot")
        self.xr_field_status.setText("Field map: pending behind three-mode links")
        self.xr_sample_label.setText(
            f"Running {len(trajectory)} samples × 3 modes…"
        )
        self._set_xr_controls_ready(False)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("XR three-mode run queued…")
        self._start_xr_demo_worker()

    def _cancel_xr_editor_run(self) -> None:
        if not self._xr_editor_active:
            return
        worker_active = self._xr_active_worker is not None
        future_worker = isinstance(
            self._xr_active_worker,
            XRFuturePreparedFieldWorker,
        )
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        self._version += 1
        self._xr_demo_start_pending = False
        self._xr_pending_run_request = None
        self._xr_pending_field_request = None
        self._xr_field_debounce.stop()
        self._cancel_active()
        if future_worker:
            self.xr_field_status.setText(
                "Future result cancelled and isolated · D P0 stops the cold build "
                "at a receiver-batch boundary"
            )
        elif self._xr_result is not None:
            self.xr_field_status.setText(
                "Field request cancelled · cached current-run results remain available"
            )
        self._xr_cancel_waiting_for_termination = worker_active
        self.xr_cancel_button.setEnabled(False)
        self.xr_run_button.setEnabled(True)
        if worker_active:
            self.xr_sample_label.setText(
                "Cancellation requested · waiting for worker termination"
            )
            self.statusBar().showMessage(
                "XR cancellation requested; worker has not terminated yet"
            )
        else:
            self.xr_sample_label.setText("Run cancelled · no active worker")
            self.statusBar().showMessage("XR queued run cancelled")

    def _enter_xr_editor(self) -> None:
        if self._xr_demo_active:
            return
        self._xr_resume_smart_space_refresh = self._smart_space_refresh_pending
        self._xr_demo_active = True
        self._xr_editor_active = True
        self._smart_metric_texts = tuple(
            widget.text()
            for widget in (
                self.power_metric,
                self.snr_metric,
                self.gain_metric,
                self.coverage_metric,
                self.dead_zone_metric,
                self.runtime_metric,
            )
        )
        self._xr_result = None
        self._xr_playback_waiting_for_field = False
        self._xr_pending_run_request = None
        self._xr_demo_start_pending = False
        self._xr_cancel_waiting_for_termination = False
        self._xr_editor_scene = create_xr_editor_scene("complex_office")
        self._validate_xr_editor_scene(self._xr_editor_scene)
        self._xr_selected_ris_id = self._xr_editor_scene.ris_surfaces[0].id
        self._xr_ris_command_states = {
            self._xr_selected_ris_id: "command pending"
        }
        self._xr_route_valid = False
        self._xr_trajectory = self._default_xr_editor_trajectory(
            self._xr_editor_scene
        )
        self._xr_selected_waypoint_index = 0
        self.xr_template_combo.setCurrentIndex(
            self.xr_template_combo.findData("complex_office")
        )
        self.xr_mode_combo.blockSignals(True)
        self.xr_mode_combo.setCurrentText(NO_RIS_MODE)
        self.xr_mode_combo.blockSignals(False)
        self.xr_quantity_combo.blockSignals(True)
        self.xr_quantity_combo.setCurrentText("接收功率")
        self.xr_quantity_combo.blockSignals(False)
        self._xr_playback_timer.stop()
        self._xr_field_debounce.stop()
        self._debounce.stop()
        self._debounced_action = None
        self._version += 1
        self._cancel_active()
        self._set_smart_space_widgets_enabled(False)
        self.xr_controls.setTitle("XR Scene & Route Editor · non-release")
        interface_label = (
            self.trajectory_backend.interface_version
            if self.trajectory_backend is not None
            else f"{EXPECTED_TRAJECTORY_INTERFACE_VERSION} pending"
        )
        self.xr_editor_group.setTitle(f"Scene & Route · {interface_label}")
        self.xr_controls.setVisible(True)
        self.xr_editor_group.setVisible(True)
        self.future_badge.setText("Non-release XR Editor Prototype")
        self._xr_editor_inputs_changed("editor opened")

    def _scenario_changed(self, index: int) -> None:
        mode = self.scenario_combo.itemData(index)
        if mode == "xr_dynamic_room_mvp":
            if self._xr_editor_active:
                self._leave_xr_demo()
            self._enter_xr_demo()
        elif mode == "xr_route_editor":
            if self._xr_demo_active and not self._xr_editor_active:
                self._leave_xr_demo()
            self._enter_xr_editor()
        else:
            self._leave_xr_demo()

    def _enter_xr_demo(self) -> None:
        if self._xr_demo_active:
            return
        self._xr_resume_smart_space_refresh = self._smart_space_refresh_pending
        self._xr_demo_active = True
        self._xr_editor_active = False
        self._xr_editor_scene = None
        self._xr_selected_ris_id = None
        self._xr_ris_command_states = {}
        self._xr_route_valid = False
        self._xr_trajectory = None
        self._xr_pending_run_request = None
        self._xr_cancel_waiting_for_termination = False
        self._smart_metric_texts = tuple(
            widget.text()
            for widget in (
                self.power_metric,
                self.snr_metric,
                self.gain_metric,
                self.coverage_metric,
                self.dead_zone_metric,
                self.runtime_metric,
            )
        )
        self._xr_result = None
        self._xr_playback_waiting_for_field = False
        self._xr_static_field = None
        self._xr_no_ris_field = None
        self._xr_field_scales = {}
        self._xr_field_runtime_summary = ""
        self._xr_field_cache = {}
        self._xr_static_field_key = None
        self._xr_pending_field_request = None
        self._xr_field_inflight_key = None
        self._xr_sample_lookup = {}
        self._xr_sample_index = 0
        self.xr_mode_combo.blockSignals(True)
        self.xr_mode_combo.setCurrentText(NO_RIS_MODE)
        self.xr_mode_combo.blockSignals(False)
        self.xr_quantity_combo.blockSignals(True)
        self.xr_quantity_combo.setCurrentText("接收功率")
        self.xr_quantity_combo.blockSignals(False)
        self.xr_timeline.setValue(0)
        self._xr_playback_timer.stop()
        self._xr_field_debounce.stop()
        self._debounce.stop()
        self._debounced_action = None
        self._version += 1
        self._cancel_active()
        self._set_smart_space_widgets_enabled(False)
        self.xr_controls.setTitle("XR MVP Playback")
        self.xr_controls.setVisible(True)
        self.xr_editor_group.setVisible(False)
        self._set_xr_controls_ready(False)
        self.future_badge.setText("Non-release XR Prototype · Adaptive provisional")

        demo_scene = create_mvp_scene()
        trajectory = build_trajectory()
        self.scene_view.set_options(
            show_labels=self.show_labels.isChecked(),
            show_rays=False,
        )
        self.scene_view.load_scene(demo_scene)
        self.scene_view.set_entities_draggable(False)
        self.scene_view.show_trajectory([sample.position for sample in trajectory])
        self.pattern_view.set_patterns(
            np.zeros(demo_scene.ris_surfaces[0].cell_count),
            np.zeros(demo_scene.ris_surfaces[0].cell_count),
            demo_scene.ris_surfaces[0].ny,
            demo_scene.ris_surfaces[0].nx,
            phase_bits=demo_scene.ris_surfaces[0].phase_bits,
            pattern_source="XR MVP Adaptive · calculating",
            diagnostics=self._pattern_diagnostics(
                demo_scene.ris_surfaces[0],
                scene=demo_scene,
            ),
        )
        self.power_metric.setText("Power: calculating…")
        self.snr_metric.setText("SNR: calculating…")
        self.gain_metric.setText("Mode: —")
        self.coverage_metric.setText("Time: 0.0 s")
        self.dead_zone_metric.setText("RX: (8.50, 4.00, 1.20) m")
        self.runtime_metric.setText("Sample: 1/11")
        self.xr_sample_label.setText("Precomputing 11 × 3 production link states…")
        self.xr_field_status.setText(
            f"Field map calculating… · {self._xr_field_precision_label()}"
        )
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("正在后台计算 XR Dynamic Room MVP…")

        self._xr_demo_start_pending = True
        self._start_xr_demo_worker()

    def _start_xr_demo_worker(self) -> None:
        if not self._xr_demo_active or not self._xr_demo_start_pending:
            return
        if (
            self._xr_active_worker is not None
            or self._smart_space_active_worker is not None
        ):
            return
        self._xr_demo_start_pending = False
        request = self._xr_pending_run_request
        future_request = isinstance(request, XRFutureFixedFieldRequest)
        if future_request:
            worker = XRFuturePreparedFieldWorker(
                self._version,
                request,
                self._xr_future_config(),
            )
        elif request is None:
            worker = XRDynamicRoomWorker(self._version)
        else:
            worker = XRDynamicRoomWorker(
                self._version,
                route_experiment=request,
            )
        self._xr_pending_run_request = None
        worker.signals.progress.connect(
            self._xr_future_field_progress
            if future_request
            else self._xr_link_progress
        )
        worker.signals.partial.connect(self._xr_links_ready)
        worker.signals.finished.connect(
            self._xr_future_field_ready
            if future_request
            else self._xr_demo_ready
        )
        worker.signals.failed.connect(self._worker_failed)
        worker.signals.terminated.connect(self._xr_worker_terminated)
        self._xr_active_worker = worker
        self._active_worker = worker
        self._workers.append(worker)
        if future_request:
            self._xr_future_started_at = time.perf_counter()
            self._xr_future_elapsed_timer.start()
        self.thread_pool.start(worker)

    def _update_xr_future_elapsed(self) -> None:
        if self._xr_future_started_at is None:
            self._xr_future_elapsed_timer.stop()
            return
        worker = self._xr_active_worker
        if not isinstance(worker, XRFuturePreparedFieldWorker):
            self._xr_future_elapsed_timer.stop()
            return
        elapsed = time.perf_counter() - self._xr_future_started_at
        width, height = worker.config.grid_width, worker.config.grid_height
        model_label = self._xr_future_model_label(
            worker.request.coefficient_model_identity
        )
        self.xr_field_status.setText(
            f"Cold {model_label} matrix build running… · "
            f"elapsed {elapsed:.1f} s · Fixed grid {width}×{height} · no stale field"
        )

    def _xr_future_field_progress(
        self,
        version: int,
        done: int,
        total: int,
        _fraction: float,
    ) -> None:
        if version != self._version or not self._xr_demo_active:
            return
        if done == 0:
            self.progress.setRange(0, 0)
            self._update_xr_future_elapsed()
            return
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        receiver_total = total - 2
        worker = self._xr_active_worker
        model_label = (
            self._xr_future_model_label(worker.request.coefficient_model_identity)
            if isinstance(worker, XRFuturePreparedFieldWorker)
            else "Future"
        )
        if done <= receiver_total:
            label = (
                f"Cold {model_label} matrix build · receivers {done}/{receiver_total}"
                if done < receiver_total
                else f"Cold {model_label} matrix built · receivers {done}/{receiver_total}"
            )
        elif done == receiver_total + 1:
            label = "Static command evaluated"
        else:
            label = "Adaptive command evaluated"
        self.xr_field_status.setText(
            f"{label} · work {done}/{total}"
        )

    def _xr_link_progress(
        self,
        version: int,
        done: int,
        total: int,
        _fraction: float,
    ) -> None:
        if version != self._version or not self._xr_demo_active:
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(int(done * 25 / max(total, 1)))
        self.xr_sample_label.setText(
            f"Precomputing three-mode links… {done}/{total} trajectory samples"
        )

    def _xr_links_ready(self, version: int, result: MVPComputation) -> None:
        if version != self._version or not self._xr_demo_active:
            return
        self._xr_result = result
        self._xr_sample_lookup = {
            (sample.trajectory.sample_index, sample.mode): sample
            for sample in result.samples
        }
        self._xr_field_cache_limit = len(result.trajectory) + 1
        self.scene_view.load_scene(result.scene)
        self.scene_view.set_entities_draggable(False)
        if self._xr_editor_active and self._xr_trajectory is not None:
            self.scene_view.set_draggable_entity_ids(
                {ris.id for ris in result.scene.ris_surfaces}
            )
            self._xr_ris_command_states = {
                result.scene.ris_surfaces[0].id: (
                    "Static frozen · Adaptive per selected receiver"
                )
            }
            self._sync_xr_ris_controls()
            self.scene_view.show_editable_route(
                [waypoint.position for waypoint in self._xr_trajectory.points],
                selected_index=self._xr_selected_waypoint_index,
            )
        else:
            self.scene_view.show_trajectory(
                [sample.position for sample in result.trajectory]
            )
        self.xr_timeline.setRange(0, len(result.trajectory) - 1)
        self._set_xr_controls_ready(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(25)
        self._set_xr_sample(0)
        self.statusBar().showMessage(
            "XR link states cached · field map calculating in background…"
        )

    def _xr_future_field_ready(
        self,
        version: int,
        result: XRFuturePreparedFieldResult,
    ) -> None:
        if version != self._version or not self._xr_demo_active:
            return
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        if self.trajectory_backend is None or self._xr_trajectory is None:
            return
        try:
            current = self.trajectory_backend.validate(
                self._xr_editor_scene,
                self._xr_trajectory,
            )
        except Exception as exc:
            self.xr_field_status.setText(
                f"Future result rejected after route validation failed: {exc}"
            )
            return
        expected = (
            result.request.experiment_identity,
            result.request.scene_identity,
            result.request.trajectory_identity,
        )
        actual = (
            current.experiment_identity,
            current.scene_identity,
            current.trajectory_identity,
        )
        if actual != expected:
            self.scene_view.clear_field_overlays()
            self.xr_field_status.setText(
                "Future result rejected · Scene/trajectory/experiment identity changed"
            )
            return
        if (
            result.coefficient_model_identity
            != result.request.coefficient_model_identity
        ):
            self.scene_view.clear_field_overlays()
            self.xr_field_status.setText(
                "Future result rejected · coefficient-model identity mismatch"
            )
            return
        if self._xr_result is not result.mvp:
            self._xr_links_ready(version, result.mvp)
        self._xr_static_field = result.static_field
        self._xr_static_field_key = result.static_key
        self._xr_cache_field(result.static_key, result.static_field)
        for adaptive_key, adaptive_field in result.adaptive_fields:
            self._xr_cache_field(adaptive_key, adaptive_field)
        self._xr_no_ris_field = self._derive_no_ris_field(
            result.static_field,
            result.mvp.scene,
        )
        self._xr_field_scales = {
            "接收功率": self.scene_view.field_value_range(
                self._xr_no_ris_field.received_power_dbm,
                result.static_field.received_power_dbm,
                *(field.received_power_dbm for _key, field in result.adaptive_fields),
            ),
            "SNR": self.scene_view.field_value_range(
                self._xr_no_ris_field.snr_db,
                result.static_field.snr_db,
                *(field.snr_db for _key, field in result.adaptive_fields),
            ),
        }
        hot_static_ms = result.static_field.runtime_s * 1000.0
        hot_adaptive_ms = result.adaptive_field.runtime_s * 1000.0
        coefficient_mib = result.coefficient_bytes / 2**20
        playback_fps = 1000.0 / self._xr_playback_timer.interval()
        self._xr_field_runtime_summary = (
            f"cold {result.build_runtime_s:.2f} s · "
            f"hot Static {hot_static_ms:.2f} ms · "
            f"hot Adaptive {hot_adaptive_ms:.2f} ms · "
            f"route hot {len(result.adaptive_fields)} commands "
            f"{result.adaptive_batch_runtime_s * 1000.0:.2f} ms total · "
            f"playback {playback_fps:.1f} fps · coefficients {coefficient_mib:.1f} MiB · "
            f"model {result.coefficient_model_identity} · "
            f"matrix {result.coefficient_identity[:23]}…"
        )
        self._set_xr_sample(0)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.xr_field_status.setText(
            "Future fixed field ready · "
            f"{self._xr_future_model_label(result.coefficient_model_identity)} · "
            f"Fixed grid {result.static_key.grid_width}×"
            f"{result.static_key.grid_height} · "
            f"{self._xr_field_runtime_summary}"
        )
        self.xr_route_status.setText(
            f"Fixed grid prepared once · selected {result.request.selected_point_id} · "
            f"{len(result.mvp.trajectory)} route commands · experiment "
            f"{result.request.experiment_identity[:23]}… · not a full-route matrix"
        )
        self.xr_route_status.setStyleSheet("color:#15803d")
        self._set_xr_controls_ready(True)
        self.statusBar().showMessage(
            "XR Future fixed-grid multi-command batch ready; no route-wide reuse claimed"
        )

    def _xr_demo_ready(self, version: int, result: XRDynamicRoomResult) -> None:
        if version != self._version or not self._xr_demo_active:
            return
        if self._xr_result is not result.mvp:
            self._xr_links_ready(version, result.mvp)
        self._xr_static_field = result.field_map
        field_key = result.field_key
        if field_key is None:
            field_key = build_xr_field_cache_key(
                result.mvp.scene,
                SimulationEngine(),
                ControllerModel(),
                self._xr_fast_config(),
                _pattern_hash(result.mvp.static_pattern),
            )
        self._xr_static_field_key = field_key
        self._xr_cache_field(field_key, result.field_map)
        self._xr_no_ris_field = self._derive_no_ris_field(
            result.field_map,
            result.mvp.scene,
        )
        self._xr_field_scales = {
            "接收功率": self.scene_view.field_value_range(
                self._xr_no_ris_field.received_power_dbm,
                self._xr_static_field.received_power_dbm,
            ),
            "SNR": self.scene_view.field_value_range(
                self._xr_no_ris_field.snr_db,
                self._xr_static_field.snr_db,
            ),
        }
        self._redraw_xr_field()
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.xr_field_status.setText(
            f"Field map cached · {self._xr_field_precision_label()} · "
            f"{result.field_map.runtime_s:.2f} s · Adaptive fields on demand"
        )
        if self._xr_editor_active:
            interface_version = (
                self.trajectory_backend.interface_version
                if self.trajectory_backend is not None
                else f"{EXPECTED_TRAJECTORY_INTERFACE_VERSION} pending"
            )
            self.xr_route_status.setText(
                f"Run snapshot complete · {interface_version} · "
                f"{len(result.mvp.trajectory)} samples"
            )
            self.xr_route_status.setStyleSheet("color:#15803d")
        self.statusBar().showMessage(
            "XR Adaptive prototype ready · Static field cached; Adaptive fields on demand"
        )
        if self._xr_pending_field_request is not None:
            self._start_pending_xr_field()

    @staticmethod
    def _xr_fast_config() -> SimulationConfig:
        fast = field_quality_preset("fast")
        return SimulationConfig(fast.grid_width, fast.grid_height, "power")

    def _xr_future_config(self) -> SimulationConfig:
        width, height = self._xr_future_grid()
        return SimulationConfig(width, height, "power", batch_size=8)

    def _xr_field_precision_label(self) -> str:
        """Keep physics precision distinct from the display-grid preset."""
        if self._xr_static_field_key is not None:
            width = self._xr_static_field_key.grid_width
            height = self._xr_static_field_key.grid_height
            model_identity = self._xr_static_field_key.coefficient_model_identity
        else:
            fast = field_quality_preset("fast")
            width, height = fast.grid_width, fast.grid_height
            model_identity = (
                self._xr_future_coefficient_model().identity
                if self._xr_editor_active and self._xr_is_full_future_scene()
                else PRODUCTION_RIS_COEFFICIENT_MODEL.identity
            )
        if (width, height) == (48, 36):
            grid_kind = "Full fixed grid"
        elif (width, height) in {(8, 6), (16, 12)}:
            grid_kind = "Small fixed grid"
        else:
            grid_kind = "Fast grid"
        return (
            f"{self._xr_future_model_label(model_identity)} · "
            f"{grid_kind} {width}×{height}"
        )

    def _xr_cache_field(
        self,
        key: XRFieldCacheKey,
        field: FieldMapResult,
    ) -> None:
        """Store one complete field in the bounded prototype result cache."""
        if (
            key not in self._xr_field_cache
            and len(self._xr_field_cache) >= self._xr_field_cache_limit
        ):
            raise RuntimeError("XR prototype field cache limit exceeded")
        self._xr_field_cache[key] = field

    def _xr_field_key_for_sample(
        self,
        sample: DynamicLinkSample,
    ) -> XRFieldCacheKey | None:
        if self._xr_static_field_key is None or not sample.command_hash:
            return None
        return replace(self._xr_static_field_key, command_hash=sample.command_hash)

    def _queue_xr_adaptive_field(
        self,
        sample: DynamicLinkSample,
        key: XRFieldCacheKey,
    ) -> None:
        if key in self._xr_field_cache:
            self._xr_field_debounce.stop()
            self._xr_pending_field_request = None
            return
        active_field_worker = self._xr_active_worker
        if (
            key == self._xr_field_inflight_key
            and active_field_worker is not None
            and not active_field_worker.cancel_requested
        ):
            self._xr_field_debounce.stop()
            self._xr_pending_field_request = None
            self.xr_field_status.setText(
                "Adaptive field calculating… · sample "
                f"{sample.trajectory.sample_index + 1}/"
                f"{len(self._xr_result.trajectory) if self._xr_result else '?'}"
            )
            return
        self._xr_pending_field_request = (
            sample.trajectory.sample_index,
            sample,
            key,
        )
        self._xr_field_debounce.start()
        self.xr_field_status.setText(
            f"Adaptive field queued… · {self._xr_field_precision_label()} · "
            "playback remains result-only"
        )

    def _start_pending_xr_field(self) -> None:
        if (
            not self._xr_demo_active
            or self._xr_result is None
            or self._xr_pending_field_request is None
        ):
            return
        if self._xr_active_worker is not None:
            return
        sample_index, sample, key = self._xr_pending_field_request
        if key in self._xr_field_cache:
            self._xr_pending_field_request = None
            self._redraw_xr_field()
            return
        commanded = sample.commanded_pattern
        if commanded is None or sample.command_hash != key.command_hash:
            raise RuntimeError("XR Adaptive field request lacks its exact command snapshot")
        self._xr_pending_field_request = None
        worker = XRAdaptiveFieldWorker(
            self._version,
            sample_index,
            copy.deepcopy(self._xr_result.scene),
            self._xr_fast_config(),
            commanded,
            sample.command_hash,
            key,
        )
        worker.signals.finished.connect(self._xr_adaptive_field_ready)
        worker.signals.failed.connect(self._worker_failed)
        worker.signals.terminated.connect(self._xr_worker_terminated)
        self._xr_active_worker = worker
        self._active_worker = worker
        self._xr_field_inflight_key = key
        self._workers.append(worker)
        self.progress.setRange(0, 0)
        state = (
            "Adaptive field buffering… · playback paused"
            if self._xr_playback_waiting_for_field
            else "Adaptive field calculating…"
        )
        self.xr_field_status.setText(
            f"{state} · sample {sample_index + 1}/"
            f"{len(self._xr_result.trajectory)} · {self._xr_field_precision_label()}"
        )
        self.thread_pool.start(worker)

    def _xr_adaptive_field_ready(
        self,
        version: int,
        result: XRAdaptiveFieldResult,
    ) -> None:
        if version != self._version or not self._xr_demo_active:
            return
        self._xr_cache_field(result.key, result.field_map)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        current = self._xr_sample_lookup.get(
            (self._xr_sample_index, ADAPTIVE_RIS_MODE)
        )
        current_key = None if current is None else self._xr_field_key_for_sample(current)
        if self.xr_mode_combo.currentText() == ADAPTIVE_RIS_MODE and current_key == result.key:
            self._redraw_xr_field()
            if self._xr_playback_waiting_for_field:
                self._xr_playback_waiting_for_field = False
                self._xr_playback_timer.start()
                self.statusBar().showMessage(
                    "Adaptive field ready · XR playback resumed"
                )
        else:
            self.statusBar().showMessage(
                "Adaptive field cached for sample "
                f"{result.sample_index + 1}/"
                f"{len(self._xr_result.trajectory) if self._xr_result else '?'}; "
                "current snapshot unchanged"
            )
        if (
            self._xr_pending_field_request is not None
            and not self._xr_field_debounce.isActive()
        ):
            self._start_pending_xr_field()

    def _xr_worker_terminated(self, _version: int, worker: object) -> None:
        """Release an XR worker only after its runnable has actually returned."""
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        if self._xr_active_worker is not worker:
            return
        self._xr_active_worker = None
        if self._active_worker is worker:
            self._active_worker = None
        if isinstance(worker, XRAdaptiveFieldWorker):
            self._xr_field_inflight_key = None
        if isinstance(worker, XRFuturePreparedFieldWorker):
            self._xr_future_elapsed_timer.stop()
            self._xr_future_started_at = None
        if self._closing:
            return
        if self._xr_cancel_waiting_for_termination:
            self._xr_cancel_waiting_for_termination = False
            if self._xr_editor_active:
                self.xr_sample_label.setText("Run cancelled · worker terminated")
                self.statusBar().showMessage(
                    "XR run cancelled; background worker terminated"
                )
                self._set_xr_controls_ready(self._xr_result is not None)
            return
        if self._xr_demo_start_pending:
            self._start_xr_demo_worker()
            return
        if (
            self._xr_demo_active
            and self._xr_pending_field_request is not None
            and not self._xr_field_debounce.isActive()
        ):
            self._start_pending_xr_field()
        elif (
            not self._xr_demo_active
            and self._debounced_action == "smart_space_refresh"
            and self._smart_space_active_worker is None
        ):
            self.start_smart_space_refresh()
        elif self._xr_editor_active:
            self._set_xr_controls_ready(self._xr_result is not None)

    @staticmethod
    def _derive_no_ris_field(
        static_field: FieldMapResult,
        scene: Scene,
    ) -> FieldMapResult:
        """Adapt the baseline arrays from one field solve for No RIS display."""
        noise_dbm = noise_power_dbm(
            scene.bandwidth_hz,
            scene.receiver().noise_figure_db,
        )
        baseline_snr = static_field.baseline_power_dbm - noise_dbm
        coverage = float(
            np.mean(baseline_snr >= scene.coverage_threshold_db) * 100.0
        )
        return replace(
            static_field,
            received_power_dbm=static_field.baseline_power_dbm,
            snr_db=baseline_snr,
            ris_gain_db=np.full_like(static_field.ris_gain_db, np.nan),
            coverage_percent=coverage,
            dead_zone_percent=100.0 - coverage,
            runtime_s=0.0,
        )

    def _redraw_xr_field(self, *_args: object) -> None:
        if not self._xr_demo_active:
            return
        mode = self.xr_mode_combo.currentText()
        quantity = self.xr_quantity_combo.currentText()
        if self._xr_static_field is None or self._xr_no_ris_field is None:
            self.scene_view.set_field_visible(False)
            self.xr_field_status.setText(
                "Field map calculating… · "
                f"{self._xr_field_precision_label()} · links remain playable when ready"
            )
            return
        if mode == NO_RIS_MODE and quantity == "RIS 增益":
            self._xr_field_debounce.stop()
            self._xr_pending_field_request = None
            self.scene_view.set_field_visible(False)
            self.xr_field_status.setText(
                "RIS Gain: N/A for No RIS · cached field remains unchanged"
            )
            return
        if mode == ADAPTIVE_RIS_MODE:
            sample = self._xr_sample_lookup.get(
                (self._xr_sample_index, ADAPTIVE_RIS_MODE)
            )
            key = None if sample is None else self._xr_field_key_for_sample(sample)
            field = None if key is None else self._xr_field_cache.get(key)
            if sample is None or key is None:
                self.scene_view.set_field_visible(False)
                self.xr_field_status.setText(
                    "Adaptive field waits for the initial Static field identity"
                )
                return
            if field is None:
                self.scene_view.set_field_visible(False)
                self._queue_xr_adaptive_field(sample, key)
                return
            self._xr_field_debounce.stop()
            self._xr_pending_field_request = None
        else:
            self._xr_field_debounce.stop()
            self._xr_pending_field_request = None
            field = (
                self._xr_static_field
                if mode == STATIC_RIS_MODE
                else self._xr_no_ris_field
            )
        self.scene_view.set_field_map(
            field,
            quantity,
            value_range=self._xr_field_scales.get(quantity),
        )
        self.scene_view.set_field_visible(self.show_field.isChecked())
        if mode == ADAPTIVE_RIS_MODE:
            if self._xr_field_runtime_summary:
                self.xr_field_status.setText(
                    "Adaptive field hot-cached · exact selected-point command · "
                    f"{self._xr_field_precision_label()} · "
                    f"{self._xr_field_runtime_summary}"
                )
            else:
                self.xr_field_status.setText(
                    "Adaptive field cached · exact sample command · "
                    f"{self._xr_field_precision_label()} · "
                    f"{field.runtime_s:.2f} s · cache {len(self._xr_field_cache)}/"
                    f"{self._xr_field_cache_limit}"
                )
        else:
            if self._xr_field_runtime_summary:
                self.xr_field_status.setText(
                    f"{mode} fixed field cached · {self._xr_field_precision_label()} · "
                    f"{self._xr_field_runtime_summary}"
                )
            else:
                self.xr_field_status.setText(
                    f"Field map cached · {self._xr_field_precision_label()} · "
                    f"{self._xr_static_field.runtime_s:.2f} s · Adaptive fields on demand"
                )

    def _buffer_adaptive_playback_if_needed(self) -> None:
        """Pause cold-cache playback until the current Adaptive field is ready."""
        if (
            not self._xr_playback_timer.isActive()
            or self.xr_mode_combo.currentText() != ADAPTIVE_RIS_MODE
            or self._xr_result is None
        ):
            return
        sample = self._xr_sample_lookup.get(
            (self._xr_sample_index, ADAPTIVE_RIS_MODE)
        )
        key = None if sample is None else self._xr_field_key_for_sample(sample)
        if key is None or key in self._xr_field_cache:
            return
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = True
        self._xr_field_debounce.stop()
        self.xr_field_status.setText(
            "Adaptive field buffering… · playback paused at sample "
            f"{self._xr_sample_index + 1}/{len(self._xr_result.trajectory)}"
        )
        if sample is not None:
            self._queue_xr_adaptive_field(sample, key)
            self._start_pending_xr_field()

    def _xr_mode_changed(self, _mode: str) -> None:
        if self.xr_mode_combo.currentText() != ADAPTIVE_RIS_MODE:
            resume_playback = self._xr_playback_waiting_for_field
            self._xr_playback_waiting_for_field = False
            if resume_playback:
                self._xr_playback_timer.start()
        self._set_xr_sample(self._xr_sample_index)

    def _set_xr_sample(self, index: int) -> None:
        if not self._xr_demo_active or self._xr_result is None:
            return
        index = max(0, min(int(index), len(self._xr_result.trajectory) - 1))
        mode = self.xr_mode_combo.currentText()
        sample = self._xr_sample_lookup[(index, mode)]
        self._xr_sample_index = index
        self.xr_timeline.blockSignals(True)
        self.xr_timeline.setValue(index)
        self.xr_timeline.blockSignals(False)
        if not self._xr_editor_active:
            self.scene_view.set_trajectory_index(index)
        self.scene_view.set_entity_visual_position(
            self._xr_result.scene.receiver().id,
            sample.trajectory.position,
        )

        ris = self._xr_result.scene.ris_surfaces[0]
        if mode == STATIC_RIS_MODE:
            commanded = self._xr_result.static_pattern
            pattern_source = "XR MVP Static RIS · frozen at t=0"
        elif mode == ADAPTIVE_RIS_MODE:
            commanded = sample.commanded_pattern
            if commanded is None:
                raise RuntimeError("XR Adaptive sample is missing its command snapshot")
            pattern_source = (
                "XR Adaptive RIS · per-sample Controller Focus · provisional"
            )
        else:
            commanded = np.zeros(ris.cell_count)
            pattern_source = "XR MVP No RIS · contribution disabled"
        self.pattern_view.set_patterns(
            commanded,
            commanded,
            ris.ny,
            ris.nx,
            phase_bits=ris.phase_bits,
            pattern_source=pattern_source,
            diagnostics=self._pattern_diagnostics(ris, scene=self._xr_result.scene),
        )
        self.pattern_view.setVisible(self.show_pattern.isChecked())
        if self._xr_editor_active:
            command_text = (
                "Command: none · RIS contribution disabled"
                if not sample.command_hash
                else f"Command: {sample.command_kind} · {sample.command_hash[:23]}…"
            )
            self.xr_command_status.setText(command_text)

        point = sample.trajectory.position
        self.power_metric.setText(
            f"Power: {sample.received_power_dbm:.2f} dBm"
        )
        self.snr_metric.setText(f"SNR: {sample.snr_db:.2f} dB")
        if mode in (STATIC_RIS_MODE, ADAPTIVE_RIS_MODE):
            baseline = self._xr_sample_lookup[(index, NO_RIS_MODE)]
            self.gain_metric.setText(
                "RIS Gain: "
                f"{sample.received_power_dbm - baseline.received_power_dbm:+.2f} dB"
                f" · Mode: {mode}"
            )
        else:
            self.gain_metric.setText(f"RIS Gain: N/A · Mode: {mode}")
        self.coverage_metric.setText(f"Time: {sample.trajectory.time_s:.1f} s")
        self.dead_zone_metric.setText(
            f"RX: ({point.x:.2f}, {point.y:.2f}, {point.z:.2f}) m"
        )
        self.runtime_metric.setText(
            f"Sample: {index + 1}/{len(self._xr_result.trajectory)}"
        )
        self.xr_sample_label.setText(
            f"t={sample.trajectory.time_s:.1f} s · "
            f"RX=({point.x:.2f}, {point.y:.2f}, {point.z:.2f}) m · "
            f"{mode}{' · provisional' if mode == ADAPTIVE_RIS_MODE else ''}"
        )
        self._redraw_xr_field()
        self._buffer_adaptive_playback_if_needed()

    def _play_xr_demo(self) -> None:
        if not self._xr_demo_active or self._xr_result is None:
            return
        if self._xr_sample_index >= len(self._xr_result.trajectory) - 1:
            self._set_xr_sample(0)
        self._xr_playback_timer.start()
        self._set_xr_sample(self._xr_sample_index)
        self._set_xr_controls_ready(True)
        self.statusBar().showMessage("XR MVP playback running")

    def _pause_xr_demo(self) -> None:
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._set_xr_controls_ready(self._xr_result is not None)
        if self._xr_demo_active and self._xr_result is not None:
            self.statusBar().showMessage("XR MVP playback paused")

    def _reset_xr_demo(self) -> None:
        self._pause_xr_demo()
        self._set_xr_sample(0)
        if self._xr_demo_active and self._xr_result is not None:
            self.statusBar().showMessage(
                f"XR playback reset to sample 1/{len(self._xr_result.trajectory)}"
            )

    def _advance_xr_sample(self) -> None:
        if not self._xr_demo_active or self._xr_result is None:
            self._xr_playback_timer.stop()
            return
        next_index = self._xr_sample_index + 1
        if next_index >= len(self._xr_result.trajectory):
            self._pause_xr_demo()
            self.statusBar().showMessage("XR MVP playback complete")
            return
        self._set_xr_sample(next_index)

    def _leave_xr_demo(self) -> None:
        if not self._xr_demo_active:
            return
        self._xr_playback_timer.stop()
        self._xr_playback_waiting_for_field = False
        self._xr_future_elapsed_timer.stop()
        self._xr_future_started_at = None
        self._xr_field_debounce.stop()
        self._version += 1
        self._cancel_active()
        if self._active_worker is self._xr_active_worker:
            self._active_worker = None
        self._xr_demo_active = False
        self._xr_editor_active = False
        self._xr_editor_scene = None
        self._xr_trajectory = None
        self._xr_selected_ris_id = None
        self._xr_ris_command_states = {}
        self._xr_route_valid = False
        self._xr_pending_run_request = None
        self._xr_cancel_waiting_for_termination = False
        self._xr_result = None
        self._xr_static_field = None
        self._xr_no_ris_field = None
        self._xr_field_scales = {}
        self._xr_field_cache = {}
        self._xr_static_field_key = None
        self._xr_demo_start_pending = False
        self._xr_pending_field_request = None
        self._xr_field_inflight_key = None
        self._xr_sample_lookup = {}
        self._xr_sample_index = 0
        self.xr_controls.setVisible(False)
        self.xr_editor_group.setVisible(False)
        self.xr_controls.setTitle("XR Playback / Editor")
        self._set_smart_space_widgets_enabled(True)
        self.scene_view.set_options(
            show_labels=self.show_labels.isChecked(),
            show_rays=self.show_rays.isChecked(),
        )
        self.scene_view.load_scene(self.scene_model)
        self.scene_view.set_entities_draggable(True)
        if self.latest_field is not None:
            if self.show_field.isChecked():
                self.scene_view.set_field_map(
                    self.latest_field,
                    self.quantity.currentText(),
                )
            self.scene_view.set_coverage_map(
                self.latest_field,
                self.scene_model.coverage_threshold_db,
                self.show_coverage.isChecked(),
            )
        self._refresh_pattern()
        if self._smart_metric_texts:
            for widget, text in zip(
                (
                    self.power_metric,
                    self.snr_metric,
                    self.gain_metric,
                    self.coverage_metric,
                    self.dead_zone_metric,
                    self.runtime_metric,
                ),
                self._smart_metric_texts,
                strict=True,
            ):
                widget.setText(text)
        generation = self.scene_model.ris_surfaces[0].generation
        self.future_badge.setText(
            "Future Scenario Assumption" if generation == "Future" else ""
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.statusBar().showMessage("Smart Space mode restored")
        if self._xr_resume_smart_space_refresh:
            self._xr_resume_smart_space_refresh = False
            self._schedule_smart_space_refresh()

    def _set_focus_pattern(self) -> None:
        ris = self.scene_model.ris_surfaces[0]
        self.patterns = {
            ris.id: generate_coherent_target_pattern(
                self.scene_model,
                self.controller_model,
                engine=self.engine,
                ris=ris,
            )
        }
        self._pattern_source = "Coherent Target Focus"
        self._record_pattern_context()

    def _set_ris_only_pattern(self) -> None:
        ris = self.scene_model.ris_surfaces[0]
        self.patterns = {
            ris.id: generate_focus_pattern(
                ris,
                self.scene_model.transmitter(),
                self.scene_model.receiver(),
                self.scene_model.frequency_hz,
            )
        }
        self._pattern_source = "RIS-only Physics Focus"
        self._record_pattern_context()

    @staticmethod
    def _position_key(position: Vec3) -> tuple[float, float, float]:
        return (position.x, position.y, position.z)

    def _command_context(
        self,
        scene: Scene,
        source: str,
        ground_truth: GroundTruthModel | None = None,
    ) -> tuple[object, ...]:
        """Identify scene inputs that determine one commanded-pattern meaning."""
        ris = scene.ris_surfaces[0]
        tx = scene.transmitter()
        rx = scene.receiver()
        ris_geometry = (
            scene.frequency_hz,
            (tx.id, self._position_key(tx.position)),
            (rx.id, self._position_key(rx.position)),
            (
                ris.id,
                self._position_key(ris.position),
                ris.yaw_rad,
                ris.width_m,
                ris.height_m,
                ris.nx,
                ris.ny,
                ris.phase_bits,
                ris.enabled,
                ris.active,
                ris.direction_exponent,
            ),
        )
        if source == "RIS-only Physics Focus":
            return (source, ris_geometry)
        geometry = ris_geometry
        feedback_source = source.startswith(("Feedback Greedy", "Physics-Guided Feedback"))
        # Finite-bit Coherent Target Focus chooses among common phase offsets
        # by comparing nominal received power.  Efficiency scales the RIS
        # contribution and can therefore change the winning legal command.
        # Continuous Coherent Focus derives only a phase alignment, while
        # RIS-only Focus is intentionally efficiency-independent at command
        # generation time; both remain reusable when efficiency changes.
        if feedback_source or (
            source == "Coherent Target Focus" and ris.phase_bits is not None
        ):
            geometry = (
                geometry[0],
                geometry[1],
                (*geometry[2], ris.reflection_efficiency),
            )
        environment = (
            tuple(
                (
                    wall.id,
                    self._position_key(wall.start),
                    self._position_key(wall.end),
                    wall.height_m,
                    wall.attenuation_db,
                    wall.reflection_magnitude,
                    wall.reflection_phase_rad,
                    wall.blocks_los,
                )
                for wall in scene.walls
            ),
            tuple(
                (
                    obstacle.id,
                    self._position_key(obstacle.min_corner),
                    self._position_key(obstacle.max_corner),
                    obstacle.attenuation_db,
                    obstacle.fully_blocking,
                )
                for obstacle in scene.obstacles
            ),
        )
        truth_key: tuple[object, ...] = ()
        if feedback_source:
            truth = self.ground_truth if ground_truth is None else ground_truth
            truth_key = (
                truth.seed,
                truth.ris_phase_error_sigma_rad,
                truth.ris_efficiency_sigma_fraction,
                truth.wall_amplitude_error_sigma_fraction,
                truth.wall_phase_error_sigma_rad,
                truth.position_error_sigma_m,
                truth.measurement_noise_sigma_db,
            )
        return (source, geometry, environment, truth_key)

    def _record_pattern_context(self) -> None:
        self._pattern_context = self._command_context(
            self.scene_model,
            self._pattern_source,
        )

    def _current_patterns(self) -> dict[str, np.ndarray] | None:
        """Return a legal current-scene command snapshot, or no reusable command."""
        if self._pattern_context != self._command_context(
            self.scene_model,
            self._pattern_source,
        ):
            return None
        if len(self.scene_model.ris_surfaces) != 1:
            return None
        ris = self.scene_model.ris_surfaces[0]
        if set(self.patterns) != {ris.id}:
            return None
        try:
            pattern = validate_commanded_pattern(ris, self.patterns[ris.id])
        except (TypeError, ValueError):
            return None
        return {ris.id: pattern}

    def _refresh_all(self, *, recompute_map: bool = True) -> None:
        self._smart_space_refresh_pending = False
        self.scene_view.load_scene(self.scene_model, preserve_heatmap=True)
        self._refresh_metrics()
        self._refresh_pattern()
        self.pattern_view.setVisible(self.show_pattern.isChecked())
        generation = self.scene_model.ris_surfaces[0].generation
        self.future_badge.setText(
            "Future Scenario Assumption" if generation == "Future" else ""
        )
        self._refresh_generation_status()
        if recompute_map:
            self._schedule_field_map()

    def _refresh_metrics(self) -> None:
        focused = self.engine.compute_channel(
            self.scene_model, ris_patterns=self.patterns, model=self.ground_truth
        )
        baseline = self.engine.compute_channel(
            self.scene_model, ris_patterns={}, model=self.ground_truth
        )
        self.power_metric.setText(f"Power: {focused.received_power_dbm:.2f} dBm")
        self.snr_metric.setText(f"SNR: {focused.snr_db:.2f} dB")
        self.gain_metric.setText(
            f"RIS Gain: {focused.received_power_dbm - baseline.received_power_dbm:+.2f} dB"
        )

    def _refresh_pattern(self) -> None:
        ris = self.scene_model.ris_surfaces[0]
        current = self._current_patterns()
        if current is None:
            self.patterns = {}
            self._pattern_context = None
            self.pattern_view.set_status(
                "Pattern 待生成",
                "当前已应用 Scene 尚无兼容命令；请等待刷新或重新 Optimize。",
            )
            return
        commanded = current[ris.id]
        actual = commanded + self.ground_truth.ris_phase_offsets(ris)
        self.pattern_view.set_patterns(
            commanded,
            actual,
            ris.ny,
            ris.nx,
            phase_bits=ris.phase_bits,
            pattern_source=self._pattern_source,
            phase_error_sigma_rad=self.ground_truth.ris_phase_error_sigma_rad,
            diagnostics=self._pattern_diagnostics(ris),
        )

    def _pattern_diagnostics(self, ris: object, *, scene: Scene | None = None) -> str:
        active_scene = self.scene_model if scene is None else scene
        diagnostics = equivalent_patch_diagnostics(ris, active_scene.frequency_hz)
        return (
            f"Equivalent patch pitch: {diagnostics.effective_pitch_x_m:.4g}×"
            f"{diagnostics.effective_pitch_y_m:.4g} m; "
            f"λ={diagnostics.operating_wavelength_m:.4g} m; "
            f"pitch/λ={diagnostics.pitch_x_over_wavelength:.4g},"
            f"{diagnostics.pitch_y_over_wavelength:.4g}"
        )

    def _refresh_generation_status(self) -> None:
        ris = self.scene_model.ris_surfaces[0]
        preset = generation_preset(
            ris.generation, identifier=ris.id, position=ris.position, yaw_rad=ris.yaw_rad
        )
        owned = (
            ris.width_m,
            ris.height_m,
            ris.nx,
            ris.ny,
            ris.phase_bits,
            ris.reflection_efficiency,
            ris.update_rate_hz,
            ris.self_sensing,
        )
        preset_owned = (
            preset.width_m,
            preset.height_m,
            preset.nx,
            preset.ny,
            preset.phase_bits,
            preset.reflection_efficiency,
            preset.update_rate_hz,
            preset.self_sensing,
        )
        suffix = " · Customized" if owned != preset_owned else ""
        self.generation_status.setText(f"{ris.generation}{suffix}")

    def _entity_moved(self, identifier: str, position: Vec3) -> None:
        if self._xr_demo_active:
            if self._xr_editor_active and self._xr_editor_scene is not None:
                if any(ris.id == identifier for ris in self._xr_editor_scene.ris_surfaces):
                    self._xr_editor_scene.ris_surfaces = [
                        replace(ris, position=position)
                        if ris.id == identifier
                        else ris
                        for ris in self._xr_editor_scene.ris_surfaces
                    ]
                    self._xr_selected_ris_id = identifier
                    self._xr_editor_inputs_changed(
                        "RIS moved on canvas",
                        render=False,
                    )
            return
        self.scene_model.transmitters = [
            replace(item, position=position) if item.id == identifier else item
            for item in self.scene_model.transmitters
        ]
        self.scene_model.receivers = [
            replace(item, position=position) if item.id == identifier else item
            for item in self.scene_model.receivers
        ]
        self.scene_model.ris_surfaces = [
            replace(item, position=position) if item.id == identifier else item
            for item in self.scene_model.ris_surfaces
        ]
        self._schedule_smart_space_refresh()

    def _mark_smart_space_results_pending(self) -> None:
        """Show that outputs are invalid until the latest snapshot completes."""
        self._smart_space_refresh_pending = True
        self.latest_field = None
        self.scene_view.clear_field_overlays()
        current = self._current_patterns()
        if current is None:
            self.patterns = {}
            self._pattern_context = None
            self.pattern_view.set_status(
                "Pattern 生成中…",
                "当前 Scene 的合法命令正在后台生成；旧 Scene Pattern 不会作为当前结果显示。",
            )
        else:
            self._refresh_pattern()
            self.pattern_view.metadata.setText(
                self.pattern_view.metadata.text()
                + "\n当前命令仍与已应用 Scene 兼容；场图与指标正在刷新。"
            )
        self.pattern_view.setVisible(self.show_pattern.isChecked())
        self.power_metric.setText("Power: calculating…")
        self.snr_metric.setText("SNR: calculating…")
        self.gain_metric.setText("RIS Gain: calculating…")
        self.coverage_metric.setText("Coverage: calculating…")
        self.dead_zone_metric.setText("Dead Zone: calculating…")
        self.runtime_metric.setText("Runtime: calculating…")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("场景已更新 · 等待拖动停止后后台计算…")

    def _schedule_smart_space_refresh(
        self, *, regenerate_pattern: bool = False
    ) -> None:
        """Invalidate immediately and debounce one coherent latest-scene solve."""
        self._version += 1
        self._cancel_active()
        if regenerate_pattern:
            self.patterns = {}
            self._pattern_context = None
        self._debounced_action = "smart_space_refresh"
        self._mark_smart_space_results_pending()
        self._debounce.start()

    def _reload_scene_and_schedule_smart_space_refresh(self) -> None:
        """Render applied inputs immediately, then solve their outputs off-thread."""
        self.scene_view.load_scene(self.scene_model)
        generation = self.scene_model.ris_surfaces[0].generation
        self.future_badge.setText(
            "Future Scenario Assumption" if generation == "Future" else ""
        )
        self._refresh_generation_status()
        self._schedule_smart_space_refresh()

    def _run_debounced_action(self) -> None:
        action = self._debounced_action
        self._debounced_action = None
        if action == "smart_space_refresh":
            self.start_smart_space_refresh()
        elif action == "field_map":
            self.start_field_map()
        elif action == "optimization":
            self._optimize()

    def _schedule_field_map(self) -> None:
        """Invalidate any running result immediately, then debounce a replacement."""
        if self._xr_demo_active:
            return
        self._version += 1
        self._cancel_active()
        self._debounced_action = "field_map"
        self._debounce.start()

    def _generation_changed(self, generation: str) -> None:
        if self._updating_controls:
            return
        if self._pending:
            answer = QMessageBox.question(
                self,
                "丢弃待应用修改？",
                "当前有尚未 Apply 的控件修改。切换 Generation 将丢弃这些修改，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                current = self.scene_model.ris_surfaces[0].generation
                self._updating_controls = True
                self.generation_combo.blockSignals(True)
                self.generation_combo.setCurrentText(current)
                self.generation_combo.blockSignals(False)
                self._updating_controls = False
                return
            self._set_pending(False)
        old = self.scene_model.ris_surfaces[0]
        new = generation_preset(
            generation, identifier=old.id, position=old.position, yaw_rad=old.yaw_rad
        )
        # Generation owns only the documented preset fields.  Preserve other
        # applied RIS state (enablement/active flag/direction model) exactly.
        new = replace(
            new,
            enabled=old.enabled,
            active=old.active,
            direction_exponent=old.direction_exponent,
        )
        self.scene_model.ris_surfaces[0] = new
        self._sync_scene_controls()
        self._sync_ris_controls()
        self._sync_ground_truth_controls()
        self._reload_scene_and_schedule_smart_space_refresh()

    def _sync_ris_controls(self) -> None:
        ris = self.scene_model.ris_surfaces[0]
        self._updating_controls = True
        try:
            self.ris_width.setValue(ris.width_m)
            self.ris_height.setValue(ris.height_m)
            self.ris_nx.setValue(ris.nx)
            self.ris_ny.setValue(ris.ny)
            self.phase_bits.setCurrentIndex(self.phase_bits.findData(ris.phase_bits))
            self.efficiency.setValue(ris.reflection_efficiency)
            self.update_rate.setValue(ris.update_rate_hz)
            self.self_sensing.setChecked(ris.self_sensing)
            self._update_search_levels_state()
        finally:
            self._updating_controls = False

    def _apply_parameters(self) -> None:
        try:
            tx = replace(self.scene_model.transmitter(), power_w=dbm_to_watts(self.tx_power.value()))
            rx = replace(self.scene_model.receiver(), noise_figure_db=self.noise_figure.value())
            old = self.scene_model.ris_surfaces[0]
            ris = replace(
                old,
                width_m=self.ris_width.value(),
                height_m=self.ris_height.value(),
                nx=self.ris_nx.value(),
                ny=self.ris_ny.value(),
                phase_bits=self.phase_bits.currentData(),
                reflection_efficiency=self.efficiency.value(),
                update_rate_hz=self.update_rate.value(),
                self_sensing=self.self_sensing.isChecked(),
            )
            self.scene_model = replace(
                self.scene_model,
                frequency_hz=self.frequency.value() * 1e9,
                bandwidth_hz=self.bandwidth.value() * 1e6,
                coverage_threshold_db=self.coverage_threshold.value(),
                transmitters=[tx],
                receivers=[rx],
                ris_surfaces=[ris],
            )
            self.ground_truth = GroundTruthModel(
                seed=self.scene_model.random_seed,
                ris_phase_error_sigma_rad=math.radians(self.phase_error.value()),
                measurement_noise_sigma_db=self.measurement_noise.value(),
                position_error_sigma_m=self.position_error.value(),
            )
            self._set_pending(False)
            self._reload_scene_and_schedule_smart_space_refresh()
        except Exception as exc:
            QMessageBox.critical(self, "参数错误", str(exc))

    def _quality_config(self) -> SimulationConfig:
        preset = field_quality_preset(str(self.quality.currentData()))
        quantity = {"接收功率": "power", "SNR": "snr", "RIS 增益": "ris_gain"}[
            self.quantity.currentText()
        ]
        return SimulationConfig(preset.grid_width, preset.grid_height, quantity)

    def start_field_map(self) -> None:
        if self._xr_demo_active:
            return
        if self._pending:
            self.statusBar().showMessage("请先 Apply 待应用参数，再重新计算场图")
            return
        patterns = self._current_patterns()
        if self._smart_space_refresh_pending or patterns is None:
            self._debounce.stop()
            self._debounced_action = "smart_space_refresh"
            self._mark_smart_space_results_pending()
            self.start_smart_space_refresh()
            return
        active_worker = self._smart_space_active_worker
        if active_worker is not None:
            self._version += 1
            active_worker.cancel()
            self._debounced_action = "field_map"
            return
        self._debounced_action = None
        self._cancel_active()
        self._version += 1
        version = self._version
        worker = MapWorker(
            version,
            SimulationEngine(),
            copy.deepcopy(self.scene_model),
            self._quality_config(),
            copy.deepcopy(patterns),
            copy.deepcopy(self.ground_truth),
        )
        worker.signals.finished.connect(self._field_ready)
        worker.signals.failed.connect(self._worker_failed)
        worker.signals.terminated.connect(self._smart_space_worker_terminated)
        self._smart_space_active_worker = worker
        self._active_worker = worker
        self._workers.append(worker)
        self.progress.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.statusBar().showMessage("正在后台计算场图…")
        self.thread_pool.start(worker)

    def start_smart_space_refresh(self) -> None:
        """Start one background Focus→metrics→field solve for the latest drag."""
        if self._xr_demo_active:
            return
        self._debounced_action = None
        active_worker = self._smart_space_active_worker
        if active_worker is not None:
            self._version += 1
            active_worker.cancel()
            self._debounced_action = "smart_space_refresh"
            return
        if self._xr_active_worker is not None:
            self._version += 1
            self._xr_active_worker.cancel()
            self._debounced_action = "smart_space_refresh"
            return
        reusable_patterns = self._current_patterns()
        if reusable_patterns is None and self._pattern_source.startswith(
            ("Feedback Greedy", "Physics-Guided Feedback")
        ):
            self._smart_space_refresh_pending = False
            self.pattern_view.set_status(
                "Pattern 需要重新 Optimize",
                "Scene 已改变，原反馈优化命令不能合法迁移；请选择当前算法重新 Optimize。",
            )
            self.pattern_view.setVisible(self.show_pattern.isChecked())
            self.statusBar().showMessage(
                "Scene 已应用；反馈优化 Pattern 已失效，请重新 Optimize"
            )
            for widget, label in (
                (self.power_metric, "Power"),
                (self.snr_metric, "SNR"),
                (self.gain_metric, "RIS Gain"),
                (self.coverage_metric, "Coverage"),
                (self.dead_zone_metric, "Dead Zone"),
                (self.runtime_metric, "Runtime"),
            ):
                widget.setText(f"{label}: — (re-optimize)")
            return
        self._version += 1
        version = self._version
        worker = SmartSpaceRefreshWorker(
            version,
            copy.deepcopy(self.scene_model),
            self._quality_config(),
            copy.deepcopy(self.ground_truth),
            copy.deepcopy(reusable_patterns),
            self._pattern_source,
        )
        worker.signals.finished.connect(self._smart_space_refresh_ready)
        worker.signals.failed.connect(self._worker_failed)
        worker.signals.terminated.connect(self._smart_space_worker_terminated)
        self._smart_space_active_worker = worker
        self._active_worker = worker
        self._workers.append(worker)
        self.progress.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.statusBar().showMessage("正在后台计算 Focus、链路指标与场图…")
        self.thread_pool.start(worker)

    def _smart_space_refresh_ready(
        self,
        version: int,
        result: SmartSpaceRefreshResult,
    ) -> None:
        if version != self._version or self._xr_demo_active:
            return
        if result.scene != self.scene_model:
            return
        self._smart_space_refresh_pending = False
        self.patterns = result.patterns
        self._pattern_source = result.pattern_source
        self._record_pattern_context()
        self.latest_field = result.field_map
        self.scene_view.load_scene(self.scene_model)
        self._refresh_pattern()
        self.pattern_view.setVisible(self.show_pattern.isChecked())
        self.power_metric.setText(
            f"Power: {result.focused.received_power_dbm:.2f} dBm"
        )
        self.snr_metric.setText(f"SNR: {result.focused.snr_db:.2f} dB")
        self.gain_metric.setText(
            "RIS Gain: "
            f"{result.focused.received_power_dbm - result.baseline.received_power_dbm:+.2f} dB"
        )
        self._redraw_latest_map()
        self.scene_view.set_coverage_map(
            result.field_map,
            self.scene_model.coverage_threshold_db,
            self.show_coverage.isChecked(),
        )
        self.coverage_metric.setText(
            f"Coverage: {result.field_map.coverage_percent:.1f}%"
        )
        self.dead_zone_metric.setText(
            f"Dead Zone: {result.field_map.dead_zone_percent:.1f}%"
        )
        self.runtime_metric.setText(f"Runtime: {result.field_map.runtime_s:.2f} s")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("最新场景的 Focus、指标与场图计算完成")

    def _field_ready(self, version: int, result: FieldMapResult) -> None:
        if version != self._version:
            return
        if self._smart_space_refresh_pending:
            return
        self.latest_field = result
        self._redraw_latest_map()
        self.scene_view.set_coverage_map(
            result,
            self.scene_model.coverage_threshold_db,
            self.show_coverage.isChecked(),
        )
        self.coverage_metric.setText(f"Coverage: {result.coverage_percent:.1f}%")
        self.dead_zone_metric.setText(f"Dead Zone: {result.dead_zone_percent:.1f}%")
        self.runtime_metric.setText(f"Runtime: {result.runtime_s:.2f} s")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.cancel_button.setEnabled(False)
        self.statusBar().showMessage("场图计算完成")

    def _redraw_latest_map(self) -> None:
        if self.latest_field is not None and self.show_field.isChecked():
            self.scene_view.set_field_map(self.latest_field, self.quantity.currentText())

    def _field_visibility_changed(self, visible: bool) -> None:
        self.scene_view.set_field_visible(visible)
        if visible:
            self._redraw_latest_map()

    def _coverage_visibility_changed(self, visible: bool) -> None:
        if self.latest_field is not None:
            self.scene_view.set_coverage_map(
                self.latest_field,
                self.scene_model.coverage_threshold_db,
                visible,
            )

    def _optimize(self) -> None:
        if self._pending:
            self.statusBar().showMessage("请先 Apply 待应用参数，再开始 Optimize")
            return
        algorithm = self.algorithm.currentText()
        if algorithm == "Coherent Target Focus":
            self._schedule_smart_space_refresh(regenerate_pattern=True)
            return
        if algorithm == "RIS-only Physics Focus":
            self._set_ris_only_pattern()
            self._refresh_all()
            self.statusBar().showMessage("RIS-only Physics Focus 完成")
            return
        self._smart_space_refresh_pending = False
        self._cancel_active()
        if self._smart_space_active_worker is not None:
            self._version += 1
            self._debounced_action = "optimization"
            return
        self._version += 1
        worker = OptimizationWorker(
            self._version,
            algorithm,
            copy.deepcopy(self.scene_model),
            copy.deepcopy(self.ground_truth),
            self.search_levels.value(),
        )
        worker.signals.finished.connect(self._optimization_ready)
        worker.signals.failed.connect(self._worker_failed)
        worker.signals.progress.connect(self._optimization_progress)
        worker.signals.terminated.connect(self._smart_space_worker_terminated)
        self._smart_space_active_worker = worker
        self._active_worker = worker
        self._workers.append(worker)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.statusBar().showMessage("正在进行测量反馈优化…")
        self.thread_pool.start(worker)

    def _optimization_progress(self, version: int, done: int, total: int, value: float) -> None:
        if version != self._version:
            return
        self.progress.setValue(int(done * 100 / max(total, 1)))
        self.statusBar().showMessage(f"反馈优化 {done}/{total} · {value:.2f} dBm")

    def _optimization_ready(self, version: int, result: object) -> None:
        if version != self._version:
            return
        self.patterns = result.patterns
        self._pattern_source = getattr(result, "pattern_source", "Feedback Greedy")
        levels = getattr(result, "search_levels", None)
        if levels is not None and self.scene_model.ris_surfaces[0].phase_bits is None:
            self._pattern_source += f" · Search Levels: {levels}"
        self._record_pattern_context()
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100)
        self._refresh_all()
        self.statusBar().showMessage(
            f"优化完成：{result.objective_db:.2f} dBm，{result.iterations} 次测量"
        )

    def _worker_failed(self, version: int, details: str) -> None:
        if version != self._version:
            return
        active_worker = self._active_worker
        if not isinstance(
            active_worker,
            (
                XRDynamicRoomWorker,
                XRAdaptiveFieldWorker,
                XRFuturePreparedFieldWorker,
            ),
        ):
            self._smart_space_refresh_pending = False
            if isinstance(active_worker, SmartSpaceRefreshWorker):
                if self._current_patterns() is None:
                    self.pattern_view.set_status(
                        "Pattern 生成失败",
                        "当前 Scene 未生成合法命令。请重试刷新或重新 Optimize。",
                    )
                else:
                    self._refresh_pattern()
                    self.pattern_view.metadata.setText(
                        self.pattern_view.metadata.text()
                        + "\n场图与指标刷新失败；可重试，当前合法命令仍保留。"
                    )
                self.pattern_view.setVisible(self.show_pattern.isChecked())
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        if self._xr_demo_active:
            self._xr_playback_waiting_for_field = False
            self._xr_future_elapsed_timer.stop()
            self._xr_future_started_at = None
            self._set_xr_controls_ready(self._xr_result is not None)
            if self._xr_result is None:
                self.xr_sample_label.setText("XR MVP calculation failed")
            else:
                self.xr_field_status.setText(
                    "Field map calculation failed · no stale field applied"
                )
        self.statusBar().showMessage("计算失败")
        QMessageBox.critical(self, "计算失败", details)

    def _smart_space_worker_terminated(self, _version: int, worker: object) -> None:
        """Release Smart Space work only after its runnable has returned."""
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        if self._smart_space_active_worker is not worker:
            return
        self._smart_space_active_worker = None
        if self._active_worker is worker:
            self._active_worker = None
        if self._closing:
            return
        if self._xr_demo_start_pending:
            self._start_xr_demo_worker()
            return
        if self._debounce.isActive():
            return
        if self._debounced_action == "smart_space_refresh":
            self.start_smart_space_refresh()
        elif self._debounced_action == "field_map":
            self.start_field_map()
        elif self._debounced_action == "optimization":
            self._optimize()

    def _cancel_active(self) -> None:
        worker = self._active_worker
        if worker is not None and hasattr(worker, "cancel"):
            worker.cancel()
        xr_worker = self._xr_active_worker
        if xr_worker is not None and xr_worker is not worker:
            xr_worker.cancel()
        smart_worker = self._smart_space_active_worker
        if smart_worker is not None and smart_worker is not worker:
            smart_worker.cancel()

    def _cancel_work(self) -> None:
        self._debounce.stop()
        self._xr_field_debounce.stop()
        self._debounced_action = None
        self._xr_pending_field_request = None
        if self._xr_active_worker is None:
            self._xr_field_inflight_key = None
        self._smart_space_refresh_pending = False
        self._version += 1
        self._cancel_active()
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.statusBar().showMessage("已请求取消")
        if self._current_patterns() is None:
            self.pattern_view.set_status(
                "Pattern 已取消",
                "当前 Scene 尚无合法命令。可点击重新计算场图或重新 Optimize。",
            )
        else:
            self._refresh_pattern()
        self.pattern_view.setVisible(self.show_pattern.isChecked())

    def _display_options_changed(self) -> None:
        self.scene_view.set_options(
            show_labels=self.show_labels.isChecked(), show_rays=self.show_rays.isChecked()
        )
        self._redraw_latest_map()

    def _save_scene(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存场景", "smart_room.json", "JSON (*.json)")
        if path:
            try:
                self.scene_model.save(path)
                self.statusBar().showMessage(f"场景已保存：{path}")
            except Exception as exc:
                QMessageBox.critical(self, "保存失败", str(exc))

    def _load_scene(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载场景", "", "JSON (*.json)")
        if path:
            try:
                self.scene_model = Scene.load(path)
                if not self.scene_model.ris_surfaces:
                    raise ValueError("v0.1 GUI requires one RIS")
                self.generation_combo.blockSignals(True)
                self.generation_combo.setCurrentText(self.scene_model.ris_surfaces[0].generation)
                self.generation_combo.blockSignals(False)
                self._sync_scene_controls()
                self._sync_ris_controls()
                self._set_pending(False)
                self._reload_scene_and_schedule_smart_space_refresh()
            except Exception as exc:
                QMessageBox.critical(self, "加载失败", str(exc))

    def _sync_scene_controls(self) -> None:
        self._updating_controls = True
        try:
            self.frequency.setValue(self.scene_model.frequency_hz / 1e9)
            self.tx_power.setValue(float(watts_to_dbm(self.scene_model.transmitter().power_w)))
            self.bandwidth.setValue(self.scene_model.bandwidth_hz / 1e6)
            self.noise_figure.setValue(self.scene_model.receiver().noise_figure_db)
            self.coverage_threshold.setValue(self.scene_model.coverage_threshold_db)
        finally:
            self._updating_controls = False

    def _sync_ground_truth_controls(self) -> None:
        self._updating_controls = True
        try:
            self.phase_error.setValue(math.degrees(self.ground_truth.ris_phase_error_sigma_rad))
            self.measurement_noise.setValue(self.ground_truth.measurement_noise_sigma_db)
            self.position_error.setValue(self.ground_truth.position_error_sigma_m)
        finally:
            self._updating_controls = False

    def _show_model_info(self) -> None:
        QMessageBox.information(
            self,
            "模型说明 / Model Info",
            "System-level electromagnetic approximation\n\n"
            "传播：复数 Friis LOS + 一次墙面镜像反射 + 单跳有限孔径 RIS。\n"
            "RIS：孔径面积归一化、有限效率、有限相位精度、前向余弦方向图。\n"
            "噪声：-174 dBm/Hz + 带宽 + Noise Figure。\n"
            "容量：平坦信道 Shannon 理论上界，不代表真实吞吐量。\n"
            "当前孔径积分：每个等效可控 patch 使用 signed midpoint 8×8 subpoints。\n"
            "A2 的 pitch/波长仅作透明度信息，不表示 lambda/2 通过或数值收敛；partial-aperture blockage 未实现。\n"
            "固定 commanded pattern 用于整张场图，不是逐像素重新聚焦的最优包络。\n"
            "Geometry Position Error：TX/RX/RIS/obstacle 按各自三维模型；v1 floor-anchored wall 仅使用同一个刚体 XY 偏移。\n"
            "Feedback Measurement Noise 只作用于 MeasurementOracle。\n\n"
            "未包含完整三维全波求解、衍射、高阶反射、互耦、极化、MIMO/OFDM。",
        )

    def closeEvent(self, event: object) -> None:
        self._closing = True
        self._version += 1
        self._xr_demo_active = False
        self._xr_editor_active = False
        self._xr_demo_start_pending = False
        self._xr_pending_run_request = None
        self._xr_playback_timer.stop()
        self._xr_field_debounce.stop()
        self._xr_pending_field_request = None
        self._cancel_active()
        super().closeEvent(event)


def configure_application_font(app: QApplication) -> None:
    """Select a CJK-capable font, registering a system font when necessary."""
    preferred = ("Microsoft YaHei UI", "Noto Sans SC", "PingFang SC", "SimHei")
    available = set(QFontDatabase.families())
    family = next((name for name in preferred if name in available), None)
    if family is None:
        candidates = (
            Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
        )
        for path in candidates:
            if not path.exists():
                continue
            font_id = QFontDatabase.addApplicationFont(str(path))
            registered = QFontDatabase.applicationFontFamilies(font_id)
            if registered:
                family = registered[0]
                break
    app.setFont(QFont(family or app.font().family(), 9))


def run_gui(
    scene: Scene,
    *,
    trajectory_backend: TrajectoryEditorBackend | None = None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AirMirror Future")
    configure_application_font(app)
    window = MainWindow(scene, trajectory_backend=trajectory_backend)
    window.show()
    return app.exec()
