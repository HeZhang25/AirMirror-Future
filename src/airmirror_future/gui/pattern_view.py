"""Compact commanded/actual RIS phase image widget."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget


class PhasePatternView(QWidget):
    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.commanded = QLabel("暂无相位图")
        self.actual = QLabel("暂无相位图")
        for label in (self.commanded, self.actual):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(120)
        self.tabs.addTab(self.commanded, "Commanded")
        self.tabs.addTab(self.actual, "Actual")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    @staticmethod
    def _pixmap(pattern: np.ndarray, ny: int, nx: int) -> QPixmap:
        values = np.mod(np.asarray(pattern).reshape(ny, nx), 2.0 * np.pi) / (2.0 * np.pi)
        angle = values * 6.0
        red = np.clip(np.abs(angle - 3.0) - 1.0, 0.0, 1.0)
        green = np.clip(2.0 - np.abs(angle - 2.0), 0.0, 1.0)
        blue = np.clip(2.0 - np.abs(angle - 4.0), 0.0, 1.0)
        rgb = np.ascontiguousarray(np.stack((red, green, blue), axis=2) * 255.0, dtype=np.uint8)
        image = QImage(rgb.data, nx, ny, nx * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(image).scaled(
            280,
            150,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

    def set_patterns(
        self, commanded: np.ndarray, actual: np.ndarray, ny: int, nx: int
    ) -> None:
        self.commanded.setPixmap(self._pixmap(commanded, ny, nx))
        self.actual.setPixmap(self._pixmap(actual, ny, nx))

