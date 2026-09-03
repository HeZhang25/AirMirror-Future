# AirMirror Future Development Status

| 属性 | 值 |
|---|---|
| 状态快照 | 2026-09-03 |
| 当前 release | v0.1 |
| release 状态 | Verified |
| 规范基线 | [docs/README.md](docs/README.md) |
| 当前 Capability | Foundation 0.1.1A Physics and Algorithm Contract（In Progress） |

## Foundation physics/algorithm master-plan integration

2026-09-03 完成一次纯 Markdown 的 Foundation 方案整合。本轮只把已评审的物理/架构结论纳入
正式事实源，没有修改 Python、tests、GUI、scene、results、cache、production quadrature behavior
或任何 Focus 实现：

- 接受 [ADR-0012](docs/adr/0012-wall-reflection-coefficient-ownership.md)，完整取代存在所有权
  冲突的 ADR-0009：Foundation `PropagationProfile` 冻结为不含 `Gamma_wall` 的
  environment-only complex modifier，由 engine 构造注入；Wall/Reflection Model 唯一拥有墙面
  复反射系数，反射前后两段 Profile modifier 分开应用，并排除反射墙自身；不修改 Scene JSON
  v1，未来多路径 `PathEnsemble` 保持独立；
- 当前 v0.1 `single_wall_reflection` 已实际按 carrier、有效墙系数、before/after 阻挡分别相乘，
  因此本次是目标架构/验收契约纠偏，不是 production 数值修复；C1 新增 FND-T13c/T13d，分别
  锁定因子只应用一次和反射墙自身排除；
- 接受 [ADR-0010](docs/adr/0010-narrowband-center-frequency-flat-channel.md)：明确
  `frequency_hz=fc`、`h(fc)` 在 `bandwidth_hz=B` 内按平坦信道处理，容量只是 flat-channel
  Shannon upper bound；
- 接受 [ADR-0011](docs/adr/0011-controller-coefficient-focus-consistency.md)：最终 production
  policy 下，RIS-only/Coherent Focus 与 Controller simulator 必须使用同一 control-level
  coefficient；Ground Truth coefficient 不得泄漏；
- 新增 Planned requirements `AMF-SIM-006`、`AMF-PHY-007`、`AMF-RIS-012`，以及 Planned
  Work Items [FND-FIX-WALL](docs/work_items/foundation_0_1_1_wall_geometry_closure.md)、
  [FND-PHY-NB](docs/work_items/foundation_0_1_1_narrowband_contract.md)、
  [FND-QA-CC](docs/work_items/foundation_0_1_1_coefficient_consistency.md)；
- 正式顺序补充为 A3 → FND-FIX-WALL → B → A/B checkpoint → C → FND-QA-AP → 必要时独立
  production migration → FND-PHY-NB → FND-QA-CC → Foundation final verification → P1A；
- 当前 Wall z/三维误差冲突、当前 `h(fc)` flat assumption、以及未来 quadrature/Profile 下的
  coefficient/Focus 分叉风险均被明确记录，但没有被误标为已修复。

本轮文档门禁：`tests/test_documentation.py` 9 项全部通过；完整 pytest 74 项全部通过；
`git diff --check` 通过。`FND-DOC-01` 可记为 Implemented（ADR/规范治理输出已落盘），但这不
等价于其约束的任何 Planned 代码能力已实现。

状态保持：A1 Verified；A2 Verified；Foundation 0.1.1A、AMF-RIS-008、AMF-RIS-009 和
Foundation 0.1.1 保持 In Progress；AMF-RIS-011/012、AMF-PHY-007、AMF-SIM-006 及四个
cross-cutting Work Items 保持 Planned。本轮不构成任何能力的 Implemented/Verified 证据。

## Foundation aperture quadrature governance update

2026-09-02 完成新的物理/架构评审并接受
[ADR-0008](docs/adr/0008-minimum-aperture-quadrature-validity-gate.md)。本轮是纯文档治理更新，
没有修改 `.py`、测试、GUI、场景、缓存或 production 数值：

- A2 semantic contract 保持 Verified；aperture discretization accuracy 明确为 Not Verified；
- 新增 Planned requirement `AMF-RIS-011` 和 cross-cutting L4 task
  [FND-QA-AP](docs/work_items/foundation_0_1_1_qa_ap.md)；
- `FND-QA-01` 继续表示 Foundation final full regression，不复用；
- `AMF-RIS-005` 校准为面积归一化/control-grid 细分不产生无界增益和稳定趋势，不再被简称为
  独立 quadrature convergence；
- 正式顺序调整为 A3 → B → A/B checkpoint → C → FND-QA-AP → Foundation final verification
  → P1A → P1C extended research；
- 当前 production 仍为每 control patch `1×1` midpoint。一次隔离审计观察到 default target 上
  `1×1` 相对内部 16×16 细化参考约 Current `+0.848 dB`、Advanced `+0.430 dB`、Future
  `+0.639 dB`；该结果尚非版本化 runner/正式验收证据，也不是 EM truth；
- FND-QA-AP 将固定 aperture/control/pattern/Profile，只细化 quadrature，使用 successive
  refinement、独立求积规则和预注册容差冻结 P1A coefficient policy；partial-aperture blockage
  明确留给独立空间分辨模型。

状态保持：A1 Verified；A2 Verified；Foundation 0.1.1A、AMF-RIS-009 和 Foundation 0.1.1
保持 In Progress；AMF-RIS-011 与 FND-QA-AP 保持 Planned。没有任何状态因本次规划自动提升。

## Foundation 0.1.1A / A2 最终验收快照

Deliverable A2（RIS aperture patch semantic contract）已完成最终人工验收并达到
**Verified**：

- 验收依据：implementation commit `974885fc5b1864ecd9c303e56400308cbaa316fa`；
- Gate 结果：G0–G8 全部 PASS；
- blocking issues：0；
- 状态边界：A1 保持 Verified；Foundation 0.1.1A、AMF-RIS-009 和 Foundation 0.1.1 仍为
  In Progress。

- `nx/ny` 已冻结为 system-level equivalent controllable aperture patches，不表示真实
  meta-atoms；实体 `width_m/height_m` 仍是孔径尺寸的唯一事实源；
- 新增只读 `EquivalentPatchDiagnostics` 与 `equivalent_patch_diagnostics()`，派生 effective
  pitch、运行波长和 `pitch/wavelength`，不修改 Scene/RIS、不参与传播；
- 改变 operating frequency 只改变波长和比例，不自动缩放实体孔径；
- ratio 仅作透明度信息，不实现 `lambda/2` pass/fail；A2 明确不输出未验证的 phase-span；
- `RISSurface` 现在拒绝非有限孔径尺寸、bool/小数/非正 patch count；
- ADR-0007 冻结未来拆分 control/quadrature/physical layout 的触发条件；GUI 只读接入留在
  B 阶段，因此 `AMF-RIS-009` 仍为 In Progress。

本机 Windows / Python 3.14.3 实现门禁：

| 门禁 | 结果 |
|---|---|
| A2 + RIS 定向 pytest | `19 passed` |
| 完整 pytest | `74 passed in 2.18s` |
| Current v0.1 fast headless | `-46.5879 dBm`，RIS Gain `+8.6874 dB`，场图 `2.845 s` |
| Advanced v0.1 fast headless | `-30.1257 dBm`，RIS Gain `+25.1496 dB`，场图 `3.401 s` |
| Future v0.1 fast headless | `-19.3118 dBm`，RIS Gain `+35.9636 dB`，场图 `8.553 s` |

三代目标数值与 A1 基线一致；它们是 current scalar center-point model 的兼容回归，显示到四位
小数不代表具有相同物理精度。运行时间波动不构成数值变化。A2 没有修改散射核心算法、GUI、
A3、PropagationProfile、缓存或实验逻辑。状态边界保持：A1 Verified；A2 Verified；
Foundation 0.1.1A、AMF-RIS-009 和 Foundation 0.1.1 均为 In Progress。

## Foundation 0.1.1A / A1 最终验收快照

Deliverable A1（Focus objective）已完成最终人工验收并达到 **Verified**：

- 验收依据：closure commit `87495ec91a490d5cd5331ad9c4a0a2e863c10b40`；
- Gate 结果：G0–G8 全部 PASS；
- blocking issues：0；
- 状态边界：Foundation 0.1.1A、AMF-RIS-008 和 Foundation 0.1.1 仍为 In Progress。

- 新增显式 `RIS-only Phase-Conjugate Focus`，兼容函数 `generate_focus_pattern()` 输出不变；
- 新增 `Coherent Target Focus`，continuous 使用 nominal baseline 解析相位对齐，finite-bit
  枚举公共 offset 可达的量化 pattern 并以 nominal target power 选择；
- `delta=0` 是 finite-bit 首个候选，平局稳定保留旧命令；零/近零分量确定性回退；
- 新策略只接受 Controller Model，拒绝 Ground Truth，不改变 GUI、CLI 和历史实验默认语义；
- 规范由 [ADR-0006](docs/adr/0006-coherent-target-focus-objective.md) 冻结，工作范围与证据见
  [A1 Work Item](docs/work_items/foundation_0_1_1_a1.md)。

验收环境为 Windows、Python 3.14.3；本机结果：

| 门禁 | 结果 |
|---|---|
| A1 定向 pytest | `30 passed`（verification closure 全绿） |
| 完整 pytest | `61 passed`（closure 自动回归全绿；待最终差异审查） |
| Current v0.1 fast headless | `-46.5879 dBm`，RIS Gain `+8.6874 dB`，场图 `1.248 s` |
| Advanced v0.1 fast headless | `-30.1257 dBm`，RIS Gain `+25.1496 dB`，场图 `1.545 s` |
| Future v0.1 fast headless | `-19.3118 dBm`，RIS Gain `+35.9636 dB`，场图 `6.628 s` |
| A1 Coherent 单目标 | Current 123 candidates / `0.083 s`；Advanced 4609 / `3.571 s`；Future continuous / `0.003 s` |

headless 仍故意运行 v0.1 RIS-only 默认算法，因此上述三代值是兼容回归，不是 Coherent
Target 新默认。A2 已 Verified，A3 commanded pattern hardware boundary 尚未实现，
因此 Foundation 0.1.1A 仍不能标为 Implemented/Verified。

## 已完成（v0.1）

- Python 可编辑安装、模块入口和离线 headless 命令；
- SI 数据模型、参数校验、场景 JSON 保存/加载；
- 复数 Friis LOS、阻挡衰减、一次墙面反射、噪声、SNR、Shannon 上界；
- 有限孔径 RIS、前向方向图、相位量化、Physics Focus；
- Current / Advanced / Future 代表性参数；
- Smart Space 目标链路、热力图、RIS Gain、Coverage、Dead Zone；
- Controller Model、Ground Truth、测量 oracle；
- tile-based Feedback Greedy 和 Physics-Guided Feedback；
- 中文 PySide6 GUI、拖动交互、参数面板、相位图、后台计算、取消和版本控制；
- Phase Resolution headless 实验；
- 物理、序列化、集成、优化和 GUI 烟雾测试。
- 产品基线、术语、需求追踪、架构、数据/API/Schema、GUI、优化、实验、测试、DoD、
  roadmap、ADR 和贡献流程文档；
- 文档结构、链接、需求编号和 Implemented 证据自动校验。

## 已知问题

- GUI、CLI、Physics-Guided 和 legacy experiment 当前仍使用 RIS-only Physics Focus；A1 的
  Coherent Target Focus 已有 headless Python API，但默认接入属于后续 B 阶段；
- `nx/ny` 的 equivalent patch 语义已冻结，但仍同时承担控制与中心点求积；GUI 尚未接入
  A2 只读 pitch/波长诊断；最小独立求积有效性进入 Foundation final exit 前的 FND-QA-AP，
  P1C 保留完整 aperture/field-map/适用域研究；
- Phase Bits 尚未在传播入口验证 commanded hardware states；
- continuous hardware 与反馈优化的 8-state search 尚未在接口/UI 中拆分；
- GUI Generation 立即应用、普通参数等待 Apply，但没有 pending/customized 状态提示；
- 所有场景仍共用固定传播编排，尚无 PropagationProfile identity；
- Profile/Reflection 的 target ownership 已由 ADR-0012 冻结，但 C1 尚未实现；
- `frequency_hz/bandwidth_hz` 的 flat-channel 语义已由 ADR-0010 冻结，但 model ID、标签和
  provenance closure 尚未实现；
- 墙 endpoint z 当前未可靠进入求交，Ground Truth wall delta 却是三维；FND-FIX-WALL 尚未实现；
- FND-QA-AP 后仍须 FND-QA-CC 证明最终 Controller coefficient 与两种 Focus 一致；
- 高质量 `200×160` 场图在 Future 64×48 网格下计算较慢，但运行于后台且可取消；
- 当前场图采用逐评价点计算，尚未建立跨点 RIS 系数矩阵缓存；
- 墙面反射是二维平面几何加三维路径高度检查，不是完整材料/极化模型；
- 反馈算法是 v0.1 教学型 tile coordinate descent，尚未实现增量复场更新。

## 尚未实现

- XR、Factory、City 场景；
- 多 RIS 联合优化和 max-min 用户目标；
- 衍射、双 RIS 连续反射、宽带、active/STAR/space-time RIS；
- Aperture、Phase Error、RIS Count、Dynamic User 四组批量实验。

## 下一阶段

1. 按 [Foundation 0.1.1 计划](docs/foundation_0_1_1_plan.md) 完成 A3 commanded pattern
   hardware boundary，再完成 FND-FIX-WALL；
2. 完成 optimizer/GUI 语义和 A/B checkpoint；
3. 建立 environment-only PropagationProfile 与最小实验 provenance；
4. 执行 FND-QA-AP，冻结 production quadrature policy；若要求改变 production，先走独立迁移；
5. 完成 FND-PHY-NB 和 FND-QA-CC，冻结 frequency/coefficient/cache identity；
6. Foundation final verification 通过后再进入 P1A 几何系数缓存与矩阵求值；
7. 随后完成相位误差和 P1C 扩展孔径研究，再扩展 XR/Factory/City。

阶段顺序、entry/exit gate 和工作颗粒度以 [docs/roadmap.md](docs/roadmap.md) 为准。本页只
记录状态，不新增需求或改变优先级。
