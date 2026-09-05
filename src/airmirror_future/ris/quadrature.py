"""Internal aperture quadrature helpers for FND-QA-AP.

The quadrature grid refines integration *inside* the existing equivalent RIS
control patches.  It never changes the public ``nx * ny`` command vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from airmirror_future.core.types import RISSurface


QuadratureRule = Literal["midpoint", "tensor_product_gauss_legendre"]


@dataclass(frozen=True, slots=True)
class QuadratureSpec:
    """Deterministic subpoint rule for one fixed RIS control grid."""

    rule: str
    order_x: int
    order_y: int
    sample_coordinates: np.ndarray
    weights: np.ndarray
    parent_control_index: np.ndarray

    def __post_init__(self) -> None:
        if self.rule not in {"midpoint", "tensor_product_gauss_legendre"}:
            raise ValueError("unsupported quadrature rule")
        for name, value in (("order_x", self.order_x), ("order_y", self.order_y)):
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        coordinates = np.asarray(self.sample_coordinates, dtype=float)
        weights = np.asarray(self.weights, dtype=float)
        parents = np.asarray(self.parent_control_index, dtype=np.int64)
        if coordinates.ndim != 2 or coordinates.shape[1] != 3:
            raise ValueError("sample_coordinates must have shape [N, 3]")
        if weights.ndim != 1 or parents.ndim != 1 or len(weights) != len(coordinates) or len(parents) != len(coordinates):
            raise ValueError("quadrature arrays must have matching lengths")
        if not np.issubdtype(parents.dtype, np.integer):
            raise ValueError("parent_control_index must contain integers")
        if not np.all(np.isfinite(coordinates)) or not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
            raise ValueError("quadrature coordinates and weights must be finite; weights positive")
        expected = self.order_x * self.order_y
        if expected <= 0 or len(coordinates) % expected:
            raise ValueError("quadrature sample count is incompatible with order")
        # Every parent group is contiguous and parent-major.  This is the
        # ordering contract consumed by the QA runner and raw artifacts.
        groups = len(coordinates) // expected
        if not np.array_equal(parents, np.repeat(np.arange(groups), expected)):
            raise ValueError("parent_control_index must be contiguous parent-major ordering")
        for value in (coordinates, weights, parents):
            value.setflags(write=False)
        object.__setattr__(self, "sample_coordinates", coordinates)
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "parent_control_index", parents)

    @property
    def sample_count(self) -> int:
        return int(self.sample_coordinates.shape[0])

    @property
    def control_count(self) -> int:
        return int(self.sample_count // (self.order_x * self.order_y))

    def inherited_commands(self, command: np.ndarray) -> np.ndarray:
        """Expand one command per control patch to one command per subpoint."""
        values = np.asarray(command)
        if values.ndim != 1 or values.size != self.control_count:
            raise ValueError("command must have one value per control patch")
        return values[self.parent_control_index]


def _rule_nodes_weights(rule: str, order: int) -> tuple[np.ndarray, np.ndarray]:
    if rule == "midpoint":
        nodes = (np.arange(order, dtype=float) + 0.5) / order - 0.5
        weights = np.full(order, 1.0 / order, dtype=float)
        return nodes, weights
    if rule == "tensor_product_gauss_legendre":
        nodes, weights = np.polynomial.legendre.leggauss(order)
        return nodes / 2.0, weights / 2.0
    raise ValueError(f"unsupported quadrature rule: {rule!r}")


def make_quadrature_spec(
    ris: RISSurface,
    *,
    rule: QuadratureRule,
    order_x: int,
    order_y: int,
) -> QuadratureSpec:
    """Construct deterministic aperture samples within every control patch."""
    for name, value in (("order_x", order_x), ("order_y", order_y)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    order_x = int(order_x)
    order_y = int(order_y)
    nodes_x, weights_x = _rule_nodes_weights(rule, order_x)
    nodes_y, weights_y = _rule_nodes_weights(rule, order_y)
    tangent = np.array((-np.sin(ris.yaw_rad), np.cos(ris.yaw_rad), 0.0))
    vertical = np.array((0.0, 0.0, 1.0))
    center = ris.position.as_array()
    pitch_x = ris.width_m / ris.nx
    pitch_y = ris.height_m / ris.ny
    coordinates: list[np.ndarray] = []
    weights: list[float] = []
    parents: list[int] = []
    # Existing cell_centers() is meshgrid(indexing="xy").reshape(-1), i.e.
    # x-index fastest.  Keep parent-major, local-y then local-x ordering.
    for iy in range(ris.ny):
        for ix in range(ris.nx):
            cell_center = center + (((ix + 0.5) / ris.nx - 0.5) * ris.width_m) * tangent
            cell_center = cell_center + (((iy + 0.5) / ris.ny - 0.5) * ris.height_m) * vertical
            parent = iy * ris.nx + ix
            for local_y, wy in zip(nodes_y, weights_y):
                for local_x, wx in zip(nodes_x, weights_x):
                    coordinates.append(cell_center + local_x * pitch_x * tangent + local_y * pitch_y * vertical)
                    # Normalized weights are part of the quadrature contract;
                    # the physical control-patch area is applied by the
                    # coefficient evaluator exactly once.
                    weights.append(float(wx * wy))
                    parents.append(parent)
    return QuadratureSpec(rule, order_x, order_y, np.asarray(coordinates), np.asarray(weights), np.asarray(parents, dtype=np.int64))


def midpoint_quadrature(ris: RISSurface, order_x: int = 1, order_y: int | None = None) -> QuadratureSpec:
    """Build a midpoint refinement rule."""
    return make_quadrature_spec(ris, rule="midpoint", order_x=order_x, order_y=order_x if order_y is None else order_y)


def tensor_product_gauss_legendre(ris: RISSurface, order_x: int, order_y: int | None = None) -> QuadratureSpec:
    """Build a tensor-product Gauss--Legendre refinement rule."""
    return make_quadrature_spec(ris, rule="tensor_product_gauss_legendre", order_x=order_x, order_y=order_x if order_y is None else order_y)


__all__ = ["QuadratureRule", "QuadratureSpec", "make_quadrature_spec", "midpoint_quadrature", "tensor_product_gauss_legendre"]
