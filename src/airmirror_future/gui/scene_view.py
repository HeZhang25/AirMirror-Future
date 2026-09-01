"""Interactive QGraphicsView scene and NumPy heatmap renderer."""

from __future__ import annotations

from collections.abc import Callable
import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from airmirror_future.core.types import FieldMapResult, Scene, Vec3


EntityMoved = Callable[[str, Vec3], None]


class _DraggableItem(QGraphicsEllipseItem):
    def __init__(
        self,
        entity_id: str,
        radius: float,
        color: QColor,
        callback: Callable[[str, QPointF], None],
    ) -> None:
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        self.entity_id = entity_id
        self.callback = callback
        self.setBrush(color)
        self.setPen(QPen(Qt.GlobalColor.white, 1.5))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(20)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.callback(self.entity_id, self.pos())
        return super().itemChange(change, value)


class _DraggableRIS(QGraphicsRectItem):
    def __init__(
        self,
        entity_id: str,
        width: float,
        callback: Callable[[str, QPointF], None],
    ) -> None:
        super().__init__(-width / 2.0, -3.0, width, 6.0)
        self.entity_id = entity_id
        self.callback = callback
        self.setBrush(QColor("#8b5cf6"))
        self.setPen(QPen(Qt.GlobalColor.white, 1.5))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(20)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.callback(self.entity_id, self.pos())
        return super().itemChange(change, value)


class SceneView(QGraphicsView):
    """Top-down room view with draggable devices and field overlay."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.setRenderHints(self.renderHints())
        self.setBackgroundBrush(QColor("#101827"))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.scale_px_m = 70.0
        self.model_scene: Scene | None = None
        self.on_entity_moved: EntityMoved | None = None
        self._suppress_moves = False
        self._heatmap_item: QGraphicsPixmapItem | None = None
        self._coverage_item: QGraphicsPixmapItem | None = None
        self._show_labels = True
        self._show_rays = True

    def _point(self, position: Vec3) -> QPointF:
        assert self.model_scene is not None
        return QPointF(
            position.x * self.scale_px_m,
            (self.model_scene.room_size.y - position.y) * self.scale_px_m,
        )

    def _model_position(self, point: QPointF, z: float) -> Vec3:
        assert self.model_scene is not None
        x = float(np.clip(point.x() / self.scale_px_m, 0.0, self.model_scene.room_size.x))
        y = float(
            np.clip(
                self.model_scene.room_size.y - point.y() / self.scale_px_m,
                0.0,
                self.model_scene.room_size.y,
            )
        )
        return Vec3(x, y, z)

    def _moved(self, identifier: str, point: QPointF) -> None:
        if self._suppress_moves or self.model_scene is None or self.on_entity_moved is None:
            return
        for entity in (
            list(self.model_scene.transmitters)
            + list(self.model_scene.receivers)
            + list(self.model_scene.ris_surfaces)
        ):
            if entity.id == identifier:
                self.on_entity_moved(identifier, self._model_position(point, entity.position.z))
                return

    def set_options(self, *, show_labels: bool, show_rays: bool) -> None:
        self._show_labels = show_labels
        self._show_rays = show_rays
        if self.model_scene is not None:
            self.load_scene(self.model_scene, preserve_heatmap=True)

    def load_scene(self, scene: Scene, *, preserve_heatmap: bool = False) -> None:
        old_pixmap = self._heatmap_item.pixmap() if preserve_heatmap and self._heatmap_item else None
        old_coverage = (
            self._coverage_item.pixmap()
            if preserve_heatmap and self._coverage_item
            else None
        )
        self.model_scene = scene
        self._suppress_moves = True
        self.graphics_scene.clear()
        self._heatmap_item = None
        self._coverage_item = None
        room_width = scene.room_size.x * self.scale_px_m
        room_height = scene.room_size.y * self.scale_px_m
        self.graphics_scene.setSceneRect(0, 0, room_width, room_height)
        if old_pixmap is not None:
            self._heatmap_item = self.graphics_scene.addPixmap(old_pixmap)
            self._heatmap_item.setZValue(-10)
        if old_coverage is not None:
            self._coverage_item = self.graphics_scene.addPixmap(old_coverage)
            self._coverage_item.setZValue(-5)
        self.graphics_scene.addRect(
            0, 0, room_width, room_height, QPen(QColor("#a7b6cc"), 2)
        )
        for obstacle in scene.obstacles:
            top_left = self._point(Vec3(obstacle.min_corner.x, obstacle.max_corner.y, 0))
            width = (obstacle.max_corner.x - obstacle.min_corner.x) * self.scale_px_m
            height = (obstacle.max_corner.y - obstacle.min_corner.y) * self.scale_px_m
            item = self.graphics_scene.addRect(
                top_left.x(), top_left.y(), width, height, QPen(QColor("#d97706"), 1)
            )
            item.setBrush(QColor(217, 119, 6, 100))
            item.setZValue(5)
        for wall in scene.walls:
            start, end = self._point(wall.start), self._point(wall.end)
            line = self.graphics_scene.addLine(
                start.x(), start.y(), end.x(), end.y(), QPen(QColor("#d7dde8"), 3)
            )
            line.setZValue(8)
        entities: list[tuple[str, Vec3, QColor, str]] = []
        entities.extend((tx.id, tx.position, QColor("#ef4444"), "TX") for tx in scene.transmitters)
        entities.extend((rx.id, rx.position, QColor("#22c55e"), "RX") for rx in scene.receivers)
        for identifier, position, color, label in entities:
            item = _DraggableItem(identifier, 8.0, color, self._moved)
            item.setPos(self._point(position))
            self.graphics_scene.addItem(item)
            if self._show_labels:
                text = self.graphics_scene.addSimpleText(label)
                text.setBrush(Qt.GlobalColor.white)
                text.setPos(item.pos() + QPointF(10, -18))
                text.setZValue(21)
        for ris in scene.ris_surfaces:
            item = _DraggableRIS(ris.id, ris.width_m * self.scale_px_m, self._moved)
            item.setPos(self._point(ris.position))
            item.setRotation(-math.degrees(ris.yaw_rad + math.pi / 2.0))
            self.graphics_scene.addItem(item)
            if self._show_labels:
                text = self.graphics_scene.addSimpleText(f"RIS · {ris.generation}")
                text.setBrush(Qt.GlobalColor.white)
                text.setPos(item.pos() + QPointF(8, 8))
                text.setZValue(21)
        if self._show_rays and scene.transmitters and scene.receivers:
            tx_point = self._point(scene.transmitter().position)
            rx_point = self._point(scene.receiver().position)
            ray_pen = QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine)
            if scene.ris_surfaces:
                ris_point = self._point(scene.ris_surfaces[0].position)
                self.graphics_scene.addLine(
                    tx_point.x(), tx_point.y(), ris_point.x(), ris_point.y(), ray_pen
                ).setZValue(9)
                self.graphics_scene.addLine(
                    ris_point.x(), ris_point.y(), rx_point.x(), rx_point.y(), ray_pen
                ).setZValue(9)
            direct_pen = QPen(QColor(239, 68, 68, 130), 1, Qt.PenStyle.DotLine)
            self.graphics_scene.addLine(
                tx_point.x(), tx_point.y(), rx_point.x(), rx_point.y(), direct_pen
            ).setZValue(9)
        self._suppress_moves = False
        self.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    @staticmethod
    def _rgba(values: np.ndarray) -> np.ndarray:
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            normalized = np.zeros_like(values)
        else:
            low, high = np.percentile(finite, (3, 97))
            if high <= low:
                high = low + 1.0
            normalized = np.clip((values - low) / (high - low), 0.0, 1.0)
        red = np.clip(1.8 * normalized, 0.0, 1.0)
        green = np.clip(1.8 - np.abs(normalized - 0.55) * 3.0, 0.0, 1.0)
        blue = np.clip(1.6 * (1.0 - normalized), 0.0, 1.0)
        alpha = np.full_like(normalized, 0.72)
        return (np.stack((red, green, blue, alpha), axis=2) * 255.0).astype(np.uint8)

    def set_field_map(self, result: FieldMapResult, quantity: str) -> None:
        if self.model_scene is None:
            return
        values = {
            "接收功率": result.received_power_dbm,
            "SNR": result.snr_db,
            "RIS 增益": result.ris_gain_db,
        }[quantity]
        rgba = np.ascontiguousarray(np.flipud(self._rgba(values)))
        height, width, _ = rgba.shape
        image = QImage(rgba.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            int(self.model_scene.room_size.x * self.scale_px_m),
            int(self.model_scene.room_size.y * self.scale_px_m),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._heatmap_item is None:
            self._heatmap_item = self.graphics_scene.addPixmap(pixmap)
            self._heatmap_item.setZValue(-10)
        else:
            self._heatmap_item.setPixmap(pixmap)

    def set_field_visible(self, visible: bool) -> None:
        if self._heatmap_item is not None:
            self._heatmap_item.setVisible(visible)

    def set_coverage_map(
        self, result: FieldMapResult, threshold_db: float, visible: bool
    ) -> None:
        """Overlay dead zones in translucent red using the declared SNR threshold."""
        if self.model_scene is None:
            return
        covered = result.snr_db >= threshold_db
        rgba = np.zeros((*covered.shape, 4), dtype=np.uint8)
        rgba[~covered] = np.array((220, 38, 38, 115), dtype=np.uint8)
        rgba[covered] = np.array((34, 197, 94, 12), dtype=np.uint8)
        rgba = np.ascontiguousarray(np.flipud(rgba))
        height, width, _ = rgba.shape
        image = QImage(rgba.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            int(self.model_scene.room_size.x * self.scale_px_m),
            int(self.model_scene.room_size.y * self.scale_px_m),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        if self._coverage_item is None:
            self._coverage_item = self.graphics_scene.addPixmap(pixmap)
            self._coverage_item.setZValue(-5)
        else:
            self._coverage_item.setPixmap(pixmap)
        self._coverage_item.setVisible(visible)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
