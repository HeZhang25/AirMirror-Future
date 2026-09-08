"""Explicit, bounded Controller-only coefficient reuse for headless XR work."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
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
    _production_quadrature_spec,
    ris_control_coefficient_matrix,
)
from airmirror_future.simulation.coefficient_identity import (
    controller_ris_coefficient_identity,
)
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.profiles import PropagationPathContext


DEFAULT_COEFFICIENT_MEMORY_BUDGET_BYTES = 128 * 1024 * 1024


def _require_controller(model: ControllerModel | None) -> ControllerModel:
    active = model or ControllerModel()
    if type(active) is not ControllerModel:
        raise ValueError(
            "prepared coefficient reuse requires the nominal ControllerModel, "
            "not GroundTruthModel or a custom subclass"
        )
    return active


def _gamma(ris: RISSurface, pattern: np.ndarray) -> np.ndarray:
    phase = validate_commanded_pattern(ris, pattern)
    return np.sqrt(ris.reflection_efficiency) * np.exp(1j * phase)


def _channel_result(
    scene: Scene,
    tx: Transmitter,
    rx: Receiver,
    los_channel: complex,
    wall_channel: complex,
    ris_channel: complex,
    ris_id: str,
) -> ChannelResult:
    total = los_channel + wall_channel + ris_channel
    power_w = tx.power_w * abs(total) ** 2
    power_dbm = float(watts_to_dbm(power_w))
    noise_dbm = noise_power_dbm(scene.bandwidth_hz, rx.noise_figure_db)
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
        shannon_capacity_bps=shannon_capacity_bps(scene.bandwidth_hz, snr_db),
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

    def evaluate(self, pattern: np.ndarray) -> ChannelResult:
        ris_channel = complex(np.dot(self.coefficients, _gamma(self.ris, pattern)))
        return _channel_result(
            self.scene,
            self.tx,
            self.rx,
            self.los_channel,
            self.wall_channel,
            ris_channel,
            self.ris.id,
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
    values = np.asarray(coefficients, dtype=complex)
    values.setflags(write=False)
    return PreparedControllerLink(
        snapshot,
        target_tx,
        target_rx,
        target_ris,
        identity,
        values,
        baseline.los_channel,
        baseline.wall_channel,
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

    def evaluate(self, pattern: np.ndarray) -> FieldMapResult:
        started = time.perf_counter()
        gamma = _gamma(self.ris, pattern)
        ris_channels = self.coefficients @ gamma
        total = self.baseline_channels + ris_channels
        power = watts_to_dbm(self.tx.power_w * np.abs(total) ** 2).reshape(
            self.config.grid_height, self.config.grid_width
        )
        baseline = watts_to_dbm(
            self.tx.power_w * np.abs(self.baseline_channels) ** 2
        ).reshape(self.config.grid_height, self.config.grid_width)
        noise_dbm = noise_power_dbm(
            self.scene.bandwidth_hz, self.rx_template.noise_figure_db
        )
        snr = power - noise_dbm
        gain = power - baseline
        threshold = (
            self.scene.coverage_threshold_db
            if self.config.coverage_threshold_db is None
            else self.config.coverage_threshold_db
        )
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
) -> PreparedControllerField:
    """Build one bounded, reusable production-M8 field coefficient matrix."""
    model = _require_controller(controller_model)
    if coefficient_memory_budget_bytes <= 0:
        raise ValueError("coefficient_memory_budget_bytes must be positive")
    snapshot = copy.deepcopy(scene)
    snapshot._validate_environment_ids()
    enabled = [ris for ris in snapshot.ris_surfaces if ris.enabled]
    if len(enabled) != 1:
        raise ValueError("prepared field requires exactly one enabled RIS")
    ris = enabled[0]
    tx = snapshot.transmitter()
    rx_template = snapshot.receiver()
    point_count = config.grid_width * config.grid_height
    coefficient_bytes = point_count * ris.cell_count * np.dtype(complex).itemsize
    if coefficient_bytes > coefficient_memory_budget_bytes:
        raise MemoryError(
            "coefficient matrix requires "
            f"{coefficient_bytes} bytes, exceeding budget "
            f"{coefficient_memory_budget_bytes} bytes"
        )
    batch_size = config.batch_size if receiver_batch_size is None else receiver_batch_size
    if batch_size <= 0:
        raise ValueError("receiver_batch_size must be positive")

    started = time.perf_counter()
    active_engine = engine or SimulationEngine()
    x_values = np.linspace(0.05, snapshot.room_size.x - 0.05, config.grid_width)
    y_values = np.linspace(0.05, snapshot.room_size.y - 0.05, config.grid_height)
    xx, yy = np.meshgrid(x_values, y_values, indexing="xy")
    receiver_points = np.column_stack(
        (xx.reshape(-1), yy.reshape(-1), np.full(point_count, snapshot.z_eval_m))
    )
    spec = _production_quadrature_spec(ris)
    incident_modifier = active_engine._environment_modifier(
        snapshot,
        PropagationPathContext(
            "ris_incident", tx.position, ris.position, ris_id=ris.id
        ),
    ).value
    coefficients = np.empty((point_count, ris.cell_count), dtype=complex)
    baselines = np.empty(point_count, dtype=complex)
    identities: list[str] = []
    for start in range(0, point_count, batch_size):
        stop = min(start + batch_size, point_count)
        points = receiver_points[start:stop]
        coefficients[start:stop] = ris_control_coefficient_matrix(
            tx,
            points,
            rx_template.gain_linear,
            ris,
            scene.frequency_hz,
            quadrature_spec=spec,
            max_point_sample_pairs=max_point_sample_pairs,
            receiver_batch_size=batch_size,
        )
        for index, point in enumerate(points, start=start):
            receiver = replace(rx_template, position=Vec3(*point.tolist()))
            scattered_modifier = active_engine._environment_modifier(
                scene,
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
                    snapshot, active_engine, tx, receiver, ris
                )
            )
    coefficients.setflags(write=False)
    baselines.setflags(write=False)
    x_values.setflags(write=False)
    y_values.setflags(write=False)
    return PreparedControllerField(
        scene=snapshot,
        config=config,
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
    )


__all__ = [
    "DEFAULT_COEFFICIENT_MEMORY_BUDGET_BYTES",
    "PreparedControllerField",
    "PreparedControllerLink",
    "prepare_controller_field",
    "prepare_controller_link",
]
