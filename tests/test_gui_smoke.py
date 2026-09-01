import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import numpy as np

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from airmirror_future.gui.main_window import MainWindow
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
