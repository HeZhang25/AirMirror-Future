"""FND-T13b..d/T14: routing, once-only factors, exclusion and world ownership."""

from dataclasses import asdict, replace
import inspect
import math

import numpy as np
import pytest

from airmirror_future.core.constants import MIN_DISTANCE_M
from airmirror_future.core.types import Obstacle, Scene, SimulationConfig, Vec3
from airmirror_future.optimization.coherent_focus import generate_coherent_target_pattern
from airmirror_future.physics import blockage, reflections
from airmirror_future.physics.free_space import complex_free_space_channel
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationCancelled, SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel, GroundTruthModel
from airmirror_future.simulation.profiles import (
    IndoorDeterministicProfile, PropagationModifier, PropagationPathContext, profile_identity,
)
from test_profile_compatibility import reflection_blockage_scene
from test_profiles import ROLES


class SpyProfile:
    """Test-only recorder; deterministic output and metadata reflect fixed role scales."""

    profile_id = "spy_profile"
    profile_version = "1"

    def __init__(self, scales=None):
        self.scales = {} if scales is None else dict(scales)
        self.calls = []
        self.outputs = []

    @property
    def canonical_parameters(self):
        return tuple(sorted(
            (f"{role}.{part}", float(getattr(complex(value), part)))
            for role, value in self.scales.items() for part in ("real", "imag")
        ))

    def environment_modifier(self, *, scene, context):
        self.calls.append((scene, context))
        original = IndoorDeterministicProfile().environment_modifier(scene=scene, context=context)
        result = replace(original, value=original.value * self.scales.get(context.role, 1))
        self.outputs.append(result)
        return result


def scene_with_ris():
    scene = reflection_blockage_scene()
    ris = replace(create_smart_space_scene().ris_surfaces[0], position=Vec3(3, 0, 1.5),
                  yaw_rad=math.pi, nx=2, ny=2)
    scene.ris_surfaces = [ris]
    return scene, {ris.id: np.zeros(ris.cell_count)}


def expected_contexts(scene, tx_position, rx_position):
    expected = [PropagationPathContext("direct", tx_position, rx_position)]
    for wall in scene.walls:
        if wall.reflection_magnitude == 0:
            continue
        point = reflections.reflection_point(tx_position, rx_position, wall)
        if point is not None:
            expected.extend((
                PropagationPathContext("reflection_before", tx_position, point, wall.id),
                PropagationPathContext("reflection_after", point, rx_position, wall.id),
            ))
    for ris in scene.ris_surfaces:
        expected.extend((
            PropagationPathContext("ris_incident", tx_position, ris.position, ris_id=ris.id),
            PropagationPathContext("ris_scattered", ris.position, rx_position, ris_id=ris.id),
        ))
    return expected


def test_profile_is_used_by_all_environment_path_roles() -> None:
    scene, patterns = scene_with_ris()
    spy = SpyProfile()
    SimulationEngine(spy).compute_channel(scene, ris_patterns=patterns)
    assert [ctx.role for _, ctx in spy.calls] == list(ROLES)
    assert [ctx for _, ctx in spy.calls] == expected_contexts(
        scene, scene.transmitter().position, scene.receiver().position)
    assert all(observed is scene for observed, _ in spy.calls)


def test_field_map_routes_each_link_through_all_applicable_roles() -> None:
    scene, patterns = scene_with_ris()
    spy = SpyProfile()
    result = SimulationEngine(spy).compute_field_map(scene, SimulationConfig(2, 2), patterns)
    expected = []
    for y in result.y_m:
        for x in result.x_m:
            expected.extend(expected_contexts(scene, scene.transmitter().position,
                                              Vec3(float(x), float(y), scene.z_eval_m)))
    assert [ctx for _, ctx in spy.calls] == expected
    assert len([ctx for _, ctx in spy.calls if ctx.role == "ris_incident"]) == 4
    # Numeric map values use the same injected Profile, not just a side-effect hook.
    scaled = SimulationEngine(SpyProfile({"direct": 0, "reflection_before": 0, "ris_incident": 0}))
    zero = scaled.compute_field_map(scene, SimulationConfig(2, 2), patterns)
    assert np.all(zero.received_power_dbm < result.received_power_dbm)


def test_disabled_uncommanded_and_invalid_reflections_do_not_call_profile() -> None:
    scene, patterns = scene_with_ris()
    ris = scene.ris_surfaces[0]
    scene.ris_surfaces = [replace(ris, enabled=False), replace(ris, id="uncommanded")]
    spy = SpyProfile()
    SimulationEngine(spy).compute_channel(scene, ris_patterns=patterns)
    assert [ctx.role for _, ctx in spy.calls] == list(ROLES[:3])
    assert [ctx.reflecting_wall_id for _, ctx in spy.calls[1:]] == ["mirror", "mirror"]


@pytest.mark.parametrize("role,component", (
    ("direct", "los_channel"), ("reflection_before", "wall_channel"),
    ("reflection_after", "wall_channel"), ("ris_incident", "ris_channel"),
    ("ris_scattered", "ris_channel"),
))
def test_complex_role_modifier_changes_only_its_component_once(role, component) -> None:
    scene, patterns = scene_with_ris()
    baseline = SimulationEngine().compute_channel(scene, ris_patterns=patterns)
    scale = 0.31 + 0.27j
    result = SimulationEngine(SpyProfile({role: scale})).compute_channel(scene, ris_patterns=patterns)
    for name in ("los_channel", "wall_channel", "ris_channel"):
        expected = getattr(baseline, name) * (scale if name == component else 1)
        assert getattr(result, name) == pytest.approx(expected, rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("factor", ("gamma", "reflection_before", "reflection_after"))
@pytest.mark.parametrize("scale", (0.0, 0.37, 1j))
def test_wall_coefficient_and_profile_modifiers_are_applied_once(factor, scale) -> None:
    scene = reflection_blockage_scene()
    class WallModel(ControllerModel):
        def __init__(self):
            self.calls = []
        def wall_coefficient(self, wall):
            self.calls.append(wall.id)
            return wall.reflection_coefficient * (scale if factor == "gamma" else 1)

    nominal = SimulationEngine().compute_channel(scene)
    model = WallModel()
    spy = SpyProfile({factor: scale} if factor != "gamma" else {})
    actual = SimulationEngine(spy).compute_channel(scene, model=model)
    assert actual.wall_channel == pytest.approx(nominal.wall_channel * scale, rel=1e-12, abs=1e-15)
    assert model.calls == ["mirror"]
    assert [ctx.role for _, ctx in spy.calls] == list(ROLES[:3])


def test_reflection_helper_is_carrier_only_and_zero_wall_skip_belongs_to_engine() -> None:
    scene = reflection_blockage_scene()
    tx, rx, wall = scene.transmitter(), scene.receiver(), scene.walls[0]
    path = reflections.single_wall_reflection_path(scene, tx, rx, wall)
    assert path is not None
    assert path.total_distance_m == pytest.approx(math.sqrt(20))
    assert path.carrier == complex_free_space_channel(path.total_distance_m, scene.frequency_hz,
                                                      tx.gain_linear, rx.gain_linear)
    changed = replace(wall, reflection_magnitude=0, reflection_phase_rad=0, attenuation_db=100)
    assert reflections.single_wall_reflection_path(scene, tx, rx, changed) == path
    no_blockers = replace(scene, walls=[changed], obstacles=[])
    assert reflections.single_wall_reflection_path(no_blockers, tx, rx, changed) == path
    spy = SpyProfile()
    assert SimulationEngine(spy).compute_channel(no_blockers).wall_channel == 0j
    assert len(spy.calls) == 1  # direct only, preserving v0.1 zero-reflectivity omission
    assert not hasattr(reflections, "single_wall_reflection")


def test_reflecting_wall_is_excluded_from_reflection_leg_blockers(monkeypatch) -> None:
    scene = reflection_blockage_scene()
    profile = IndoorDeterministicProfile()
    point = Vec3(0, 0, 1.5)
    before = PropagationPathContext("reflection_before", scene.transmitter().position, point, "mirror")
    after = PropagationPathContext("reflection_after", point, scene.receiver().position, "mirror")
    first = profile.environment_modifier(scene=scene, context=before)
    second = profile.environment_modifier(scene=scene, context=after)
    assert first.blocker_ids == ("before", "incident-box")
    assert second.blocker_ids == ("after", "scattered-box")
    assert first.value == pytest.approx(10 ** (-5 / 20))
    assert second.value == pytest.approx(10 ** (-11 / 20))
    # Prove explicit ID exclusion rather than relying on endpoint intersection tolerances.
    original_intersection = blockage.path_intersects_wall
    def forced_fixture_intersection(start, end, wall):
        if any(wall is candidate for candidate in scene.walls):
            return True
        return original_intersection(start, end, wall)
    monkeypatch.setattr(blockage, "path_intersects_wall", forced_fixture_intersection)
    for ctx in (before, after):
        ids = profile.environment_modifier(scene=scene, context=ctx).blocker_ids
        assert "mirror" not in ids
        assert ids[:3] == ("before", "after", "miss")


def test_default_is_deterministic_and_owns_only_blockage() -> None:
    scene = reflection_blockage_scene()
    profile = IndoorDeterministicProfile()
    ctx = PropagationPathContext("direct", scene.transmitter().position, scene.receiver().position)
    scene.obstacles = [Obstacle("opaque", Vec3(1.9, -0.5, 1), Vec3(2.1, 0.5, 2), fully_blocking=True)]
    original = profile.environment_modifier(scene=scene, context=ctx)
    assert original.value == complex(1e-15, 0)
    assert original.blocker_ids == ("opaque",)
    identity = profile_identity(profile)
    scene.walls[0] = replace(scene.walls[0], reflection_magnitude=0.9, reflection_phase_rad=0.2)
    scene.frequency_hz *= 2
    scene.transmitter().gain_linear *= 3
    scene.random_seed = 444
    for _ in range(5):
        assert profile.environment_modifier(scene=scene, context=ctx) == original
        assert profile_identity(profile) == identity


@pytest.mark.parametrize("mutation", ("append", "rename"))
@pytest.mark.parametrize("mode", ("channel", "map"))
def test_mutated_duplicate_wall_ids_fail_before_profile_or_world(monkeypatch, mutation, mode) -> None:
    scene = reflection_blockage_scene()
    if mutation == "append":
        scene.walls.append(replace(scene.walls[0]))
    else:
        scene.walls[1].id = "mirror"
    spy = SpyProfile()
    def forbidden(*args, **kwargs):
        pytest.fail("wall-ID preflight must precede world/reflection evaluation")
    engine = SimulationEngine(spy)
    # Keep probes instance-local: earlier GUI tests can still have live workers.
    monkeypatch.setattr(engine, "_working_scene", forbidden)
    monkeypatch.setattr(engine, "_components", forbidden)
    with pytest.raises(ValueError, match="duplicate wall id.*mirror"):
        if mode == "channel":
            engine.compute_channel(scene)
        else:
            engine.compute_field_map(scene, SimulationConfig(2, 2))
    assert spy.calls == []


def test_duplicate_wall_ids_rejected_by_constructor_and_loader(tmp_path) -> None:
    scene = reflection_blockage_scene()
    with pytest.raises(ValueError, match="duplicate wall id.*mirror"):
        replace(scene, walls=[scene.walls[0], replace(scene.walls[0])])
    scene.walls.append(replace(scene.walls[0]))
    source = tmp_path / "duplicate.json"
    scene.save(source)
    with pytest.raises(ValueError, match="duplicate wall id.*mirror"):
        Scene.load(source)


def test_scene_v1_round_trip_does_not_persist_profile_or_reflection_classes(tmp_path) -> None:
    scene = create_smart_space_scene()
    SimulationEngine(SpyProfile()).compute_channel(scene)
    target = tmp_path / "scene.json"
    scene.save(target)
    assert asdict(Scene.load(target)) == asdict(scene)
    assert scene.schema_version == 1
    assert "profile" not in target.read_text(encoding="utf-8")
    assert "reflection_model" not in target.read_text(encoding="utf-8")


BAD_RESULTS = (1j, (1j, ()), PropagationModifier([1]), PropagationModifier(np.array([1j])),
               PropagationModifier("invalid"), PropagationModifier(None), PropagationModifier(float("nan")),
               PropagationModifier(complex(0, float("inf"))), PropagationModifier(1j, ["x"]),
               PropagationModifier(1j, ("",)), PropagationModifier(1j, (1,)))


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("bad_result", BAD_RESULTS)
def test_engine_rejects_bad_outputs_with_profile_and_role(role, bad_result) -> None:
    class BrokenProfile(SpyProfile):
        def environment_modifier(self, *, scene, context):
            if context.role == role:
                return bad_result
            return super().environment_modifier(scene=scene, context=context)
    scene, patterns = scene_with_ris()
    with pytest.raises(ValueError, match=f"spy_profile.*{role}"):
        SimulationEngine(BrokenProfile()).compute_channel(scene, ris_patterns=patterns)


@pytest.mark.parametrize("error", (RuntimeError("profile failed"), NotImplementedError("missing role"),
                                   SimulationCancelled("cancelled by profile")))
def test_profile_exceptions_are_not_swallowed_or_replaced(error) -> None:
    class FailingProfile(SpyProfile):
        def environment_modifier(self, *, scene, context):
            if context.role == "reflection_after":
                raise error
            return super().environment_modifier(scene=scene, context=context)
    scene, patterns = scene_with_ris()
    with pytest.raises(type(error)) as raised:
        SimulationEngine(FailingProfile()).compute_channel(scene, ris_patterns=patterns)
    assert raised.value is error


def test_no_uniform_minimum_distance_rejection_for_ris_center_or_reflection_leg() -> None:
    scene, patterns = scene_with_ris()
    ris = scene.ris_surfaces[0]  # 2x2 cells, none at the aperture center
    scene.transmitter().position = ris.position
    spy = SpyProfile()
    SimulationEngine(spy).compute_channel(scene, ris_patterns=patterns)
    assert any(ctx.role == "ris_incident" and ctx.start == ctx.end for _, ctx in spy.calls)
    scene.receiver().position = ris.position
    scene.transmitter().position = Vec3(2, -1, 1.5)
    spy.calls.clear()
    SimulationEngine(spy).compute_channel(scene, ris_patterns=patterns)
    assert any(ctx.role == "ris_scattered" and ctx.start == ctx.end for _, ctx in spy.calls)
    # Valid image path with a leg below MIN_DISTANCE_M; total length remains valid.
    scene = reflection_blockage_scene()
    scene.transmitter().position = Vec3(MIN_DISTANCE_M / 10, 0, 1.5)
    spy = SpyProfile()
    SimulationEngine(spy).compute_channel(scene)
    legs = [ctx for _, ctx in spy.calls if ctx.role == "reflection_before"]
    assert legs and legs[0].start.distance_to(legs[0].end) < MIN_DISTANCE_M


def test_existing_kernel_and_cancellation_errors_remain() -> None:
    scene, patterns = scene_with_ris()
    scene.receiver().position = scene.transmitter().position
    with pytest.raises(ValueError, match="distance_m"):
        SimulationEngine().compute_channel(scene)
    scene, patterns = scene_with_ris()
    scene.ris_surfaces[0].active = True
    with pytest.raises(NotImplementedError, match="active RIS"):
        SimulationEngine().compute_channel(scene, ris_patterns=patterns)
    scene.ris_surfaces[0].active = False
    scene.transmitter().position = Vec3(*scene.ris_surfaces[0].cell_centers()[0])
    with pytest.raises(ValueError, match="cell centre"):
        SimulationEngine().compute_channel(scene, ris_patterns=patterns)
    spy = SpyProfile()
    with pytest.raises(SimulationCancelled):
        SimulationEngine(spy).compute_field_map(scene, SimulationConfig(2, 2), cancel_check=lambda: True)
    assert spy.calls == []


def test_ground_truth_geometry_is_explicit_but_ris_errors_do_not_enter_profile() -> None:
    scene, patterns = scene_with_ris()
    spy = SpyProfile()
    engine = SimulationEngine(spy)
    identity = engine.profile_identity
    nominal = engine.compute_channel(scene, ris_patterns=patterns)
    nominal_contexts, nominal_modifiers = [ctx for _, ctx in spy.calls], list(spy.outputs)
    spy.calls.clear()
    spy.outputs.clear()
    actual = engine.compute_channel(scene, ris_patterns=patterns, model=GroundTruthModel(
        seed=13, ris_phase_error_sigma_rad=0.4, ris_efficiency_sigma_fraction=0.1,
        wall_phase_error_sigma_rad=0.3, wall_amplitude_error_sigma_fraction=0.05))
    assert [ctx for _, ctx in spy.calls] == nominal_contexts
    assert spy.outputs == nominal_modifiers
    assert actual.wall_channel != nominal.wall_channel
    assert actual.ris_channel != nominal.ris_channel
    spy.calls.clear()
    truth = GroundTruthModel(seed=15, position_error_sigma_m=0.02)
    engine.compute_channel(scene, ris_patterns=patterns, model=truth)
    working, direct = spy.calls[0]
    assert working is not scene
    assert direct.start == truth.perturb("tx:tx", scene.transmitter().position)
    assert direct.end == truth.perturb("rx:rx", scene.receiver().position)
    assert working.walls[0] is not scene.walls[0]
    assert engine.profile_identity == identity
    assert set(inspect.signature(IndoorDeterministicProfile.environment_modifier).parameters) == {
        "self", "scene", "context"}


def test_hidden_ground_truth_cannot_change_nominal_focus_or_profile_selection() -> None:
    scene = create_smart_space_scene()
    scene.ris_surfaces[0] = replace(scene.ris_surfaces[0], nx=2, ny=2)
    spy = SpyProfile()
    engine = SimulationEngine(spy)
    before = generate_coherent_target_pattern(scene, engine=engine)
    identity = engine.profile_identity
    results = []
    for seed in (42, 987):
        truth = GroundTruthModel(seed=seed, position_error_sigma_m=0.02,
                                 wall_phase_error_sigma_rad=0.1, ris_phase_error_sigma_rad=0.3)
        results.append(engine.compute_channel(scene, model=truth,
                       ris_patterns={scene.ris_surfaces[0].id: before}).total_channel)
        with pytest.raises(ValueError, match="cannot use GroundTruthModel"):
            generate_coherent_target_pattern(scene, truth, engine=engine)
    assert results[0] != results[1]
    np.testing.assert_array_equal(before, generate_coherent_target_pattern(scene, engine=engine))
    assert engine.profile is spy
    assert engine.profile_identity == identity
