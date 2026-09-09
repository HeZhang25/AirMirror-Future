"""Explicit, bounded Controller-only coefficient reuse for headless XR work."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field, replace
import math
import time

import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import (
    ChannelResult,
    FieldMapResult,
    Receiver,
    RISSurface,
    Scene,
    SimulationConfig,
    Transmitter,
    Vec3,
)
from airmirror_future.core.units import watts_to_dbm
from airmirror_future.physics.noise import noise_power_dbm, shannon_capacity_bps
from airmirror_future.physics.ris_scattering import (
    PRODUCTION_RIS_COEFFICIENT_MODEL,
    ris_control_coefficient_matrix,
)
from airmirror_future.simulation.coefficient_identity import (
    _quadrature_canonical_json,
    controller_ris_coefficient_identity,
)
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.profiles import PropagationPathContext


DEFAULT_COEFFICIENT_MEMORY_BUDGET_BYTES = 128 * 1024 * 1024
ReceiverProgress = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class _RISCommandSnapshot:
    """Only the immutable RIS command contract consumed by validation."""

    id: str
    cell_count: int
    phase_bits: int | None


@dataclass(frozen=True, slots=True)
class _LinkEvaluationSnapshot:
    ris: _RISCommandSnapshot
    reflection_efficiency: float
    bandwidth_hz: float
    tx_power_w: float
    rx_noise_figure_db: float
    ris_id: str


@dataclass(frozen=True, slots=True)
class _FieldEvaluationSnapshot:
    ris: _RISCommandSnapshot
    reflection_efficiency: float
    bandwidth_hz: float
    tx_power_w: float
    rx_noise_figure_db: float
    grid_width: int
    grid_height: int
    coverage_threshold_db: float


def _immutable_array(values: np.ndarray, *, dtype: object | None = None) -> np.ndarray:
    """Return an ndarray backed by immutable bytes, not caller-writeable storage."""
    contiguous = np.ascontiguousarray(values, dtype=dtype)
    return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(
        contiguous.shape
    )


def _command_snapshot(ris: RISSurface) -> _RISCommandSnapshot:
    return _RISCommandSnapshot(ris.id, ris.cell_count, ris.phase_bits)


def _require_controller(model: ControllerModel | None) -> ControllerModel:
    active = model or ControllerModel()
    if type(active) is not ControllerModel:
        raise ValueError(
            "prepared coefficient reuse requires the nominal ControllerModel, "
            "not GroundTruthModel or a custom subclass"
        )
    return active


def _gamma(
    ris: _RISCommandSnapshot,
    reflection_efficiency: float,
    pattern: np.ndarray,
) -> np.ndarray:
    phase = validate_commanded_pattern(ris, pattern)
    return np.sqrt(reflection_efficiency) * np.exp(1j * phase)


def _channel_result(
    snapshot: _LinkEvaluationSnapshot,
    los_channel: complex,
    wall_channel: complex,
    ris_channel: complex,
    ris_id: str,
) -> ChannelResult:
    total = los_channel + wall_channel + ris_channel
    power_w = snapshot.tx_power_w * abs(total) ** 2
    power_dbm = float(watts_to_dbm(power_w))
    noise_dbm = noise_power_dbm(
        snapshot.bandwidth_hz, snapshot.rx_noise_figure_db
    )
    snr_db = power_dbm - noise_dbm
    return ChannelResult(
        total_channel=total,
        los_channel=los_channel,
        wall_channel=wall_channel,
        ris_channel=ris_channel,
        received_power_w=power_w,
        received_power_dbm=power_dbm,
        noise_power_dbm=noise_dbm,
        snr_db=snr_db,
        shannon_capacity_bps=shannon_capacity_bps(snapshot.bandwidth_hz, snr_db),
        path_details=[{"kind": "prepared-controller", "ris_id": ris_id}],
    )


@dataclass(frozen=True, slots=True)
class PreparedControllerLink:
    """One Controller link whose M8 coefficient vector is built once."""

    scene: Scene
    tx: Transmitter
    rx: Receiver
    ris: RISSurface
    coefficient_identity: str
    coefficients: np.ndarray
    los_channel: complex
    wall_channel: complex
    coefficient_model_identity: str
    _evaluation: _LinkEvaluationSnapshot = field(repr=False)

    def evaluate(self, pattern: np.ndarray) -> ChannelResult:
        evaluation = self._evaluation
        ris_channel = complex(
            np.dot(
                self.coefficients,
                _gamma(
                    evaluation.ris,
                    evaluation.reflection_efficiency,
                    pattern,
                ),
            )
        )
        return _channel_result(
            evaluation,
            self.los_channel,
            self.wall_channel,
            ris_channel,
            evaluation.ris_id,
        )


def prepare_controller_link(
    scene: Scene,
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris: RISSurface | str | None = None,
    controller_model: ControllerModel | None = None,
) -> PreparedControllerLink:
    """Prepare one nominal link using C's shared coefficient/focus seam."""
    model = _require_controller(controller_model)
    active_engine = engine or SimulationEngine()
    snapshot = copy.deepcopy(scene)
    if isinstance(tx, Transmitter):
        target_tx = copy.deepcopy(tx)
    else:
        target_tx = active_engine._resolve_tx(snapshot, tx)
    if isinstance(rx, Receiver):
        target_rx = copy.deepcopy(rx)
    else:
        target_rx = active_engine._resolve_rx(snapshot, rx)
    if isinstance(ris, RISSurface):
        matches = [item for item in snapshot.ris_surfaces if item.id == ris.id and item.enabled]
        if len(matches) != 1:
            raise ValueError(f"enabled RIS id not found or not unique: {ris.id}")
        target_ris = matches[0]
    elif ris is None:
        enabled = [item for item in snapshot.ris_surfaces if item.enabled]
        if len(enabled) != 1:
            raise ValueError("prepared link requires exactly one enabled RIS")
        target_ris = enabled[0]
    else:
        matches = [item for item in snapshot.ris_surfaces if item.id == ris and item.enabled]
        if len(matches) != 1:
            raise ValueError(f"enabled RIS id not found or not unique: {ris}")
        target_ris = matches[0]
    coefficients, _ = active_engine.controller_focus_terms(
        snapshot, target_tx, target_rx, target_ris, model
    )
    baseline = active_engine.compute_channel(
        snapshot, tx=target_tx, rx=target_rx, ris_patterns={}, model=model
    )
    identity = controller_ris_coefficient_identity(
        snapshot, active_engine, target_tx, target_rx, target_ris
    )
    values = _immutable_array(np.asarray(coefficients), dtype=complex)
    evaluation = _LinkEvaluationSnapshot(
        ris=_command_snapshot(target_ris),
        reflection_efficiency=target_ris.reflection_efficiency,
        bandwidth_hz=snapshot.bandwidth_hz,
        tx_power_w=target_tx.power_w,
        rx_noise_figure_db=target_rx.noise_figure_db,
        ris_id=target_ris.id,
    )
    return PreparedControllerLink(
        snapshot,
        target_tx,
        target_rx,
        target_ris,
        identity,
        values,
        baseline.los_channel,
        baseline.wall_channel,
        active_engine.coefficient_model.identity,
        evaluation,
    )


@dataclass(frozen=True, slots=True)
class PreparedControllerField:
    """A fixed grid's baseline and M8 ``A`` matrix for repeated commands."""

    scene: Scene
    config: SimulationConfig
    tx: Transmitter
    rx_template: Receiver
    ris: RISSurface
    x_m: np.ndarray
    y_m: np.ndarray
    baseline_channels: np.ndarray
    coefficients: np.ndarray
    coefficient_identities: tuple[str, ...]
    build_runtime_s: float
    coefficient_bytes: int
    receiver_batch_size: int
    max_point_sample_pairs: int
    coefficient_model_identity: str
    _evaluation: _FieldEvaluationSnapshot = field(repr=False)

    def evaluate(self, pattern: np.ndarray) -> FieldMapResult:
        started = time.perf_counter()
        evaluation = self._evaluation
        gamma = _gamma(
            evaluation.ris, evaluation.reflection_efficiency, pattern
        )
        ris_channels = self.coefficients @ gamma
        total = self.baseline_channels + ris_channels
        power = watts_to_dbm(evaluation.tx_power_w * np.abs(total) ** 2).reshape(
            evaluation.grid_height, evaluation.grid_width
        )
        baseline = watts_to_dbm(
            evaluation.tx_power_w * np.abs(self.baseline_channels) ** 2
        ).reshape(evaluation.grid_height, evaluation.grid_width)
        noise_dbm = noise_power_dbm(
            evaluation.bandwidth_hz, evaluation.rx_noise_figure_db
        )
        snr = power - noise_dbm
        gain = power - baseline
        threshold = evaluation.coverage_threshold_db
        coverage = float(np.mean(snr >= threshold) * 100.0)
        return FieldMapResult(
            x_m=self.x_m,
            y_m=self.y_m,
            received_power_dbm=power,
            snr_db=snr,
            baseline_power_dbm=baseline,
            ris_gain_db=gain,
            coverage_percent=coverage,
            dead_zone_percent=100.0 - coverage,
            runtime_s=time.perf_counter() - started,
        )


def prepare_controller_field(
    scene: Scene,
    config: SimulationConfig,
    *,
    engine: SimulationEngine | None = None,
    controller_model: ControllerModel | None = None,
    coefficient_memory_budget_bytes: int = DEFAULT_COEFFICIENT_MEMORY_BUDGET_BYTES,
    receiver_batch_size: int | None = None,
    max_point_sample_pairs: int = 262_144,
    progress: ReceiverProgress | None = None,
    progress_callback: ReceiverProgress | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> PreparedControllerField:
    """Build one bounded, reusable production-M8 field coefficient matrix.

    ``progress`` receives exact ``(completed_receiver_points, total_points)``
    values at receiver-batch boundaries. Cancellation is checked only at those
    safe boundaries and raises :class:`SimulationCancelled`; no partial
    prepared object or cache entry is produced.
    """
    if progress is not None and progress_callback is not None:
        raise ValueError("pass only one of progress or progress_callback")
    progress = progress if progress is not None else progress_callback
    model = _require_controller(controller_model)
    if coefficient_memory_budget_bytes <= 0:
        raise ValueError("coefficient_memory_budget_bytes must be positive")
    snapshot = copy.deepcopy(scene)
    config_snapshot = copy.deepcopy(config)
    snapshot._validate_environment_ids()
    enabled = [ris for ris in snapshot.ris_surfaces if ris.enabled]
    if len(enabled) != 1:
        raise ValueError("prepared field requires exactly one enabled RIS")
    ris = enabled[0]
    tx = snapshot.transmitter()
    rx_template = snapshot.receiver()
    point_count = config_snapshot.grid_width * config_snapshot.grid_height
    coefficient_bytes = point_count * ris.cell_count * np.dtype(complex).itemsize
    if coefficient_bytes > coefficient_memory_budget_bytes:
        raise MemoryError(
            "coefficient matrix requires "
            f"{coefficient_bytes} bytes, exceeding budget "
            f"{coefficient_memory_budget_bytes} bytes"
        )
    batch_size = (
        config_snapshot.batch_size
        if receiver_batch_size is None
        else receiver_batch_size
    )
    if batch_size <= 0:
        raise ValueError("receiver_batch_size must be positive")

    started = time.perf_counter()
    active_engine = engine or SimulationEngine()
    if cancel_check is not None and cancel_check():
        raise SimulationCancelled("prepared field calculation cancelled")
    if progress is not None:
        progress(0, point_count)
    x_values = np.linspace(
        0.05, snapshot.room_size.x - 0.05, config_snapshot.grid_width
    )
    y_values = np.linspace(
        0.05, snapshot.room_size.y - 0.05, config_snapshot.grid_height
    )
    xx, yy = np.meshgrid(x_values, y_values, indexing="xy")
    receiver_points = np.column_stack(
        (xx.reshape(-1), yy.reshape(-1), np.full(point_count, snapshot.z_eval_m))
    )
    coefficient_model = active_engine.coefficient_model
    spec = coefficient_model.quadrature_spec(ris)
    incident_modifier = active_engine._environment_modifier(
        snapshot,
        PropagationPathContext(
            "ris_incident", tx.position, ris.position, ris_id=ris.id
        ),
    ).value
    coefficients = np.empty((point_count, ris.cell_count), dtype=complex)
    baselines = np.empty(point_count, dtype=complex)
    identities: list[str] = []
    quadrature_json = None
    if coefficient_model is PRODUCTION_RIS_COEFFICIENT_MODEL:
        quadrature_json = _quadrature_canonical_json(
            spec,
            coefficient_model.quadrature_policy_id,
            coefficient_model.quadrature_policy_version,
            array_identity="derived_by_signed_production_policy",
        )
    for start in range(0, point_count, batch_size):
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("prepared field calculation cancelled")
        stop = min(start + batch_size, point_count)
        points = receiver_points[start:stop]
        coefficients[start:stop] = ris_control_coefficient_matrix(
            tx,
            points,
            rx_template.gain_linear,
            ris,
            snapshot.frequency_hz,
            quadrature_spec=spec,
            max_point_sample_pairs=max_point_sample_pairs,
            receiver_batch_size=batch_size,
        )
        for index, point in enumerate(points, start=start):
            receiver = replace(rx_template, position=Vec3(*point.tolist()))
            scattered_modifier = active_engine._environment_modifier(
                snapshot,
                PropagationPathContext(
                    "ris_scattered", ris.position, receiver.position, ris_id=ris.id
                ),
            ).value
            coefficients[index] *= incident_modifier * scattered_modifier
            no_ris = active_engine.compute_channel(
                snapshot, tx=tx, rx=receiver, ris_patterns={}, model=model
            )
            baselines[index] = no_ris.total_channel
            identities.append(
                controller_ris_coefficient_identity(
                    snapshot,
                    active_engine,
                    tx,
                    receiver,
                    ris,
                    **({"_quadrature_json": quadrature_json} if quadrature_json else {}),
                )
            )
        if progress is not None:
            progress(stop, point_count)
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("prepared field calculation cancelled")
    coefficients = _immutable_array(coefficients)
    baselines = _immutable_array(baselines)
    x_values = _immutable_array(x_values)
    y_values = _immutable_array(y_values)
    threshold = (
        snapshot.coverage_threshold_db
        if config_snapshot.coverage_threshold_db is None
        else config_snapshot.coverage_threshold_db
    )
    evaluation = _FieldEvaluationSnapshot(
        ris=_command_snapshot(ris),
        reflection_efficiency=ris.reflection_efficiency,
        bandwidth_hz=snapshot.bandwidth_hz,
        tx_power_w=tx.power_w,
        rx_noise_figure_db=rx_template.noise_figure_db,
        grid_width=config_snapshot.grid_width,
        grid_height=config_snapshot.grid_height,
        coverage_threshold_db=threshold,
    )
    return PreparedControllerField(
        scene=snapshot,
        config=config_snapshot,
        tx=tx,
        rx_template=rx_template,
        ris=ris,
        x_m=x_values,
        y_m=y_values,
        baseline_channels=baselines,
        coefficients=coefficients,
        coefficient_identities=tuple(identities),
        build_runtime_s=time.perf_counter() - started,
        coefficient_bytes=coefficient_bytes,
        receiver_batch_size=batch_size,
        max_point_sample_pairs=max_point_sample_pairs,
        coefficient_model_identity=coefficient_model.identity,
        _evaluation=evaluation,
    )


__all__ = [
    "DEFAULT_COEFFICIENT_MEMORY_BUDGET_BYTES",
    "ReceiverProgress",
    "PreparedControllerField",
    "PreparedControllerLink",
    "prepare_controller_field",
    "prepare_controller_link",
]
