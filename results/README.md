# Results

Headless experiments write reproducible CSV and PNG artifacts below this directory.

`phase_bits/`（如存在）属于 v0.1 RIS-only/current scalar center-point model 的 legacy 输出；
小数位数不代表已验证的 aperture quadrature accuracy。

Foundation result readers classify directories without modifying their CSV/PNG artifacts:

- `legacy_v0_1_unversioned`: only the confirmed `results/phase_bits/` v0.1 output;
- `checkpoint_non_formal`: the dated A/B interim checkpoint below;
- `foundation_partial` / `foundation_complete`: valid C2 schema `airmirror_experiment_provenance/1`
  with the matching `provenance_status`;
- `malformed`: a Foundation run with missing or empty schema discriminators;
- `unclassified`: an unknown schema-less source.

An unknown non-empty schema ID or version is rejected rather than downgraded to legacy. Legacy,
checkpoint, partial, and complete outputs are not silently combined into one evidence grade.

Foundation `FND-QA-AP` 已 Verified；正式 v1 run `20260906T094526-de4745c3` 与 continuation
`20260906T123708-78615a33` 是只读历史证据。production canonical quadrature identity 已签署为
`midpoint_8x8_per_control_patch/1`；不得回填或改写历史 runner 的
`fnd_qa_ap_candidate/1`，也不得把内部 refined reference 标为 Ground Truth/EM truth。

2026-09-03 的 `checkpoints/foundation_0_1_1_ab_checkpoint_20260903/` 是 Foundation 0.1.1
A/B Interim Checkpoint 的隔离输出，仅标记为 checkpoint / non-formal provenance。它不是正式
Foundation experiment，不覆盖 `phase_bits/` legacy，也不回填 C2 尚未完成的 provenance 字段。
