# ADR-0006：RIS-only 与 Coherent Target Focus 目标契约

- 状态：Accepted
- 日期：2026-09-02
- 关联：AMF-RIS-004、AMF-RIS-008、Foundation 0.1.1A/A1

## 背景

v0.1 的 `generate_focus_pattern()` 只补偿 TX–patch–RX 传播相位，使各 RIS patch 在目标点
互相同相。它没有读取 `h_LOS+h_wall` 的复相位，因此不能保证 RIS 合成场与无 RIS 基线相长，
也不能把“目标点总接收功率最大化”作为自身语义。直接改变旧函数会破坏教学性质测试、历史
Phase Resolution 实验和现有调用方的可解释性。

Foundation A1 需要同时保留旧算法，并为 nominal 单目标总功率建立一个具名、可测试且不读取
Ground Truth 私有误差的新算法。

## 决定

### 1. 两个算法名称和所有权

- **RIS-only Phase-Conjugate Focus**：公开函数
  `generate_ris_only_focus_pattern()`；仅使用名义几何、频率和 RIS `phase_bits`。
- **Coherent Target Focus**：公开函数 `generate_coherent_target_pattern()`；属于 model-based
  optimization strategy，读取公开 `Scene` 和 `ControllerModel`，通过 `SimulationEngine`
  评价 nominal target received power。
- `generate_focus_pattern()` 在 Foundation A1 中保持 v0.1 RIS-only 语义，作为兼容别名；GUI、
  CLI、Physics-Guided Feedback 和旧实验的默认行为暂不改变。

`ris/phase.py` 只包含几何相位、量化和公共 offset 候选等纯 helper；策略和 objective 比较位于
`optimization/coherent_focus.py`。SimulationEngine 不硬编码任何 Focus 策略，`ris` 层也不
反向依赖 `simulation`。

### 2. 相位符号和连续相位规则

沿用项目约定：传播项为 `exp(-j*k*L)`，命令项为 `exp(+j*phi)`。第 n 个 patch 的 RIS-only
连续命令为：

```text
phi0_n = k*(d_TX,n+d_n,RX) mod 2*pi
```

定义：

```text
h_b   = h_LOS + sum(h_wall)
h_r0  = h_RIS(phi0)
delta = [arg(h_b)-arg(h_r0)] mod 2*pi
phi_n = [phi0_n+delta] mod 2*pi
```

在 continuous、单 RIS、Controller Model 且命令相位不改变反射幅度时，非退化链路满足：

```text
arg(h_RIS) = arg(h_b)  (mod 2*pi)
|h_total| = |h_b| + |h_RIS|
```

从而 nominal target power 不低于 No-RIS baseline。该结论不外推到有限 bit、Ground Truth
误差、幅相耦合、多 RIS 或其他 objective。

### 3. 退化分支

设 `s=max(|h_b|,|h_r0|,tiny)`，相对退化容差固定为 `64*machine_epsilon`。若
`|h_b|<=tolerance*s` 或 `|h_r0|<=tolerance*s`，公共 offset 确定性返回精确 `0.0`。这避免
对近零复数执行不稳定角度断言，并保留 RIS-only 命令。非有限复信道属于输入错误，抛
`ValueError`，不得静默替换为零。

### 4. 有限 bit 公共 offset 搜索

量化仍使用 v0.1 最近均匀状态量化器。若 `M=2^bits`、`Delta=2*pi/M`，当公共 offset 穿过
以下边界时，量化 pattern 才会改变：

```text
b_n,m = [(m+1/2)*Delta-phi0_n] mod 2*pi
```

候选集合由以下项组成：

1. 首项精确为 `delta=0`；
2. 所有唯一边界排序后，每个环形相邻边界开区间取一个中点。

因此每个由公共 offset 可达的 piecewise-constant 量化 pattern 至少被评价一次。目标为：

```text
P_nominal(delta) = Pt*|h_b+h_RIS(Q(phi0+delta))|^2
```

候选按确定顺序评价，只在功率严格超过数值比较容差时替换 incumbent；平局保留先出现的
pattern。因为 `delta=0` 是首个候选，新策略在同一 Controller Model objective 下不会差于
未偏置 RIS-only 候选。

这里的“最优”严格限定为**公共 offset 可达的量化 pattern 族内最优**，不是任意逐 patch
离散组合的全局最优，也不是 Ground Truth 最优。

### 5. 边界与错误

- A1 只支持一个被选中的 enabled RIS 和单 TX–RX target；零个/多个默认目标或未知/禁用 RIS
  抛 `ValueError`；
- 策略接受 `ControllerModel`，显式拒绝 `GroundTruthModel`；不调用 MeasurementOracle；
- 输入 phase array 必须是一维、非空且有限；公共 offset 必须有限；
- Scene schema、物理公式、GUI 默认算法和历史实验文件均不在 A1 中改变。

## 后果

- 旧回归与历史实验保持相同 phase-conjugate 语义；
- 新 API 可在 GUI 改动前通过 headless/测试独立验收；
- finite-bit 候选数上界与 `cell_count*2^bits` 同阶，A1 优先正确性和可审计性；GUI 接入前若
  需要更低时延，必须以等价候选或另行声明的候选最优策略优化；
- `ChannelResult` 已公开提供 LOS、wall 和 RIS 复分量，A1 无需增加专用 simulation 接口。

## 否决方案

- 静默把 `generate_focus_pattern()` 改成总信道目标：破坏兼容性和历史实验语义；
- 只做 `phi0` 后量化再旋转：有限 bit 命令通常不再属于硬件状态；
- 使用不含 `delta=0` 的固定角度网格：无法保证不差于旧候选；
- 从 Ground Truth 读取真实误差直接对齐：违反 ADR-0003，不能代表 nominal controller；
- 在 SimulationEngine 中加入 Focus 分支：把传播计算和优化策略耦合，形成错误依赖方向。

## 验证

- FND-T01：旧函数与显式 RIS-only 函数输出完全一致，既有 random median 性质继续通过；
- FND-T02/T02b：continuous nominal 场相位对齐并满足解析总幅关系；
- FND-T03：continuous nominal target 不低于 No RIS；
- FND-T04：finite-bit 候选首项为 `0.0`，输出不差于 unshifted；
- FND-T05：零/近零 baseline 或 RIS 分量确定性回退，无 NaN/Inf。
