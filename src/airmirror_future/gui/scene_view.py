"""Interactive QGraphicsView scene and NumPy heatmap renderer."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import math

import numpy as np
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from airmirror_future.core.types import FieldMapResult, Scene, Vec3


EntityMoved = Callable[[str, Vec3], None]
RoutePointMoved = Callable[[int, Vec3], None]
RoutePointSelected = Callable[[int], None]


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


class _RoutePointItem(QGraphicsEllipseItem):
    """Selectable route control point with a model-coordinate drag callback."""

    def __init__(
        self,
        route_index: int,
        moved_callback: Callable[[int, QPointF], None],
        selected_callback: RoutePointSelected,
    ) -> None:
        super().__init__(-6.0, -6.0, 12.0, 12.0)
        self.route_index = route_index
        self.moved_callback = moved_callback
        self.selected_callback = selected_callback
        self.setBrush(QColor("#0ea5e9"))
        self.setPen(QPen(QColor("#e0f2fe"), 1.5))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(13)
        self.setToolTip(f"Route point {route_index + 1} · drag or use the form")

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: object,
    ) -> object:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.moved_callback(self.route_index, self.pos())
        elif (
            change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged
            and bool(value)
        ):
            self.selected_callback(self.route_index)
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
        self.on_route_point_moved: RoutePointMoved | None = None
        self.on_route_point_selected: RoutePointSelected | None = None
        self._suppress_moves = False
        self._suppress_route_events = False
        self._heatmap_item: QGraphicsPixmapItem | None = None
        self._coverage_item: QGraphicsPixmapItem | None = None
        self._field_legend_item: QGraphicsPixmapItem | None = None
        self._field_legend_labels: list[QGraphicsSimpleTextItem] = []
        self._field_legend_text: str | None = None
        self._gain_legend_gmax_db: float | None = None
        self._field_value_range: tuple[float, float] | None = None
        self._show_labels = True
        self._show_rays = True
        self._entities_draggable = True
        self._entity_items: dict[str, QGraphicsItem] = {}
        self._entity_labels: dict[str, QGraphicsSimpleTextItem] = {}
        self._trajectory_path: QGraphicsPathItem | None = None
        self._trajectory_markers: list[QGraphicsEllipseItem] = []
        self._route_positions: list[Vec3] = []
        self._route_point_items: list[_RoutePointItem] = []
        self._route_event_generation = 0
        self._pending_route_moves: dict[int, Vec3] = {}
        self._route_move_delivery_scheduled = False
        self._editable_route_valid = True
        self._editable_route_error: str | None = None

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
                label = self._entity_labels.get(identifier)
                item = self._entity_items.get(identifier)
                if label is not None and item is not None:
                    is_ris = any(
                        ris.id == identifier for ris in self.model_scene.ris_surfaces
                    )
                    offset = QPointF(8, 8) if is_ris else QPointF(10, -18)
                    label.setPos(item.pos() + offset)
                return

    def _route_point_moved(self, index: int, point: QPointF) -> None:
        if (
            self._suppress_route_events
            or self.model_scene is None
            or self.on_route_point_moved is None
            or not 0 <= index < len(self._route_positions)
        ):
            return
        position = self._model_position(point, self._route_positions[index].z)
        self._route_positions[index] = position
        clamped_point = self._point(position)
        if self._route_point_items[index].pos() != clamped_point:
            self._suppress_route_events = True
            try:
                self._route_point_items[index].setPos(clamped_point)
            finally:
                self._suppress_route_events = False
        if self._trajectory_path is not None:
            points = [self._point(route_position) for route_position in self._route_positions]
            path = QPainterPath(points[0])
            for route_point in points[1:]:
                path.lineTo(route_point)
            self._trajectory_path.setPath(path)
        self._pending_route_moves[index] = position
        if not self._route_move_delivery_scheduled:
            self._route_move_delivery_scheduled = True
            generation = self._route_event_generation
            QTimer.singleShot(0, lambda: self._deliver_route_moves(generation))

    def _deliver_route_moves(self, generation: int) -> None:
        """Notify the model only after the active QGraphicsItem callback returns."""
        if generation != self._route_event_generation:
            return
        self._route_move_delivery_scheduled = False
        pending = self._pending_route_moves
        self._pending_route_moves = {}
        callback = self.on_route_point_moved
        if callback is None:
            return
        for index, position in pending.items():
            callback(index, position)

    def _route_point_selected(self, index: int) -> None:
        if self._suppress_route_events or self.on_route_point_selected is None:
            return
        self.on_route_point_selected(index)

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
        old_gain_gmax = (
            self._gain_legend_gmax_db if preserve_heatmap and old_pixmap is not None else None
        )
        self.model_scene = scene
        self._suppress_moves = True
        self.graphics_scene.clear()
        self._heatmap_item = None
        self._coverage_item = None
        self._field_legend_item = None
        self._field_legend_labels = []
        self._field_legend_text = None
        self._gain_legend_gmax_db = old_gain_gmax
        self._field_value_range = None
        self._entity_items = {}
        self._entity_labels = {}
        self._trajectory_path = None
        self._trajectory_markers = []
        self._route_positions = []
        self._route_point_items = []
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
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self._entities_draggable,
            )
            item.setPos(self._point(position))
            self.graphics_scene.addItem(item)
            self._entity_items[identifier] = item
            if self._show_labels:
                text = self.graphics_scene.addSimpleText(label)
                text.setBrush(Qt.GlobalColor.white)
                text.setPos(item.pos() + QPointF(10, -18))
                text.setZValue(21)
                self._entity_labels[identifier] = text
        for ris in scene.ris_surfaces:
            item = _DraggableRIS(ris.id, ris.width_m * self.scale_px_m, self._moved)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self._entities_draggable,
            )
            item.setPos(self._point(ris.position))
            item.setRotation(-math.degrees(ris.yaw_rad + math.pi / 2.0))
            item.setOpacity(1.0 if ris.enabled else 0.35)
            item.setToolTip(
                f"{ris.id} · {ris.generation} · "
                f"{'enabled' if ris.enabled else 'disabled'}"
            )
            self.graphics_scene.addItem(item)
            self._entity_items[ris.id] = item
            if self._show_labels:
                state = "on" if ris.enabled else "off"
                text = self.graphics_scene.addSimpleText(
                    f"{ris.id} · {ris.generation} · {state}"
                )
                text.setBrush(Qt.GlobalColor.white)
                text.setPos(item.pos() + QPointF(8, 8))
                text.setZValue(21)
                self._entity_labels[ris.id] = text
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
        if old_gain_gmax is not None:
            self._render_gain_legend(old_gain_gmax)
        self._suppress_moves = False
        self.fitInView(self.graphics_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_entities_draggable(self, enabled: bool) -> None:
        """Enable ordinary scene editing or freeze entities for result playback."""
        self._entities_draggable = bool(enabled)
        for item in self._entity_items.values():
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self._entities_draggable,
            )

    def set_draggable_entity_ids(self, identifiers: set[str]) -> None:
        """Allow a bounded entity subset to move while other entities stay frozen."""
        allowed = set(identifiers)
        for identifier, item in self._entity_items.items():
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                identifier in allowed,
            )

    def set_entity_visual_position(self, identifier: str, position: Vec3) -> None:
        """Move one rendered entity without mutating the underlying Scene."""
        item = self._entity_items.get(identifier)
        if item is None or self.model_scene is None:
            return
        self._suppress_moves = True
        try:
            item.setPos(self._point(position))
            label = self._entity_labels.get(identifier)
            if label is not None:
                label.setPos(item.pos() + QPointF(10, -18))
        finally:
            self._suppress_moves = False

    def clear_trajectory(self) -> None:
        """Remove the prototype trajectory overlay, if present."""
        self._route_event_generation += 1
        self._pending_route_moves = {}
        self._route_move_delivery_scheduled = False
        if self._trajectory_path is not None:
            self.graphics_scene.removeItem(self._trajectory_path)
        for marker in self._trajectory_markers:
            self.graphics_scene.removeItem(marker)
        self._trajectory_path = None
        self._trajectory_markers = []
        self._route_positions = []
        self._route_point_items = []
        self._editable_route_valid = True
        self._editable_route_error = None

    def show_trajectory(self, positions: Sequence[Vec3]) -> None:
        """Draw one fixed top-down trajectory and all of its sample positions."""
        self.clear_trajectory()
        if self.model_scene is None or not positions:
            return
        points = [self._point(position) for position in positions]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        self._trajectory_path = self.graphics_scene.addPath(
            path,
            QPen(QColor("#38bdf8"), 2, Qt.PenStyle.DashLine),
        )
        self._trajectory_path.setZValue(10)
        for point in points:
            marker = self.graphics_scene.addEllipse(
                -3.0,
                -3.0,
                6.0,
                6.0,
                QPen(QColor("#e0f2fe"), 1),
                QBrush(QColor("#0ea5e9")),
            )
            marker.setPos(point)
            marker.setZValue(11)
            self._trajectory_markers.append(marker)
        self.set_trajectory_index(0)

    def set_trajectory_index(self, index: int) -> None:
        """Highlight the active sample without rebuilding the overlay."""
        if not 0 <= index < len(self._trajectory_markers):
            return
        for marker_index, marker in enumerate(self._trajectory_markers):
            active = marker_index == index
            marker.setBrush(QBrush(QColor("#facc15" if active else "#0ea5e9")))
            if active:
                marker.setRect(-5.0, -5.0, 10.0, 10.0)
            else:
                marker.setRect(-3.0, -3.0, 6.0, 6.0)
            marker.setZValue(12 if active else 11)

    def show_editable_route(
        self,
        positions: Sequence[Vec3],
        *,
        selected_index: int = 0,
    ) -> None:
        """Render selectable, draggable route control points and their polyline."""
        self.clear_trajectory()
        if self.model_scene is None or not positions:
            return
        self._route_positions = list(positions)
        points = [self._point(position) for position in positions]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        self._trajectory_path = self.graphics_scene.addPath(
            path,
            QPen(QColor("#38bdf8"), 2.5, Qt.PenStyle.SolidLine),
        )
        self._trajectory_path.setZValue(10)
        self._suppress_route_events = True
        try:
            for index, point in enumerate(points):
                marker = _RoutePointItem(
                    index,
                    self._route_point_moved,
                    self._route_point_selected,
                )
                marker.setPos(point)
                self.graphics_scene.addItem(marker)
                marker.setSelected(index == selected_index)
                self._trajectory_markers.append(marker)
                self._route_point_items.append(marker)
        finally:
            self._suppress_route_events = False

    def set_editable_route_validity(
        self,
        valid: bool,
        message: str | None = None,
    ) -> None:
        """Show validation state without rebuilding live route graphics items."""
        self._editable_route_valid = bool(valid)
        self._editable_route_error = message
        if self._trajectory_path is not None and self._route_point_items:
            color = QColor("#38bdf8" if valid else "#ef4444")
            style = Qt.PenStyle.SolidLine if valid else Qt.PenStyle.DashLine
            self._trajectory_path.setPen(QPen(color, 2.5, style))
        for index, item in enumerate(self._route_point_items):
            selected = item.isSelected()
            if selected:
                color = "#facc15"
            else:
                color = "#0ea5e9" if valid else "#ef4444"
            item.setBrush(QBrush(QColor(color)))
            if valid or not message:
                item.setToolTip(f"Route point {index + 1} · drag or use the form")
            else:
                item.setToolTip(f"Route invalid: {message}")

    def select_route_point(self, index: int) -> None:
        """Select one route point without recreating the route."""
        if not 0 <= index < len(self._route_point_items):
            return
        self._suppress_route_events = True
        try:
            for item_index, item in enumerate(self._route_point_items):
                item.setSelected(item_index == index)
                item.setBrush(
                    QBrush(
                        QColor(
                            "#facc15"
                            if item_index == index
                            else "#0ea5e9"
                            if self._editable_route_valid
                            else "#ef4444"
                        )
                    )
                )
                item.setZValue(14 if item_index == index else 13)
        finally:
            self._suppress_route_events = False

    @staticmethod
    def field_value_range(*arrays: np.ndarray) -> tuple[float, float]:
        """Return one robust color range shared by all supplied field arrays."""
        finite_parts = [
            np.asarray(values, dtype=float)[np.isfinite(values)]
            for values in arrays
        ]
        finite_parts = [values for values in finite_parts if values.size]
        if not finite_parts:
            return (0.0, 1.0)
        low, high = np.percentile(np.concatenate(finite_parts), (3, 97))
        if high <= low:
            high = low + 1.0
        return float(low), float(high)

    @staticmethod
    def _rgba(
        values: np.ndarray,
        *,
        value_range: tuple[float, float] | None = None,
    ) -> np.ndarray:
        low, high = (
            SceneView.field_value_range(values)
            if value_range is None
            else value_range
        )
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ValueError("field color range must be finite and increasing")
        normalized = np.clip((values - low) / (high - low), 0.0, 1.0)
        normalized = np.where(np.isfinite(normalized), normalized, 0.0)
        red = np.clip(1.8 * normalized, 0.0, 1.0)
        green = np.clip(1.8 - np.abs(normalized - 0.55) * 3.0, 0.0, 1.0)
        blue = np.clip(1.6 * (1.0 - normalized), 0.0, 1.0)
        alpha = np.full_like(normalized, 0.72)
        return (np.stack((red, green, blue, alpha), axis=2) * 255.0).astype(np.uint8)

    @staticmethod
    def _ris_gain_rgba(
        values: np.ndarray, *, gmax: float | None = None
    ) -> tuple[np.ndarray, float]:
        """Render gain with a robust symmetric range and a fixed neutral zero."""
        values = np.asarray(values, dtype=float)
        if gmax is None:
            finite = np.abs(values[np.isfinite(values)])
            gmax = float(np.percentile(finite, 97)) if finite.size else 0.0
        if gmax <= np.finfo(float).eps:
            gmax = 1.0

        signed = np.zeros_like(values, dtype=float)
        np.divide(values, gmax, out=signed, where=np.isfinite(values))
        signed = np.clip(signed, -1.0, 1.0)
        negative = np.clip(-signed, 0.0, 1.0)[..., None]
        positive = np.clip(signed, 0.0, 1.0)[..., None]
        neutral = np.array((0.95, 0.95, 0.95))
        blue = np.array((0.12, 0.47, 0.84))
        red = np.array((0.88, 0.18, 0.18))
        rgb = neutral + negative * (blue - neutral) + positive * (red - neutral)
        alpha = np.full((*values.shape, 1), 0.72)
        rgba = (np.concatenate((rgb, alpha), axis=2) * 255.0).astype(np.uint8)
        return rgba, gmax

    def _remove_field_legend_items(self) -> None:
        if self._field_legend_item is not None:
            self.graphics_scene.removeItem(self._field_legend_item)
        for label in self._field_legend_labels:
            self.graphics_scene.removeItem(label)
        self._field_legend_item = None
        self._field_legend_labels = []
        self._field_legend_text = None

    def _render_gain_legend(self, gmax: float) -> None:
        self._remove_field_legend_items()
        bar_width = 300
        bar_height = 12
        samples = np.linspace(-gmax, gmax, bar_width, dtype=float)[None, :]
        bar_rgba, _ = self._ris_gain_rgba(samples, gmax=gmax)
        bar_rgba[:, :, 3] = 255
        bar_rgba = np.ascontiguousarray(np.repeat(bar_rgba, bar_height, axis=0))
        image = QImage(
            bar_rgba.data,
            bar_width,
            bar_height,
            bar_width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        self._field_legend_item = self.graphics_scene.addPixmap(QPixmap.fromImage(image))
        self._field_legend_item.setPos(10, 26)
        self._field_legend_item.setZValue(30)

        title = "RIS Gain: blue < 0 · neutral = 0 · red > 0"
        numeric_labels = (f"{-gmax:+.2f} dB", "0.00 dB", f"{gmax:+.2f} dB")
        for text in (title, *numeric_labels):
            label = self.graphics_scene.addSimpleText(text)
            label.setBrush(QColor("#f8fafc"))
            label.setZValue(31)
            self._field_legend_labels.append(label)
        self._field_legend_labels[0].setPos(10, 6)
        low, zero, high = self._field_legend_labels[1:]
        low.setPos(10, 40)
        zero.setPos(10 + bar_width / 2 - zero.boundingRect().width() / 2, 40)
        high.setPos(10 + bar_width - high.boundingRect().width(), 40)
        self._field_legend_text = f"{title}; {' | '.join(numeric_labels)}"
        self._field_legend_item.setToolTip(self._field_legend_text)

    def _render_scalar_legend(
        self,
        quantity: str,
        value_range: tuple[float, float],
    ) -> None:
        """Render the explicit shared scale used by an XR scalar field."""
        self._remove_field_legend_items()
        low, high = value_range
        bar_width = 300
        bar_height = 12
        samples = np.linspace(low, high, bar_width, dtype=float)[None, :]
        bar_rgba = self._rgba(samples, value_range=value_range)
        bar_rgba[:, :, 3] = 255
        bar_rgba = np.ascontiguousarray(np.repeat(bar_rgba, bar_height, axis=0))
        image = QImage(
            bar_rgba.data,
            bar_width,
            bar_height,
            bar_width * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        self._field_legend_item = self.graphics_scene.addPixmap(QPixmap.fromImage(image))
        self._field_legend_item.setPos(10, 26)
        self._field_legend_item.setZValue(30)

        unit = "dBm" if quantity == "接收功率" else "dB"
        title = (
            "Power · shared No RIS / Static RIS scale · Adaptive uses same bounds"
            if quantity == "接收功率"
            else "SNR · shared No RIS / Static RIS scale · Adaptive uses same bounds"
        )
        numeric_labels = (f"{low:.2f} {unit}", f"{high:.2f} {unit}")
        for text in (title, *numeric_labels):
            label = self.graphics_scene.addSimpleText(text)
            label.setBrush(QColor("#f8fafc"))
            label.setZValue(31)
            self._field_legend_labels.append(label)
        self._field_legend_labels[0].setPos(10, 6)
        low_label, high_label = self._field_legend_labels[1:]
        low_label.setPos(10, 40)
        high_label.setPos(10 + bar_width - high_label.boundingRect().width(), 40)
        self._field_legend_text = (
            f"{title}; {numeric_labels[0]} | {numeric_labels[1]}"
        )
        self._field_legend_item.setToolTip(self._field_legend_text)

    def set_field_map(
        self,
        result: FieldMapResult,
        quantity: str,
        *,
        value_range: tuple[float, float] | None = None,
    ) -> None:
        if self.model_scene is None:
            return
        values = {
            "接收功率": result.received_power_dbm,
            "SNR": result.snr_db,
            "RIS 增益": result.ris_gain_db,
        }[quantity]
        if quantity == "RIS 增益":
            rgba, gmax = self._ris_gain_rgba(values)
            self._gain_legend_gmax_db = gmax
            self._field_value_range = None
        else:
            active_range = (
                self.field_value_range(values)
                if value_range is None
                else value_range
            )
            rgba = self._rgba(values, value_range=active_range)
            self._gain_legend_gmax_db = None
            self._field_value_range = active_range
            if value_range is None:
                self._remove_field_legend_items()
            else:
                self._render_scalar_legend(quantity, active_range)
        rgba = np.ascontiguousarray(np.flipud(rgba))
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
        if self._gain_legend_gmax_db is not None:
            self._render_gain_legend(self._gain_legend_gmax_db)

    def set_field_visible(self, visible: bool) -> None:
        if self._heatmap_item is not None:
            self._heatmap_item.setVisible(visible)
        if self._field_legend_item is not None:
            self._field_legend_item.setVisible(visible)
        for label in self._field_legend_labels:
            label.setVisible(visible)

    def clear_field_overlays(self) -> None:
        """Remove field and coverage graphics after their inputs become stale."""
        if self._heatmap_item is not None:
            self.graphics_scene.removeItem(self._heatmap_item)
        if self._coverage_item is not None:
            self.graphics_scene.removeItem(self._coverage_item)
        self._heatmap_item = None
        self._coverage_item = None
        self._remove_field_legend_items()
        self._field_legend_text = None
        self._gain_legend_gmax_db = None
        self._field_value_range = None

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
