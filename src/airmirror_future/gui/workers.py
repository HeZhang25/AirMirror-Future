"""Cancelable QThreadPool workers with versioned result delivery."""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from airmirror_future.core.types import Scene, SimulationConfig
from airmirror_future.optimization.greedy import FeedbackGreedyOptimizer
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.physics_guided import PhysicsGuidedFeedbackOptimizer
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


class WorkerSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)
    progress = Signal(int, int, int, float)


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


class OptimizationWorker(QRunnable):
    def __init__(
        self,
        version: int,
        algorithm: str,
        scene: Scene,
        ground_truth: GroundTruthModel,
    ) -> None:
        super().__init__()
        self.version = version
        self.algorithm = algorithm
        self.scene = scene
        self.ground_truth = ground_truth
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
                optimizer = FeedbackGreedyOptimizer(4, 4, 1)
            else:
                optimizer = PhysicsGuidedFeedbackOptimizer(4, 4, 1)

            def progress(done: int, total: int, value: float) -> None:
                try:
                    self.signals.progress.emit(self.version, done, total, value)
                except RuntimeError:
                    pass

            result = optimizer.optimize(
                ControllerModel(),
                oracle,
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
