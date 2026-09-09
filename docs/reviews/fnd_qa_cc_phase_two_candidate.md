# FND-QA-CC 阶段二生产候选证据

- Ready contract：`86fb9ceaad07a03a653b2b8016f8af75b35805f7`
- Independent Ready evidence：`73fc59fa37ccc0668d3da9db2c46bae482b41d92`，READY PASS，blocking 0
- Integrated main：`a7271648d3d6d98d6af953eadcc4784b7776222f`
- Production implementation：`11f65a3b0762d738c8880901e00244ace3dd2a88`
- Follow-up regression alignment：`18aa2e1d5c6252cc5bb0c75ee0b4bd63af41bd89`
- 状态：production candidate；等待非作者 D 独立代码/证据复核与维护者 closure

## 实现边界

- `physics.ris_scattering` 提供唯一 M8 control-level coefficient reduction；engine 与 QA-AP evaluator
  复用同一底层公式；面积、gain、direction 与 Profile modifier 各应用一次；RIS efficiency/phase
  仍由 Gamma 层拥有。
- engine 提供 Controller-only focus terms；拒绝 GroundTruthModel。
- legacy RIS-only public API 与 Scene v1 不变；新增 scene-aware RIS-only 使用 ADR-0013 方案 A 的
  `P_RIS` common-offset objective；Coherent 使用同一 `a^C` 与 baseline total-power objective。
- coefficient identity 使用 tagged float64 canonical JSON + SHA-256；排除 commanded state、phase bits、
  efficiency、Pt、B/NF、coverage 与 RNG。provenance 写入 identity，但在正式 closure 前仍保持
  `partial` 和 `FND-QA-CC` pending。
- 未实现 cache、A matrix、chunking、incremental Greedy 或 P1A。

## 实际测试证据

Focused suite（11 个测试文件）：`219 passed`。

完整回归第一次：`514 passed, 1 skipped, 1 failed`。唯一失败为 PR #22 XR Route 测试仍期待已由
PR #23 closure 移除的 `FND-PHY-NB` pending；修正该过期断言后重新执行：

```text
515 passed, 1 skipped in 102.29s
```

Documentation/provenance/coefficient focused check：`38 passed`。`git diff --check` 通过。

三代 Fast headless 均 PASS：

| Generation | focused dBm | RIS gain dB | coverage | field runtime |
|---|---:|---:|---:|---:|
| Current | -47.7341042832 | 7.5412315249 | 71.8958% | 9.4181 s |
| Advanced | -30.5748654813 | 24.7004703268 | 77.9167% | 43.0612 s |
| Future | -19.9539049589 | 35.3214308492 | 81.6667% | 239.1110 s |

## XR / 历史结果影响

Coherent commanded patterns may change because the production path now uses M8-derived `a^C` instead of
the legacy center-path seed. Existing XR Adaptive/Route CSV, pattern hashes, fields and screenshots remain
historical/provisional and are not overwritten or relabelled. Any formal regeneration must use a new unique
output directory and record the new coefficient identity and implementation SHA.

## Closure boundary

本文件不自行宣布 FND-QA-CC/Foundation Verified。仍需非作者 D 对精确候选 SHA、T21/T22 oracle、
identity mutation/no-leak、三代结果和完整回归做独立复核；维护者决定 PR merge 与正式 closure。

## 独立复核差异修正（candidate follow-up）

- custom `PropagationProfile` 的 identity 现在保留实际两段 modifier，并纳入完整 canonical
  environment collection（包括 room bounds、evaluation height、Scene schema 与实体几何），因此
  未声明 dependency projection 的 Profile 不会因场景 mutation 发生 identity collision。
- XR Dynamic/Route 的 run-level provenance 不再把 initial receiver 的单一 transfer identity
  冒充整条 trajectory；No-RIS 行为空值，含 RIS 行按该行实际 receiver position 重新计算
  `controller_ris_coefficient_identity`。command hash 仍独立记录 `Gamma_cmd`。
- QA-AP raw rows 记录每个 generation/geometry/evaluation receiver 的 canonical coefficient identity；
  run-level provenance 保持 partial/pending，不再写固定 candidate 字符串。
- T21/T22 focused matrix 覆盖 Current/Advanced/Future × default/near-field/oblique/off-focus，
  并保留 zero/nonfinite、candidate ordering/strict-better/first-wins、legacy API 与 custom-profile
  mutation tests。测试证据仅表示已执行的 focused checks；正式 closure 仍需 D 核对原始输出与
  operation-count-aware oracle。
