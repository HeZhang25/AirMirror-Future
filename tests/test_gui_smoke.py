import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import numpy as np

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from airmirror_future.gui.main_window import MainWindow
from airmirror_future.gui.pattern_view import PhasePatternView
from airmirror_future.core.types import FieldMapResult
from airmirror_future.scenarios.smart_space import create_smart_space_scene


def test_main_window_constructs_and_can_cancel() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    window._cancel_work()
    assert "AirMirror Future" in window.windowTitle()
    window.close()
    app.processEvents()


def test_stale_field_result_is_ignored() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    values = np.zeros((2, 2))
    stale = FieldMapResult(
        np.array([0.0, 1.0]),
        np.array([0.0, 1.0]),
        values,
        values,
        values,
        values,
        0.0,
        100.0,
        0.0,
    )
    window._version = 10
    window._field_ready(9, stale)
    assert window.latest_field is None
    window.close()
    app.processEvents()


def test_pending_parameters_block_optimize_and_preserve_applied_scene() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    original_generation = window.scene_model.ris_surfaces[0].generation
    window.phase_bits.setCurrentIndex(window.phase_bits.findData(None))
    assert window._pending is True
    assert window.optimize_button.isEnabled() is False
    window._optimize()
    assert "请先 Apply" in window.statusBar().currentMessage()
    assert window.scene_model.ris_surfaces[0].generation == original_generation
    window.close()
    app.processEvents()


def test_generation_cancel_preserves_pending_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    window.ris_nx.setValue(window.ris_nx.value() + 1)
    pending_nx = window.ris_nx.value()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.No))
    window.generation_combo.setCurrentText("Future")
    assert window.scene_model.ris_surfaces[0].generation == "Current"
    assert window.ris_nx.value() == pending_nx
    assert window._pending is True
    window.close()
    app.processEvents()


def test_generation_confirm_discards_pending_and_marks_customized_display(monkeypatch: pytest.MonkeyPatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    window.ris_nx.setValue(window.ris_nx.value() + 1)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    window.generation_combo.setCurrentText("Future")
    ris = window.scene_model.ris_surfaces[0]
    assert ris.generation == "Future"
    assert ris.nx == 64 and ris.ny == 48
    assert window._pending is False
    assert "Future" in window.generation_status.text()
    window.close()
    app.processEvents()


def test_generation_confirm_restores_all_applied_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    applied_frequency = window.frequency.value()
    applied_phase_error = window.phase_error.value()
    window.frequency.setValue(applied_frequency + 0.5)
    window.phase_error.setValue(applied_phase_error + 7.0)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    window.generation_combo.setCurrentText("Advanced")
    assert window.frequency.value() == applied_frequency
    assert window.phase_error.value() == applied_phase_error
    assert window._pending is False
    window.close()
    app.processEvents()


def test_generation_preset_preserves_non_owned_ris_state(monkeypatch: pytest.MonkeyPatch) -> None:
    app = QApplication.instance() or QApplication([])
    scene = create_smart_space_scene()
    scene.ris_surfaces[0].direction_exponent = 2.5
    window = MainWindow(scene)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    window.generation_combo.setCurrentText("Future")
    ris = window.scene_model.ris_surfaces[0]
    assert ris.enabled is True and ris.active is False and ris.direction_exponent == 2.5
    window.close()
    app.processEvents()


def test_generation_customized_is_display_only() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene("Current"))
    preset_nx = window.scene_model.ris_surfaces[0].nx

    window.ris_nx.setValue(preset_nx + 1)
    assert window._pending is True
    window._apply_parameters()

    assert window.scene_model.ris_surfaces[0].generation == "Current"
    assert window.generation_status.text() == "Current · Customized"

    window.ris_nx.setValue(preset_nx)
    window._apply_parameters()
    assert window.scene_model.ris_surfaces[0].generation == "Current"
    assert window.generation_status.text() == "Current"
    window.close()
    app.processEvents()


def test_pattern_metadata_and_ground_truth_labels_are_explicit() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene("Current"))
    metadata = window.pattern_view.metadata.text()
    assert "Grid: 8×8" in metadata
    assert "Hardware Phase: 1-bit" in metadata
    assert "Allowed States: 2" in metadata
    assert "Used States:" in metadata
    assert "Pattern Source: Coherent Target Focus" in metadata
    assert "Actual = Commanded + Ground Truth phase error" in metadata
    assert "pitch/λ=" in metadata
    assert not window.pattern_view.legend.pixmap().isNull()
    assert "floor-anchored" in window.position_error.toolTip()
    assert "MeasurementOracle" in window.measurement_noise.toolTip()
    window.close()
    app.processEvents()


@pytest.mark.parametrize("bits", (1, 2, 3, 4))
def test_pattern_allowed_and_used_states_match_hardware_bits(bits: int) -> None:
    app = QApplication.instance() or QApplication([])
    view = PhasePatternView()
    levels = 2**bits
    commanded = np.arange(levels, dtype=float) * 2.0 * np.pi / levels
    view.set_patterns(
        commanded,
        commanded,
        1,
        levels,
        phase_bits=bits,
        pattern_source="test",
    )
    assert f"Allowed States: {levels}" in view.metadata.text()
    assert f"Used States: {levels} / {levels}" in view.metadata.text()
    view.close()
    app.processEvents()


def test_continuous_pattern_does_not_infer_hardware_states_from_search_levels() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene("Future"))
    metadata = window.pattern_view.metadata.text()
    assert "Hardware Phase: Continuous" in metadata
    assert "Allowed States: continuous (no discrete Allowed States)" in metadata
    assert "Allowed States: 8" not in metadata
    window.close()
    app.processEvents()


def test_gui_defaults_to_coherent_target_and_keeps_ris_only_accessible() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(create_smart_space_scene())
    assert window.algorithm.currentText() == "Coherent Target Focus"
    assert "Pattern Source: Coherent Target Focus" in window.pattern_view.metadata.text()
    window.algorithm.setCurrentText("RIS-only Physics Focus")
    window._optimize()
    assert "Pattern Source: RIS-only Physics Focus" in window.pattern_view.metadata.text()
    window.close()
    app.processEvents()
