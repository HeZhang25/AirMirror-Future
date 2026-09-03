"""Functional Chinese desktop UI for the Smart Space vertical slice."""

from __future__ import annotations

import copy
from dataclasses import replace
import math
from pathlib import Path
import sys

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
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from airmirror_future.core.config import FIELD_QUALITY_PRESETS, field_quality_preset
from airmirror_future.core.types import FieldMapResult, Scene, SimulationConfig, Vec3
from airmirror_future.core.units import dbm_to_watts, watts_to_dbm
from airmirror_future.gui.pattern_view import PhasePatternView
from airmirror_future.gui.scene_view import SceneView
from airmirror_future.gui.workers import MapWorker, OptimizationWorker
from airmirror_future.ris.generations import generation_preset
from airmirror_future.ris.aperture import equivalent_patch_diagnostics
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


class MainWindow(QMainWindow):
    """AirMirror Future v0.1 Smart Space desktop application."""

    def __init__(self, scene: Scene) -> None:
        super().__init__()
        self.setWindowTitle("AirMirror Future · 可编程电磁空间仿真平台")
        self.resize(1460, 900)
        self.scene_model = scene
        self.engine = SimulationEngine()
        self.controller_model = ControllerModel()
        self.ground_truth = GroundTruthModel(seed=scene.random_seed)
        self.patterns: dict[str, np.ndarray] = {}
        self.latest_field: FieldMapResult | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: list[object] = []
        self._version = 0
        self._active_worker: object | None = None
        self._updating_controls = False
        self._pending = False
        self._pattern_source = "Coherent Target Focus"
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self.start_field_map)

        self.scene_view = SceneView()
        self.scene_view.on_entity_moved = self._entity_moved
        self.pattern_view = PhasePatternView()
        self._build_ui()
        self._set_pending(False)
        self._set_focus_pattern()
        self._refresh_all(recompute_map=False)
        QTimer.singleShot(100, self.start_field_map)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self.scene_view)
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([230, 900, 320])

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
        panel = QWidget()
        panel.setMinimumWidth(220)
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("<b>场景 / Scenario</b>"))
        scenario = QComboBox()
        scenario.addItem("Future Smart Space")
        layout.addWidget(scenario)
        roadmap = QLabel("路线图：XR · Smart Factory · Future City\n尚未实现，不提供假功能入口。")
        roadmap.setWordWrap(True)
        roadmap.setStyleSheet("color:#64748b")
        layout.addWidget(roadmap)

        files = QGroupBox("场景文件")
        files_layout = QVBoxLayout(files)
        load_button = QPushButton("加载场景 / Load")
        save_button = QPushButton("保存场景 / Save")
        load_button.clicked.connect(self._load_scene)
        save_button.clicked.connect(self._save_scene)
        files_layout.addWidget(load_button)
        files_layout.addWidget(save_button)
        layout.addWidget(files)

        layers = QGroupBox("显示层")
        layers_layout = QVBoxLayout(layers)
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
        layout.addWidget(layers)

        info = QPushButton("模型说明 / Model Info")
        info.clicked.connect(self._show_model_info)
        layout.addWidget(info)
        layout.addStretch()
        return panel

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

    def _refresh_all(self, *, recompute_map: bool = True) -> None:
        self.scene_view.load_scene(self.scene_model, preserve_heatmap=True)
        self._refresh_metrics()
        self._refresh_pattern()
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
        commanded = self.patterns.get(ris.id, np.zeros(ris.cell_count))
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

    def _pattern_diagnostics(self, ris: object) -> str:
        diagnostics = equivalent_patch_diagnostics(ris, self.scene_model.frequency_hz)
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
        self._set_focus_pattern()
        self._refresh_metrics()
        self._refresh_pattern()
        self._schedule_field_map()

    def _schedule_field_map(self) -> None:
        """Invalidate any running result immediately, then debounce a replacement."""
        self._version += 1
        self._cancel_active()
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
        self._set_focus_pattern()
        self._refresh_all()

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
            self._set_focus_pattern()
            self._set_pending(False)
            self._refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, "参数错误", str(exc))

    def _quality_config(self) -> SimulationConfig:
        preset = field_quality_preset(str(self.quality.currentData()))
        quantity = {"接收功率": "power", "SNR": "snr", "RIS 增益": "ris_gain"}[
            self.quantity.currentText()
        ]
        return SimulationConfig(preset.grid_width, preset.grid_height, quantity)

    def start_field_map(self) -> None:
        self._cancel_active()
        self._version += 1
        version = self._version
        worker = MapWorker(
            version,
            SimulationEngine(),
            copy.deepcopy(self.scene_model),
            self._quality_config(),
            copy.deepcopy(self.patterns),
            copy.deepcopy(self.ground_truth),
        )
        worker.signals.finished.connect(self._field_ready)
        worker.signals.failed.connect(self._worker_failed)
        self._active_worker = worker
        self._workers.append(worker)
        self.progress.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.statusBar().showMessage("正在后台计算场图…")
        self.thread_pool.start(worker)

    def _field_ready(self, version: int, result: FieldMapResult) -> None:
        if version != self._version:
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
        self._active_worker = None

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
            self._set_focus_pattern()
            self._refresh_all()
            self.statusBar().showMessage("Coherent Target Focus 完成")
            return
        if algorithm == "RIS-only Physics Focus":
            self._set_ris_only_pattern()
            self._refresh_all()
            self.statusBar().showMessage("RIS-only Physics Focus 完成")
            return
        self._cancel_active()
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
        self._active_worker = None
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100)
        self._refresh_all()
        self.statusBar().showMessage(
            f"优化完成：{result.objective_db:.2f} dBm，{result.iterations} 次测量"
        )

    def _worker_failed(self, version: int, details: str) -> None:
        if version != self._version:
            return
        self._active_worker = None
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.statusBar().showMessage("计算失败")
        QMessageBox.critical(self, "计算失败", details)

    def _cancel_active(self) -> None:
        worker = self._active_worker
        if worker is not None and hasattr(worker, "cancel"):
            worker.cancel()
        self._active_worker = None

    def _cancel_work(self) -> None:
        self._version += 1
        self._cancel_active()
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.statusBar().showMessage("已请求取消")

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
                self._set_focus_pattern()
                self._set_pending(False)
                self._refresh_all()
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
            "当前孔径积分：每个等效可控 patch 使用 1×1 midpoint；结果是 scalar center-point model。\n"
            "A2 的 pitch/波长仅作透明度信息，不表示 lambda/2 通过或数值收敛；partial-aperture blockage 未实现。\n"
            "固定 commanded pattern 用于整张场图，不是逐像素重新聚焦的最优包络。\n"
            "Geometry Position Error：TX/RX/RIS/obstacle 按各自三维模型；v1 floor-anchored wall 仅使用同一个刚体 XY 偏移。\n"
            "Feedback Measurement Noise 只作用于 MeasurementOracle。\n\n"
            "未包含完整三维全波求解、衍射、高阶反射、互耦、极化、MIMO/OFDM。",
        )

    def closeEvent(self, event: object) -> None:
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


def run_gui(scene: Scene) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AirMirror Future")
    configure_application_font(app)
    window = MainWindow(scene)
    window.show()
    return app.exec()
