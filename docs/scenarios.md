# 场景规格与演进边界

| 属性 | 值 |
|---|---|
| 文档状态 | Smart Space Normative；其余 Planned |
| 基线版本 | v0.1 + Foundation scenario/channel separation plan |

## 1. Future Smart Space — Verified

### 研究问题

在室内墙体阻挡和一次反射存在时，有限孔径、有限相位精度的 RIS 能否把目标 RX 从弱区
提升，并随目标移动重构空间分布？器件代际参数如何影响目标 gain 和 coverage？

### 场景基线

详细默认值以 [project_baseline.md](project_baseline.md#6-默认-smart-space-基线) 和
`scenes/smart_room.json` 为准。可运行比较：No RIS、Current/Advanced/Future RIS-only Physics Focus、
Feedback Greedy、Physics-Guided Feedback。

### 输出

- target received power、SNR、Shannon upper bound；
- target RIS Gain；
- power/SNR/RIS Gain FieldMap；
- Coverage/Dead Zone（默认 SNR 35 dB）；
- commanded/actual phase；
- optimization measurements/runtime。

FieldMap/Coverage 使用同一 fixed commanded RIS pattern 扫描所有评价点，不表示每个像素各自
重新聚焦的最优场。当前 channel 是中心频率 `h(fc)` 的平坦窄带近似；Shannon 指标不是 OFDM
或真实吞吐。

### 不在 v0.1

Work/XR/IoT/Privacy objective presets、轨迹动画、多目标 coverage 优化。增加这些模式前先
分别定义 objective；不能用不同标签调用同一 target Focus。

## 1.1 Foundation 场景与信道分层（Planned）

所有场景必须遵循：

```text
Scenario/Scene geometry and parameters
  -> Physics Kernel geometric carriers / propagation phase
  -> Reflection Model geometry and Gamma_wall
  -> PropagationProfile direct/per-leg environment modifiers
  -> RIS device and commanded/actual state
  -> coherent received channel and link metrics
```

ADR-0012 只为 Foundation 默认室内确定性模型建立不含 `Gamma_wall` 的 environment-only Profile；
墙系数由 Wall/Reflection Model 唯一拥有。该决定不表示 XR、
Factory、City、Tunnel 或 UAV channel 已实现。未来场景必须分别定义有来源的 path loss、
LOS/NLOS、fading/dynamics 和有效域；需要多路径 delay/angle/Doppler 时建立独立 PathEnsemble，
不能把所有场景简单映射到一个 1/d² multiplier。

## 2. XR / Spatial Computing — Planned v0.2

### 研究问题

28/60 GHz 下，人体和头部姿态变化造成的动态遮挡能否由有限 update rate 的 adaptive RIS
缓解？Physics prior、feedback latency 和 outage 之间有什么关系？

### 最小可运行切片

- 一个 AP、一个 headset、一个人体吸收体、一块 RIS；
- `position(t)`、head yaw(t)、固定 time step；
- No RIS、Static RIS、Adaptive Physics Focus；
- 每步 target channel，heatmap 每 N 步；
- `outage = SNR<threshold`，输出 SNR(t) 和 outage probability。

### Definition of Ready

轨迹 JSON v2、动态状态所有权、body 几何/衰减、update-rate scheduling、deterministic clock、
取消和回放测试全部先定义。Prediction control 是后续 Deliverable，不进入第一切片。

## 3. Future Smart Factory — Planned v0.3

### 研究问题

复杂工业遮挡下，多块 RIS 是否能改善 worst-user reliability，而不只提高平均值？

### 最小可运行切片

- 20×12 m、一个 AP、3 个 RX/AGV、2 块 RIS、矩形金属设备；
- 所有 RIS 的 `TX→RIS→RX` 单跳复场同时叠加；
- No/Single/Multi RIS；
- objective：average SNR 和 min-user SNR；
- 输出每用户 SNR、average、minimum、coverage reliability、runtime。

### 延后项

`TX→RIS1→RIS2→RX` 双反射不是第一切片。若实现必须显式建附加距离、两次效率、方向图和
复杂度；测试应显示更多反射不保证更优。

## 4. Future City / Low-Altitude Network — Planned v0.4

### 研究问题

建筑立面成为 programmable electromagnetic facade 时，能否沿 vehicle/UAV 轨迹减少连续
覆盖断点，形成模型定义的 Electromagnetic Corridor？

### 最小可运行切片

- 俯视街区、矩形 buildings、一个 BS、一个移动终端、2–4 facade RIS；
- 建筑 NLoS、所有立面 RIS 单跳贡献、离散 trajectory；
- No/Single/Multi/Cooperative 对照；
- corridor 定义为轨迹上连续 `SNR≥threshold` 的距离/时间比例与最长中断段；
- 输出 coverage corridor、outage segments、target SNR(t)、runtime。

### 风险

无衍射时街角 NLoS 可能过深；City release 前必须决定实现 knife-edge、使用受控额外衰减，
或明确只做模型内对比。不能用手绘 corridor 弥补。

## 5. Emergency / Disaster Response — Proposed

Portable/UAV RIS 用于临时补盲。它依赖动态轨迹、UAV 位置、功率/载荷约束和可能的 airborne
RIS 朝向，因此至少在 XR 动态引擎与 City 基础之后评估。

## 场景新增规则

每个场景必须先有研究问题、控制变量、模型边界、headless demo、metrics、JSON、性质测试、
performance budget 和 limitation，再进入 GUI。共享能力进入核心层，场景模块只组装数据，
不得复制传播公式。
