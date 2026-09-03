# ADR-0012：墙面复反射系数与环境修正因子分离

- 状态：Accepted
- 日期：2026-09-03
- Supersedes：[ADR-0009](0009-environment-modifier-propagation-profile.md)
- 关联需求：AMF-PHY-004、AMF-SIM-005
- 关联工作项：[Foundation 0.1.1C / C1](../foundation_0_1_1_plan.md#73-foundation-011c--propagationprofile-boundary)

## 背景

ADR-0009 正确选择了 environment-only `PropagationProfile`，但又错误地允许
`m_environment` 包含墙面复反射系数，并在 `wall_reflection` path role 中把墙系数与反射前后
两段的其他阻挡合并。与此同时，权威物理规格已经定义：Wall 保存名义反射幅值/相位，
Reflection Model 计算镜像反射几何并应用 `Gamma_wall`，Controller/Ground Truth Model 提供
对应世界模型中的有效墙系数。

这形成了双重所有权。如果 C1 按旧文字实现，`Gamma_wall` 可能被 Reflection Model 和 Profile
重复相乘，也可能被迁入 Profile 后丢失 Wall/Ground Truth、identity 和实验 provenance 的清晰
边界。该问题在 Profile 尚未接入 production 前被发现；当前 v0.1 数值实现已经把墙系数和两段
阻挡分别相乘，本 ADR 只纠正规范，不授权改变现有数值行为。

## 决定

### 1. 墙反射的唯一因子分解

Foundation 的一次墙面反射必须遵循：

```text
h_wall = h_FS(L_reflection)
         * Gamma_wall
         * m_before_env
         * m_after_env

Gamma_wall = rho * exp(j*phi_wall), 0 <= rho <= 1
```

- `h_FS(L_reflection)` 由 Physics Kernel 拥有，包含总反射路径长度的自由空间幅度、天线 gain
  和 `exp(-j*k*L_reflection)` 传播相位；
- 反射点、有效有限墙面和 `L_reflection` 由 Reflection Model 拥有；
- `Gamma_wall` 由 Wall/Reflection Model 域拥有，在所选 Controller 或 Ground Truth world model
  下恰好应用一次；
- `m_before_env`、`m_after_env` 是 `PropagationProfile` 对 TX→反射点和反射点→RX 两段返回的
  无量纲 environment-only complex modifier；
- 反射墙自身必须通过稳定 wall ID 从两段 blocker 查询中排除，避免把同一墙同时当作镜面反射体
  和穿墙衰减体。

Foundation v1 的默认 Profile 使用既有两段其他墙/障碍物阻挡幅度。它不得在 modifier 中再次
放入 `Gamma_wall`、整段 Friis carrier、反射传播相位或天线 gain。未来若增加粗糙度、角度相关
Fresnel/极化或频变材料响应，应通过独立 Reflection Model requirement/ADR 定义其属于
`Gamma_wall` 还是新的具名反射因子，不能匿名塞入 Profile。

### 2. Foundation Profile 的保留语义

`PropagationProfile` 仍是 environment-only complex modifier，不是完整传递函数或路径生成器：

```text
h_direct = h_FS(d_TX_RX) * m_direct_env

h_wall = h_FS(L_reflection) * Gamma_wall
         * m_before_env * m_after_env

h_RIS = sum_n K_geom,n * m_incident_env,n * m_scattered_env,n
                  * Gamma_RIS,n
```

Profile 不得拥有或重复：

- `1/d`、`1/(d1*d2)` 距离扩散和载波传播相位；
- 墙面复反射系数 `Gamma_wall`；
- TX/RX antenna gain；
- RIS 孔径面积、方向图、效率、commanded/actual phase；
- 接收机噪声、measurement noise 或 GUI 状态。

Foundation 初次接入保持现有确定性路径集合、一次反射和 RIS center scalar blockage。Profile
不得借重构增加逐 patch 遮挡、高阶反射、fading、delay、angle 或 Doppler。未来多径集合继续由
独立 `PathEnsemble` capability/ADR 管理。

### 3. 数据和世界模型所有权

- `Scene/Wall` 保存名义 `reflection_magnitude` 与 `reflection_phase_rad`；
- Reflection Model 根据 Wall、反射几何及所选 world model 获得该次计算唯一的有效
  `Gamma_wall`；
- `ControllerModel` 使用名义墙系数；`GroundTruthModel` 可对同一墙系数施加已定义且可复现的
  幅相误差，但误差仍由 Reflection Model 消费，不转移给 Profile；
- Profile 选择环境修正规则，不选择 Controller/Ground Truth realization；
- RIS Model 继续独立拥有其器件与孔径响应。

这一区分是职责所有权，不要求 C1 把 Profile、Reflection Model 或 world model 合成一个对象。

### 4. Path role 与注入

C1 必须让 Profile 参与 `direct`、反射前段、反射后段、`ris_incident` 和 `ris_scattered` 环境
修正。具体 Protocol/context 名称可在 C1 Ready review 冻结，但 `wall_reflection` 不能再返回
包含 `Gamma_wall` 的聚合 multiplier。反射上下文至少要能稳定标识反射墙，以执行自身排除规则。

Profile 仍由 `SimulationEngine` 构造时显式注入，缺省为不可变
`IndoorDeterministicProfile`。Foundation 不修改 Scene JSON v1，不持久化 Python 类名，也不建立
动态插件注册中心。

### 5. 身份、provenance 与未来缓存

Profile 提供稳定、可序列化的：

```text
profile_identity = hash(profile_id, profile_version, canonical_profile_parameters)
```

其中只包含会改变 environment modifier 的 Profile 规则和参数，不包含场景中每面墙的
`Gamma_wall`。总体 coefficient/world-model identity 必须另行包含：

- Reflection Model ID/version；
- 墙几何和名义反射幅相参数；
- Controller/Ground Truth 下实际参与计算的有效墙状态或其稳定 realization identity；
- Profile、frequency、quadrature 和其他既有 coefficient 依赖。

因此“墙系数不属于 profile identity”不等于“墙系数可从总 identity 省略”。本 ADR 只冻结身份
分层，不实现 cache。

## 后果

- 墙反射 carrier、墙面材料/系统级反射响应和其他环境衰减各有唯一所有者；
- 默认 Profile 可以等价复现 v0.1，而不会重复应用墙系数；
- Ground Truth 墙面幅相误差仍可复现，并且不会泄漏到 nominal Profile/Focus；
- C1 context 和测试需要分别观察 `Gamma_wall` 与反射两段 modifier，不能只比较一个不可解释的
  聚合系数；
- ADR-0009 的其余设计由本 ADR 原样保留，但 ADR-0009 作为整体标为 Superseded，避免新人需要
  判断哪一句仍有效。

## 候选与否决理由

- **Profile 同时拥有 `Gamma_wall` 与两段 modifier**：否决。与 Wall/Reflection Model 和
  Ground Truth 墙误差重复所有权。
- **Reflection Model 吞并所有环境阻挡**：否决。会使 direct/RIS/reflection 三类路径无法共享
  场景环境规则，也阻碍未来不同 Profile。
- **把 `Gamma_wall` 视为任意 blocker attenuation**：否决。它带有反射路径特有的复幅相响应，
  不能与穿透/遮挡衰减混为同一物理事件。
- **只修改文字，不增加防重复验证**：否决。所有权错误可能在数值回归中被相反的重复/遗漏偶然
  抵消，必须分别扰动各因子。

## 验证

- FND-T13：默认 Profile 的 direct、每条 wall 和 RIS 分量复现 v0.1 reference；
- FND-T13b：所有环境 path roles 均经过 Profile，且 Profile 输出不包含 carrier 或
  `Gamma_wall`；
- FND-T13c：固定几何/Profile，单独把 `Gamma_wall` 幅值乘 `s` 时 wall-channel 幅度只乘 `s`；
  固定 `Gamma_wall`，单独改变任一 leg modifier 时只产生对应一次缩放；
- FND-T13d：反射墙从 before/after blocker 集合排除，其他阻挡仍分别作用于对应路径段；
- FND-T14：Profile identity 只随 Profile ID/version/canonical parameters 改变；墙系数变化不冒充
  Profile identity 变化，但必须改变总体 coefficient/world-model identity；
- Controller/Ground Truth 边界测试确认墙面幅相误差通过有效 `Gamma_wall` 生效，Profile 选择和
  nominal Focus 不读取隐藏 realization；
- C1 完整 pytest、三代 headless 和人工因子所有权复核通过后才能提升状态。
