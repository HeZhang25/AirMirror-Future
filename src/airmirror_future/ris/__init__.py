"""RIS geometry, presets, phase control, and patterns."""

from airmirror_future.core.types import RISGeneration, RISSurface
from airmirror_future.core.pattern_contract import (
    COMMANDED_PHASE_ATOL_RAD,
    validate_commanded_pattern,
)
from airmirror_future.ris.aperture import (
    EQUIVALENT_PATCH_SEMANTIC,
    EquivalentPatchDiagnostics,
    equivalent_patch_diagnostics,
)
from airmirror_future.ris.generations import GENERATION_METADATA, generation_preset
from airmirror_future.ris.phase import (
    apply_common_phase_offset,
    common_phase_offset_candidates,
    generate_focus_pattern,
    generate_ris_only_focus_pattern,
    generate_unquantized_ris_only_focus_pattern,
    quantize_phase,
)

__all__ = [
    "GENERATION_METADATA",
    "EQUIVALENT_PATCH_SEMANTIC",
    "EquivalentPatchDiagnostics",
    "COMMANDED_PHASE_ATOL_RAD",
    "RISGeneration",
    "RISSurface",
    "apply_common_phase_offset",
    "common_phase_offset_candidates",
    "equivalent_patch_diagnostics",
    "generation_preset",
    "generate_focus_pattern",
    "generate_ris_only_focus_pattern",
    "generate_unquantized_ris_only_focus_pattern",
    "quantize_phase",
    "validate_commanded_pattern",
]
