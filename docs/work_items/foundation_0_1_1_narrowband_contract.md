# Work Item：Foundation / Narrowband Frequency Contract

- 层级：L4 Task（cross-cutting physics/provenance closure）
- Task ID：FND-PHY-NB
- Requirement IDs：AMF-PHY-007
- 状态：Verified（2026-09-08；PR #19 implementation、FND-T20 与独立复核通过）
- 父项：Foundation 0.1.1 Final Exit Gate
- 依赖：ADR-0010 Accepted；C2 minimum experiment provenance
- 不属于：OFDM、frequency-selective channel、delay spread、beam squint、材料色散

## 目标与用户结果

把当前“只在一个频点求 h、带宽只进入噪声和 Shannon 公式”的实际行为变成精确、可追踪、
不误导的窄带合同。完成后，新开发者和结果使用者能够判断 `fc`、`B` 分别改变什么，并能从
结果元数据确认它不是宽带/OFDM 仿真。

## In / Out

包含：

- 以 ADR-0010 冻结 `frequency_hz=fc`、`bandwidth_hz=B` 和 flat-channel 假设；
- 在 Model Info、GUI/CLI/实验字段中使用准确的容量标签；
- 记录 `channel_frequency_model_id=narrowband_center_frequency_flat_v1`；
- 验证 `fc`/`B` 的依赖与未来 cache invalidation 分类；
- legacy 结果缺失 model ID 时只标记 legacy。

不包含：

- 对频带采样、子载波循环、冲激响应或 OFDM sum-rate；
- 自动估计 coherence bandwidth 或通过单一阈值拒绝场景；
- `Gamma_n(f)`、频变 wall coefficient、beam squint 或新 Scene 字段；
- 改变 v0.1 `ChannelResult.shannon_capacity_bps` 字段名。

## 接口与数据

- Scene v1 字段不变；`frequency_hz` 与 `bandwidth_hz` 继续要求 finite、`>0`；
- `Transmitter.power_w` 明确为 B 内总发射功率，不新增 PSD/子载波 power-allocation 字段；
- `ChannelResult.shannon_capacity_bps` 数值公式不变，文档/API/GUI 名称变得更精确；
- Foundation experiment provenance 增加 `channel_frequency_model_id`；
- headless 输出是否新增该字段由 C2 schema 一次决定，不在多个入口各自发明；
- 若未来新增 cache，`fc` 属 coefficient/propagation identity，`B/NF` 只属于 link-metric identity。

## 物理/算法约束

```text
lambda = c/fc
h(f) ~= h(fc) over B
N = k_B*T_0*B*NF  (implemented in dBm form)
C_flat_upper = B*log2(1+SNR(fc))
```

不允许把 `C_flat_upper` 表述为真实吞吐量。任何频率选择性扩展必须保留旧 ID 以解释历史结果，
并用新 ADR 定义频率网格、路径 delay、RIS 频响和容量聚合。

## Tasks

| Task | 状态 | 预计 | 输出 |
|---|---|---:|---|
| `FND-PHY-NB-01` 对齐 data/API/GUI/CLI/experiment 标签 | Verified | 0.5–1 天 | 无歧义文案与字段定义 |
| `FND-PHY-NB-02` 接入稳定 model ID 与 legacy 规则 | Verified | 0.5–1 天 | C2 provenance 字段 |
| `FND-PHY-NB-03` 增加 fc/B 属性与序列化回归 | Verified | 0.5–1 天 | FND-T20 |
| `FND-PHY-NB-04` 人工复核并记录适用域 | Verified | 0.5 天 | closure record |

## Verification and authoritative closure

2026-09-08 维护者依据 PR #19 merge `99cde97eefdecbcab41a68871663655c90dd1698`、
implementation `62a1c7b511618d9febd29a24045b8b8cf998c6d3`、follow-up tests `99fd49d`
与 `895bb13`，以及 D closure handoff `5e628696d677a858ef241dfe656a9c4e3a30bfe3`
和独立复核提交 `617cd602c5e7f791d0f8801145a29db471e727bb`，
将 FND-PHY-NB-01..04、FND-PHY-NB、AMF-PHY-007 和 FND-T20 签署为 **Verified**。

证据确认：改变 `fc` 会重算 `lambda/k` 并改变 LOS、wall、RIS 和 total complex channel；固定
commanded pattern 时该频率依赖仍来自 production propagation；仅改变 `B` 不改变上述复信道
或 received power，只按公式改变 noise、SNR 和 capacity；新 provenance 使用 canonical
`narrowband_center_frequency_flat_v1`；Scene v1 round-trip 不新增该 identity。已有 C2 完整
回归 `372 passed, 1 skipped`、Current/Advanced/Future fast headless、documentation/diff-check
证据保持有效；D 在 PR #19 精确基线上复核的 narrowband/C2/M8 focused suite 为 34 tests，扩大
至 Focus/XR/GUI/documentation 为 100 tests，均 PASS。

该 closure 只移除新 C2 provenance 的 `FND-PHY-NB` pending owner。FND-QA-CC 继续 pending，
`coefficient_model_identity` 继续为空；历史结果不回填，Foundation overall 保持 In Progress，
P1A gate 保持 closed。

## 验收证据

- FND-T20a：改变 `fc` 后 `lambda/k` 与传播复信道重新计算；
- FND-T20b：固定 scene/geometry/pattern/fc，仅改变 `B` 时四个复信道分量不变，noise/SNR/capacity
  按公式变化；
- FND-T20c：provenance 的 model ID 稳定，legacy 缺失值不会被伪造；
- Model Info/GUI/CLI/实验人工检查不出现“真实吞吐”“OFDM 容量”或“宽带信道”误称；
- 完整 pytest、三代 headless 和文档链接检查通过。

## 风险与回退

| 风险 | 检测 | 安全回退 |
|---|---|---|
| 文案变了但结果无 model ID | provenance schema test | 不签署 FND-PHY-NB |
| 新 ID 被误写入 Scene v1 | round-trip diff | 撤回 Scene 字段，保留运行元数据 |
| 将 `B` 错加进 coefficient key | identity review | 分离 propagation 与 metric identity |
| scope 漂移到 OFDM | Work Item diff review | 拒绝新增频率轴，建立后续 capability |

## 文档影响

- [x] ADR-0010、requirements、Foundation plan、physics/data/API、GUI、experiments、limitations；
- [x] architecture/cache identity、test strategy、DoD、roadmap、status；
- [x] code/tests：PR #19 与 FND-T20 已实现并通过独立复核；
- [ ] scene/results/cache：本工作项不修改。
