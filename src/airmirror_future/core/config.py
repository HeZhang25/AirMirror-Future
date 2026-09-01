"""Shared immutable application presets that must not drift across frontends."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldQualityPreset:
    """A named field-map grid shared by GUI, CLI, and experiments."""

    key: str
    display_name: str
    grid_width: int
    grid_height: int


FIELD_QUALITY_PRESETS = (
    FieldQualityPreset("fast", "Fast", 80, 60),
    FieldQualityPreset("balanced", "Balanced", 120, 90),
    FieldQualityPreset("high", "High", 200, 160),
)


def field_quality_preset(key: str) -> FieldQualityPreset:
    """Return a field quality by stable lowercase key."""
    normalized = key.strip().lower()
    for preset in FIELD_QUALITY_PRESETS:
        if preset.key == normalized:
            return preset
    raise ValueError(f"unknown field quality: {key}")

