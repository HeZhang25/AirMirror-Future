# ADR-0009：Foundation PropagationProfile 使用环境修正因子

- 状态：Accepted
- 日期：2026-09-03
- Supersedes：无；关闭 Foundation 计划中的 Profile path-response 未决项
- 关联需求：AMF-SIM-005
- 关联工作项：[Foundation 0.1.1C / C1](../foundation_0_1_1_plan.md#73-foundation-011c--propagationprofile-boundary)

## 背景

v0.1 的 `SimulationEngine` 直接编排自由空间载波、几何阻挡、一次墙面反射和 RIS 双基地散射。
后续室内、城市、隧道、工厂、空地和 UAV 场景需要不同环境模型；若场景模块复制公式，模型
会漂移，未来缓存也无法判断两个结果是否使用同一传播假设。

Foundation 只需要建立一个能复现 v0.1 的最小边界。此时若让 Profile 返回完整复传播响应，
它会与 Friis/RIS kernel 已包含的距离扩散和 `exp(-jkd)` 重复；若立即抽象为任意多径集合，
又会把尚未实现的 fading、delay、Doppler 和 wideband 路径状态提前塞进 v0.1 接口。

## 决定

### 1. Foundation Profile 的语义

Foundation 的 `PropagationProfile` 是 **environment-only complex modifier**。几何载波仍由
physics 层负责，Profile 只返回无量纲复修正：

```text
h_path = h_geometric_carrier * m_environment
```

`m_environment` 可以表达本 Profile 所有的阻挡幅度、墙面复反射系数或后续经 ADR 允许的环境
修正，但不得再次包含：

- `1/d` 或 `1/(d1*d2)` 距离扩散；
- `exp(-j*k*L)` 传播相位；
- TX/RX antenna gain；
- RIS 孔径面积、方向图、效率、commanded/actual phase；
- 接收机噪声、Ground Truth 隐藏误差或 GUI 状态。

### 2. Path role 与 v0.1 映射

最小接口使用有限、稳定的 path role/context，不建立插件注册中心：

| Path role | geometric carrier | environment modifier 的职责 |
|---|---|---|
| `direct` | `h_FS(d_TX_RX)` | 当前墙/障碍物 LOS 衰减 |
| `wall_reflection` | `h_FS(L_reflection)` | 墙复系数与两段其他阻挡衰减 |
| `ris_incident` | RIS kernel 的 TX→sample leg | 当前 TX→RIS center 标量阻挡修正 |
| `ris_scattered` | RIS kernel 的 sample→RX leg | 当前 RIS center→RX 标量阻挡修正 |

Foundation 初次接入必须保持 RIS center scalar blockage 和一次反射路径集合不变。Profile 不能
借重构之名加入逐 patch 遮挡、高阶反射、fading 或新路径。

### 3. 所有权与注入

- `Scenario/Scene` 保存几何和环境参数，不保存 Python 类名；
- Foundation 不改变 Scene JSON v1，也不新增 profile 字段；
- Profile 是一次仿真运行的不可变配置，由 `SimulationEngine` 构造时显式注入；未提供时使用
  `IndoorDeterministicProfile`；
- `ControllerModel/GroundTruthModel` 只描述 nominal-vs-truth 误差，不选择环境传播律；
- RIS model 只负责器件/孔径响应，不拥有 Profile；
- experiments/GUI 可以选择已注册的产品内 Profile ID，但不能动态导入任意类名。

计划中的构造形式为：

```text
SimulationEngine(profile=IndoorDeterministicProfile(...))
```

具体 Python Protocol 名称与只读 context 数据类可在 C1 Work Item 中微调，但不得改变上述
所有权和乘法语义。

### 4. 稳定身份

Profile 必须提供稳定、可序列化的：

```text
profile_id
profile_version
canonical_parameters
profile_identity = hash(profile_id, profile_version, canonical_parameters)
```

canonical parameters 必须包含所有会改变 `m_environment` 的值，排序和浮点编码规则在 C1 冻结。
对象地址、Python `hash()`、显示名称或类名不能作为身份。该身份进入 Foundation experiment
provenance，并作为未来 coefficient/cache identity 的一层；身份契约的存在不表示缓存已实现。

### 5. 未来 PathEnsemble 是独立抽象

能够产生多条带 delay/angle/Doppler/statistics 的路径集合不属于 Foundation Profile v1。
需要 frequency-selective、Rayleigh/Rician、clustered channel 或动态多径时，应新增
`PathEnsemble`（名称可由后续 ADR 决定）和对应 requirement，而不是让一个复数 modifier
偷偷变成任意路径生成器。届时由新 ADR 决定它如何与 Profile v1 兼容或替代。

## 后果

- C1 可以在不改变 v0.1 数值的前提下抽出环境职责，并为不同未来场景留下稳定选择点；
- 避免 Profile 与 Friis/RIS kernel 双重计算距离损耗和传播相位；
- Scene v1 保持兼容，但一个 Scene 文件本身仍不足以唯一重放结果，实验必须另存 Profile 身份；
- future fading/wideband 不能通过添加几个 multiplier 参数冒充完整模型；
- Profile 初次接入仍保留当前 RIS center blockage 近似，其物理限制不会因架构抽象消失。

## 候选与否决理由

- **Profile 返回完整复传播响应**：否决。与现有 carrier 的所有权重叠，最容易重复距离/相位。
- **Profile 直接返回任意路径集合**：Foundation 否决。接口颗粒度超过当前确定性窄带范围。
- **把 Profile 写入 Scene v1**：本阶段否决。需要 schema 迁移且不能仅靠字符串保证可运行实现。
- **每个场景复制一套 engine**：否决。会破坏物理、测试和缓存身份的一致性。
- **Profile 与 Ground Truth 合并**：否决。会让优化器环境选择和隐藏误差边界混乱。

## 验证

- FND-T13：默认 Profile 的 LOS、每条墙反射和 RIS 分量复数值复现 v0.1 reference；
- FND-T13b：四种 path role 都经过 Profile，且 carrier 不重复距离/相位；
- FND-T14：ID、version 或任一 canonical parameter 改变时 identity 改变；相同输入跨进程稳定；
- C1 人工架构复核确认 Scene、Profile、Ground Truth、RIS 与 noise 的职责没有重叠；
- C2 provenance 必须能区分 legacy 无 Profile 身份结果和 Foundation 新结果。
