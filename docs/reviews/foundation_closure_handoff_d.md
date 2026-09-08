# Foundation closure handoff：D → owner/维护者

本交接记录与 PERF-PREP-01 benchmark 分离。D 不修改正式状态、不猜测 policy ID、不移除 pending，
也不承担后续 owner 的生产接线职责。

## FND-PHY-NB（交给 PHY-NB owner / maintainer）

### 技术证据（D 已独立复核）

- `fc` 改变会重算 wavelength/k，并改变 LOS、wall、RIS、total complex channel；
- 固定 commanded pattern 时，频率依赖仍来自生产传播路径，而不是 Focus 重生成；
- `B` 不改变 complex channel 或 received power，只改变 noise/SNR/capacity；
- provenance 使用 canonical `channel_frequency_model_id=narrowband_center_frequency_flat_v1`；
- Scene v1 round-trip 不新增未经版本化的 model-ID scene 字段；
- 与 C2/provenance/production quadrature 及 Focus/XR/GUI/documentation 的既有 focused evidence 均已记录
  为通过（历史证据详见 `docs/reviews/perf_prep_01_fnd_phy_nb_review.md`）。

### 正式 closure 的最小缺口

1. owner/维护者在 authoritative roadmap、Foundation plan、FND-PHY-NB Work Item 和状态记录中明确
   closure/Verified 决策；
2. 保留并引用实现提交 `62a1c7b511618d9febd29a24045b8b8cf998c6d3`、PR #19 merge
   `99cde97eefdecbcab41a68871663655c90dd1698` 及 follow-up tests `99fd49d`、`895bb13`；
3. 若 closure 依赖其他 pending contract，显式列出依赖，不由 D 代填或回填 legacy。

## QA-AP / C2 / production M8 identity（交给 QA-AP owner / maintainer）

### 已复核事实

- production quadrature 为 signed midpoint 8×8 per control patch；control count、pattern shape 与
  `parent_control_index = repeat(arange(control_count), 64)` 的 canonical mapping 保持一致；
- field-map 单次调用构造一份 M8 sample table 并复用；receiver×sample intermediate pair 受
  `_MAX_POINT_SAMPLE_PAIRS=262144` 有界约束；Current/Advanced/Future M8 channel 均有限；
- C2 结果保持 schema v1、no-overwrite/pending-owner 边界；不猜 legacy；
- 现有 focused/documentation evidence 已记录为 PASS（详见
  `docs/reviews/perf_prep_01_c2_m8_identity_review.md`）。

### 正式 closure 的最小缺口

1. QA-AP owner/维护者签署 production M8 的 canonical `quadrature_policy_id/version`；不得将
   `fnd_qa_ap_candidate/1` 复用为 production identity；
2. 将该签署值接入 C2/provenance/production identity 的唯一字段，并补充跨进程稳定性与 mutation 证据；
3. 保持 `coefficient_model_identity` 与 M8 policy identity 分层；QA-CC 未闭合前不得宣称 coefficient
   source/identity complete；
4. 修正文档中的旧状态冲突（`results/README.md` 仍写 QA-AP Planned/尚无正式结果），但不要在性能 PR
   中混改或覆盖历史结果。

## QA-CC / migration handoff（交给 C + maintainer）

- D 的正式决策见 `fnd_qa_cc_ready_review_d_decision.md`：当前 **HOLD**；1 项设计阻断是 RIS-only
  finite-bit singleton 与 ADR-0006/0011 公共 offset 契约的冲突。
- 外部依赖为 canonical M8 identity 与 PHY-NB closure；二者不是 D 可自行签署的事项。
- 维护者明确语义和 owner 签署后，C 再补 FND-T21/T22、identity mutation/no-leak、完整 migration
  evidence 与三代 headless；独立 reviewer 不得参与其核心 builder 实现后再审该部分。

## P1A gate

P1A 继续关闭。只有 QA-CC Ready PASS、NB/C2 identity/QA-AP/Foundation Final 正式闭合并经维护者
明确授权后，才可复用已验收 coefficient source 设计 A matrix/cache/增量 Greedy。
