"""Bounded Controller-only prepared evaluation for up to two RIS surfaces.

The dual path deliberately reuses the existing coefficient, Focus, Gamma and
Engine seams.  It stores independent ``A1``/``A2`` matrices and evaluates the
single coherent channel ``baseline + A1 @ Gamma1 + A2 @ Gamma2``.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
import time
from types import MappingProxyType

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
from airmirror_future.simulation.ground_truth import ControllerModel
from airmirror_future.simulation.prepared_controller import (
    _command_snapshot,
    _gamma,
    _immutable_array,
    _require_controller,
)
from airmirror_future.simulation.profiles import PropagationPathContext


DEFAULT_DUAL_RIS_COEFFICIENT_MEMORY_BUDGET_BYTES = 256 * 1024 * 1024
ReceiverProgress = Callable[[int, int], None]


def _resolve_ris_pair(
    scene: Scene, ris_ids: tuple[str, ...] | list[str] | None
) -> tuple[RISSurface, ...]:
    if ris_ids is None:
        return tuple(ris for ris in scene.ris_surfaces if ris.enabled)[:2]
    if not isinstance(ris_ids, (tuple, list)) or not 0 < len(ris_ids) <= 2:
        raise ValueError("ris_ids must contain one or two RIS ids")
    if any(not isinstance(identifier, str) or not identifier for identifier in ris_ids):
        raise ValueError("ris_ids must contain non-empty strings")
    if len(set(ris_ids)) != len(ris_ids):
        raise ValueError("ris_ids must be unique")
    selected: list[RISSurface] = []
    for identifier in ris_ids:
        matches = [ris for ris in scene.ris_surfaces if ris.id == identifier]
        if len(matches) != 1:
            raise ValueError(f"RIS id not found or not unique: {identifier}")
        selected.append(matches[0])
    return tuple(selected)


def _mapping_snapshot(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


def _validate_patterns(
    patterns: Mapping[str, np.ndarray] | None,
    snapshots: Mapping[str, object],
) -> Mapping[str, np.ndarray]:
    if patterns is None:
        return MappingProxyType({})
    if not isinstance(patterns, Mapping) or len(patterns) > 2:
        raise ValueError("patterns must contain zero, one, or two RIS commands")
    unknown = set(patterns) - set(snapshots)
    if unknown:
        raise ValueError(f"RIS pattern id not prepared: {sorted(unknown)!r}")
    return MappingProxyType(
        {identifier: validate_commanded_pattern(snapshots[identifier], pattern) for identifier, pattern in patterns.items()}
    )


@dataclass(frozen=True, slots=True)
class _DualRISSnapshot:
    command: object
    reflection_efficiency: float
    enabled: bool
    ris_id: str


@dataclass(frozen=True, slots=True)
class _DualLinkEvaluationSnapshot:
    ris: tuple[_DualRISSnapshot, ...]
    los_channel: complex
    wall_channel: complex
    bandwidth_hz: float
    tx_power_w: float
    rx_noise_figure_db: float


@dataclass(frozen=True, slots=True)
class PreparedDualRISControllerLink:
    """Prepared dual-RIS link with independent coefficients and commands."""

    scene: Scene
    tx: Transmitter
    rx: Receiver
    ris_surfaces: tuple[RISSurface, ...]
    coefficient_identities: Mapping[str, str]
    coefficients: Mapping[str, np.ndarray]
    baseline_channel: complex
    coefficient_model_identity: str
    _evaluation: _DualLinkEvaluationSnapshot = field(repr=False)

    @property
    def ris_ids(self) -> tuple[str, ...]:
        return tuple(ris.ris_id for ris in self._evaluation.ris)

    def evaluate(self, patterns: Mapping[str, np.ndarray] | None = None) -> ChannelResult:
        snapshots = {item.ris_id: item.command for item in self._evaluation.ris}
        validated = _validate_patterns(patterns, snapshots)
        ris_total = 0.0j
        details: list[dict[str, object]] = []
        for item in self._evaluation.ris:
            pattern = validated.get(item.ris_id)
            contribution = 0.0j
            if pattern is not None and item.enabled:
                contribution = complex(
                    np.dot(
                        self.coefficients[item.ris_id],
                        _gamma(item.command, item.reflection_efficiency, pattern),
                    )
                )
            ris_total += contribution
            details.append(
                {
                    "kind": "prepared-controller-dual",
                    "ris_id": item.ris_id,
                    "channel": contribution,
                    "coefficient_model_id": self.coefficient_model_identity,
                }
            )
        total = self.baseline_channel + ris_total
        evaluation = self._evaluation
        power_w = evaluation.tx_power_w * abs(total) ** 2
        power_dbm = float(watts_to_dbm(power_w))
        noise_dbm = noise_power_dbm(
            evaluation.bandwidth_hz, evaluation.rx_noise_figure_db
        )
        snr_db = power_dbm - noise_dbm
        return ChannelResult(
            total_channel=total,
            los_channel=evaluation.los_channel,
            wall_channel=evaluation.wall_channel,
            ris_channel=ris_total,
            received_power_w=power_w,
            received_power_dbm=power_dbm,
            noise_power_dbm=noise_dbm,
            snr_db=snr_db,
            shannon_capacity_bps=shannon_capacity_bps(evaluation.bandwidth_hz, snr_db),
            path_details=details,
        )


def prepare_dual_ris_controller_link(
    scene: Scene,
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris_ids: tuple[str, ...] | list[str] | None = None,
    controller_model: ControllerModel | None = None,
) -> PreparedDualRISControllerLink:
    """Prepare one or two independent RIS links using the Engine coefficient model."""

    model = _require_controller(controller_model)
    active_engine = engine or SimulationEngine()
    snapshot = copy.deepcopy(scene)
    snapshot._validate_environment_ids()
    target_tx = (
        copy.deepcopy(tx)
        if isinstance(tx, Transmitter)
        else active_engine._resolve_tx(snapshot, tx)
    )
    target_rx = (
        copy.deepcopy(rx)
        if isinstance(rx, Receiver)
        else active_engine._resolve_rx(snapshot, rx)
    )
    selected = _resolve_ris_pair(snapshot, ris_ids)
    baseline = active_engine.compute_channel(
        snapshot, tx=target_tx, rx=target_rx, ris_patterns={}, model=model
    )
    coefficients: dict[str, np.ndarray] = {}
    identities: dict[str, str] = {}
    snapshots: list[_DualRISSnapshot] = []
    for ris in selected:
        snapshots.append(
            _DualRISSnapshot(_command_snapshot(ris), ris.reflection_efficiency, ris.enabled, ris.id)
        )
        if ris.enabled:
            values, _ = active_engine.controller_focus_terms(
                snapshot, target_tx, target_rx, ris, model
            )
            coefficients[ris.id] = _immutable_array(np.asarray(values), dtype=complex)
            identities[ris.id] = controller_ris_coefficient_identity(
                snapshot, active_engine, target_tx, target_rx, ris
            )
        else:
            coefficients[ris.id] = _immutable_array(
                np.zeros(ris.cell_count, dtype=complex)
            )
            identities[ris.id] = f"disabled:{ris.id}"
    return PreparedDualRISControllerLink(
        scene=snapshot,
        tx=target_tx,
        rx=target_rx,
        ris_surfaces=tuple(copy.deepcopy(ris) for ris in selected),
        coefficient_identities=_mapping_snapshot(identities),
        coefficients=_mapping_snapshot(coefficients),
        baseline_channel=baseline.total_channel,
        coefficient_model_identity=active_engine.coefficient_model.identity,
        _evaluation=_DualLinkEvaluationSnapshot(
            tuple(snapshots),
            baseline.los_channel,
            baseline.wall_channel,
            snapshot.bandwidth_hz,
            target_tx.power_w,
            target_rx.noise_figure_db,
        ),
    )


@dataclass(frozen=True, slots=True)
class _DualFieldEvaluationSnapshot:
    ris: tuple[_DualRISSnapshot, ...]
    bandwidth_hz: float
    tx_power_w: float
    rx_noise_figure_db: float
    grid_width: int
    grid_height: int
    coverage_threshold_db: float


@dataclass(frozen=True, slots=True)
class PreparedDualRISControllerField:
    """Prepared dual-RIS field storing independent ``A1`` and ``A2`` matrices."""

    scene: Scene
    config: SimulationConfig
    tx: Transmitter
    rx_template: Receiver
    ris_surfaces: tuple[RISSurface, ...]
    x_m: np.ndarray
    y_m: np.ndarray
    baseline_channels: np.ndarray
    coefficients: Mapping[str, np.ndarray]
    coefficient_identities: Mapping[str, tuple[str, ...]]
    build_runtime_s: float
    coefficient_bytes: int
    receiver_batch_size: int
    max_point_sample_pairs: int
    coefficient_model_identity: str
    _evaluation: _DualFieldEvaluationSnapshot = field(repr=False)

    @property
    def ris_ids(self) -> tuple[str, ...]:
        return tuple(item.ris_id for item in self._evaluation.ris)

    @property
    def coefficients_by_ris(self) -> Mapping[str, np.ndarray]:
        return self.coefficients

    def evaluate(self, patterns: Mapping[str, np.ndarray] | None = None) -> FieldMapResult:
        started = time.perf_counter()
        snapshots = {item.ris_id: item.command for item in self._evaluation.ris}
        validated = _validate_patterns(patterns, snapshots)
        ris_channels = np.zeros(self.baseline_channels.shape, dtype=complex)
        for item in self._evaluation.ris:
            pattern = validated.get(item.ris_id)
            if pattern is not None and item.enabled:
                ris_channels += self.coefficients[item.ris_id] @ _gamma(
                    item.command, item.reflection_efficiency, pattern
                )
        total = self.baseline_channels + ris_channels
        evaluation = self._evaluation
        power = watts_to_dbm(
            evaluation.tx_power_w * np.abs(total) ** 2
        ).reshape(evaluation.grid_height, evaluation.grid_width)
        baseline = watts_to_dbm(
            evaluation.tx_power_w * np.abs(self.baseline_channels) ** 2
        ).reshape(evaluation.grid_height, evaluation.grid_width)
        noise_dbm = noise_power_dbm(
            evaluation.bandwidth_hz, evaluation.rx_noise_figure_db
        )
        snr = power - noise_dbm
        gain = power - baseline
        coverage = float(np.mean(snr >= evaluation.coverage_threshold_db) * 100.0)
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


def prepare_dual_ris_controller_field(
    scene: Scene,
    config: SimulationConfig,
    *,
    engine: SimulationEngine | None = None,
    controller_model: ControllerModel | None = None,
    ris_ids: tuple[str, ...] | list[str] | None = None,
    coefficient_memory_budget_bytes: int = DEFAULT_DUAL_RIS_COEFFICIENT_MEMORY_BUDGET_BYTES,
    receiver_batch_size: int | None = None,
    max_point_sample_pairs: int = 262_144,
    progress: ReceiverProgress | None = None,
    progress_callback: ReceiverProgress | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> PreparedDualRISControllerField:
    """Build bounded dual-RIS Controller matrices for repeated command evaluation.

    A receiver batch builds each selected RIS in sequence, so aperture/sample
    broadcasts remain bounded.  The resident output budget accounts for both
    matrices; the default 256 MiB budget is intentionally larger than the
    single-RIS 128 MiB budget because two Future matrices are independent.
    """

    if progress is not None and progress_callback is not None:
        raise ValueError("pass only one of progress or progress_callback")
    progress = progress if progress is not None else progress_callback
    model = _require_controller(controller_model)
    if coefficient_memory_budget_bytes <= 0:
        raise ValueError("coefficient_memory_budget_bytes must be positive")
    if max_point_sample_pairs <= 0:
        raise ValueError("max_point_sample_pairs must be positive")
    active_engine = engine or SimulationEngine()
    snapshot = copy.deepcopy(scene)
    snapshot._validate_environment_ids()
    config_snapshot = copy.deepcopy(config)
    selected = _resolve_ris_pair(snapshot, ris_ids)
    tx = snapshot.transmitter()
    rx_template = snapshot.receiver()
    point_count = config_snapshot.grid_width * config_snapshot.grid_height
    enabled = tuple(ris for ris in selected if ris.enabled)
    coefficient_bytes = point_count * sum(
        ris.cell_count * np.dtype(complex).itemsize for ris in enabled
    )
    if coefficient_bytes > coefficient_memory_budget_bytes:
        raise MemoryError(
            "dual RIS coefficient matrices require "
            f"{coefficient_bytes} bytes, exceeding budget "
            f"{coefficient_memory_budget_bytes} bytes"
        )
    batch_size = config_snapshot.batch_size if receiver_batch_size is None else receiver_batch_size
    if batch_size <= 0:
        raise ValueError("receiver_batch_size must be positive")
    if cancel_check is not None and cancel_check():
        raise SimulationCancelled("prepared dual RIS field calculation cancelled")
    if progress is not None:
        progress(0, point_count)
    started = time.perf_counter()
    x_values = np.linspace(0.05, snapshot.room_size.x - 0.05, config_snapshot.grid_width)
    y_values = np.linspace(0.05, snapshot.room_size.y - 0.05, config_snapshot.grid_height)
    xx, yy = np.meshgrid(x_values, y_values, indexing="xy")
    receiver_points = np.column_stack(
        (xx.reshape(-1), yy.reshape(-1), np.full(point_count, snapshot.z_eval_m))
    )
    coefficient_model = active_engine.coefficient_model
    coefficients = {
        ris.id: np.empty((point_count, ris.cell_count), dtype=complex)
        for ris in enabled
    }
    baselines = np.empty(point_count, dtype=complex)
    identities: dict[str, list[str]] = {ris.id: [] for ris in selected}
    incident_modifiers = {
        ris.id: active_engine._environment_modifier(
            snapshot,
            PropagationPathContext("ris_incident", tx.position, ris.position, ris_id=ris.id),
        ).value
        for ris in enabled
    }
    quadrature_json = None
    if coefficient_model is PRODUCTION_RIS_COEFFICIENT_MODEL:
        quadrature_json = {
            ris.id: _quadrature_canonical_json(
                coefficient_model.quadrature_spec(ris),
                coefficient_model.quadrature_policy_id,
                coefficient_model.quadrature_policy_version,
                array_identity="derived_by_signed_production_policy",
            )
            for ris in enabled
        }
    specs = {ris.id: coefficient_model.quadrature_spec(ris) for ris in enabled}
    for start in range(0, point_count, batch_size):
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("prepared dual RIS field calculation cancelled")
        stop = min(start + batch_size, point_count)
        points = receiver_points[start:stop]
        for ris in enabled:
            coefficients[ris.id][start:stop] = ris_control_coefficient_matrix(
                tx,
                points,
                rx_template.gain_linear,
                ris,
                snapshot.frequency_hz,
                quadrature_spec=specs[ris.id],
                max_point_sample_pairs=max_point_sample_pairs,
                receiver_batch_size=batch_size,
            )
        for index, point in enumerate(points, start=start):
            receiver = replace(rx_template, position=Vec3(*point.tolist()))
            no_ris = active_engine.compute_channel(
                snapshot, tx=tx, rx=receiver, ris_patterns={}, model=model
            )
            baselines[index] = no_ris.total_channel
            for ris in selected:
                if ris.enabled:
                    scattered_modifier = active_engine._environment_modifier(
                        snapshot,
                        PropagationPathContext(
                            "ris_scattered", ris.position, receiver.position, ris_id=ris.id
                        ),
                    ).value
                    coefficients[ris.id][index] *= (
                        incident_modifiers[ris.id] * scattered_modifier
                    )
                    identities[ris.id].append(
                        controller_ris_coefficient_identity(
                            snapshot,
                            active_engine,
                            tx,
                            receiver,
                            ris,
                            **(
                                {"_quadrature_json": quadrature_json[ris.id]}
                                if quadrature_json is not None
                                else {}
                            ),
                        )
                    )
                else:
                    identities[ris.id].append(f"disabled:{ris.id}")
        if progress is not None:
            progress(stop, point_count)
        if cancel_check is not None and cancel_check():
            raise SimulationCancelled("prepared dual RIS field calculation cancelled")
    coefficients_snapshot = {
        identifier: _immutable_array(values) for identifier, values in coefficients.items()
    }
    selected_snapshots = tuple(
        _DualRISSnapshot(_command_snapshot(ris), ris.reflection_efficiency, ris.enabled, ris.id)
        for ris in selected
    )
    threshold = (
        snapshot.coverage_threshold_db
        if config_snapshot.coverage_threshold_db is None
        else config_snapshot.coverage_threshold_db
    )
    return PreparedDualRISControllerField(
        scene=snapshot,
        config=config_snapshot,
        tx=tx,
        rx_template=rx_template,
        ris_surfaces=tuple(copy.deepcopy(ris) for ris in selected),
        x_m=_immutable_array(x_values),
        y_m=_immutable_array(y_values),
        baseline_channels=_immutable_array(baselines),
        coefficients=_mapping_snapshot(coefficients_snapshot),
        coefficient_identities=_mapping_snapshot(
            {identifier: tuple(values) for identifier, values in identities.items()}
        ),
        build_runtime_s=time.perf_counter() - started,
        coefficient_bytes=coefficient_bytes,
        receiver_batch_size=batch_size,
        max_point_sample_pairs=max_point_sample_pairs,
        coefficient_model_identity=coefficient_model.identity,
        _evaluation=_DualFieldEvaluationSnapshot(
            selected_snapshots,
            snapshot.bandwidth_hz,
            tx.power_w,
            rx_template.noise_figure_db,
            config_snapshot.grid_width,
            config_snapshot.grid_height,
            threshold,
        ),
    )


# Naming aliases keep the public seam discoverable beside the existing
# prepare_controller_link/field functions.
prepare_controller_dual_link = prepare_dual_ris_controller_link
prepare_controller_dual_field = prepare_dual_ris_controller_field


__all__ = [
    "DEFAULT_DUAL_RIS_COEFFICIENT_MEMORY_BUDGET_BYTES",
    "PreparedDualRISControllerField",
    "PreparedDualRISControllerLink",
    "prepare_controller_dual_field",
    "prepare_controller_dual_link",
    "prepare_dual_ris_controller_field",
    "prepare_dual_ris_controller_link",
]
