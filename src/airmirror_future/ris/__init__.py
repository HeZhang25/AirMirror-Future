"""RIS geometry, presets, phase control, and patterns."""

from airmirror_future.core.types import RISGeneration, RISSurface
from airmirror_future.ris.generations import GENERATION_METADATA, generation_preset
from airmirror_future.ris.phase import generate_focus_pattern, quantize_phase

__all__ = [
    "GENERATION_METADATA",
    "RISGeneration",
    "RISSurface",
    "generation_preset",
    "generate_focus_pattern",
    "quantize_phase",
]
