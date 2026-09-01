"""High-level channel and field-map simulation engine."""

from __future__ import annotations

from dataclasses import replace
import math
import time
from typing import Mapping

import numpy as np

from airmirror_future.core.types import (
    CancelCheck,
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
from airmirror_future.physics.blockage import path_attenuation_amplitude
from airmirror_future.physics.free_space import complex_free_space_channel
from airmirror_future.physics.noise import noise_power_dbm, shannon_capacity_bps
from airmirror_future.physics.reflections import single_wall_reflection
from airmirror_future.physics.ris_scattering import ris_channel
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel


Model = ControllerModel | GroundTruthModel


class SimulationCancelled(RuntimeError):
    """Raised when a caller cancels a long field-map calculation."""


class SimulationEngine:
    """CPU system-level complex-field propagation engine."""

    def __init__(self) -> None:
        self._cell_cache: dict[tuple[object, ...], np.ndarray] = {}

    @staticmethod
    def _resolve_tx(scene: Scene, tx: Transmitter | str | None) -> Transmitter:
        if isinstance(tx, Transmitter):
            return tx
        return scene.transmitter(tx)

    @staticmethod
    def _resolve_rx(scene: Scene, rx: Receiver | str | None) -> Receiver:
        if isinstance(rx, Receiver):
            return rx
        return scene.receiver(rx)

    @staticmethod
    def _working_scene(
        scene: Scene, tx: Transmitter, rx: Receiver, model: Model
    ) -> tuple[Scene, Transmitter, Receiver]:
        if not isinstance(model, GroundTruthModel) or model.position_error_sigma_m == 0.0:
            return scene, tx, rx
        working_tx = replace(tx, position=model.perturb(f"tx:{tx.id}", tx.position))
        working_rx = replace(rx, position=model.perturb(f"rx:{rx.id}", rx.position))
        walls = [
            replace(
                wall,
                start=model.perturb(f"wall:{wall.id}", wall.start),
                end=model.perturb(f"wall:{wall.id}", wall.end),
            )
            for wall in scene.walls
        ]
        obstacles = []
        for obstacle in scene.obstacles:
            delta = model.position_delta(f"obstacle:{obstacle.id}")
            minimum = obstacle.min_corner.as_array() + delta
            maximum = obstacle.max_corner.as_array() + delta
            obstacles.append(
                replace(
                    obstacle,
                    min_corner=Vec3(*minimum.tolist()),
                    max_corner=Vec3(*maximum.tolist()),
                )
            )
        surfaces = [
            replace(ris, position=model.perturb(f"ris:{ris.id}", ris.position))
            for ris in scene.ris_surfaces
        ]
        working = replace(
            scene,
            transmitters=[working_tx],
            receivers=[working_rx],
            walls=walls,
            obstacles=obstacles,
            ris_surfaces=surfaces,
        )
        return working, working_tx, working_rx

    def _components(
        self,
        scene: Scene,
        tx: Transmitter,
        rx: Receiver,
        ris_patterns: Mapping[str, np.ndarray],
        model: Model,
    ) -> tuple[complex, complex, complex, list[dict[str, object]]]:
        distance = tx.position.distance_to(rx.position)
        attenuation, blockers = path_attenuation_amplitude(scene, tx.position, rx.position)
        los = complex_free_space_channel(
            distance, scene.frequency_hz, tx.gain_linear, rx.gain_linear
        ) * attenuation
        details: list[dict[str, object]] = [
            {"kind": "LOS", "distance_m": distance, "blockers": blockers}
        ]

        wall_total = 0.0j
        for wall in scene.walls:
            channel, point = single_wall_reflection(
                scene, tx, rx, wall, model.wall_coefficient(wall)
            )
            wall_total += channel
            if point is not None and abs(channel) > 0.0:
                details.append(
                    {"kind": "wall", "wall_id": wall.id, "point": point, "channel": channel}
                )

        ris_total = 0.0j
        for ris in scene.ris_surfaces:
            pattern = ris_patterns.get(ris.id)
            if pattern is None or not ris.enabled:
                continue
            before, before_blockers = path_attenuation_amplitude(
                scene, tx.position, ris.position
            )
            after, after_blockers = path_attenuation_amplitude(
                scene, ris.position, rx.position
            )
            contribution = ris_channel(
                tx,
                rx.position,
                rx.gain_linear,
                ris,
                pattern,
                scene.frequency_hz,
                cell_phase_error_rad=model.ris_phase_offsets(ris),
                efficiency_scale=model.ris_efficiency_scale(ris),
            ) * before * after
            ris_total += contribution
            details.append(
                {
                    "kind": "RIS",
                    "ris_id": ris.id,
                    "blockers": before_blockers + after_blockers,
                    "channel": contribution,
                }
            )
        return complex(los), complex(wall_total), complex(ris_total), details

    def compute_channel(
        self,
        scene: Scene,
        tx: Transmitter | str | None = None,
        rx: Receiver | str | None = None,
        ris_patterns: Mapping[str, np.ndarray] | None = None,
        model: Model | None = None,
    ) -> ChannelResult:
        """Compute one TX-RX link with coherent LOS, wall, and RIS fields."""
        nominal_tx = self._resolve_tx(scene, tx)
        nominal_rx = self._resolve_rx(scene, rx)
        active_model = model or ControllerModel()
        working_scene, working_tx, working_rx = self._working_scene(
            scene, nominal_tx, nominal_rx, active_model
        )
        los, wall, ris, details = self._components(
            working_scene, working_tx, working_rx, ris_patterns or {}, active_model
        )
        total = los + wall + ris
        power_w = working_tx.power_w * abs(total) ** 2
        power_dbm = float(watts_to_dbm(power_w))
        noise_dbm = noise_power_dbm(working_scene.bandwidth_hz, working_rx.noise_figure_db)
        link_snr_db = power_dbm - noise_dbm
        return ChannelResult(
            total_channel=total,
            los_channel=los,
            wall_channel=wall,
            ris_channel=ris,
            received_power_w=power_w,
            received_power_dbm=power_dbm,
            noise_power_dbm=noise_dbm,
            snr_db=link_snr_db,
            shannon_capacity_bps=shannon_capacity_bps(
                working_scene.bandwidth_hz, link_snr_db
            ),
            path_details=details,
        )

    def compute_field_map(
        self,
        scene: Scene,
        config: SimulationConfig,
        ris_patterns: Mapping[str, np.ndarray] | None = None,
        model: Model | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> FieldMapResult:
        """Compute a regular fixed-height power/SNR map on the CPU."""
        started = time.perf_counter()
        tx = scene.transmitter()
        rx_template = scene.receiver()
        active_model = model or ControllerModel()
        x_values = np.linspace(0.05, scene.room_size.x - 0.05, config.grid_width)
        y_values = np.linspace(0.05, scene.room_size.y - 0.05, config.grid_height)
        power = np.empty((config.grid_height, config.grid_width), dtype=float)
        baseline = np.empty_like(power)
        patterns = ris_patterns or {}
        for row, y_value in enumerate(y_values):
            if cancel_check is not None and cancel_check():
                raise SimulationCancelled("field-map calculation cancelled")
            for column, x_value in enumerate(x_values):
                receiver = replace(
                    rx_template,
                    position=Vec3(float(x_value), float(y_value), scene.z_eval_m),
                )
                working_scene, working_tx, working_rx = self._working_scene(
                    scene, tx, receiver, active_model
                )
                los, wall, ris, _ = self._components(
                    working_scene, working_tx, working_rx, patterns, active_model
                )
                power[row, column] = watts_to_dbm(
                    working_tx.power_w * abs(los + wall + ris) ** 2
                )
                baseline[row, column] = watts_to_dbm(
                    working_tx.power_w * abs(los + wall) ** 2
                )
        noise_dbm = noise_power_dbm(scene.bandwidth_hz, rx_template.noise_figure_db)
        snr = power - noise_dbm
        gain = power - baseline
        threshold = (
            scene.coverage_threshold_db
            if config.coverage_threshold_db is None
            else config.coverage_threshold_db
        )
        coverage = float(np.mean(snr >= threshold) * 100.0)
        return FieldMapResult(
            x_m=x_values,
            y_m=y_values,
            received_power_dbm=power,
            snr_db=snr,
            baseline_power_dbm=baseline,
            ris_gain_db=gain,
            coverage_percent=coverage,
            dead_zone_percent=100.0 - coverage,
            runtime_s=time.perf_counter() - started,
        )
