# 路线图、阶段门禁与工作颗粒度

| 属性 | 值 |
|---|---|
| 文档状态 | Operational / Normative for sequencing |
| 当前 release | v0.1 Verified，Foundation 0.1.1 In Progress |

## 1. 统一规划层级

| 层级 | 大小 | 示例 | 状态汇报方式 |
|---|---|---|---|
| L0 Vision | 多 release | Programmable Electromagnetic Space | 不报告百分比 |
| L1 Release | 多个 capability | v0.2 Dynamic XR | 以 capability gate 汇总 |
| L2 Capability | 完整用户/研究能力 | Phase Error Robustness | Proposed→Verified |
| L3 Deliverable | 可独立验收纵向结果 | 三算法共享 seed 的 CSV | 入口/输出/验收 |
| L4 Task | 0.5–2 天工程工作 | 实现 phase sigma sweep CLI | done/not done |

状态页同一列表只能放同一层级。禁止把“实现一个函数”和“完成 Future City”放成并列步骤；
禁止用文件数或代码行数表示 capability 完成度。

## 2. 依赖路线

```text
v0.1 Smart Space (Verified)
  -> Foundation 0.1.1 model contract
       -> 0.1.1A physics and algorithm contract
       -> FND-FIX-WALL floor-anchored wall closure
       -> 0.1.1B optimizer and GUI semantics
       -> A/B interim human checkpoint (not Foundation Verified)
       -> 0.1.1C propagation profile boundary
       -> FND-QA-AP minimum aperture quadrature validity
       -> conditional production migration (only if required)
       -> FND-PHY-NB narrowband frequency contract
       -> FND-QA-CC controller coefficient consistency
       -> Foundation final verification
  -> P1A geometry coefficient cache
  -> P1B phase-error statistical experiment
       -> v0.2 XR dynamic engine
            -> v0.3 Factory multi-user/multi-RIS
                 -> v0.4 City geometry and corridor
  -> P1C extended aperture/quadrature research
```

后续场景不能越过依赖门禁。尤其 Factory 的多 RIS 和 City 的立面网络依赖统一的多 RIS
pattern ownership；不能各自实现不兼容版本。

## 3. v0.1 Smart Space — Verified

已交付 capabilities：

- C01 Core SI Geometry and Scene v1；
- C02 Complex LOS/Blockage/One-bounce Wall；
- C03 Finite Passive RIS and Physics Focus；
- C04 Smart Space Headless + FieldMap；
- C05 Interactive GUI and Background Workers；
- C06 Controller/Ground Truth + Feedback；
- C07 Phase Resolution Experiment；
- C08 Documentation and Traceability Baseline。

已知技术债不回写为“未完成 v0.1”：矩阵缓存未启用、反馈非增量、高质量 Future 较慢、
id 错误异常待统一。这些进入 P1 tasks。

## 4. Foundation 0.1.1：物理模型契约

状态：In Progress；A1/A2/A3、FND-FIX-WALL Verified；B1/B2/B3 Implemented（待独立审查）；C、
FND-QA-AP、FND-PHY-NB 与 FND-QA-CC 尚未完成。详细背景、范围、
Requirement IDs、L3/L4 工作项、测试、兼容策略和 Exit Gate 见
[foundation_0_1_1_plan.md](foundation_0_1_1_plan.md)。

本 Capability 必须在 P1A 前完成，包含：

1. 区分 RIS-only Focus 与 total-channel Coherent Target Focus；
2. 冻结 equivalent controllable aperture patch 语义；
3. 建立 Commanded Pattern hardware-state validation；
4. 分离 hardware phase resolution 与 optimizer search levels；
5. 建立 GUI pending/apply/preset/customized 和准确 Ground Truth 标签；
6. 建立不含 `Gamma_wall` 的最小 PropagationProfile 与默认 IndoorDeterministicProfile；墙面复反射
   系数保持由 Wall/Reflection Model 唯一拥有；
7. 版本化实验 provenance，不覆盖 v0.1 历史结果。
8. 在 final exit 前完成最小 aperture quadrature validity，冻结 P1A 将缓存的 control-level
   coefficient policy；A2 语义验收与求积精度验收分层。
9. 关闭 floor-anchored Wall/XY-only Ground Truth 几何歧义；
10. 冻结 `h(fc)` 在 B 内平坦的 narrowband/capacity/provenance 语义；
11. 验证 RIS-only/Coherent Focus 与最终 Controller `a_n^C` 一致，Ground Truth 不泄漏。

B-stage implementation handoff 见 [combined B Work Item](work_items/foundation_0_1_1_b.md)。
本次只同步到 implementation-level，不执行 A/B Interim Checkpoint，不提升 Foundation 或 B
deliverables 为 Verified。

Exit gate：三个子 Capability 全部达到各自门禁，默认 Profile 可解释地复现 v0.1 reference，
FND-T13c/T13d 证明墙系数与反射两段 modifier 各只应用一次并排除反射墙自身；
FND-QA-AP 的代表性矩阵和 FND-T16..18 通过，production quadrature policy 已签署；FND-T19..22
关闭 Wall、narrowband 和 coefficient/Focus 一致性；目标算法变化有 ADR/测试/实验版本记录，
P1A cache identity 所需契约冻结。任一 cross-cutting gate 不通过时
Foundation 保持 In Progress，不能以“P1A 只改性能”为理由绕过。

A/B 完成后必须先执行维护者与物理审查者共同参与的 interim checkpoint。该检查点允许评审
Focus、Pattern 和 GUI，但不代表 Foundation Verified；0.1.1C、最小 experiment provenance、
FND-QA-AP、已 Verified 的 FND-FIX-WALL、FND-PHY-NB 和 FND-QA-CC 均是 P1A 前置
条件。FND-QA-AP 不重开 A2，也不
取消 P1C；它只回答 P1A 将缓存的 `a_n` 怎样计算才满足当前声明精度。

## 5. P1：性能与模型误差研究

### Capability P1A — Geometry Cache and Matrix Evaluation

Entry gate：Foundation 0.1.1 Verified；frequency model、Profile、Wall geometry、RIS geometry、
pattern validation、实验版本、`quadrature_policy_id/version` 与 coefficient identity 已冻结；
不存在未解释的 FND-QA-AP/FND-QA-CC blocking case。

Deliverables：

1. 规范 geometry/cache key 和 invalidation；
2. 按已签署 quadrature policy 与 ADR-0011 coefficient contract 预计算 control-level `a_n` 和
   多点分块 A；不得把未经 QA 的
   center-point 系数硬编码为永恒定义；
3. pattern 更新只执行 `A @ Gamma`；
4. Greedy 单 tile 使用复场增量；
5. Current/Advanced/Future 性能、内存和数值等价基准。

Exit gate：与 v0.1 scalar/reference 结果在声明容差内一致；全部失效测试通过；同机 Fast
基准显著改善或给出为何不采用的 ADR。

### Capability P1B — Phase Error Robustness

Deliverables：多 seed runner、Physics/Feedback/Physics-Guided 公平对照、median/quantile CSV、
PNG、运行配置元数据、研究结论和限制。

Exit gate：三算法共享每个 seed 的 truth；结果可完全重放；不以单 seed 下结论。

### Capability P1C — Extended Aperture Sweep and Quadrature Research

Deliverables：在 FND-QA-AP 已冻结最小 production policy 后，定义固定 equivalent-patch
density/固定 control-patch count 两类孔径实验；扩大 aperture、control/quadrature order、
field-map、phase-span、frequency/angle/near-field sensitivity 和异常趋势研究。报告复数
`h_RIS`、功率差、target gain、coverage、成本和适用域。`pitch/wavelength` 与 patch 相位跨度
只作 advisory；遮挡边缘只有在 spatially resolved blockage model 就绪后才能进入该矩阵。

P1C 的 refined scalar result 仍不是 full-wave/measurement truth。P1C 可以促成后续 policy
修订，但不能回填或伪造 FND-QA-AP 的历史验收结果。

## 6. v0.2：XR / Spatial Computing

Entry gate：P1A Verified；动态状态和轨迹 schema ADR 完成。

Deliverables：人体吸收体、`position(t)`/head orientation、28/60 GHz preset、No/Static/Adaptive
RIS、SNR(t)、outage probability、更新率和 heatmap cadence、headless dynamic experiment、GUI
Play/Pause。

Exit gate：转身遮挡造成模型产生的链路下降；adaptive 依据明确更新策略重构；outage 定义和
轨迹可重放；GUI 不逐帧强制高分辨率场图。

## 7. v0.3：Future Smart Factory

Entry gate：多 RX API、objective ADR、多 RIS pattern ownership 完成。

Deliverables：20×12 m、金属遮挡、3 AGV、2–3 RIS、所有 RIS 单跳复场、average/min-user
SNR、No/Single/Multi/Cooperative 对照、RIS Count 实验。

双 RIS 连跳不是 release 必需项；若加入，需单独建模额外传播、效率和计算复杂度。

## 8. v0.4：Future City / Low-Altitude Network

Entry gate：Factory 多 RIS Verified；城市几何性能预算完成。

Deliverables：建筑、BS、vehicle/UAV、facade RIS、轨迹、NLoS、No/Single/Multi/Cooperative、
coverage corridor 指标与动态场图。Electromagnetic Corridor 必须由路径模型和阈值连续性
定义，不能手绘。

## 9. Future Extensions — Proposed

宽带、STAR、active、space-time、communication+sensing、localization、WPT、physical-layer
security 和应急 RIS 均为 Proposed。每项独立 ADR 和物理模型；不共享一个“Future mode”
开关绕过建模。

## 10. 每轮开发计划模板

每轮最多选择一个 L2 Capability，拆成 3–7 个 L3 Deliverables；每个 Deliverable 再拆
0.5–2 天 L4 Tasks。计划必须列 requirement IDs、输入/输出、测试、依赖、风险和 exit gate。
模板见 [templates/work_item.md](templates/work_item.md)。
