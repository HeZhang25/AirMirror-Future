"""High-level channel and field-map simulation engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import math
import time

import numpy as np

from airmirror_future.core.pattern_contract import validate_commanded_pattern
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
from airmirror_future.physics.free_space import complex_free_space_channel
from airmirror_future.physics.noise import noise_power_dbm, shannon_capacity_bps
from airmirror_future.physics.reflections import single_wall_reflection_path
from airmirror_future.physics.ris_scattering import _ris_channel_from_validated_pattern
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.profiles import (
    IndoorDeterministicProfile,
    PropagationModifier,
    PropagationPathContext,
    PropagationProfile,
    profile_identity,
)


Model = ControllerModel | GroundTruthModel


class SimulationCancelled(RuntimeError):
    """Raised when a caller cancels a long field-map calculation."""


class SimulationEngine:
    """CPU system-level complex-field propagation engine."""

    def __init__(self, profile: PropagationProfile | None = None) -> None:
        self._profile = IndoorDeterministicProfile() if profile is None else profile
        self._profile_identity = profile_identity(self._profile)
        if not callable(getattr(self._profile, "environment_modifier", None)):
            raise ValueError("Profile must implement environment_modifier for all five path roles")
        self._cell_cache: dict[tuple[object, ...], np.ndarray] = {}

    @property
    def profile(self) -> PropagationProfile:
        return self._profile

    @property
    def profile_identity(self) -> str:
        return self._profile_identity

    def _environment_modifier(
        self, scene: Scene, context: PropagationPathContext
    ) -> PropagationModifier:
        # Profile exceptions are deliberately outside the output-validation handler.
        result = self._profile.environment_modifier(scene=scene, context=context)
        message = f"invalid modifier from Profile {self._profile.profile_id!r}, role {context.role!r}"
        if not isinstance(result, PropagationModifier):
            raise ValueError(message + ": expected PropagationModifier")
        try:
            if np.ndim(result.value) != 0:
                raise ValueError("value must be scalar")
            value = complex(result.value)
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError("value must be finite")
            if not isinstance(result.blocker_ids, tuple) or any(
                not isinstance(identifier, str) or not identifier for identifier in result.blocker_ids
            ):
                raise ValueError("blocker_ids must be a tuple of non-empty strings")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{message}: {exc}") from exc
        return PropagationModifier(value, result.blocker_ids)

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
    def _validated_patterns(
        scene: Scene,
        ris_patterns: Mapping[str, np.ndarray] | None,
    ) -> dict[str, np.ndarray]:
        if ris_patterns is None:
            return {}
        if not isinstance(ris_patterns, Mapping):
            raise ValueError("ris_patterns must be a mapping from RIS id to phase array")

        validated: dict[str, np.ndarray] = {}
        for identifier, pattern in ris_patterns.items():
            matches = [ris for ris in scene.ris_surfaces if ris.id == identifier]
            if not matches:
                raise ValueError(f"RIS pattern id not found in scene: {identifier!r}")
            if len(matches) > 1:
                raise ValueError(f"RIS pattern id is not unique in scene: {identifier!r}")
            validated[identifier] = validate_commanded_pattern(matches[0], pattern)
        return validated

    @staticmethod
    def _working_scene(
        scene: Scene, tx: Transmitter, rx: Receiver, model: Model
    ) -> tuple[Scene, Transmitter, Receiver]:
        if not isinstance(model, GroundTruthModel) or model.position_error_sigma_m == 0.0:
            return scene, tx, rx
        working_tx = replace(tx, position=model.perturb(f"tx:{tx.id}", tx.position))
        working_rx = replace(rx, position=model.perturb(f"rx:{rx.id}", rx.position))
        walls = []
        for wall in scene.walls:
            delta = model.position_delta(f"wall:{wall.id}")
            walls.append(
                replace(
                    wall,
                    start=Vec3(
                        wall.start.x + float(delta[0]),
                        wall.start.y + float(delta[1]),
                        wall.start.z,
                    ),
                    end=Vec3(
                        wall.end.x + float(delta[0]),
                        wall.end.y + float(delta[1]),
                        wall.end.z,
                    ),
                )
            )
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
        direct = self._environment_modifier(
            scene, PropagationPathContext("direct", tx.position, rx.position)
        )
        los = complex_free_space_channel(
            distance, scene.frequency_hz, tx.gain_linear, rx.gain_linear
        ) * direct.value
        details: list[dict[str, object]] = [
            {"kind": "LOS", "distance_m": distance, "blockers": list(direct.blocker_ids)}
        ]

        wall_total = 0.0j
        for wall in scene.walls:
            # Preserve v0.1's zero-reflectivity path omission without giving the
            # carrier-only helper ownership of Gamma_wall.
            if wall.reflection_magnitude == 0.0:
                continue
            path = single_wall_reflection_path(scene, tx, rx, wall)
            if path is None:
                continue
            coefficient = model.wall_coefficient(wall)
            before = self._environment_modifier(
                scene, PropagationPathContext("reflection_before", tx.position, path.point,
                                              reflecting_wall_id=wall.id)
            )
            after = self._environment_modifier(
                scene, PropagationPathContext("reflection_after", path.point, rx.position,
                                              reflecting_wall_id=wall.id)
            )
            channel = path.carrier * coefficient * before.value * after.value
            wall_total += channel
            if abs(channel) > 0.0:
                details.append(
                    {"kind": "wall", "wall_id": wall.id, "point": path.point, "channel": channel}
                )

        ris_total = 0.0j
        for ris in scene.ris_surfaces:
            pattern = ris_patterns.get(ris.id)
            if pattern is None or not ris.enabled:
                continue
            before = self._environment_modifier(
                scene, PropagationPathContext("ris_incident", tx.position, ris.position, ris_id=ris.id)
            )
            after = self._environment_modifier(
                scene, PropagationPathContext("ris_scattered", ris.position, rx.position, ris_id=ris.id)
            )
            contribution = _ris_channel_from_validated_pattern(
                tx,
                rx.position,
                rx.gain_linear,
                ris,
                pattern,
                scene.frequency_hz,
                cell_phase_error_rad=model.ris_phase_offsets(ris),
                efficiency_scale=model.ris_efficiency_scale(ris),
            ) * before.value * after.value
            ris_total += contribution
            details.append(
                {
                    "kind": "RIS",
                    "ris_id": ris.id,
                    "blockers": list(before.blocker_ids + after.blocker_ids),
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
        scene._validate_wall_ids()
        nominal_tx = self._resolve_tx(scene, tx)
        nominal_rx = self._resolve_rx(scene, rx)
        patterns = self._validated_patterns(scene, ris_patterns)
        active_model = model or ControllerModel()
        working_scene, working_tx, working_rx = self._working_scene(
            scene, nominal_tx, nominal_rx, active_model
        )
        los, wall, ris, details = self._components(
            working_scene, working_tx, working_rx, patterns, active_model
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
        scene._validate_wall_ids()
        tx = scene.transmitter()
        rx_template = scene.receiver()
        patterns = self._validated_patterns(scene, ris_patterns)
        active_model = model or ControllerModel()
        x_values = np.linspace(0.05, scene.room_size.x - 0.05, config.grid_width)
        y_values = np.linspace(0.05, scene.room_size.y - 0.05, config.grid_height)
        power = np.empty((config.grid_height, config.grid_width), dtype=float)
        baseline = np.empty_like(power)
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
