from __future__ import annotations

import copy
import csv
from dataclasses import replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from airmirror_future.core.pattern_contract import validate_commanded_pattern
from airmirror_future.core.types import (
    Obstacle,
    Receiver,
    RISSurface,
    Scene,
    Transmitter,
    Vec3,
    Wall,
)
from airmirror_future.experiments import xr_dynamic_room_mvp as mvp
from airmirror_future.experiments import xr_route
from airmirror_future.experiments import xr_route_headless
from airmirror_future.simulation.engine import SimulationEngine
from airmirror_future.simulation.ground_truth import ControllerModel


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROUTE = REPOSITORY_ROOT / "configs" / "xr_route_01" / "multi_room_route_v1.json"


def _scene() -> Scene:
    return Scene(
        name="XR route test scene",
        room_size=Vec3(10.0, 8.0, 3.0),
        frequency_hz=5.0e9,
        bandwidth_hz=100.0e6,
        transmitters=[Transmitter("tx", Vec3(1.0, 6.0, 2.4), 0.1, 1.0)],
        receivers=[Receiver("rx", Vec3(1.0, 2.0, 1.2), 1.0, 7.0)],
        walls=[
            Wall("partition-low", Vec3(4.0, 0.0, 0.0), Vec3(4.0, 3.0, 0.0)),
            Wall("partition-high", Vec3(4.0, 5.0, 0.0), Vec3(4.0, 8.0, 0.0)),
        ],
        obstacles=[Obstacle("cabinet", Vec3(6.0, 1.0, 0.0), Vec3(7.0, 2.0, 2.0))],
        ris_surfaces=[
            RISSurface(
                "ris",
                Vec3(5.0, 7.5, 1.5),
                -math.pi / 2.0,
                0.8,
                0.8,
                8,
                8,
                1,
                0.7,
                10.0,
                False,
                "Current",
            )
        ],
        z_eval_m=1.2,
        coverage_threshold_db=35.0,
        random_seed=20260908,
    )


def _write_experiment(
    tmp_path: Path,
    *,
    scene: Scene | None = None,
    waypoints: list[dict[str, object]] | None = None,
    timing: dict[str, object] | None = None,
    sampling: dict[str, object] | None = None,
    validation: dict[str, object] | None = None,
    document_updates: dict[str, object] | None = None,
) -> Path:
    scene_path = tmp_path / "scene.json"
    (scene or _scene()).save(scene_path)
    payload: dict[str, object] = {
        "schema_id": xr_route.XR_ROUTE_SCHEMA_ID,
        "schema_version": xr_route.XR_ROUTE_SCHEMA_VERSION,
        "experiment_id": "test-route",
        "scene": {"kind": "scene_v1_reference", "path": "scene.json"},
        "trajectory": {
            "waypoints": waypoints
            or [
                {"position_m": {"x": 1.0, "y": 4.0, "z": 1.2}},
                {"position_m": {"x": 5.0, "y": 4.0, "z": 1.2}},
            ],
            "timing": timing
            or {"kind": "explicit_times", "waypoint_times_s": [0.0, 2.0]},
        },
        "sampling": sampling
        or {"sample_interval_s": 1.0, "max_samples": 16},
        "validation": validation
        or {"clearance_warning_m": 0.1, "touch_is_collision": True},
    }
    if document_updates:
        payload.update(document_updates)
    route_path = tmp_path / "route.json"
    route_path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
    return route_path


def _lookup(
    computation: mvp.MVPComputation,
) -> dict[tuple[int, str], mvp.DynamicLinkSample]:
    return {
        (sample.trajectory.sample_index, sample.mode): sample
        for sample in computation.samples
    }


def test_checked_in_complex_route_loads_deterministically_with_real_door_gaps() -> None:
    first = xr_route.load_route_experiment(EXAMPLE_ROUTE)
    second = xr_route.load_route_experiment(EXAMPLE_ROUTE)

    assert first.experiment_id == "xr-multi-room-doorway-route-v1"
    assert first.scene.schema_version == 1
    assert len(first.scene.walls) == 10
    assert len(first.scene.obstacles) == 3
    assert len(first.trajectory) == 13
    assert first.trajectory[0].position == Vec3(2.0, 2.0, 1.2)
    assert first.trajectory[-1].position == Vec3(12.5, 8.2, 1.2)
    assert first.trajectory[-1].time_s == 17.0
    assert first.validation_report.is_valid
    assert first.validation_report.collisions == ()
    assert first.trajectory == second.trajectory
    assert first.scene_identity == second.scene_identity
    assert first.trajectory_identity == second.trajectory_identity
    assert first.experiment_identity == second.experiment_identity


def test_explicit_time_sampling_preserves_waypoints_endpoints_and_dwell() -> None:
    route = xr_route.RouteDefinition(
        (Vec3(1.0, 1.0, 1.2), Vec3(1.0, 1.0, 1.2), Vec3(3.0, 1.0, 1.2)),
        "explicit_times",
        waypoint_times_s=(0.0, 1.0, 3.0),
    )
    samples = xr_route.sample_route(
        route, xr_route.RouteSamplingPolicy(0.75, 16)
    )

    assert [sample.time_s for sample in samples] == [0.0, 0.75, 1.0, 1.5, 2.25, 3.0]
    assert samples[0].position == route.waypoints[0]
    assert samples[1].position == route.waypoints[0]
    assert samples[2].position == route.waypoints[1]
    assert samples[-1].position == route.waypoints[-1]
    assert [sample.sample_index for sample in samples] == list(range(len(samples)))


def test_speed_sampling_derives_deterministic_times_and_single_point_is_legal() -> None:
    route = xr_route.RouteDefinition(
        (Vec3(0.0, 0.0, 1.2), Vec3(3.0, 0.0, 1.2), Vec3(3.0, 4.0, 1.2)),
        "speed",
        segment_speeds_m_s=(1.5, 2.0),
    )
    samples = xr_route.sample_route(route, xr_route.RouteSamplingPolicy(1.5, 16))
    assert [sample.time_s for sample in samples] == [0.0, 1.5, 2.0, 3.0, 4.0]
    assert samples[2].position == route.waypoints[1]
    assert samples[-1].position == route.waypoints[-1]

    stationary = xr_route.RouteDefinition(
        (Vec3(2.0, 2.0, 1.2),), "speed", default_speed_m_s=1.0
    )
    assert xr_route.sample_route(
        stationary, xr_route.RouteSamplingPolicy(0.5, 1)
    ) == (mvp.TrajectorySample(0, 0.0, stationary.waypoints[0]),)


@pytest.mark.parametrize(
    ("route", "sampling", "message"),
    [
        (
            xr_route.RouteDefinition(
                (Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 1.0)),
                "explicit_times",
                waypoint_times_s=(1.0, 2.0),
            ),
            xr_route.RouteSamplingPolicy(1.0, 10),
            "start at exactly 0",
        ),
        (
            xr_route.RouteDefinition(
                (Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 1.0)),
                "explicit_times",
                waypoint_times_s=(0.0, 0.0),
            ),
            xr_route.RouteSamplingPolicy(1.0, 10),
            "strictly increasing",
        ),
        (
            xr_route.RouteDefinition(
                (Vec3(0.0, 0.0, 1.0), Vec3(0.0, 0.0, 1.0)),
                "speed",
                default_speed_m_s=1.0,
            ),
            xr_route.RouteSamplingPolicy(1.0, 10),
            "zero-length speed segment",
        ),
        (
            xr_route.RouteDefinition(
                (Vec3(0.0, 0.0, 1.0), Vec3(10.0, 0.0, 1.0)),
                "speed",
                default_speed_m_s=1.0,
            ),
            xr_route.RouteSamplingPolicy(0.25, 5),
            "exceeds max_samples",
        ),
        (
            xr_route.RouteDefinition(
                (Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 1.0)),
                "speed",
                default_speed_m_s=-1.0,
            ),
            xr_route.RouteSamplingPolicy(1.0, 10),
            "must be positive",
        ),
    ],
)
def test_sampling_rejects_invalid_timing_and_budget(
    route: xr_route.RouteDefinition,
    sampling: xr_route.RouteSamplingPolicy,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        xr_route.sample_route(route, sampling)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"schema_id": "unknown"}, "unsupported XR route schema_id"),
        ({"schema_version": 2}, "unsupported XR route schema_version"),
        ({"experiment_id": ""}, "experiment_id must be"),
    ],
)
def test_loader_rejects_unknown_or_incomplete_document(
    tmp_path: Path, updates: dict[str, object], message: str
) -> None:
    path = _write_experiment(tmp_path, document_updates=updates)
    with pytest.raises(ValueError, match=message):
        xr_route.load_route_experiment(path)


def test_loader_rejects_nonfinite_speed_and_invalid_sampling(tmp_path: Path) -> None:
    path = _write_experiment(
        tmp_path,
        timing={"kind": "speed", "default_speed_m_s": float("nan")},
    )
    with pytest.raises(ValueError, match="must be finite"):
        xr_route.load_route_experiment(path)

    path = _write_experiment(
        tmp_path,
        sampling={"sample_interval_s": 0.0, "max_samples": 10},
    )
    with pytest.raises(ValueError, match="must be positive"):
        xr_route.load_route_experiment(path)


def test_json_round_trip_preserves_semantics_and_identities(tmp_path: Path) -> None:
    loaded = xr_route.load_route_experiment(EXAMPLE_ROUTE)
    copy_path = tmp_path / "nested" / "route-copy.json"
    xr_route.save_route_experiment(loaded, copy_path)
    copied = xr_route.load_route_experiment(copy_path)

    assert copied.scene == loaded.scene
    assert copied.route == loaded.route
    assert copied.sampling == loaded.sampling
    assert copied.validation == loaded.validation
    assert copied.trajectory == loaded.trajectory
    assert copied.scene_identity == loaded.scene_identity
    assert copied.trajectory_identity == loaded.trajectory_identity
    assert copied.experiment_identity == loaded.experiment_identity
    with pytest.raises(FileExistsError):
        xr_route.save_route_experiment(loaded, copy_path)


def test_in_memory_factory_owns_one_consistent_validated_snapshot() -> None:
    scene = _scene()
    route = xr_route.RouteDefinition(
        (Vec3(1.0, 4.0, 1.2), Vec3(5.0, 4.0, 1.2)),
        "explicit_times",
        waypoint_times_s=(0.0, 2.0),
    )
    sampling = xr_route.RouteSamplingPolicy(0.75, 16)
    validation = xr_route.RouteValidationPolicy(0.1)

    experiment = xr_route.create_route_experiment(
        scene,
        route,
        sampling,
        validation,
        experiment_id="editor-draft",
    )
    scene.name = "mutated caller scene"
    scene.receivers[0] = replace(scene.receiver(), position=Vec3(9.0, 7.0, 1.2))

    assert experiment.scene is not scene
    assert experiment.scene.name == "XR route test scene"
    assert experiment.route == route
    assert experiment.sampling == sampling
    assert experiment.validation == validation
    assert experiment.scene_path is None
    assert [sample.time_s for sample in experiment.trajectory] == [
        0.0,
        0.75,
        1.5,
        2.0,
    ]
    assert experiment.validation_report.is_valid
    assert experiment.scene_identity.startswith("sha256:")
    assert experiment.trajectory_identity.startswith("sha256:")
    assert experiment.experiment_identity.startswith("sha256:")
    with pytest.raises(TypeError):
        xr_route.XRRouteExperiment(
            "manual",
            experiment.scene,
            None,
            route,
            sampling,
            validation,
            (),
            experiment.validation_report,
            "bad",
            "bad",
            "bad",
        )


def test_in_memory_factory_rejects_invalid_route_and_sample_budget() -> None:
    colliding = xr_route.RouteDefinition(
        (Vec3(1.0, 2.0, 1.2), Vec3(5.0, 2.0, 1.2)),
        "explicit_times",
        waypoint_times_s=(0.0, 1.0),
    )
    with pytest.raises(xr_route.RouteValidationError, match="partition-low"):
        xr_route.create_route_experiment(
            _scene(),
            colliding,
            xr_route.RouteSamplingPolicy(1.0, 2),
            xr_route.RouteValidationPolicy(),
            experiment_id="invalid-route",
        )

    valid = replace(
        colliding,
        waypoints=(Vec3(1.0, 4.0, 1.2), Vec3(5.0, 4.0, 1.2)),
    )
    with pytest.raises(ValueError, match="exceeds max_samples"):
        xr_route.create_route_experiment(
            _scene(),
            valid,
            xr_route.RouteSamplingPolicy(0.25, 2),
            xr_route.RouteValidationPolicy(),
            experiment_id="invalid-budget",
        )


def test_in_memory_factory_revalidates_a_mutated_scene() -> None:
    scene = _scene()
    scene.frequency_hz = -1.0
    route = xr_route.RouteDefinition(
        (Vec3(1.0, 4.0, 1.2),),
        "explicit_times",
        waypoint_times_s=(0.0,),
    )

    with pytest.raises(ValueError, match="frequency_hz"):
        xr_route.create_route_experiment(
            scene,
            route,
            xr_route.RouteSamplingPolicy(1.0, 1),
            xr_route.RouteValidationPolicy(),
            experiment_id="invalid-scene",
        )


def test_explicit_speed_retime_shifts_later_arrivals_and_preserves_dwell() -> None:
    route = xr_route.RouteDefinition(
        (
            Vec3(0.0, 0.0, 1.2),
            Vec3(2.0, 0.0, 1.2),
            Vec3(2.0, 0.0, 1.2),
            Vec3(6.0, 0.0, 1.2),
        ),
        "explicit_times",
        waypoint_times_s=(0.0, 2.0, 5.0, 9.0),
    )

    retimed = xr_route.retime_route_from_previous_speed(route, 1, 2.0)

    assert retimed.waypoint_times_s == (0.0, 1.0, 4.0, 8.0)
    assert retimed.waypoint_times_s[2] - retimed.waypoint_times_s[1] == 3.0
    assert retimed.waypoint_times_s[3] - retimed.waypoint_times_s[2] == 4.0
    assert route.waypoint_times_s == (0.0, 2.0, 5.0, 9.0)
    with pytest.raises(ValueError, match="zero-length dwell"):
        xr_route.retime_route_from_previous_speed(route, 2, 1.0)


def test_speed_route_retime_changes_only_selected_segment() -> None:
    route = xr_route.RouteDefinition(
        (
            Vec3(0.0, 0.0, 1.2),
            Vec3(3.0, 0.0, 1.2),
            Vec3(3.0, 4.0, 1.2),
        ),
        "speed",
        default_speed_m_s=1.0,
    )

    retimed = xr_route.retime_route_from_previous_speed(route, 2, 2.0)

    assert retimed.default_speed_m_s is None
    assert retimed.segment_speeds_m_s == (1.0, 2.0)
    samples = xr_route.sample_route(
        retimed,
        xr_route.RouteSamplingPolicy(1.0, 10),
    )
    assert samples[-1].time_s == 5.0


@pytest.mark.parametrize("speed", (0.0, -1.0, float("inf"), float("nan")))
def test_speed_retime_rejects_invalid_speed(speed: float) -> None:
    route = xr_route.RouteDefinition(
        (Vec3(0.0, 0.0, 1.2), Vec3(1.0, 0.0, 1.2)),
        "explicit_times",
        waypoint_times_s=(0.0, 1.0),
    )
    with pytest.raises(ValueError, match="speed_m_s must"):
        xr_route.retime_route_from_previous_speed(route, 1, speed)


@pytest.mark.parametrize("index", (0, 2, True))
def test_speed_retime_rejects_invalid_or_single_point_index(index: int) -> None:
    route = xr_route.RouteDefinition(
        (Vec3(0.0, 0.0, 1.2), Vec3(1.0, 0.0, 1.2)),
        "explicit_times",
        waypoint_times_s=(0.0, 1.0),
    )
    with pytest.raises(ValueError, match="waypoint_index"):
        xr_route.retime_route_from_previous_speed(route, index, 1.0)

    single = xr_route.RouteDefinition(
        (Vec3(0.0, 0.0, 1.2),),
        "explicit_times",
        waypoint_times_s=(0.0,),
    )
    with pytest.raises(ValueError, match="waypoint_index"):
        xr_route.retime_route_from_previous_speed(single, 1, 1.0)


def test_single_point_factory_obeys_sample_budget() -> None:
    experiment = xr_route.create_route_experiment(
        _scene(),
        xr_route.RouteDefinition(
            (Vec3(1.0, 4.0, 1.2),),
            "explicit_times",
            waypoint_times_s=(0.0,),
        ),
        xr_route.RouteSamplingPolicy(0.5, 1),
        xr_route.RouteValidationPolicy(),
        experiment_id="stationary",
    )
    assert experiment.trajectory == (
        mvp.TrajectorySample(0, 0.0, Vec3(1.0, 4.0, 1.2)),
    )


def test_scene_path_binding_requires_the_same_scene_snapshot(tmp_path: Path) -> None:
    scene = _scene()
    route = xr_route.RouteDefinition(
        (Vec3(1.0, 4.0, 1.2), Vec3(5.0, 4.0, 1.2)),
        "explicit_times",
        waypoint_times_s=(0.0, 2.0),
    )
    scene_path = tmp_path / "scene.json"
    different_path = tmp_path / "different.json"
    scene.save(scene_path)
    replace(scene, name="different scene").save(different_path)

    bound = xr_route.create_route_experiment(
        scene,
        route,
        xr_route.RouteSamplingPolicy(1.0, 4),
        xr_route.RouteValidationPolicy(),
        experiment_id="bound",
        scene_path=scene_path,
    )
    assert bound.scene_path == scene_path.resolve()
    with pytest.raises(ValueError, match="same validated Scene v1"):
        xr_route.create_route_experiment(
            scene,
            route,
            xr_route.RouteSamplingPolicy(1.0, 4),
            xr_route.RouteValidationPolicy(),
            experiment_id="mismatch",
            scene_path=different_path,
        )
    with pytest.raises(FileNotFoundError, match="does not exist"):
        xr_route.create_route_experiment(
            scene,
            route,
            xr_route.RouteSamplingPolicy(1.0, 4),
            xr_route.RouteValidationPolicy(),
            experiment_id="missing",
            scene_path=tmp_path / "missing.json",
        )


def test_scene_identity_is_stable_across_scene_v1_numeric_round_trip(
    tmp_path: Path,
) -> None:
    scene = _scene()
    scene.room_size = Vec3(10, 8, 3)
    scene.walls[0] = replace(
        scene.walls[0],
        start=Vec3(4, 0, 0),
        end=Vec3(4, 3, 0),
    )
    route = xr_route.RouteDefinition(
        (Vec3(1.0, 4.0, 1.2),),
        "explicit_times",
        waypoint_times_s=(0.0,),
    )
    experiment = xr_route.create_route_experiment(
        scene,
        route,
        xr_route.RouteSamplingPolicy(1.0, 1),
        xr_route.RouteValidationPolicy(),
        experiment_id="numeric-normalization",
    )
    route_path = tmp_path / "route.json"

    bound = xr_route.save_route_experiment_bundle(experiment, route_path)
    loaded = xr_route.load_route_experiment(route_path)

    assert loaded.scene == bound.scene == experiment.scene
    assert loaded.scene_identity == bound.scene_identity == experiment.scene_identity
    assert loaded.experiment_identity == experiment.experiment_identity


def test_route_identity_is_stable_across_numeric_round_trip(tmp_path: Path) -> None:
    experiment = xr_route.create_route_experiment(
        _scene(),
        xr_route.RouteDefinition(
            (Vec3(1, 4, 1), Vec3(2, 4, 1)),
            "explicit_times",
            waypoint_times_s=(0, 2),
        ),
        xr_route.RouteSamplingPolicy(1, 3),
        xr_route.RouteValidationPolicy(0),
        experiment_id="route-numeric-normalization",
    )
    route_path = tmp_path / "route.json"

    xr_route.save_route_experiment_bundle(experiment, route_path)
    loaded = xr_route.load_route_experiment(route_path)

    assert loaded.trajectory == experiment.trajectory
    assert loaded.trajectory_identity == experiment.trajectory_identity
    assert loaded.experiment_identity == experiment.experiment_identity


def test_unbound_route_save_rejects_and_controlled_bundle_round_trips(
    tmp_path: Path,
) -> None:
    experiment = xr_route.create_route_experiment(
        _scene(),
        xr_route.RouteDefinition(
            (Vec3(1.0, 4.0, 1.2), Vec3(5.0, 4.0, 1.2)),
            "explicit_times",
            waypoint_times_s=(0.0, 2.0),
        ),
        xr_route.RouteSamplingPolicy(0.75, 8),
        xr_route.RouteValidationPolicy(),
        experiment_id="editor-bundle",
    )
    route_path = tmp_path / "saved-route.json"
    with pytest.raises(ValueError, match="route-only save requires"):
        xr_route.save_route_experiment(experiment, route_path)
    assert not route_path.exists()

    bound = xr_route.save_route_experiment_bundle(experiment, route_path)
    assert bound.scene_path == (tmp_path / "saved-route.scene.json").resolve()
    assert bound.scene_path.is_file()
    loaded = xr_route.load_route_experiment(route_path)
    assert loaded.scene == bound.scene == experiment.scene
    assert loaded.route == bound.route == experiment.route
    assert loaded.trajectory == bound.trajectory == experiment.trajectory
    assert loaded.scene_identity == bound.scene_identity == experiment.scene_identity
    assert (
        loaded.trajectory_identity
        == bound.trajectory_identity
        == experiment.trajectory_identity
    )
    assert (
        loaded.experiment_identity
        == bound.experiment_identity
        == experiment.experiment_identity
    )


def test_bundle_never_reuses_or_overwrites_a_different_scene(tmp_path: Path) -> None:
    experiment = xr_route.create_route_experiment(
        _scene(),
        xr_route.RouteDefinition(
            (Vec3(1.0, 4.0, 1.2),),
            "explicit_times",
            waypoint_times_s=(0.0,),
        ),
        xr_route.RouteSamplingPolicy(1.0, 1),
        xr_route.RouteValidationPolicy(),
        experiment_id="no-overwrite",
    )
    scene_path = tmp_path / "existing-scene.json"
    different = replace(_scene(), name="different scene")
    different.save(scene_path)
    original = scene_path.read_bytes()

    with pytest.raises(ValueError, match="same validated Scene v1"):
        xr_route.save_route_experiment_bundle(
            experiment,
            tmp_path / "route.json",
            scene_path=scene_path,
        )
    assert scene_path.read_bytes() == original
    assert not (tmp_path / "route.json").exists()


def test_bound_route_save_rejects_scene_file_changed_after_validation(
    tmp_path: Path,
) -> None:
    scene = _scene()
    scene_path = tmp_path / "scene.json"
    scene.save(scene_path)
    experiment = xr_route.create_route_experiment(
        scene,
        xr_route.RouteDefinition(
            (Vec3(1.0, 4.0, 1.2),),
            "explicit_times",
            waypoint_times_s=(0.0,),
        ),
        xr_route.RouteSamplingPolicy(1.0, 1),
        xr_route.RouteValidationPolicy(),
        experiment_id="stale-scene-path",
        scene_path=scene_path,
    )
    replace(scene, name="changed scene").save(scene_path)

    with pytest.raises(ValueError, match="same validated Scene v1"):
        xr_route.save_route_experiment(experiment, tmp_path / "route.json")
    assert not (tmp_path / "route.json").exists()


def test_saving_or_headless_compute_rejects_a_mutated_snapshot(tmp_path: Path) -> None:
    experiment = xr_route.create_route_experiment(
        _scene(),
        xr_route.RouteDefinition(
            (Vec3(1.0, 4.0, 1.2),),
            "explicit_times",
            waypoint_times_s=(0.0,),
        ),
        xr_route.RouteSamplingPolicy(1.0, 1),
        xr_route.RouteValidationPolicy(),
        experiment_id="mutation-guard",
    )
    corrupted = copy.deepcopy(experiment)
    corrupted.scene.name = "mutated after validation"

    with pytest.raises(ValueError, match="mutated or is inconsistent"):
        xr_route.save_route_experiment_bundle(corrupted, tmp_path / "route.json")
    with pytest.raises(ValueError, match="mutated or is inconsistent"):
        xr_route_headless.compute_route_experiment(corrupted)


def test_collision_validation_uses_continuous_3d_geometry_and_true_gap() -> None:
    scene = _scene()
    policy = xr_route.RouteValidationPolicy(0.1)
    low_wall_scene = replace(
        scene,
        walls=[replace(wall, height_m=2.0) for wall in scene.walls],
    )
    through_gap = xr_route.validate_route(
        scene, (Vec3(1.0, 4.0, 1.2), Vec3(5.0, 4.0, 1.2)), policy
    )
    through_wall = xr_route.validate_route(
        scene, (Vec3(1.0, 2.0, 1.2), Vec3(5.0, 2.0, 1.2)), policy
    )
    above_wall = xr_route.validate_route(
        low_wall_scene,
        (Vec3(1.0, 2.0, 2.5), Vec3(5.0, 2.0, 2.5)),
        policy,
    )
    through_obstacle = xr_route.validate_route(
        scene, (Vec3(5.0, 1.5, 1.2), Vec3(8.0, 1.5, 1.2)), policy
    )
    out_of_room = xr_route.validate_route(
        scene, (Vec3(-0.1, 4.0, 1.2), Vec3(2.0, 4.0, 1.2)), policy
    )

    assert through_gap.is_valid
    assert through_gap.collisions == ()
    assert not through_wall.is_valid
    assert {(item.geometry_kind, item.geometry_id) for item in through_wall.collisions} == {
        ("wall", "partition-low")
    }
    assert above_wall.is_valid
    assert not through_obstacle.is_valid
    assert {(item.geometry_kind, item.geometry_id) for item in through_obstacle.collisions} == {
        ("obstacle", "cabinet")
    }
    assert not out_of_room.is_valid
    assert any("outside the room" in error for error in out_of_room.errors)


def test_touch_is_collision_and_clearance_is_only_a_warning() -> None:
    scene = _scene()
    touching = xr_route.validate_route(
        scene,
        (Vec3(4.0, 3.0, 1.2),),
        xr_route.RouteValidationPolicy(0.1),
    )
    near = xr_route.validate_route(
        scene,
        (Vec3(3.95, 5.0, 1.2),),
        xr_route.RouteValidationPolicy(0.1),
    )

    assert not touching.is_valid
    assert touching.collisions[0].geometry_kind == "wall"
    assert near.is_valid
    assert any(warning.code == "wall_clearance" for warning in near.warnings)


def test_vertical_segment_cannot_cross_wall_top_at_fixed_xy() -> None:
    scene = _scene()
    report = xr_route.validate_route(
        scene,
        (Vec3(4.0, 2.0, 3.5), Vec3(4.0, 2.0, 2.5)),
        xr_route.RouteValidationPolicy(0.0),
    )

    assert not report.is_valid
    assert {(item.geometry_kind, item.geometry_id) for item in report.collisions} == {
        ("wall", "partition-low")
    }


@pytest.fixture(scope="module")
def real_route_computation(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("xr-route-real")
    path = _write_experiment(
        root,
        waypoints=[
            {"position_m": {"x": 1.0, "y": 4.0, "z": 1.2}},
            {"position_m": {"x": 2.0, "y": 4.0, "z": 1.2}},
        ],
        timing={"kind": "explicit_times", "waypoint_times_s": [0.0, 1.0]},
        sampling={"sample_interval_s": 1.0, "max_samples": 2},
    )
    experiment = xr_route.load_route_experiment(path)
    computation = xr_route_headless.compute_route_experiment(experiment)
    return path, experiment, computation


def test_real_three_mode_route_uses_shared_conditions_and_immutable_commands(
    real_route_computation,
) -> None:
    _, experiment, computation = real_route_computation
    assert computation.trajectory == experiment.trajectory
    assert len(computation.trajectory) == 2
    assert len(computation.samples) == 6
    assert not computation.static_pattern.flags.writeable
    lookup = _lookup(computation)
    ris = computation.scene.ris_surfaces[0]
    static_hashes = set()

    for point in computation.trajectory:
        no_ris = lookup[(point.sample_index, mvp.NO_RIS_MODE)]
        static = lookup[(point.sample_index, mvp.STATIC_RIS_MODE)]
        adaptive = lookup[(point.sample_index, mvp.ADAPTIVE_RIS_MODE)]
        assert no_ris.trajectory == static.trajectory == adaptive.trajectory == point
        assert no_ris.commanded_pattern is None
        assert no_ris.command_hash == ""
        assert no_ris.ris_channel == 0.0j
        assert static.commanded_pattern is computation.static_pattern
        assert not static.commanded_pattern.flags.writeable
        assert adaptive.commanded_pattern is not None
        assert not adaptive.commanded_pattern.flags.writeable
        assert np.array_equal(
            validate_commanded_pattern(ris, adaptive.commanded_pattern),
            adaptive.commanded_pattern,
        )
        assert no_ris.los_channel == static.los_channel == adaptive.los_channel
        assert no_ris.wall_channel == static.wall_channel == adaptive.wall_channel
        assert no_ris.noise_power_dbm == static.noise_power_dbm == adaptive.noise_power_dbm
        static_hashes.add(static.command_hash)
    assert len(static_hashes) == 1

    static_zero = lookup[(0, mvp.STATIC_RIS_MODE)]
    adaptive_zero = lookup[(0, mvp.ADAPTIVE_RIS_MODE)]
    assert np.array_equal(static_zero.commanded_pattern, adaptive_zero.commanded_pattern)
    assert static_zero.command_hash == adaptive_zero.command_hash
    assert static_zero.total_channel == adaptive_zero.total_channel
    assert static_zero.received_power_dbm == adaptive_zero.received_power_dbm
    assert static_zero.snr_db == adaptive_zero.snr_db


def test_route_csv_metadata_retain_actual_commands_identities_and_partial_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_route_computation,
) -> None:
    route_path, experiment, computation = real_route_computation
    monkeypatch.setattr(
        xr_route_headless,
        "compute_route_experiment",
        lambda *_args, **_kwargs: computation,
    )
    output = tmp_path / "route-run"
    artifacts = xr_route_headless.run_route_experiment(route_path, output)

    assert artifacts.output_directory == output.resolve()
    assert artifacts.sample_count == len(experiment.trajectory)
    assert artifacts.png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["schema_id"] == xr_route_headless.XR_ROUTE_RESULT_SCHEMA_ID
    assert metadata["prototype_status"] == "non_release_xr_route_provisional"
    assert metadata["experiment_identity"] == experiment.experiment_identity
    assert metadata["scene_identity"] == experiment.scene_identity
    assert metadata["trajectory_identity"] == experiment.trajectory_identity
    assert metadata["sample_count"] == len(experiment.trajectory)
    assert metadata["provenance"]["provenance_status"] == "partial"
    assert set(json.loads(metadata["provenance"]["pending_contracts_json"])) == {
        "FND-QA-CC",
    }
    assert metadata["provenance"]["coefficient_model_identity"] == ""

    with artifacts.csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == xr_route_headless.ROUTE_CSV_FIELDS
    assert len(rows) == len(experiment.trajectory) * 3
    assert {row["experiment_identity"] for row in rows} == {
        experiment.experiment_identity
    }
    assert {row["trajectory_identity"] for row in rows} == {
        experiment.trajectory_identity
    }
    assert {row["provenance_status"] for row in rows} == {"partial"}
    assert {row["prototype_status"] for row in rows} == {
        "non_release_xr_route_provisional"
    }
    ris = experiment.scene.ris_surfaces[0]
    for row in rows:
        if row["mode"] == mvp.NO_RIS_MODE:
            assert row["command_values_json"] == ""
            assert row["command_hash"] == ""
            assert float(row["ris_channel_real"]) == 0.0
            assert float(row["ris_channel_imag"]) == 0.0
        else:
            command = np.asarray(json.loads(row["command_values_json"]), dtype=float)
            command = validate_commanded_pattern(ris, command)
            assert mvp._pattern_hash(command) == row["command_hash"]
        assert all(
            math.isfinite(float(row[field]))
            for field in (
                "time_s",
                "rx_x_m",
                "rx_y_m",
                "rx_z_m",
                "total_channel_real",
                "total_channel_imag",
                "los_channel_real",
                "los_channel_imag",
                "wall_channel_real",
                "wall_channel_imag",
                "ris_channel_real",
                "ris_channel_imag",
                "received_power_dbm",
                "snr_db",
            )
        )


def test_existing_output_fails_before_route_physics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("physics must not run")

    monkeypatch.setattr(xr_route_headless, "compute_route_experiment", unexpected)
    with pytest.raises(FileExistsError):
        xr_route_headless.run_route_experiment(EXAMPLE_ROUTE, output)
    assert called is False
    assert marker.read_text(encoding="utf-8") == "keep"


def test_default_output_is_external_and_legacy_trajectory_contract_is_unchanged() -> None:
    default_root = xr_route_headless._DEFAULT_OUTPUT_ROOT.resolve()
    assert not default_root.is_relative_to(REPOSITORY_ROOT.resolve())
    legacy = mvp.build_trajectory()
    assert len(legacy) == 11
    assert legacy[0].position == mvp.TRAJECTORY_START
    assert legacy[-1].time_s == mvp.TRAJECTORY_DURATION_S


def test_route_compute_accepts_injected_production_engine_and_model(
    real_route_computation,
) -> None:
    _, experiment, expected = real_route_computation
    repeated = xr_route_headless.compute_route_experiment(
        experiment,
        engine=SimulationEngine(),
        model=ControllerModel(),
    )
    assert repeated.trajectory == expected.trajectory
    assert np.array_equal(repeated.static_pattern, expected.static_pattern)
    for left, right in zip(repeated.samples, expected.samples, strict=True):
        assert left.mode == right.mode
        assert left.command_hash == right.command_hash
        assert left.total_channel == right.total_channel
        assert left.received_power_dbm == right.received_power_dbm
