from dataclasses import replace
import math

import numpy as np
import pytest

from airmirror_future.core.types import RISSurface, Receiver, Transmitter, Vec3
from airmirror_future.physics.ris_scattering import ris_channel
from airmirror_future.ris.phase import generate_focus_pattern, quantize_phase


def _surface(nx: int = 8, ny: int = 8, width: float = 1.0, height: float = 1.0) -> RISSurface:
    return RISSurface(
        "ris",
        Vec3(0.0, 0.0, 1.5),
        -math.pi / 2.0,
        width,
        height,
        nx,
        ny,
        None,
        0.8,
    )


def _link() -> tuple[Transmitter, Receiver]:
    return Transmitter("tx", Vec3(-0.5, -5.0, 2.0)), Receiver(
        "rx", Vec3(1.0, -4.0, 1.2)
    )


def test_passive_efficiency_above_one_is_rejected() -> None:
    with pytest.raises(ValueError):
        replace(_surface(), reflection_efficiency=1.01)


def test_phase_quantization_states() -> None:
    phases = np.linspace(0.0, 2.0 * math.pi, 101, endpoint=False)
    one_bit = np.unique(np.round(quantize_phase(phases, 1), 12))
    two_bit = np.unique(np.round(quantize_phase(phases, 2), 12))
    assert set(one_bit) == {0.0, round(math.pi, 12)}
    assert set(two_bit) == {
        0.0,
        round(math.pi / 2.0, 12),
        round(math.pi, 12),
        round(3.0 * math.pi / 2.0, 12),
    }


def test_physics_focus_beats_random_pattern_median() -> None:
    tx, rx = _link()
    ris = _surface(12, 12)
    frequency = 5.0e9
    focus = generate_focus_pattern(ris, tx, rx, frequency)
    focused = abs(ris_channel(tx, rx.position, rx.gain_linear, ris, focus, frequency))
    rng = np.random.default_rng(20260901)
    random_values = []
    for _ in range(100):
        pattern = rng.uniform(0.0, 2.0 * math.pi, ris.cell_count)
        random_values.append(
            abs(ris_channel(tx, rx.position, rx.gain_linear, ris, pattern, frequency))
        )
    assert focused > 4.0 * np.median(random_values)


def test_fixed_aperture_subdivision_converges_without_cell_gain() -> None:
    tx, rx = _link()
    frequency = 5.0e9
    amplitudes = []
    for count in (8, 16, 32):
        ris = _surface(count, count, 1.0, 1.0)
        pattern = generate_focus_pattern(ris, tx, rx, frequency)
        amplitudes.append(
            abs(ris_channel(tx, rx.position, rx.gain_linear, ris, pattern, frequency))
        )
    spread_db = 20.0 * math.log10(max(amplitudes) / min(amplitudes))
    assert spread_db < 0.5


def test_larger_aperture_improves_focused_channel() -> None:
    tx, rx = _link()
    frequency = 5.0e9
    small = _surface(8, 8, 0.5, 0.5)
    large = _surface(16, 16, 1.0, 1.0)
    small_value = abs(
        ris_channel(
            tx,
            rx.position,
            rx.gain_linear,
            small,
            generate_focus_pattern(small, tx, rx, frequency),
            frequency,
        )
    )
    large_value = abs(
        ris_channel(
            tx,
            rx.position,
            rx.gain_linear,
            large,
            generate_focus_pattern(large, tx, rx, frequency),
            frequency,
        )
    )
    assert large_value > small_value


def test_back_side_receiver_gets_no_ris_field() -> None:
    tx, _ = _link()
    rx = Receiver("back", Vec3(0.0, 4.0, 1.2))
    ris = _surface()
    pattern = generate_focus_pattern(ris, tx, rx, 5.0e9)
    assert abs(ris_channel(tx, rx.position, 1.0, ris, pattern, 5.0e9)) == 0.0

