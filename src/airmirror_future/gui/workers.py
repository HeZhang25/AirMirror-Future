"""Cancelable QThreadPool workers with versioned result delivery."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from airmirror_future.core.config import field_quality_preset
from airmirror_future.core.types import FieldMapResult, Scene, SimulationConfig
from airmirror_future.experiments.xr_dynamic_room_mvp import MVPComputation, compute_mvp
from airmirror_future.optimization.greedy import FeedbackGreedyOptimizer
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.physics_guided import PhysicsGuidedFeedbackOptimizer
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


class WorkerSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)
    progress = Signal(int, int, int, float)
    partial = Signal(int, object)


@dataclass(frozen=True, slots=True)
class XRDynamicRoomResult:
    """Cached link states and the single production Static-RIS field map."""

    mvp: MVPComputation
    field_map: FieldMapResult


class MapWorker(QRunnable):
    def __init__(
        self,
        version: int,
        engine: SimulationEngine,
        scene: Scene,
        config: SimulationConfig,
        patterns: dict[str, object],
        model: ControllerModel,
    ) -> None:
        super().__init__()
        self.version = version
        self.engine = engine
        self.scene = scene
        self.config = config
        self.patterns = patterns
        self.model = model
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self.engine.compute_field_map(
                self.scene,
                self.config,
                self.patterns,
                self.model,
                cancel_check=self._cancelled.is_set,
            )
        except SimulationCancelled:
            return
        except Exception:
            try:
                self.signals.failed.emit(self.version, traceback.format_exc())
            except RuntimeError:
                pass
            return
        try:
            self.signals.finished.emit(self.version, result)
        except RuntimeError:
            pass


class XRDynamicRoomWorker(QRunnable):
    """Sequentially cache XR link states and one Static-RIS Fast field map."""

    def __init__(self, version: int) -> None:
        super().__init__()
        self.version = version
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            if self._cancelled.is_set():
                return
            engine = SimulationEngine()
            model = ControllerModel()
            mvp = compute_mvp(engine=engine, model=model)
            if self._cancelled.is_set():
                return
            try:
                self.signals.partial.emit(self.version, mvp)
            except RuntimeError:
                return

            fast = field_quality_preset("fast")
            ris = mvp.scene.ris_surfaces[0]
            field_map = engine.compute_field_map(
                mvp.scene,
                SimulationConfig(fast.grid_width, fast.grid_height, "power"),
                {ris.id: mvp.static_pattern},
                model,
                cancel_check=self._cancelled.is_set,
            )
            result = XRDynamicRoomResult(mvp=mvp, field_map=field_map)
        except SimulationCancelled:
            return
        except Exception:
            if not self._cancelled.is_set():
                try:
                    self.signals.failed.emit(self.version, traceback.format_exc())
                except RuntimeError:
                    pass
            return
        if self._cancelled.is_set():
            return
        try:
            self.signals.finished.emit(self.version, result)
        except RuntimeError:
            pass


class OptimizationWorker(QRunnable):
    def __init__(
        self,
        version: int,
        algorithm: str,
        scene: Scene,
        ground_truth: GroundTruthModel,
        search_levels: int = 8,
    ) -> None:
        super().__init__()
        self.version = version
        self.algorithm = algorithm
        self.scene = scene
        self.ground_truth = ground_truth
        self.search_levels = search_levels
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            engine = SimulationEngine()
            oracle = MeasurementOracle(self.scene, engine, self.ground_truth)
            if self.algorithm == "Feedback Greedy":
                optimizer = FeedbackGreedyOptimizer(4, 4, 1, self.search_levels)
            else:
                optimizer = PhysicsGuidedFeedbackOptimizer(4, 4, 1, self.search_levels)

            def progress(done: int, total: int, value: float) -> None:
                try:
                    self.signals.progress.emit(self.version, done, total, value)
                except RuntimeError:
                    pass

            result = optimizer.optimize(
                ControllerModel(),
                oracle,
                search_levels=self.search_levels,
                cancel_check=self._cancelled.is_set,
                progress=progress,
            )
        except Exception:
            try:
                self.signals.failed.emit(self.version, traceback.format_exc())
            except RuntimeError:
                pass
            return
        try:
            self.signals.finished.emit(self.version, result)
        except RuntimeError:
            pass
