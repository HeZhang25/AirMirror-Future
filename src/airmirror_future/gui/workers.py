"""Cancelable QThreadPool workers with versioned result delivery."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import threading
import traceback

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from airmirror_future.core.config import field_quality_preset
from airmirror_future.core.types import (
    CancelCheck,
    ChannelResult,
    FieldMapResult,
    Scene,
    SimulationConfig,
)
from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.experiments.xr_dynamic_room_mvp import (
    ADAPTIVE_RIS_MODE,
    NO_RIS_MODE,
    STATIC_RIS_MODE,
    DynamicLinkSample,
    MVPComputation,
    TrajectorySample,
    _pattern_hash,
    compute_adaptive_mvp,
    generate_adaptive_pattern,
    generate_static_pattern,
)
from airmirror_future.experiments.xr_route import XRRouteExperiment
from airmirror_future.experiments.xr_route_headless import compute_route_experiment
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.physics.ris_scattering import PRODUCTION_QUADRATURE_ORDER
from airmirror_future.optimization.greedy import FeedbackGreedyOptimizer
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.physics_guided import PhysicsGuidedFeedbackOptimizer
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_field,
    prepare_controller_link,
)


class WorkerSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)
    progress = Signal(int, int, int, float)
    partial = Signal(int, object)
    terminated = Signal(int, object)


class _XRPhysicsWorker(QRunnable):
    """Report when one XR runnable has actually left the thread pool."""

    @property
    def cancel_requested(self) -> bool:
        return self._cancelled.is_set()

    @Slot()
    def run(self) -> None:
        try:
            self._run()
        finally:
            try:
                self.signals.terminated.emit(self.version, self)
            except RuntimeError:
                pass


class _SmartSpacePhysicsWorker(QRunnable):
    """Report when one Smart Space runnable has actually left the pool."""

    @property
    def cancel_requested(self) -> bool:
        return self._cancelled.is_set()

    @Slot()
    def run(self) -> None:
        try:
            self._run()
        finally:
            try:
                self.signals.terminated.emit(self.version, self)
            except RuntimeError:
                pass


@dataclass(frozen=True, slots=True)
class XRDynamicRoomResult:
    """Cached link states and the single production Static-RIS field map."""

    mvp: MVPComputation
    field_map: FieldMapResult
    field_key: XRFieldCacheKey | None = None


@dataclass(frozen=True, slots=True)
class XRFieldCacheKey:
    """Session-local identity for a complete real XR field-map result.

    This key is a bounded prototype result-cache identity, not the planned
    production coefficient identity and not a P1A matrix cache.
    """

    scene_identity: str
    profile_identity: str
    world_model_identity: str
    command_hash: str
    grid_width: int
    grid_height: int
    map_quantity: str
    coverage_threshold_db: float | None
    batch_size: int
    production_quadrature_order: int
    coefficient_identity: str = ""


@dataclass(frozen=True, slots=True)
class XRAdaptiveFieldResult:
    """One complete Adaptive command field returned by a background worker."""

    sample_index: int
    command_hash: str
    key: XRFieldCacheKey
    field_map: FieldMapResult


@dataclass(frozen=True, slots=True)
class XRFutureFixedFieldRequest:
    """One immutable selected-point request; never a whole-route cache claim."""

    scene: Scene
    static_position: Vec3
    selected_position: Vec3
    selected_point_id: str
    experiment_identity: str
    scene_identity: str
    trajectory_identity: str


@dataclass(frozen=True, slots=True)
class XRFuturePreparedFieldResult:
    """Exact M8 fixed-grid fields produced from one prepared coefficient matrix."""

    request: XRFutureFixedFieldRequest
    mvp: MVPComputation
    static_key: XRFieldCacheKey
    static_field: FieldMapResult
    adaptive_key: XRFieldCacheKey
    adaptive_field: FieldMapResult
    coefficient_identity: str
    build_runtime_s: float
    coefficient_bytes: int


@dataclass(frozen=True, slots=True)
class SmartSpaceRefreshResult:
    """One coherent Smart Space snapshot spanning pattern, metrics, and map."""

    scene: Scene
    patterns: dict[str, np.ndarray]
    pattern_source: str
    focused: ChannelResult
    baseline: ChannelResult
    field_map: FieldMapResult


class _CancelableSimulationEngine(SimulationEngine):
    """Keep existing channel physics while adding worker cancellation points."""

    def __init__(self, cancel_check: CancelCheck) -> None:
        super().__init__()
        self._cancel_check = cancel_check

    def compute_channel(self, *args, **kwargs) -> ChannelResult:
        if self._cancel_check():
            raise SimulationCancelled("background calculation cancelled")
        return super().compute_channel(*args, **kwargs)


def _xr_scene_identity(scene: Scene) -> str:
    payload = json.dumps(
        ["xr_dynamic_room_field_scene", 1, asdict(scene)],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_xr_field_cache_key(
    scene: Scene,
    engine: SimulationEngine,
    model: ControllerModel,
    config: SimulationConfig,
    command_hash: str,
    *,
    coefficient_identity: str = "",
) -> XRFieldCacheKey:
    """Build the complete bounded XR field-result identity for one command."""
    if not isinstance(model, ControllerModel) or isinstance(model, GroundTruthModel):
        raise ValueError("XR field cache requires ControllerModel")
    if not isinstance(command_hash, str) or not command_hash:
        raise ValueError("XR field cache requires a non-empty command hash")
    return XRFieldCacheKey(
        scene_identity=_xr_scene_identity(scene),
        profile_identity=engine.profile_identity,
        world_model_identity="controller_nominal/1",
        command_hash=command_hash,
        grid_width=config.grid_width,
        grid_height=config.grid_height,
        map_quantity=config.map_quantity,
        coverage_threshold_db=config.coverage_threshold_db,
        batch_size=config.batch_size,
        production_quadrature_order=PRODUCTION_QUADRATURE_ORDER,
        coefficient_identity=coefficient_identity,
    )


def _prepared_identity_digest(identities: tuple[str, ...]) -> str:
    """Compact D's exact per-grid receiver coefficient identities for GUI keys."""
    digest = hashlib.sha256()
    digest.update(b"airmirror_prepared_controller_field_gui/1\0")
    for identity in identities:
        digest.update(identity.encode("utf-8"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _dynamic_sample(
    trajectory: TrajectorySample,
    mode: str,
    channel: ChannelResult,
    static_hash: str,
    pattern: np.ndarray | None,
) -> DynamicLinkSample:
    command_hash = "" if pattern is None else _pattern_hash(pattern)
    command_kind = {
        NO_RIS_MODE: "none",
        STATIC_RIS_MODE: "static",
        ADAPTIVE_RIS_MODE: "adaptive",
    }[mode]
    return DynamicLinkSample(
        trajectory=trajectory,
        mode=mode,
        received_power_dbm=channel.received_power_dbm,
        snr_db=channel.snr_db,
        ris_channel=channel.ris_channel,
        static_pattern_hash=static_hash,
        total_channel=channel.total_channel,
        los_channel=channel.los_channel,
        wall_channel=channel.wall_channel,
        noise_power_dbm=channel.noise_power_dbm,
        command_kind=command_kind,
        command_hash=command_hash,
        commanded_pattern=pattern,
    )


class MapWorker(_SmartSpacePhysicsWorker):
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
    def _run(self) -> None:
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


class SmartSpaceRefreshWorker(_SmartSpacePhysicsWorker):
    """Compute one latest-scene Focus, link metrics, and field map in order."""

    def __init__(
        self,
        version: int,
        scene: Scene,
        config: SimulationConfig,
        ground_truth: GroundTruthModel,
        patterns: dict[str, np.ndarray] | None = None,
        pattern_source: str = "Coherent Target Focus",
    ) -> None:
        super().__init__()
        self.version = version
        self.scene = scene
        self.config = config
        self.ground_truth = ground_truth
        self.patterns = patterns
        self.pattern_source = pattern_source
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def _run(self) -> None:
        try:
            if self._cancelled.is_set():
                return
            engine = _CancelableSimulationEngine(self._cancelled.is_set)
            model = ControllerModel()
            ris = self.scene.ris_surfaces[0]
            if self.patterns is not None:
                if set(self.patterns) != {ris.id}:
                    raise ValueError(
                        "Smart Space refresh requires one current RIS command"
                    )
                patterns = {
                    identifier: validate_commanded_pattern(ris, pattern)
                    for identifier, pattern in self.patterns.items()
                    if identifier == ris.id
                }
                if set(patterns) != {ris.id}:
                    raise ValueError(
                        "Smart Space refresh requires one current RIS command"
                    )
                pattern_source = self.pattern_source
            elif self.pattern_source == "RIS-only Physics Focus":
                pattern = generate_focus_pattern(
                    ris,
                    self.scene.transmitter(),
                    self.scene.receiver(),
                    self.scene.frequency_hz,
                )
                patterns = {ris.id: pattern}
                pattern_source = self.pattern_source
            else:
                pattern = generate_coherent_target_pattern(
                    self.scene,
                    model,
                    engine=engine,
                    ris=ris,
                )
                patterns = {ris.id: pattern}
                pattern_source = "Coherent Target Focus"
            if self._cancelled.is_set():
                return
            focused = engine.compute_channel(
                self.scene,
                ris_patterns=patterns,
                model=self.ground_truth,
            )
            if self._cancelled.is_set():
                return
            baseline = engine.compute_channel(
                self.scene,
                ris_patterns={},
                model=self.ground_truth,
            )
            if self._cancelled.is_set():
                return
            field_map = engine.compute_field_map(
                self.scene,
                self.config,
                patterns,
                self.ground_truth,
                cancel_check=self._cancelled.is_set,
            )
            result = SmartSpaceRefreshResult(
                scene=self.scene,
                patterns=patterns,
                pattern_source=pattern_source,
                focused=focused,
                baseline=baseline,
                field_map=field_map,
            )
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


class XRDynamicRoomWorker(_XRPhysicsWorker):
    """Cache three-mode XR links, then one Static-RIS Fast field map."""

    def __init__(
        self,
        version: int,
        route_experiment: XRRouteExperiment | None = None,
    ) -> None:
        super().__init__()
        self.version = version
        self.route_experiment = route_experiment
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def _run(self) -> None:
        try:
            if self._cancelled.is_set():
                return
            engine = _CancelableSimulationEngine(self._cancelled.is_set)
            model = ControllerModel()

            def link_progress(done: int, total: int) -> None:
                try:
                    self.signals.progress.emit(
                        self.version,
                        done,
                        total,
                        done / max(total, 1),
                    )
                except RuntimeError:
                    pass

            if self.route_experiment is None:
                mvp = compute_adaptive_mvp(
                    engine=engine,
                    model=model,
                    cancel_check=self._cancelled.is_set,
                    progress=link_progress,
                )
            else:
                mvp = compute_route_experiment(
                    self.route_experiment,
                    engine=engine,
                    model=model,
                    cancel_check=self._cancelled.is_set,
                    progress=link_progress,
                )
            if self._cancelled.is_set():
                return
            try:
                self.signals.partial.emit(self.version, mvp)
            except RuntimeError:
                return

            fast = field_quality_preset("fast")
            ris = mvp.scene.ris_surfaces[0]
            config = SimulationConfig(fast.grid_width, fast.grid_height, "power")
            field_key = build_xr_field_cache_key(
                mvp.scene,
                engine,
                model,
                config,
                _pattern_hash(mvp.static_pattern),
            )
            field_map = engine.compute_field_map(
                mvp.scene,
                config,
                {ris.id: mvp.static_pattern},
                model,
                cancel_check=self._cancelled.is_set,
            )
            result = XRDynamicRoomResult(
                mvp=mvp,
                field_map=field_map,
                field_key=field_key,
            )
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


class XRFuturePreparedFieldWorker(_XRPhysicsWorker):
    """Build one bounded exact-Future M8 grid and evaluate two real commands."""

    def __init__(
        self,
        version: int,
        request: XRFutureFixedFieldRequest,
        config: SimulationConfig,
    ) -> None:
        super().__init__()
        self.version = version
        self.request = copy.deepcopy(request)
        self.config = copy.deepcopy(config)
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _emit_progress(self, done: int, total: int) -> None:
        try:
            self.signals.progress.emit(
                self.version,
                done,
                total,
                done / max(total, 1),
            )
        except RuntimeError:
            pass

    @Slot()
    def _run(self) -> None:
        try:
            if self._cancelled.is_set():
                return
            scene = copy.deepcopy(self.request.scene)
            enabled = [ris for ris in scene.ris_surfaces if ris.enabled]
            if len(enabled) != 1 or enabled[0].generation != "Future":
                raise ValueError(
                    "XR Future fixed field requires exactly one enabled full Future RIS"
                )
            supported_grids = {(8, 6), (16, 12), (48, 36)}
            grid = (self.config.grid_width, self.config.grid_height)
            if grid not in supported_grids:
                raise ValueError(
                    "XR Future exact field grid must be 8x6, 16x12, or 48x36"
                )
            if PRODUCTION_QUADRATURE_ORDER != 8:
                raise ValueError("XR Future fixed field requires Production M8")

            selected_receiver = replace(
                scene.receiver(),
                position=self.request.selected_position,
            )
            scene.receivers = [selected_receiver]
            engine = SimulationEngine()
            model = ControllerModel()
            static_pattern = generate_static_pattern(
                scene,
                self.request.static_position,
                engine=engine,
                model=model,
            )
            adaptive_pattern = generate_adaptive_pattern(
                scene,
                self.request.selected_position,
                engine=engine,
                model=model,
            )
            trajectory = TrajectorySample(
                0,
                0.0,
                self.request.selected_position,
            )
            prepared_link = prepare_controller_link(
                scene,
                engine=engine,
                rx=selected_receiver,
                controller_model=model,
            )
            baseline = engine.compute_channel(
                scene,
                tx=scene.transmitter(),
                rx=selected_receiver,
                ris_patterns={},
                model=model,
            )
            static_channel = prepared_link.evaluate(static_pattern)
            adaptive_channel = prepared_link.evaluate(adaptive_pattern)
            static_hash = _pattern_hash(static_pattern)
            mvp = MVPComputation(
                scene,
                (trajectory,),
                static_pattern,
                (
                    _dynamic_sample(
                        trajectory,
                        NO_RIS_MODE,
                        baseline,
                        static_hash,
                        None,
                    ),
                    _dynamic_sample(
                        trajectory,
                        STATIC_RIS_MODE,
                        static_channel,
                        static_hash,
                        static_pattern,
                    ),
                    _dynamic_sample(
                        trajectory,
                        ADAPTIVE_RIS_MODE,
                        adaptive_channel,
                        static_hash,
                        adaptive_pattern,
                    ),
                ),
            )
            if self._cancelled.is_set():
                return
            try:
                self.signals.partial.emit(self.version, mvp)
            except RuntimeError:
                return

            total = 3
            self._emit_progress(0, total)
            prepared = prepare_controller_field(
                scene,
                self.config,
                engine=engine,
                controller_model=model,
                receiver_batch_size=8,
            )
            if self._cancelled.is_set():
                return
            coefficient_identity = _prepared_identity_digest(
                prepared.coefficient_identities
            )
            self._emit_progress(1, total)
            static_field = prepared.evaluate(static_pattern)
            self._emit_progress(2, total)
            adaptive_field = prepared.evaluate(adaptive_pattern)
            self._emit_progress(3, total)
            static_key = build_xr_field_cache_key(
                scene,
                engine,
                model,
                self.config,
                static_hash,
                coefficient_identity=coefficient_identity,
            )
            adaptive_key = replace(
                static_key,
                command_hash=_pattern_hash(adaptive_pattern),
            )
            result = XRFuturePreparedFieldResult(
                mvp=mvp,
                static_key=static_key,
                static_field=static_field,
                adaptive_key=adaptive_key,
                adaptive_field=adaptive_field,
                coefficient_identity=coefficient_identity,
                build_runtime_s=prepared.build_runtime_s,
                coefficient_bytes=prepared.coefficient_bytes,
                request=self.request,
            )
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


class XRAdaptiveFieldWorker(_XRPhysicsWorker):
    """Compute one requested Adaptive field without concurrent XR physics."""

    def __init__(
        self,
        version: int,
        sample_index: int,
        scene: Scene,
        config: SimulationConfig,
        commanded_pattern: np.ndarray,
        command_hash: str,
        expected_key: XRFieldCacheKey,
    ) -> None:
        super().__init__()
        self.version = version
        self.sample_index = sample_index
        self.scene = scene
        self.config = config
        ris = scene.ris_surfaces[0]
        self.commanded_pattern = validate_commanded_pattern(ris, commanded_pattern)
        self.commanded_pattern.setflags(write=False)
        self.command_hash = command_hash
        self.expected_key = expected_key
        self.signals = WorkerSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def _run(self) -> None:
        try:
            if self._cancelled.is_set():
                return
            if _pattern_hash(self.commanded_pattern) != self.command_hash:
                raise ValueError("XR Adaptive command hash does not match command snapshot")
            engine = SimulationEngine()
            model = ControllerModel()
            actual_key = build_xr_field_cache_key(
                self.scene,
                engine,
                model,
                self.config,
                self.command_hash,
            )
            if actual_key != self.expected_key:
                raise ValueError("XR Adaptive field request identity changed")
            ris = self.scene.ris_surfaces[0]
            field_map = engine.compute_field_map(
                self.scene,
                self.config,
                {ris.id: self.commanded_pattern},
                model,
                cancel_check=self._cancelled.is_set,
            )
            result = XRAdaptiveFieldResult(
                sample_index=self.sample_index,
                command_hash=self.command_hash,
                key=actual_key,
                field_map=field_map,
            )
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


class OptimizationWorker(_SmartSpacePhysicsWorker):
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
    def _run(self) -> None:
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
