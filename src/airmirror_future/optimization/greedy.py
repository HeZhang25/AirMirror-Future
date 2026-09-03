"""Tile-based measurement-only coordinate descent."""

from __future__ import annotations

import math
import time
from typing import Callable

import numpy as np

from airmirror_future.core.types import OptimizationResult
from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.optimization.base import Optimizer, ProgressCallback
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.simulation.ground_truth import ControllerModel


class FeedbackGreedyOptimizer(Optimizer):
    """Coordinate descent over RIS tiles using only ``oracle.measure``."""

    def __init__(
        self,
        tile_height: int = 4,
        tile_width: int = 4,
        max_passes: int = 1,
        search_levels: int = 8,
    ):
        values = (tile_height, tile_width, max_passes, search_levels)
        if any(
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or value <= 0
            for value in values
        ):
            raise ValueError("tile sizes, max_passes, and search_levels must be positive integers")
        self.tile_height = tile_height
        self.tile_width = tile_width
        self.max_passes = max_passes
        self.search_levels = int(search_levels)

    def optimize(
        self,
        controller_model: ControllerModel,
        measurement_oracle: MeasurementOracle,
        objective: str = "received_power_dbm",
        *,
        initial_patterns: dict[str, np.ndarray] | None = None,
        search_levels: int | None = None,
        cancel_check: Callable[[], bool] | None = None,
        progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        if objective != "received_power_dbm":
            raise ValueError("v0.1 feedback optimizer supports received_power_dbm only")
        started = time.perf_counter()
        scene = measurement_oracle.scene
        if len(scene.ris_surfaces) != 1:
            raise ValueError("v0.1 feedback optimizer requires exactly one RIS")
        ris = scene.ris_surfaces[0]
        if initial_patterns and ris.id in initial_patterns:
            pattern = np.asarray(initial_patterns[ris.id], dtype=float).copy()
        else:
            pattern = np.zeros(ris.cell_count, dtype=float)
        if pattern.ndim != 1 or pattern.size != ris.cell_count:
            raise ValueError(
                f"initial pattern for RIS {ris.id!r} must have shape ({ris.cell_count},)"
            )
        if not np.all(np.isfinite(pattern)):
            raise ValueError("initial pattern must contain only finite values")
        # Reuse the commanded-pattern boundary before any oracle call.  This
        # preserves continuous values and rejects illegal finite-bit states;
        # it never quantizes or otherwise edits the caller's initial pattern.
        pattern = validate_commanded_pattern(ris, pattern)
        pattern_grid = pattern.reshape(ris.ny, ris.nx)
        configured_levels = self.search_levels if search_levels is None else search_levels
        if (
            isinstance(configured_levels, (bool, np.bool_))
            or not isinstance(configured_levels, (int, np.integer))
            or configured_levels <= 0
        ):
            raise ValueError("search_levels must be a positive integer")
        # Hardware resolution owns the candidate set for finite-bit RIS.  For
        # continuous hardware, search_levels is an explicit finite refinement
        # grid and does not change the hardware's continuous state space.
        levels = 2**ris.phase_bits if ris.phase_bits is not None else int(configured_levels)
        candidates = np.arange(levels, dtype=float) * 2.0 * math.pi / levels
        row_starts = list(range(0, ris.ny, self.tile_height))
        col_starts = list(range(0, ris.nx, self.tile_width))
        total_tiles = len(row_starts) * len(col_starts) * self.max_passes
        current = measurement_oracle.measure({ris.id: pattern_grid.reshape(-1)})
        history = [current]
        iterations = 1
        completed_tiles = 0
        cancelled = False
        for _ in range(self.max_passes):
            for row in row_starts:
                for column in col_starts:
                    if cancel_check is not None and cancel_check():
                        cancelled = True
                        break
                    r_slice = slice(row, min(row + self.tile_height, ris.ny))
                    c_slice = slice(column, min(column + self.tile_width, ris.nx))
                    original = pattern_grid[r_slice, c_slice].copy()
                    best_value = current
                    best_phase: float | None = None
                    for candidate in candidates:
                        pattern_grid[r_slice, c_slice] = candidate
                        value = measurement_oracle.measure(
                            {ris.id: pattern_grid.reshape(-1)}
                        )
                        iterations += 1
                        if value > best_value:
                            best_value = value
                            best_phase = float(candidate)
                    if best_phase is None:
                        pattern_grid[r_slice, c_slice] = original
                    else:
                        pattern_grid[r_slice, c_slice] = best_phase
                        current = best_value
                    history.append(current)
                    completed_tiles += 1
                    if progress is not None:
                        progress(completed_tiles, total_tiles, current)
                if cancelled:
                    break
            if cancelled:
                break
        return OptimizationResult(
            patterns={ris.id: pattern_grid.reshape(-1).copy()},
            objective_db=current,
            iterations=iterations,
            runtime_s=time.perf_counter() - started,
            history_db=history,
            cancelled=cancelled,
            algorithm="Feedback Greedy",
            hardware_phase_bits=ris.phase_bits,
            search_levels=int(configured_levels) if ris.phase_bits is None else None,
            pattern_source="Feedback Greedy",
            metadata={
                "candidate_levels": int(levels),
                "search_levels_applies": ris.phase_bits is None,
                "hardware_phase": "continuous" if ris.phase_bits is None else f"{ris.phase_bits}-bit",
            },
        )
