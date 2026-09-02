# RIS 优化与反馈规格

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation 0.1.1A/A1 |
| 当前目标 | 单 RX 接收功率最大化 |

## 1. 隔离原则

优化器可读取 Scene 和 Controller Model，可调用 `MeasurementOracle.measure(patterns)`，但
不得读取 Ground Truth 的 phase errors、wall coefficients、position deltas 或 noise sigma。
绕过 oracle 会使反馈实验失去意义，属于 P0 研究有效性缺陷。

## 2. 目标与输入

v0.1 feedback optimizer objective 唯一合法值为 `received_power_dbm`。Coherent Target Focus
内部比较 `received_power_w`，以避免 dBm 数值下限影响；在正功率区两者排序等价。目标 RX 和
TX 默认为 Scene 首个。
优化器要求恰好一块 RIS；多 RIS 必须在新接口中明确 pattern ownership 和联合/顺序优化，
不能在现算法外层循环后声称协同。

共同输出是 `OptimizationResult`，iterations 表示 oracle measurement 次数而非 tile 数。

## 3. Model-based Focus algorithms

### 3.1 RIS-only Phase-Conjugate Focus

输入名义 TX/RX/RIS 几何，按 `phi=k(d1+d2)` 生成并量化。它不调用 oracle，复杂度
`O(N_cells)`，只最大化 RIS 自身合成幅度，不读取 direct/wall baseline 的相位。公开函数是
`generate_ris_only_focus_pattern()`；`generate_focus_pattern()` 作为兼容别名保持同一行为。

验收：简单前向场景中，目标幅度大于 100 个固定 seed 随机 patterns 的中位数至少 4 倍。
该阈值是 v0.1 回归门禁，不表示所有场景的理论界。

### 3.2 Coherent Target Focus

该算法是独立的 model-based strategy，不继承面向 MeasurementOracle 的反馈 Optimizer 接口。
它只读取公开 Scene 与 Controller Model，并以单个 TX–RX target 的 nominal
`received_power_w` 为 objective：

- continuous：解析计算一个公共 offset，使 aggregate RIS channel 与
  `h_LOS+h_wall` 同相；
- finite bit：公共 offset 在量化前加入；候选首项精确为 `delta=0`，其余候选覆盖所有
  quantizer transition 划分的不同区间；
- 按确定顺序评价候选，仅在严格改善超过浮点比较容差时更新，平局保留先出现的候选；
- baseline 或 RIS 分量近零时确定性回退 `delta=0`；
- 只支持单个 enabled RIS，显式拒绝 GroundTruthModel，不调用 MeasurementOracle。

continuous nominal、相位不改变幅度时，验收关系为
`|h_total|≈|h_baseline|+|h_RIS|`，且 target power 不低于 No RIS。finite-bit 只声明公共 offset
可达 pattern 族内最优并且不差于 unshifted；不得宣称任意逐 patch 组合或 Ground Truth 全局
最优。精确定义见 [ADR-0006](adr/0006-coherent-target-focus-objective.md)。

## 4. Algorithm B：Feedback Greedy

默认参数：tile 高 4 cells、宽 4 cells、1 pass。若没有 initial pattern，从全零相位开始。

对每个 tile：

1. 在 tile 开始前检查 cancel；
2. 保存原 tile；
3. 枚举所有相位候选；
4. 每个候选只通过 oracle 测量完整 pattern；
5. 仅当 measured objective 严格大于当前 best 时接受；
6. 无候选改善时恢复原 tile；
7. 写入一次 history 并报告进度。

候选数：量化 RIS 为 `2^bits`；continuous 为离散 8 个反馈候选。continuous 的反馈结果
因此是 8-state refinement，不是连续优化。

无取消时单 pass measurement 上界：

```text
1 + ceil(Ny/tile_h)*ceil(Nx/tile_w)*candidate_count
```

默认 Current 为 9，Advanced 为 289，Future 为 1537。取消粒度是 tile 边界，最坏还会
完成当前 tile 的候选测量。

## 5. Algorithm C：Physics-Guided Feedback

先根据 Controller Model 生成 v0.1 RIS-only Physics Focus，再把它作为 Greedy initial pattern。除初始化
外，后续流程和候选/取消规则完全相同。

研究预期而非无条件保证：模型误差小时 RIS-only Physics Focus 可能接近最佳；误差增大时物理先验
下降，Physics-Guided 以更少搜索恢复部分损失。必须通过 phase-error sweep 的统计结果
验证，不能用单个随机 seed 宣称算法优越。

## 6. Measurement Oracle

- 真值 channel 使用 GroundTruthModel；
- 返回 `true_received_power_dbm + N(0,sigma_measure²)`；
- noise RNG 由 `ground_truth.seed+7919` 初始化，调用顺序决定序列；
- 同一 oracle 的 measurement 计数单调增加；
- 复现实验必须固定 scene、seed、算法参数和候选顺序。

measurement noise 可能让贪心接受噪声峰值，这是预期误差机制。稳健重复测量、置信区间或
回退规则属于后续新算法，不能无记录地改变现算法语义。

## 7. 进度、取消和失败

progress callback 参数是 `(completed_tiles,total_tiles,current_best_dbm)`。cancelled result 保留
已接受 pattern、history 和 measurement 次数，但 GUI v0.1 不应用 cancelled result。非法
objective、RIS 数量或 pattern shape 抛 `ValueError`。

## 8. 后续多用户目标契约

Factory 前必须新增具名 objective：

```text
average_snr = mean_i(SNR_i)
min_user_snr = min_i(SNR_i)
```

结果必须记录每用户 SNR、aggregate objective、用户权重、RIS 集合和是否联合优化。
Privacy Mode 需要明确 target region 与 leakage region penalty，并声明不替代加密。
