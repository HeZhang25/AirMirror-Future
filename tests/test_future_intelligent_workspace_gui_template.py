from __future__ import annotations

from airmirror_future.scenarios.xr_editor import (
    XR_EDITOR_SCENE_TEMPLATES,
    create_xr_editor_scene,
)


def test_future_intelligent_workspace_is_a_real_gui_template() -> None:
    template_ids = {identifier for identifier, _label in XR_EDITOR_SCENE_TEMPLATES}
    assert "future_intelligent_workspace" in template_ids
    scene = create_xr_editor_scene("future_intelligent_workspace")
    assert scene.name == "Future Intelligent Workspace"
    assert len(scene.ris_surfaces) == 2
    assert all(ris.generation == "Future" and ris.enabled for ris in scene.ris_surfaces)
