"""FND-T13d compatibility closure: environment IDs fail at data boundaries."""

from dataclasses import asdict, replace
import json

import pytest

from airmirror_future.core.types import Obstacle, Scene, SimulationConfig, Vec3, Wall
from airmirror_future.scenarios.smart_space import create_smart_space_scene
from airmirror_future.simulation.engine import SimulationEngine


@pytest.mark.parametrize("entity_type", (Wall, Obstacle))
@pytest.mark.parametrize("identifier", ("", None, 1))
def test_environment_constructor_rejects_invalid_id(entity_type, identifier) -> None:
    with pytest.raises(ValueError, match=f"{entity_type.__name__.lower()} id.*non-empty string"):
        if entity_type is Wall:
            Wall(identifier, Vec3(0, 0, 0), Vec3(1, 1, 0))
        else:
            Obstacle(identifier, Vec3(0, 0, 0), Vec3(1, 1, 1))


@pytest.mark.parametrize("collection", ("walls", "obstacles"))
def test_scene_constructor_rejects_mutated_empty_environment_id(collection) -> None:
    scene = create_smart_space_scene()
    getattr(scene, collection)[0].id = ""
    with pytest.raises(ValueError, match=f"{collection[:-1]} id.*non-empty string"):
        replace(scene)


@pytest.mark.parametrize("collection", ("walls", "obstacles"))
@pytest.mark.parametrize("identifier", ("", None, 1))
def test_scene_v1_loader_rejects_invalid_environment_id(tmp_path, collection, identifier) -> None:
    data = asdict(create_smart_space_scene())
    assert data["schema_version"] == 1
    data[collection][0]["id"] = identifier
    source = tmp_path / "invalid-id.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError) as error:
        Scene.load(source)
    message = str(error.value)
    assert f"{collection[:-1]} id={identifier!r}" in message
    assert "non-empty string" in message
    assert "assign an explicit identifier" in message


@pytest.mark.parametrize("collection", ("walls", "obstacles"))
@pytest.mark.parametrize("mutation", ("rename", "append"))
@pytest.mark.parametrize("mode", ("channel", "map"))
def test_engine_rejects_empty_environment_id_before_world_or_profile(
    monkeypatch, collection, mutation, mode
) -> None:
    scene = create_smart_space_scene()
    # Even a wall with neither reflection nor blockage must have a valid ID.
    scene.walls[0] = replace(scene.walls[0], reflection_magnitude=0, blocks_los=False)
    entities = getattr(scene, collection)
    entity = entities[0] if mutation == "rename" else replace(entities[0])
    entity.id = ""
    if mutation == "append":
        entities.append(entity)
    engine = SimulationEngine()

    def forbidden(*args, **kwargs):
        pytest.fail("environment-ID preflight must precede world/physics/Profile evaluation")

    for method in ("_working_scene", "_components", "_environment_modifier"):
        monkeypatch.setattr(engine, method, forbidden)
    with pytest.raises(ValueError, match=f"{collection[:-1]} id.*non-empty string"):
        if mode == "channel":
            engine.compute_channel(scene)
        else:
            engine.compute_field_map(scene, SimulationConfig(2, 2))
    assert entity.id == ""  # No silent renaming or removal of the invalid entity.
    assert any(item is entity for item in entities)


@pytest.mark.parametrize("identifier", (" ", " 墙/Obstacle:α "))
def test_nonempty_environment_ids_round_trip_without_normalization(tmp_path, identifier) -> None:
    scene = create_smart_space_scene()
    scene.walls[0] = replace(scene.walls[0], id=identifier)
    scene.obstacles[0] = replace(scene.obstacles[0], id=identifier)
    source = tmp_path / "nonempty-id.json"
    scene.save(source)
    loaded = Scene.load(source)
    assert loaded.schema_version == 1
    assert asdict(loaded) == asdict(scene)
    SimulationEngine().compute_channel(loaded)
