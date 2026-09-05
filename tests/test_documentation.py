from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
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


def _tag_config_identity_value(value: object) -> object:
    if value is None:
        return ["null", None]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        assert math.isfinite(value)
        return ["float64_hex", value.hex()]
    if type(value) is str:
        return ["str", value]
    if isinstance(value, list):
        return [_tag_config_identity_value(child) for child in value]
    if isinstance(value, dict):
        return {
            key: _tag_config_identity_value(value[key])
            for key in sorted(value)
        }
    raise AssertionError(f"unsupported identity value type: {type(value)!r}")


def _recompute_fnd_qa_ap_config_identity(payload: dict[str, object]) -> str:
    identity = payload["identity"]
    assert isinstance(identity, dict)
    canonicalization = identity["canonicalization"]
    assert isinstance(canonicalization, dict)
    excluded = canonicalization["excluded_top_level_fields"]
    assert excluded == [
        "identity",
        "status",
        "approval_state",
        "qa_ap_status",
        "review_and_unresolved",
        "final_independent_ready_review",
        "review",
        "measured_results",
    ]
    unsigned_payload = {
        key: value for key, value in payload.items() if key not in excluded
    }
    canonical = _tag_config_identity_value(unsigned_payload)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_fnd_qa_ap_preregistration_is_signed_frozen_finite_config() -> None:
    path = ROOT / "configs" / "foundation_0_1_1" / "fnd_qa_ap_01_preregistration_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["config_kind"] == "fnd_qa_ap_01_preregistration"
    assert payload["config_version"] == "1"
    assert payload["status"] == "Ready"
    assert payload["approval_state"] == "signed"
    assert payload["qa_ap_status"] == "Ready"
    assert payload["freeze_policy"]["status"] == "frozen"
    assert payload["final_independent_ready_review"] == {
        "result": "PASS",
        "blocking_issues": 0,
        "scope": "FND-QA-AP-01 preregistration, physics, numerical and contract review",
        "status": "signed_frozen",
    }
    assert payload["identity"]["config_identity"] == _recompute_fnd_qa_ap_config_identity(payload)
    assert payload["scope_and_ownership"]["main_gating_world"] == "ControllerModel"
    assert payload["scope_and_ownership"]["ground_truth_in_main_gate"] is False
    pattern_hash_spec = payload["pattern_matrix"]["random_pattern_generator"]["pattern_hash"]
    assert "canonical JSON bytes" in pattern_hash_spec
    assert "array [generation, geometry_case, pattern_seed" not in pattern_hash_spec
    assert "series_identity" in payload["pattern_matrix"]
    generator = payload["pattern_matrix"]["random_pattern_generator"]
    assert "pack('<I'" in generator["digest_input"]
    assert "pack('<Q', pattern_seed)" in generator["digest_input"]
    assert "byte_level_requirements" in generator
    assert "lexicographically" in generator["pattern_hash"]
    assert "IEEE-754 binary64" in generator["finite_phase_bits"]
    assert "domain_separator" in generator["pattern_hash"]
    assert "ordered_phase_binary64_be_hex" in generator["pattern_hash"]
    assert "0x1.921fb54442d18p+2" in generator["byte_level_requirements"]
    assert "struct.pack('>d', phase).hex()" in generator["byte_level_requirements"]
    assert "m=r >> 11" in generator["continuous_phase"]
    assert "strictly in [0,tau_binary64)" in generator["continuous_phase"]
    assert "+ 0.5) / 2**64" not in generator["continuous_phase"]
    assert "ris_cell_centers_meshgrid_xy_c_v1" in generator["byte_level_requirements"]
    assert "float64_hex" in payload["identity"]["canonicalization"]["numbers"]
    assert payload["pattern_matrix"]["series_identity"]["canonicalization"].find("C1 tagged") >= 0
    assert payload["quadrature_matrix"]["cross_rule"]["base_order"] == [16, 16]
    assert payload["quadrature_matrix"]["cross_rule"]["conditional_order"] == [32, 32]
    assert "midpoint32-to-GL32" in payload["quadrature_matrix"]["reference_selection"]["conditional_32_reference"]
    assert "GL32" in payload["reference_environment_and_measurement"]["conditional_32_measurement"]
    assert "candidate quadrature values never enter" in payload["metrics_and_rules"]["aggregate_complex_metric"]["scale_ownership"]
    assert "candidate_deep_null" in payload["metrics_and_rules"]["deep_null_definition"]
    assert payload["quadrature_matrix"]["ordering_and_ownership"]["control_flatten_order"] == "ris_cell_centers_meshgrid_xy_c_v1"
    assert "quadrature_runtime_s" in payload["runner_contract"]["raw_columns"]
    assert "runtime_s" not in payload["runner_contract"]["raw_columns"]
    assert "reject_pattern_seed_collision_with_c2_seed" not in payload["validation_rules"]
    assert payload["runner_contract"]["raw_columns"]
    assert "a_normalization_floor_active" in payload["runner_contract"]["raw_columns"]
    assert "normalization_floor_active_h_ris" in payload["runner_contract"]["raw_columns"]
    assert "runner_implementation" in payload["dependency_classification"]["downstream_pending_dependencies_not_ready_blockers"]
    assert payload["dependency_classification"]["ready_blockers"] == []
    assert payload["reference_environment_and_measurement"]["runtime_budget_s"] == {
        "Current": 120,
        "Advanced": 240,
        "Future": 600,
    }
    assert payload["reference_environment_and_measurement"]["peak_rss_budget_mb"] == 4096
    assert payload["reference_environment_and_measurement"]["base_minimum_matrix_wall_budget_h"] == 8
    assert "series_runtime_s" in payload["runner_contract"]["runtime_measurements"]["budget_scope"]
    assert "run_runtime_s" in payload["runner_contract"]["runtime_measurements"]["budget_scope"]
    assert payload["runner_contract"]["c2_provenance_wiring"]["pending_contracts"] == [
        "FND-PHY-NB",
        "FND-QA-AP",
        "FND-QA-CC",
    ]

    config_identity = payload["identity"]["config_identity"]
    status = (ROOT / "DEVELOPMENT_STATUS.md").read_text(encoding="utf-8")
    work_item = (DOCS / "work_items" / "foundation_0_1_1_qa_ap.md").read_text(encoding="utf-8")
    assert config_identity in status
    assert config_identity in work_item

    def assert_finite(value: object) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for child in value.values():
                assert_finite(child)
        elif isinstance(value, list):
            for child in value:
                assert_finite(child)

    assert_finite(payload)


def test_adr_0008_uses_controller_only_qa_ap_gate() -> None:
    adr = (ROOT / "docs" / "adr" / "0008-minimum-aperture-quadrature-validity-gate.md").read_text(encoding="utf-8")
    assert "`ControllerModel` world/scene realization" in adr
    assert "`GroundTruthModel` 不进入 QA-AP 主门禁" in adr
    assert "`pattern_seed`" in adr
    assert "GL16×16" in adr
    assert "GL32" in adr
    assert "quadrature values" in adr


def test_c2_status_is_consistent_with_current_verified_fact() -> None:
    plan = (ROOT / "docs" / "foundation_0_1_1_plan.md").read_text(encoding="utf-8")
    status = (ROOT / "DEVELOPMENT_STATUS.md").read_text(encoding="utf-8")
    assert "| 13 | `FND-EXP-01` 加入最小实验 provenance | Verified |" in plan
    assert "`AMF-EXP-006` / C2 已为 **Verified**" in status
    assert "C2 provenance/no-overwrite 已 Verified" in status


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
