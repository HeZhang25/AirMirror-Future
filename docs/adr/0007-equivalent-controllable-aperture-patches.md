# ADR-0007：RIS 等效可控孔径 Patch 语义

- 状态：Accepted
- 日期：2026-09-02
- 关联：AMF-RIS-001、AMF-RIS-005、AMF-RIS-009、Foundation 0.1.1A/A2
- 后续决策：[ADR-0008](0008-minimum-aperture-quadrature-validity-gate.md) 在不重开 A2 的前提下，
  将最小独立 quadrature validity 提升为 Foundation final exit/P1A 前置门禁

## 背景

v0.1 的 `RISSurface.nx/ny` 同时决定两件事：每个位置可以拥有独立 commanded phase，以及
有限孔径散射积分使用多少个中心采样点。如果继续把这些位置简称为“cell”，新开发者容易把它们
误解为真实 meta-atom，并进一步错误推导 `lambda/2` 阵元间距、互耦、栅瓣或制造可行性。

当前面积归一化公式能保护固定孔径不随网格数量产生无界增益，但因为细分同时增加控制自由度和
求积点，它不能证明 control grid、quadrature grid 或真实器件布局已经收敛。Foundation A2
需要冻结系统级语义，并提供不会改变实体几何的派生诊断。

## 决定

### 1. `nx/ny` 的唯一规范含义

`nx/ny` 表示 **System-level equivalent controllable aperture patches（系统级等效可控孔径
patch）** 的两个局部网格维度：

- `nx` 沿 RIS 实体 `width_m` 方向；
- `ny` 沿 RIS 实体 `height_m` 方向；
- 每个 patch 拥有一个 commanded phase；
- 每个 patch 的等效面积为 `width_m*height_m/(nx*ny)`；
- 当前散射模型以 patch 中心近似该面积的贡献，并按满填充孔径处理。

这些 patch 不是经过器件建模或校准的真实 meta-atoms。当前没有 physical element layout、
fill factor、patch 内积分、互耦、材料色散、极化或器件频率响应。

### 2. 实体孔径和运行频率的所有权

`RISSurface.width_m/height_m` 是实体孔径尺寸的唯一事实源。Scene 的 operating
`frequency_hz` 只决定传播波长和诊断比例：

```text
pitch_x = width_m/nx
pitch_y = height_m/ny
lambda  = c/frequency_hz
r_x     = pitch_x/lambda
r_y     = pitch_y/lambda
```

改变 `nx/ny` 只改变等效 pitch、patch 面积、控制自由度和当前中心点求积离散；改变 operating
frequency 只改变 `lambda` 与比值。两者都不得自动修改 `width_m/height_m`。

`design_frequency_hz` 继续 Deferred，Scene schema v1 不增加字段。只有引入 RIS 硬件带宽、
`Gamma_n(f)`、`eta(f)` 或 beam-squint 模型时，才重新评审它属于 RIS hardware model 还是
scene。

### 3. 公共诊断 API

新增纯函数：

```text
equivalent_patch_diagnostics(ris, frequency_hz)
    -> EquivalentPatchDiagnostics
```

返回实体宽高/面积、patch 数量、effective pitch、运行频率/波长和两个 `pitch/lambda` 比值。
它不修改 RIS 或 Scene，不参与传播，不改变 pattern，也不产生 pass/fail、warning severity 或
经验增益。

数值字段全部使用 SI；频率必须 finite 且大于零，否则沿用 `wavelength_m()` 的 `ValueError`
契约。RIS 自身尺寸和网格合法性继续由 `RISSurface` 构造校验负责。

### 4. Advisory 边界

`pitch/lambda` 只用于模型透明度。特别是 `pitch/lambda > 0.5` 不构成当前系统级模型错误，
因为 patch 不是物理天线阵元，当前模型也没有真实 element factor、互耦或周期阵列栅瓣模型。
A2 不设置 `lambda/2`、`45 degree`、`0.2 dB` 等无来源硬阈值。

A2 选择**只公开 pitch/波长诊断，不公开 phase-span 数值**。可靠的 patch 内相位跨度还需要
明确 TX/RX、入射/出射角色、角点或求积采样规则、遮挡边缘处理及验证阈值；在 control grid 与
quadrature grid 尚未拆分时给出单一数值容易被误解为物理有效性证明。若后续增加 phase-span，
它仍只能是 advisory，并必须由新的测试和文档说明采样定义。

### 5. 未来拆网格触发条件

以下任一目标进入实现前，必须在 P1C 或新的 ADR 中拆分当前合并语义：

- 声称 patch 内数值积分收敛或给出通用误差阈值；
- 研究真实 meta-atom 尺寸、间距、fill factor、互耦或制造约束；
- 研究由物理周期阵列产生的栅瓣、材料频响或 beam squint；
- 用高保真/实测数据校准近场、斜入射或遮挡边缘误差。

目标结构至少区分 control grid、integration/quadrature grid 和 physical meta-atom layout。
真正的求积验证必须固定实体孔径、control grid 和 commanded pattern，只细化 quadrature grid，
并比较复数 `h_RIS` 误差和功率差。

## 后果

- 当前 `cell_count`、`cell_area_m2` 和 `cell_centers()` 的数值行为保持不变；旧 JSON、GUI、
  headless 和实验不发生数值迁移；
- 文档和新 API 使用 equivalent patch 术语；旧代码标识符中的 `cell` 暂保留兼容，不表示
  physical meta-atom；
- 下游 GUI 可无歧义展示 effective pitch 和 `pitch/lambda`，但 A2 不提前实现 B 阶段 GUI
  状态机或 Pattern metadata；
- 固定孔径 8/16/32 测试仍是面积归一化/不发散证据，不升级成严格 quadrature convergence。

## 否决方案

- 将 `nx/ny` 定义为真实 meta-atom 数量：当前模型没有支持该结论的器件物理；
- 强制 `pitch=lambda/2` 并由频率重算孔径：会破坏实体尺寸事实源和跨频率场景可比性；
- 看到 `pitch/lambda>0.5` 就拒绝计算：把系统级求积 patch 错当物理阵元；
- 在 Scene v1 增加 `design_frequency_hz`：没有频率相关 RIS hardware model，字段缺少行为；
- 在 A2 同时拆分 quadrature grid：属于 P1C 数值有效性工作，超出 Foundation semantic contract。

## 验证

- FND-T09：改变 `nx/ny` 只改变派生 pitch/patch 数，不改变实体宽高；改变 operating frequency
  只改变波长和比值，不改变孔径；
- 非法 frequency 抛 `ValueError`，诊断输出均为有限正值；
- 既有固定孔径细分、孔径增大、JSON round-trip 和三代 headless 回归继续通过；
- 文档人工检查确认 UI/报告术语不把 equivalent patch 宣称为真实 meta-atom，也不声称完成
  独立 quadrature convergence。
