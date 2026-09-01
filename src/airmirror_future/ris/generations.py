"""Representative, editable RIS technology-generation assumptions."""

from __future__ import annotations

from airmirror_future.core.types import RISGeneration, RISSurface, Vec3


GENERATION_METADATA = {
    "Current": RISGeneration("Current", "当前 RIS", False),
    "Advanced": RISGeneration("Advanced", "先进 RIS", False),
    "Future": RISGeneration("Future", "未来电磁基础设施", True),
}


def generation_preset(
    generation: str,
    *,
    identifier: str = "ris-1",
    position: Vec3 = Vec3(5.0, 7.9, 1.5),
    yaw_rad: float = -1.5707963267948966,
) -> RISSurface:
    """Build a documented representative preset, not an industry claim."""
    key = generation.strip().lower()
    common = {"id": identifier, "position": position, "yaw_rad": yaw_rad}
    if key == "current":
        return RISSurface(
            **common,
            width_m=0.8,
            height_m=0.8,
            nx=8,
            ny=8,
            phase_bits=1,
            reflection_efficiency=0.70,
            update_rate_hz=10.0,
            self_sensing=False,
            generation="Current",
        )
    if key == "advanced":
        return RISSurface(
            **common,
            width_m=1.6,
            height_m=1.2,
            nx=24,
            ny=24,
            phase_bits=3,
            reflection_efficiency=0.85,
            update_rate_hz=100.0,
            self_sensing=True,
            generation="Advanced",
        )
    if key == "future":
        return RISSurface(
            **common,
            width_m=3.0,
            height_m=2.0,
            nx=64,
            ny=48,
            phase_bits=None,
            reflection_efficiency=0.95,
            update_rate_hz=1000.0,
            self_sensing=True,
            generation="Future",
        )
    raise ValueError(f"unknown RIS generation: {generation}")
