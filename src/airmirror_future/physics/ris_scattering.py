"""Area-normalized bistatic finite-aperture RIS scattering."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from airmirror_future.core.constants import MIN_DISTANCE_M
from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import RISSurface, Transmitter, Vec3
from airmirror_future.physics.free_space import wave_number_rad_m
from airmirror_future.ris.quadrature import QuadratureSpec, midpoint_quadrature


PRODUCTION_QUADRATURE_POLICY_ID = "midpoint_8x8_per_control_patch"
PRODUCTION_QUADRATURE_POLICY_VERSION = "1"
PRODUCTION_QUADRATURE_ORDER = 8
FAST_QUADRATURE_POLICY_ID = "midpoint_1x1_per_control_patch"
FAST_QUADRATURE_POLICY_VERSION = "1"
_MAX_POINT_SAMPLE_PAIRS = 262_144


@dataclass(frozen=True, slots=True)
class RISCoefficientModel:
    """Named aperture-reduction model used consistently by Focus and Engine."""

    model_id: str
    model_version: str
    quadrature_policy_id: str
    quadrature_policy_version: str
    quadrature_order_x: int
    quadrature_order_y: int

    def __post_init__(self) -> None:
        for name in (
            "model_id",
            "model_version",
            "quadrature_policy_id",
            "quadrature_policy_version",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("quadrature_order_x", "quadrature_order_y"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)
            ) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def identity(self) -> str:
        return f"{self.model_id}/{self.model_version}"

    @property
    def quadrature_identity(self) -> str:
        return f"{self.quadrature_policy_id}/{self.quadrature_policy_version}"

    def quadrature_spec(self, ris: RISSurface) -> QuadratureSpec:
        return midpoint_quadrature(
            ris,
            order_x=self.quadrature_order_x,
            order_y=self.quadrature_order_y,
        )


PRODUCTION_RIS_COEFFICIENT_MODEL = RISCoefficientModel(
    model_id="finite_aperture_bistatic_control_coefficients_m8",
    model_version="1",
    quadrature_policy_id=PRODUCTION_QUADRATURE_POLICY_ID,
    quadrature_policy_version=PRODUCTION_QUADRATURE_POLICY_VERSION,
    quadrature_order_x=PRODUCTION_QUADRATURE_ORDER,
    quadrature_order_y=PRODUCTION_QUADRATURE_ORDER,
)

FAST_1X1_RIS_COEFFICIENT_MODEL = RISCoefficientModel(
    model_id="control_patch_center_bistatic_coefficients",
    model_version="1",
    quadrature_policy_id=FAST_QUADRATURE_POLICY_ID,
    quadrature_policy_version=FAST_QUADRATURE_POLICY_VERSION,
    quadrature_order_x=1,
    quadrature_order_y=1,
)


def _production_quadrature_spec(ris: RISSurface) -> QuadratureSpec:
    """Build the signed midpoint 8x8 rule inside each control patch."""
    return midpoint_quadrature(
        ris,
        order_x=PRODUCTION_QUADRATURE_ORDER,
        order_y=PRODUCTION_QUADRATURE_ORDER,
    )


def _quadrature_spec_for_model(
    ris: RISSurface,
    coefficient_model: RISCoefficientModel,
) -> QuadratureSpec:
    if not isinstance(coefficient_model, RISCoefficientModel):
        raise ValueError("coefficient_model must be a RISCoefficientModel")
    return coefficient_model.quadrature_spec(ris)


def _require_production_quadrature(
    ris: RISSurface,
    spec: QuadratureSpec,
) -> QuadratureSpec:
    if (
        spec.rule != "midpoint"
        or spec.order_x != PRODUCTION_QUADRATURE_ORDER
        or spec.order_y != PRODUCTION_QUADRATURE_ORDER
        or spec.control_count != ris.cell_count
    ):
        raise ValueError(
            "production RIS quadrature must be midpoint 8x8 with one parent "
            "group per control patch"
        )
    return spec


def _ris_channel_for_points_from_validated_pattern(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    phase: np.ndarray,
    frequency_hz: float,
    *,
    cell_phase_error_rad: np.ndarray | None = None,
    efficiency_scale: np.ndarray | float = 1.0,
    quadrature_spec: QuadratureSpec | None = None,
) -> np.ndarray:
    """Evaluate scattering after the commanded hardware boundary."""
    if ris.active:
        raise NotImplementedError("active RIS requires an explicit power and noise model")
    if not ris.enabled:
        return np.zeros(len(receiver_points), dtype=complex)
    points = np.asarray(receiver_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("receiver_points must have shape [N, 3]")
    if len(points) == 0:
        return np.zeros(0, dtype=complex)
    spec = _require_production_quadrature(
        ris,
        _production_quadrature_spec(ris) if quadrature_spec is None else quadrature_spec,
    )
    weights_m2 = spec.weights * ris.cell_area_m2
    result = np.zeros(len(points), dtype=complex)
    receiver_batch_size = min(len(points), 64)
    for point_start in range(0, len(points), receiver_batch_size):
        point_stop = min(point_start + receiver_batch_size, len(points))
        point_batch = points[point_start:point_stop]
        sample_batch_size = max(1, _MAX_POINT_SAMPLE_PAIRS // len(point_batch))
        batch_total = np.zeros(len(point_batch), dtype=complex)
        for sample_start in range(0, spec.sample_count, sample_batch_size):
            sample_stop = min(sample_start + sample_batch_size, spec.sample_count)
            contributions = _ris_aperture_point_contributions(
                tx,
                point_batch,
                receiver_gain_linear,
                ris,
                spec.sample_coordinates[sample_start:sample_stop],
                spec.parent_control_index[sample_start:sample_stop],
                weights_m2[sample_start:sample_stop],
                phase,
                frequency_hz,
                cell_phase_error_rad=cell_phase_error_rad,
                efficiency_scale=efficiency_scale,
            )
            batch_total += np.sum(contributions, axis=1)
        result[point_start:point_stop] = batch_total
    return result


def _ris_aperture_point_contributions(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    aperture_points: np.ndarray,
    parent_control_index: np.ndarray,
    weights_m2: np.ndarray,
    phase: np.ndarray,
    frequency_hz: float,
    *,
    cell_phase_error_rad: np.ndarray | None = None,
    efficiency_scale: np.ndarray | float = 1.0,
    include_efficiency: bool = True,
) -> np.ndarray:
    """Return one contribution per receiver and aperture sample."""
    samples = np.asarray(aperture_points, dtype=float)
    points = np.asarray(receiver_points, dtype=float)
    parents = np.asarray(parent_control_index, dtype=int)
    weights = np.asarray(weights_m2, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("receiver_points must have shape [N, 3]")
    if samples.ndim != 2 or samples.shape[1] != 3:
        raise ValueError("aperture_points must have shape [N, 3]")
    if parents.ndim != 1 or weights.ndim != 1 or len(parents) != len(samples) or len(weights) != len(samples):
        raise ValueError("sample arrays must have matching lengths")
    if not np.all((parents >= 0) & (parents < ris.cell_count)):
        raise ValueError("parent_control_index contains an invalid control index")
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("weights_m2 must be finite and positive")
    tx_vector = tx.position.as_array()[None, :] - samples
    d1 = np.linalg.norm(tx_vector, axis=1)
    if np.any(d1 < MIN_DISTANCE_M):
        raise ValueError("transmitter is too close to a RIS cell centre/sample point")
    incoming_direction = tx_vector / d1[:, None]
    cos_in = np.maximum(incoming_direction @ ris.normal, 0.0)

    output_vector = points[:, None, :] - samples[None, :, :]
    d2 = np.linalg.norm(output_vector, axis=2)
    if np.any(d2 < MIN_DISTANCE_M):
        raise ValueError("receiver is too close to a RIS aperture sample")
    outgoing_direction = output_vector / d2[:, :, None]
    cos_out = np.maximum(np.einsum("bnk,k->bn", outgoing_direction, ris.normal), 0.0)
    direction_amplitude = np.power(cos_in[None, :] * cos_out, ris.direction_exponent / 2.0)
    errors = np.zeros(ris.cell_count, dtype=float) if cell_phase_error_rad is None else np.asarray(cell_phase_error_rad, dtype=float)
    if errors.ndim == 0:
        errors = np.full(ris.cell_count, float(errors), dtype=float)
    if errors.ndim != 1 or errors.size != ris.cell_count or not np.all(np.isfinite(errors)):
        raise ValueError("cell_phase_error_rad must be finite with one value per control cell")
    eta = np.clip(ris.reflection_efficiency * np.asarray(efficiency_scale, dtype=float), 0.0, 1.0)
    if np.ndim(eta) == 0:
        eta_sample = np.full(len(samples), math.sqrt(float(eta)), dtype=float)
    else:
        eta_values = np.asarray(eta, dtype=float).reshape(-1)
        if eta_values.size != ris.cell_count:
            raise ValueError("efficiency_scale must be scalar or one value per control cell")
        eta_sample = np.sqrt(eta_values[parents])
    amplitude = (
        math.sqrt(tx.gain_linear * receiver_gain_linear)
        * (eta_sample[None, :] if include_efficiency else 1.0) * weights[None, :]
        / (4.0 * math.pi * d1[None, :] * d2) * direction_amplitude
    )
    propagation_phase = -wave_number_rad_m(frequency_hz) * (d1[None, :] + d2)
    sample_phase = propagation_phase + phase[parents][None, :] + errors[parents][None, :]
    return amplitude * np.exp(1j * sample_phase)


def ris_channel_for_points(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    *,
    cell_phase_error_rad: np.ndarray | None = None,
    efficiency_scale: np.ndarray | float = 1.0,
) -> np.ndarray:
    """Return RIS complex channel for receiver points.

    Each integration-subpoint contribution is

    ``sqrt(Gt*Gr*eta_n) * w/(4*pi*d1*d2) * D * exp(-jk(d1+d2)+j*phi_n)``.

    Production uses signed midpoint 8x8 integration inside every existing
    control patch. The subpoint weights sum to the original control-patch
    area, and each subpoint inherits its parent patch command. Thus the
    command vector and control grid are unchanged. ``D`` is the square root
    of a cosine power pattern because the directional quantity is treated as
    a power gain.
    """
    phase = validate_commanded_pattern(ris, pattern_rad)
    return _ris_channel_for_points_from_validated_pattern(
        tx,
        receiver_points,
        receiver_gain_linear,
        ris,
        phase,
        frequency_hz,
        cell_phase_error_rad=cell_phase_error_rad,
        efficiency_scale=efficiency_scale,
    )


def ris_channel(
    tx: Transmitter,
    rx_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    **kwargs: object,
) -> complex:
    phase = validate_commanded_pattern(ris, pattern_rad)
    points = rx_position.as_array()[None, :]
    return complex(
        _ris_channel_for_points_from_validated_pattern(
            tx, points, receiver_gain_linear, ris, phase, frequency_hz, **kwargs
        )[0]
    )


def ris_control_coefficients(
    tx: Transmitter,
    receiver_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    frequency_hz: float,
    *,
    coefficient_model: RISCoefficientModel | None = None,
    quadrature_spec: QuadratureSpec | None = None,
) -> np.ndarray:
    """Return the pure geometry/propagation coefficient per control patch.

    Reflection efficiency and commanded/actual phase belong to ``Gamma`` and
    are intentionally excluded.  The default remains signed production M8.
    Callers may explicitly select the named 1x1 model, which samples each
    control-patch centre and applies the complete patch area exactly once.
    """
    if ris.active:
        raise NotImplementedError("active RIS requires an explicit power and noise model")
    if not ris.enabled:
        return np.zeros(ris.cell_count, dtype=complex)
    active_model = (
        PRODUCTION_RIS_COEFFICIENT_MODEL
        if coefficient_model is None
        else coefficient_model
    )
    if not isinstance(active_model, RISCoefficientModel):
        raise ValueError("coefficient_model must be a RISCoefficientModel")
    spec = (
        _quadrature_spec_for_model(ris, active_model)
        if quadrature_spec is None
        else quadrature_spec
    )
    if spec.control_count != ris.cell_count:
        raise ValueError("quadrature must have one parent group per control patch")
    if (
        spec.rule != "midpoint"
        or spec.order_x != active_model.quadrature_order_x
        or spec.order_y != active_model.quadrature_order_y
    ):
        raise ValueError(
            "RIS coefficient quadrature does not match the selected coefficient model"
        )
    return _ris_control_coefficients_for_quadrature(
        tx, receiver_position, receiver_gain_linear, ris, frequency_hz, spec
    )


def ris_control_coefficient_matrix(
    tx: Transmitter,
    receiver_points: np.ndarray,
    receiver_gain_linear: float,
    ris: RISSurface,
    frequency_hz: float,
    *,
    quadrature_spec: QuadratureSpec | None = None,
    max_point_sample_pairs: int = _MAX_POINT_SAMPLE_PAIRS,
    receiver_batch_size: int = 16,
) -> np.ndarray:
    """Return the production M8 coefficient matrix ``[receiver, control]``.

    The output is the multi-receiver form of :func:`ris_control_coefficients`.
    Receiver and aperture-sample axes are both blocked, so no
    ``receiver_count * production_sample_count`` array is materialized.  The
    returned control matrix intentionally excludes reflection efficiency and
    commanded/actual phase; those remain owned by ``Gamma``.
    """
    if ris.active:
        raise NotImplementedError("active RIS requires an explicit power and noise model")
    points = np.asarray(receiver_points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("receiver_points must have shape [N, 3]")
    if not np.all(np.isfinite(points)):
        raise ValueError("receiver_points must contain only finite values")
    if max_point_sample_pairs <= 0:
        raise ValueError("max_point_sample_pairs must be positive")
    if receiver_batch_size <= 0:
        raise ValueError("receiver_batch_size must be positive")
    if not ris.enabled:
        return np.zeros((len(points), ris.cell_count), dtype=complex)
    if len(points) == 0:
        return np.zeros((0, ris.cell_count), dtype=complex)
    spec = (
        _production_quadrature_spec(ris)
        if quadrature_spec is None
        else quadrature_spec
    )
    if (
        spec.rule != "midpoint"
        or spec.control_count != ris.cell_count
        or spec.order_x <= 0
        or spec.order_y <= 0
    ):
        raise ValueError(
            "RIS coefficient quadrature must be midpoint with one parent group "
            "per control patch"
        )
    samples_per_control = spec.order_x * spec.order_y
    expected_parents = np.repeat(np.arange(ris.cell_count), samples_per_control)
    if not np.array_equal(spec.parent_control_index, expected_parents):
        raise ValueError("production quadrature parent ordering must be control-major")

    result = np.empty((len(points), ris.cell_count), dtype=complex)
    zero_phase = np.zeros(ris.cell_count, dtype=float)
    weights_m2 = spec.weights * ris.cell_area_m2
    point_step = min(
        len(points),
        receiver_batch_size,
        max(1, max_point_sample_pairs // samples_per_control),
    )
    for point_start in range(0, len(points), point_step):
        point_stop = min(point_start + point_step, len(points))
        point_batch = points[point_start:point_stop]
        controls_per_batch = max(
            1,
            max_point_sample_pairs // (len(point_batch) * samples_per_control),
        )
        for control_start in range(0, ris.cell_count, controls_per_batch):
            control_stop = min(control_start + controls_per_batch, ris.cell_count)
            sample_start = control_start * samples_per_control
            sample_stop = control_stop * samples_per_control
            terms = _ris_aperture_point_contributions(
                tx,
                point_batch,
                receiver_gain_linear,
                ris,
                spec.sample_coordinates[sample_start:sample_stop],
                spec.parent_control_index[sample_start:sample_stop],
                weights_m2[sample_start:sample_stop],
                zero_phase,
                frequency_hz,
                include_efficiency=False,
            )
            result[
                point_start:point_stop, control_start:control_stop
            ] = terms.reshape(
                len(point_batch), control_stop - control_start, samples_per_control
            ).sum(axis=2)
    return result


def _ris_control_coefficients_for_quadrature(
    tx: Transmitter,
    receiver_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    frequency_hz: float,
    spec: QuadratureSpec,
) -> np.ndarray:
    """Shared pure reduction for a validated research or production rule."""
    if spec.control_count != ris.cell_count:
        raise ValueError("quadrature must have one parent group per control patch")
    points = receiver_position.as_array()[None, :]
    result = np.zeros(ris.cell_count, dtype=complex)
    zero_phase = np.zeros(ris.cell_count, dtype=float)
    for sample_start in range(0, spec.sample_count, _MAX_POINT_SAMPLE_PAIRS):
        sample_stop = min(sample_start + _MAX_POINT_SAMPLE_PAIRS, spec.sample_count)
        terms = _ris_aperture_point_contributions(
            tx,
            points,
            receiver_gain_linear,
            ris,
            spec.sample_coordinates[sample_start:sample_stop],
            spec.parent_control_index[sample_start:sample_stop],
            (spec.weights[sample_start:sample_stop] * ris.cell_area_m2),
            zero_phase,
            frequency_hz,
            include_efficiency=False,
        )[0]
        np.add.at(result, spec.parent_control_index[sample_start:sample_stop], terms)
    return result


def _ris_channel_from_validated_pattern(
    tx: Transmitter,
    rx_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    pattern_rad: np.ndarray,
    frequency_hz: float,
    **kwargs: object,
) -> complex:
    """Internal scalar entry for an engine-validated commanded snapshot."""
    points = rx_position.as_array()[None, :]
    return complex(
        _ris_channel_for_points_from_validated_pattern(
            tx, points, receiver_gain_linear, ris, pattern_rad, frequency_hz, **kwargs
        )[0]
    )
