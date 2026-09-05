from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
import re

from airmirror_future.core.config import FIELD_QUALITY_PRESETS
from airmirror_future.core.types import Scene
from airmirror_future.experiments.phase_bits import PHASE_BITS_RESULT_FIELDS
from airmirror_future.ris.generations import generation_preset
from airmirror_future.scenarios.smart_space import create_smart_space_scene


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

REQUIRED_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "DEVELOPMENT_STATUS.md",
    DOCS / "README.md",
    DOCS / "project_baseline.md",
    DOCS / "glossary.md",
    DOCS / "requirements.md",
    DOCS / "architecture.md",
    DOCS / "data_model.md",
    DOCS / "public_api.md",
    DOCS / "physics_model.md",
    DOCS / "scene_schema.md",
    DOCS / "gui_spec.md",
    DOCS / "optimization_spec.md",
    DOCS / "experiment_spec.md",
    DOCS / "test_strategy.md",
    DOCS / "definition_of_done.md",
    DOCS / "roadmap.md",
    DOCS / "decisions.md",
    DOCS / "future_assumptions.md",
    DOCS / "limitations.md",
    DOCS / "scenarios.md",
)


def _markdown_files() -> list[Path]:
    return [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "DEVELOPMENT_STATUS.md",
        *sorted(DOCS.rglob("*.md")),
    ]


def test_required_documentation_set_exists() -> None:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DOCUMENTS if not path.is_file()]
    assert not missing, f"missing required documentation: {missing}"


def test_normative_documents_declare_v01_baseline() -> None:
    normative = (
        "README.md",
        "project_baseline.md",
        "glossary.md",
        "requirements.md",
        "architecture.md",
        "data_model.md",
        "public_api.md",
        "physics_model.md",
        "scene_schema.md",
        "gui_spec.md",
        "optimization_spec.md",
        "experiment_spec.md",
        "test_strategy.md",
        "definition_of_done.md",
        "roadmap.md",
        "decisions.md",
    )
    missing = []
    for name in normative:
        text = (DOCS / name).read_text(encoding="utf-8")
        if "v0.1" not in text:
            missing.append(name)
    assert not missing, f"documents missing v0.1 baseline marker: {missing}"


def test_local_markdown_links_resolve() -> None:
    failures: list[str] = []
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for document in _markdown_files():
        text = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (document.parent / path_part).resolve()
            if not resolved.exists():
                failures.append(
                    f"{document.relative_to(ROOT)} -> {target}"
                )
    assert not failures, "broken local Markdown links:\n" + "\n".join(failures)


def test_requirement_ids_are_unique_and_well_formed() -> None:
    text = (DOCS / "requirements.md").read_text(encoding="utf-8")
    identifiers = re.findall(r"\|\s*(AMF-[A-Z]+-\d{3})\s*\|", text)
    duplicates = [identifier for identifier, count in Counter(identifiers).items() if count > 1]
    assert len(identifiers) >= 30, "requirements baseline is unexpectedly incomplete"
    assert not duplicates, f"duplicate requirement IDs: {duplicates}"


def test_implemented_requirements_have_verification_evidence() -> None:
    text = (DOCS / "requirements.md").read_text(encoding="utf-8")
    missing: list[str] = []
    for line in text.splitlines():
        if "| Implemented |" not in line and "| Verified |" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not cells[0].startswith("AMF-"):
            continue
        evidence = cells[-1]
        if evidence in {"", "—", "-"}:
            missing.append(cells[0])
    assert not missing, f"requirements without verification evidence: {missing}"


def test_builtin_smart_space_matches_versioned_json() -> None:
    built_in = create_smart_space_scene()
    serialized = Scene.load(ROOT / "scenes" / "smart_room.json")
    assert asdict(built_in) == asdict(serialized)


def test_generation_assumption_table_matches_code_presets() -> None:
    text = (DOCS / "future_assumptions.md").read_text(encoding="utf-8")
    for name in ("Current", "Advanced", "Future"):
        ris = generation_preset(name)
        assert f"{ris.width_m:.1f}×{ris.height_m:.1f} m" in text
        assert f"{ris.nx}×{ris.ny}" in text
        assert f"{ris.reflection_efficiency:.2f}" in text
        assert f"{ris.update_rate_hz:g} Hz" in text


def test_field_quality_documentation_matches_shared_config() -> None:
    public_api = (DOCS / "public_api.md").read_text(encoding="utf-8")
    gui_spec = (DOCS / "gui_spec.md").read_text(encoding="utf-8")
    experiment_spec = (DOCS / "experiment_spec.md").read_text(encoding="utf-8")
    for preset in FIELD_QUALITY_PRESETS:
        grid = f"{preset.grid_width}×{preset.grid_height}"
        assert grid in public_api
        assert grid in gui_spec
    fast = FIELD_QUALITY_PRESETS[0]
    assert f"{fast.display_name} {fast.grid_width}×{fast.grid_height}" in experiment_spec


def test_phase_bits_result_schema_contains_required_tracking_fields() -> None:
    required = {
        "provenance_schema_id",
        "provenance_schema_version",
        "provenance_status",
        "pending_contracts_json",
        "run_id",
        "software_version",
        "timestamp",
        "scenario",
        "frequency_hz",
        "bandwidth_hz",
        "generation",
        "ris_count",
        "ris_width_m",
        "ris_height_m",
        "nx",
        "ny",
        "phase_bits",
        "efficiency",
        "phase_error_sigma_rad",
        "algorithm",
        "focus_mode_id",
        "focus_mode_version",
        "search_levels",
        "profile_id",
        "profile_version",
        "profile_parameters_json",
        "profile_identity",
        "reflection_model_id",
        "reflection_model_version",
        "world_model_id",
        "world_model_version",
        "world_model_parameters_json",
        "rx_x_m",
        "rx_y_m",
        "rx_z_m",
        "received_power_dbm",
        "ris_gain_db",
        "snr_db",
        "coverage_percent",
        "coverage_threshold_db",
        "iterations",
        "runtime_s",
        "random_seed",
        "channel_frequency_model_id",
        "quadrature_policy_id",
        "quadrature_policy_version",
        "coefficient_model_identity",
    }
    assert required <= set(PHASE_BITS_RESULT_FIELDS)
