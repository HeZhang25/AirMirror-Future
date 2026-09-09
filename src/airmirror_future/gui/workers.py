"""Cancelable QThreadPool workers with versioned result delivery."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import threading
import traceback
from types import MappingProxyType

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
from airmirror_future.optimization.dual_ris_focus import (
    generate_dual_ris_coordinated_patterns,
)
from airmirror_future.experiments.xr_route import XRRouteExperiment
from airmirror_future.experiments.xr_route_headless import compute_route_experiment
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.physics.ris_scattering import (
    FAST_1X1_RIS_COEFFICIENT_MODEL,
    PRODUCTION_QUADRATURE_ORDER,
    PRODUCTION_RIS_COEFFICIENT_MODEL,
    RISCoefficientModel,
)
from airmirror_future.optimization.greedy import FeedbackGreedyOptimizer
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.optimization.physics_guided import PhysicsGuidedFeedbackOptimizer
from airmirror_future.ris.phase import generate_focus_pattern
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.prepared_controller import (
    prepare_controller_field,
    prepare_controller_link,
    prepare_controller_dual_ris_field,
    prepare_controller_dual_ris_link,
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
    coefficient_model_identity: str = ""
    quadrature_identity: str = ""
    quadrature_order_x: int = PRODUCTION_QUADRATURE_ORDER
    quadrature_order_y: int = PRODUCTION_QUADRATURE_ORDER


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
    coefficient_model_identity: str = PRODUCTION_RIS_COEFFICIENT_MODEL.identity
    trajectory: tuple[TrajectorySample, ...] = ()


@dataclass(frozen=True, slots=True)
class XRFuturePreparedFieldResult:
    """Fixed-grid fields produced from one explicitly selected prepared model."""

    request: XRFutureFixedFieldRequest
    mvp: MVPComputation
    static_key: XRFieldCacheKey
    static_field: FieldMapResult
    adaptive_key: XRFieldCacheKey
    adaptive_field: FieldMapResult
    adaptive_fields: tuple[tuple[XRFieldCacheKey, FieldMapResult], ...]
    adaptive_batch_runtime_s: float
    coefficient_identity: str
    coefficient_model_identity: str
    quadrature_identity: str
    build_runtime_s: float
    coefficient_bytes: int
    static_patterns: Mapping[str, np.ndarray]
    adaptive_patterns: tuple[tuple[str, Mapping[str, np.ndarray]], ...]


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
        coefficient_model_identity=engine.coefficient_model.identity,
        quadrature_identity=engine.coefficient_model.quadrature_identity,
        quadrature_order_x=engine.coefficient_model.quadrature_order_x,
        quadrature_order_y=engine.coefficient_model.quadrature_order_y,
    )


def _prepared_identity_digest(identities: tuple[str, ...]) -> str:
    """Compact D's exact per-grid receiver coefficient identities for GUI keys."""
    digest = hashlib.sha256()
    digest.update(b"airmirror_prepared_controller_field_gui/1\0")
    for identity in identities:
        digest.update(identity.encode("utf-8"))
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _command_hash(command: object) -> str:
    """Hash one command or a deterministic RIS-id to command mapping."""
    if isinstance(command, dict):
        digest = hashlib.sha256()
        digest.update(b"airmirror_dual_ris_command_gui/1\0")
        for identifier in sorted(command):
            digest.update(identifier.encode("utf-8"))
            digest.update(b"\0")
            digest.update(np.asarray(command[identifier], dtype=">f8").tobytes())
        return "sha256:" + digest.hexdigest()
    return _pattern_hash(np.asarray(command))


def _first_command(command: object) -> np.ndarray:
    if isinstance(command, dict):
        return next(iter(command.values()))
    return np.asarray(command)


def _frozen_command_mapping(
    command: object,
    ris_ids: tuple[str, ...],
) -> Mapping[str, np.ndarray]:
    """Preserve every evaluated RIS command for truthful GUI inspection."""
    if isinstance(command, dict):
        if set(command) != set(ris_ids):
            raise ValueError("multi-RIS command does not match enabled RIS ids")
        source = command
    elif len(ris_ids) == 1:
        source = {ris_ids[0]: np.asarray(command)}
    else:
        raise ValueError("dual-RIS command must be an RIS-id mapping")
    frozen: dict[str, np.ndarray] = {}
    for identifier in ris_ids:
        pattern = np.array(source[identifier], dtype=float, copy=True)
        pattern.setflags(write=False)
        frozen[identifier] = pattern
    return MappingProxyType(frozen)


def _future_coefficient_model(identity: str) -> RISCoefficientModel:
    """Resolve only the two explicit Future GUI coefficient-model choices."""
    for model in (
        FAST_1X1_RIS_COEFFICIENT_MODEL,
        PRODUCTION_RIS_COEFFICIENT_MODEL,
    ):
        if identity == model.identity:
            return model
    raise ValueError(f"unsupported XR Future coefficient model: {identity}")


def _dynamic_sample(
    trajectory: TrajectorySample,
    mode: str,
    channel: ChannelResult,
    static_hash: str,
    pattern: np.ndarray | None,
    command_hash: str | None = None,
) -> DynamicLinkSample:
    resolved_command_hash = (
        ("" if pattern is None else _pattern_hash(pattern))
        if command_hash is None
        else command_hash
    )
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
        command_hash=resolved_command_hash,
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
    """Build one bounded Future grid and evaluate two real commands."""

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
            if not 1 <= len(enabled) <= 2 or any(
                ris.generation != "Future" for ris in enabled
            ):
                raise ValueError(
                    "XR Future fixed field requires one or two enabled full Future RIS surfaces"
                )
            supported_grids = {(8, 6), (16, 12), (48, 36)}
            grid = (self.config.grid_width, self.config.grid_height)
            if grid not in supported_grids:
                raise ValueError(
                    "XR Future field grid must be 8x6, 16x12, or 48x36"
                )
            coefficient_model = _future_coefficient_model(
                self.request.coefficient_model_identity
            )
            if (
                coefficient_model is PRODUCTION_RIS_COEFFICIENT_MODEL
                and PRODUCTION_QUADRATURE_ORDER != 8
            ):
                raise ValueError("XR Future exact field requires Production M8")

            selected_receiver = replace(
                scene.receiver(),
                position=self.request.selected_position,
            )
            scene.receivers = [selected_receiver]
            engine = SimulationEngine(coefficient_model=coefficient_model)
            model = ControllerModel()
            dual = len(enabled) == 2
            ris_ids = tuple(ris.id for ris in enabled)

            def command_at(position: object) -> object:
                if not dual:
                    if position is self.request.static_position:
                        return generate_static_pattern(
                            scene, position, engine=engine, model=model
                        )
                    return generate_adaptive_pattern(
                        scene, position, engine=engine, model=model
                    )
                target_scene = copy.deepcopy(scene)
                target_scene.receivers = [
                    replace(target_scene.receiver(), position=position)
                ]
                return generate_dual_ris_coordinated_patterns(
                    target_scene,
                    model,
                    engine=engine,
                    tx=target_scene.transmitter(),
                    rx=target_scene.receiver(),
                    ris_ids=ris_ids,
                ).patterns

            static_pattern = command_at(self.request.static_position)
            selected_adaptive_pattern = command_at(self.request.selected_position)
            trajectory = self.request.trajectory or (
                TrajectorySample(
                    0,
                    0.0,
                    self.request.selected_position,
                ),
            )
            if len(trajectory) > 512:
                raise ValueError(
                    "XR Future prepared route playback is bounded to 512 samples"
                )
            static_hash = _command_hash(static_pattern)
            dynamic_samples: list[DynamicLinkSample] = []
            adaptive_patterns: dict[str, object] = {}
            for trajectory_sample in trajectory:
                if self._cancelled.is_set():
                    return
                route_scene = copy.deepcopy(scene)
                route_receiver = replace(
                    route_scene.receiver(),
                    position=trajectory_sample.position,
                )
                route_scene.receivers = [route_receiver]
                if dual:
                    adaptive_pattern = generate_dual_ris_coordinated_patterns(
                        route_scene,
                        model,
                        engine=engine,
                        tx=route_scene.transmitter(),
                        rx=route_receiver,
                        ris_ids=ris_ids,
                    ).patterns
                    prepared_link = prepare_controller_dual_ris_link(
                        route_scene,
                        engine=engine,
                        rx=route_receiver,
                        controller_model=model,
                        ris_ids=ris_ids,
                    )
                else:
                    adaptive_pattern = generate_adaptive_pattern(
                        route_scene,
                        trajectory_sample.position,
                        engine=engine,
                        model=model,
                    )
                    prepared_link = prepare_controller_link(
                        route_scene,
                        engine=engine,
                        rx=route_receiver,
                        controller_model=model,
                    )
                if (
                    prepared_link.coefficient_model_identity
                    != coefficient_model.identity
                ):
                    raise RuntimeError(
                        "prepared link coefficient-model identity does not match request"
                    )
                baseline = engine.compute_channel(
                    route_scene,
                    tx=route_scene.transmitter(),
                    rx=route_receiver,
                    ris_patterns={},
                    model=model,
                )
                static_channel = prepared_link.evaluate(static_pattern)
                adaptive_channel = prepared_link.evaluate(adaptive_pattern)
                adaptive_hash = _command_hash(adaptive_pattern)
                adaptive_patterns.setdefault(adaptive_hash, adaptive_pattern)
                dynamic_samples.extend(
                    (
                        _dynamic_sample(
                            trajectory_sample,
                            NO_RIS_MODE,
                            baseline,
                            static_hash,
                            None,
                        ),
                        _dynamic_sample(
                            trajectory_sample,
                            STATIC_RIS_MODE,
                            static_channel,
                            static_hash,
                            _first_command(static_pattern),
                        ),
                        _dynamic_sample(
                            trajectory_sample,
                            ADAPTIVE_RIS_MODE,
                            adaptive_channel,
                            static_hash,
                            _first_command(adaptive_pattern),
                            adaptive_hash,
                        ),
                    )
                )
            selected_adaptive_hash = _command_hash(selected_adaptive_pattern)
            adaptive_patterns.setdefault(
                selected_adaptive_hash,
                selected_adaptive_pattern,
            )
            mvp = MVPComputation(
                scene,
                tuple(trajectory),
                # The prepared evaluator keeps the complete RIS-id mapping;
                # MVP's legacy pattern view remains a single-array snapshot.
                _first_command(static_pattern),
                tuple(dynamic_samples),
            )
            receiver_total = self.config.grid_width * self.config.grid_height
            total = receiver_total + 2
            self._emit_progress(0, total)

            def build_progress(completed: int, build_total: int) -> None:
                if build_total != receiver_total:
                    raise RuntimeError(
                        "prepared field progress total does not match map grid"
                    )
                # The worker already emitted the initial zero. Keep every
                # subsequent value as D's real completed-receiver count.
                if completed > 0:
                    self._emit_progress(completed, total)

            if dual:
                prepared = prepare_controller_dual_ris_field(
                    scene,
                    self.config,
                    engine=engine,
                    controller_model=model,
                    ris_ids=ris_ids,
                    receiver_batch_size=8,
                    progress=build_progress,
                    cancel_check=self._cancelled.is_set,
                )
            else:
                prepared = prepare_controller_field(
                    scene,
                    self.config,
                    engine=engine,
                    controller_model=model,
                    receiver_batch_size=8,
                    progress=build_progress,
                    cancel_check=self._cancelled.is_set,
                )
            if self._cancelled.is_set():
                return
            if prepared.coefficient_model_identity != coefficient_model.identity:
                raise RuntimeError(
                    "prepared field coefficient-model identity does not match request"
                )
            raw_identities = prepared.coefficient_identities
            if raw_identities and isinstance(raw_identities[0], tuple):
                raw_identities = tuple(
                    identity for group in raw_identities for identity in group
                )
            coefficient_identity = _prepared_identity_digest(raw_identities)
            static_field = prepared.evaluate(static_pattern)
            if self._cancelled.is_set():
                return
            self._emit_progress(receiver_total + 1, total)
            static_key = build_xr_field_cache_key(
                scene,
                engine,
                model,
                self.config,
                static_hash,
                coefficient_identity=coefficient_identity,
            )
            adaptive_fields: list[tuple[XRFieldCacheKey, FieldMapResult]] = []
            for command_hash, pattern in adaptive_patterns.items():
                adaptive_field = prepared.evaluate(pattern)
                if self._cancelled.is_set():
                    return
                adaptive_fields.append(
                    (
                        replace(static_key, command_hash=command_hash),
                        adaptive_field,
                    )
                )
            adaptive_field_lookup = {
                key.command_hash: field for key, field in adaptive_fields
            }
            adaptive_key = replace(
                static_key,
                command_hash=selected_adaptive_hash,
            )
            adaptive_field = adaptive_field_lookup[selected_adaptive_hash]
            self._emit_progress(receiver_total + 2, total)
            result = XRFuturePreparedFieldResult(
                mvp=mvp,
                static_key=static_key,
                static_field=static_field,
                adaptive_key=adaptive_key,
                adaptive_field=adaptive_field,
                adaptive_fields=tuple(adaptive_fields),
                adaptive_batch_runtime_s=sum(
                    field.runtime_s for _key, field in adaptive_fields
                ),
                coefficient_identity=coefficient_identity,
                coefficient_model_identity=prepared.coefficient_model_identity,
                quadrature_identity=coefficient_model.quadrature_identity,
                build_runtime_s=prepared.build_runtime_s,
                coefficient_bytes=prepared.coefficient_bytes,
                request=self.request,
                static_patterns=_frozen_command_mapping(static_pattern, ris_ids),
                adaptive_patterns=tuple(
                    (
                        command_hash,
                        _frozen_command_mapping(pattern, ris_ids),
                    )
                    for command_hash, pattern in adaptive_patterns.items()
                ),
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
