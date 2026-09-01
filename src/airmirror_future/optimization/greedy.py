"""Tile-based measurement-only coordinate descent."""

from __future__ import annotations

import math
import time
from typing import Callable

import numpy as np

from airmirror_future.core.types import OptimizationResult
from airmirror_future.optimization.base import Optimizer, ProgressCallback
from airmirror_future.optimization.measurement import MeasurementOracle
from airmirror_future.simulation.ground_truth import ControllerModel


class FeedbackGreedyOptimizer(Optimizer):
    """Coordinate descent over RIS tiles using only ``oracle.measure``."""

    def __init__(self, tile_height: int = 4, tile_width: int = 4, max_passes: int = 1):
        if min(tile_height, tile_width, max_passes) <= 0:
            raise ValueError("tile sizes and max_passes must be positive")
        self.tile_height = tile_height
        self.tile_width = tile_width
        self.max_passes = max_passes

    def optimize(
        self,
        controller_model: ControllerModel,
        measurement_oracle: MeasurementOracle,
        objective: str = "received_power_dbm",
        *,
        initial_patterns: dict[str, np.ndarray] | None = None,
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
        pattern_grid = pattern.reshape(ris.ny, ris.nx)
        levels = 8 if ris.phase_bits is None else 2**ris.phase_bits
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
        )

