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
        self.metadata = QLabel("")
        self.metadata.setWordWrap(True)
        self.metadata.setStyleSheet("color:#475569;font-size:11px")
        self.legend = QLabel()
        self.legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legend.setPixmap(self._legend_pixmap())
        for label in (self.commanded, self.actual):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(120)
        self.tabs.addTab(self.commanded, "Commanded")
        self.tabs.addTab(self.actual, "Actual")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)
        layout.addWidget(self.legend)
        layout.addWidget(self.metadata)

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

    @classmethod
    def _legend_pixmap(cls) -> QPixmap:
        samples = np.linspace(0.0, 2.0 * np.pi, 280, endpoint=True)[None, :]
        return cls._pixmap(samples, 1, samples.shape[1]).scaled(
            280,
            14,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def set_patterns(
        self,
        commanded: np.ndarray,
        actual: np.ndarray,
        ny: int,
        nx: int,
        *,
        phase_bits: int | None = None,
        pattern_source: str = "Unknown",
        phase_error_sigma_rad: float = 0.0,
        diagnostics: str = "",
    ) -> None:
        self.commanded.setPixmap(self._pixmap(commanded, ny, nx))
        self.actual.setPixmap(self._pixmap(actual, ny, nx))
        hardware = "Continuous" if phase_bits is None else f"{phase_bits}-bit"
        allowed = "continuous (no discrete Allowed States)" if phase_bits is None else str(2**phase_bits)
        values = np.mod(np.asarray(commanded).reshape(-1), 2.0 * np.pi)
        if phase_bits is None:
            used = f"{len(np.unique(np.round(values, 12)))} observed values"
        else:
            step = 2.0 * np.pi / (2**phase_bits)
            used = f"{len(np.unique(np.round(values / step) % (2**phase_bits)))} / {2**phase_bits}"
        self.metadata.setText(
            f"Grid: {nx}×{ny} · Hardware Phase: {hardware} · Allowed States: {allowed} · "
            f"Used States: {used} · Pattern Source: {pattern_source}\n"
            f"Actual = Commanded + Ground Truth phase error (σ={phase_error_sigma_rad:.4g} rad)\n"
            "循环相位图例（左→右）：0 → π/2 → π → 3π/2 → 2π；颜色不用于判断硬件命令状态。"
        )
        if diagnostics:
            self.metadata.setText(self.metadata.text() + "\n" + diagnostics)
