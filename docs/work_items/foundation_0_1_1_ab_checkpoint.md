# Work Item：Foundation 0.1.1 A/B Interim Checkpoint

- 层级：L4 checkpoint
- Requirement / plan gate：Foundation 0.1.1 §14.3–14.4（A/B Interim Checkpoint）
- 状态：Checkpoint PASS（非正式 Foundation experiment）
- 基线：`be52a60f6a06e80620869096700cd21ad453c657`
- 范围：仅记录 A/B 实现后的 interim checkpoint；不实现 C，不解除 P1A 门禁，不把 Foundation 标为 Verified。

## Scope and provenance boundary

本 Work Item 仅收集 §14.4 所需的自动门禁、三代 fast headless、Phase Resolution 隔离复算以及外部人工验收证据。原则上未修改功能代码；Phase Resolution 输出写入
`results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/`，不覆盖
`results/phase_bits/` legacy 输出。

该目录中的 CSV/PNG 明确是 **A/B checkpoint / non-formal provenance**。它由当前 v0.1
`phase_bits` runner 生成，仍是 Advanced、RIS-only Physics Focus、固定 seed 的兼容性复算；在 C2
provenance 完成前不得作为正式 Foundation experiment 发布。它不伪造
`channel_frequency_model_id`、Profile/reflection identity、quadrature/coefficient policy 或
`focus_mode` 等尚未完成的字段，也不将内部数值 reference 称为 Ground Truth/EM truth。

## §14.4 gate evidence

### Automatic and headless gates

| 门禁 | 命令/证据 | 结果 |
|---|---|---|
| 完整 pytest | `python -m pytest` | **PASS — 122 passed in 36.20s** |
| Current fast headless | `python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast` | **PASS**；focused `-46.5879005740 dBm`，RIS Gain `+8.6874352341 dB`，SNR `40.4120994260 dB`，coverage `77.1042%`，field `2.7234 s` |
| Advanced fast headless | 同上，`--generation Advanced` | **PASS**；focused `-30.1257141514 dBm`，RIS Gain `+25.1496216567 dB`，SNR `56.8742858486 dB`，coverage `78.5208%`，field `3.2077 s` |
| Future fast headless | 同上，`--generation Future` | **PASS**；focused `-19.3117697205 dBm`，RIS Gain `+35.9635660876 dB`，SNR `67.6882302795 dB`，coverage `82.5625%`，field `7.6656 s` |
| Phase Resolution isolation | `python -m airmirror_future.experiments.phase_bits --output results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903` | **PASS**；生成 `phase_bits.csv` 与 `phase_bits.png`，legacy 目录未覆盖 |
| `git diff --check` | checkpoint commit 前执行 | **PASS** |

### Manual and independent evidence

以下人工事实由用户提供的外部验收记录支持，**不是本次 Codex 自行完成的人工 GUI 验收**：

- B1/B2/B3 implementation independent review：通过；repository/code blockers：0；
- 真实 GUI 人工验收：通过，覆盖 Pending/Apply/Optimize、Pattern Source、Allowed/Used States、
  Geometry Position Error 与 Feedback Measurement Noise 标签；
- RIS Gain visualization blocker 已在基线 commit `be52a60f6a06e80620869096700cd21ad453c657`
  关闭，并完成独立远端审查。

维护者与物理审查者对 Focus objective、Commanded/Actual 边界和 GUI 表达的共同确认，依据上述
外部独立审查事实记录为 **PASS（external evidence）**。本文件不把这些事实改写为 Codex 亲自
执行的 GUI 操作。

## Remaining §14.4 / Foundation boundaries

本 checkpoint 通过不提升 Foundation 状态。Foundation 仍为 **In Progress**；C/Profile、C2
experiment provenance、FND-QA-AP、FND-PHY-NB、FND-QA-CC 及最终人工 verification 仍是后续门禁。
Phase Resolution checkpoint 结果不得用于正式 Foundation experiment 发布，P1A 仍被锁定。

未发现真实 blocker；本次没有修改 Python、GUI、物理模型、测试逻辑、Scene schema 或 legacy
results。未执行/未声明后续 C、QA、cache、P1 或新场景工作。

## Reproduction and files

- Phase Resolution output: `results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/phase_bits.csv`
- Plot: `results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/phase_bits.png`
- Directory note: `results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/README.md`
- Legacy output `results/phase_bits/` remains untouched.

## Checklist

- [x] 基线 branch/HEAD/working tree/remote main 核对
- [x] 完整 pytest
- [x] Current/Advanced/Future fast headless
- [x] 新隔离目录 Phase Resolution
- [x] checkpoint / non-formal provenance 标注
- [x] §14.4 外部人工验收证据与剩余门禁边界
- [x] `git diff --check`
- [x] focused checkpoint commit；未 push
