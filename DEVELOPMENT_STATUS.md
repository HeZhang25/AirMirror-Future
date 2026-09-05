# AirMirror Future Development Status

| 属性 | 值 |
|---|---|
| 状态快照 | 2026-09-05 |
| 当前 release | v0.1 |
| release 状态 | Verified |
| 规范基线 | [docs/README.md](docs/README.md) |
| 当前 Capability | Foundation 0.1.1C overall In Progress：C1 Verified，C2 Verified；Foundation overall In Progress；P1A gate closed |

## Foundation 0.1.1C / C2 implementation

2026-09-04：D-owned C2 integration wiring 已完成，`AMF-EXP-006` 与 C2 子任务
`FND-EXP-01A..01C` 状态为 **Implemented**。Phase Resolution runner 现在先独占创建
`results/foundation_0_1_1/phase_bits/<run_id>/`（或显式完整 output directory），再使用实际
Advanced scene、显式 `ControllerModel` 和同一 world 完成 baseline/focused channel 与 field map
计算，调用 A-owned provenance builder 写入 schema v1 CSV，并生成同目录 PNG；最后由 C-owned
只读 classifier 验证 `foundation_partial`。pending owners 保留 `FND-PHY-NB`、`FND-QA-AP`、
`FND-QA-CC`，未签署 identity 保持空，legacy/checkpoint 结果未修改。

证据：D-owned integration tests 5 passed；完整 `python -m pytest` 372 passed, 1 skipped；
Current/Advanced/Future fast headless 通过；真实 C2 Foundation run 的 CSV/PNG、run_id、
provenance schema/status/pending 与最终 classification 已人工检查。该段记录 C2 implementation
阶段；当前状态见下方 verification closure。Foundation overall 保持 In Progress，P1A gate 保持关闭。

## Foundation 0.1.1C / C2 verification and status closure

2026-09-05：基于 `integration/c2` HEAD
`a5c434dd3d673069ea93c689e6435002aef4e83d` 的 C2 independent review 结论为 **PASS**，
blocking issues 为 **0**。复核证据包括完整 `python -m pytest`（372 passed, 1 skipped）、
Current/Advanced/Future fast headless、真实 C2 Phase Resolution Foundation run，以及
`git diff --check`；CSV/PNG、schema v1 partial provenance、pending owners、最终
`foundation_partial` classification 和 legacy/checkpoint unchanged 均已确认。

C2 与 `AMF-EXP-006` 由 **Implemented** 提升为 **Verified**。C1 保持 Verified；C overall 与
Foundation overall 保持 In Progress；P1A gate 保持 closed；`FND-QA-AP`、`FND-PHY-NB`、
`FND-QA-CC` 继续 pending。该 closure 仅更新文档/状态，不修改 Python、tests、results、
物理模型、schema 或 public API。

## Foundation 0.1.1C / C1 verification closure

以独立远端 Ready PASS 基线 `9fad9b05273fd0d15569d8307e50321d40d05c4a` 实现
`FND-ARCH-01A..01E`：`simulation.profiles`、不可变默认 Profile、tagged canonical identity、
carrier-only reflection helper、engine 五类 role 接入与 duplicate wall-ID preflight。
根据维护者提供的三轮外部独立审查最终结论，`AMF-SIM-005`、C1 / `FND-ARCH-01A..01E`
由 Implemented 提升为 **Verified**：C1 review PASS、blocking issues 0。C 整体与 Foundation 保持
**In Progress**，`AMF-EXP-006` / C2 已为 **Verified**，P1A gate closed；FND-QA-AP / FND-PHY-NB /
FND-QA-CC 状态不变。审查 SHA 与逐轮结论见
[C1 verification evidence](docs/work_items/foundation_0_1_1_c.md#c1-verification-and-status-closure)。

默认分量与路径集合通过 `d9ab04a` 的 8 组 nominal/GT 固定 reference；三代 fast headless 的
功率、RIS Gain、SNR 和 coverage 与改动前一致。完整命令、FND-T13..T14 与数值见
[C Work Item 的 C1 implementation evidence](docs/work_items/foundation_0_1_1_c.md#c1-implementation-evidence)。
没有修改 GUI、版本化 Scene、results、Focus/scattering 公式或实验 runner；未实现 C2、最终
coefficient builder、QA-AP/PHY-NB/QA-CC、cache 或新路径。

迁移说明：Scene 构造/加载及 engine preflight 现在拒绝重复 wall ID，错误包含该 ID；
对 `a641b0d` 的独立审查后，focused compatibility closure 还在 Wall/Obstacle 构造/loader 及
Scene/engine preflight 拒绝空或非字符串 ID。受支持 Scene、内建场景、tests 与可达 Git 历史无
合法空 ID 依赖；外部空/歧义 ID 输入须显式赋名，不过滤 blocker 或放宽 Profile 契约。证据见
[C1 environment-ID closure](docs/work_items/foundation_0_1_1_c.md#c1-environment-id-compatibility-closure)。
内部聚合 `single_wall_reflection` 已由 carrier-only helper 取代，
完整反射贡献由 engine 唯一编排。Scene schema version、公共 channel/map 签名和默认数值不变。

第二轮对 `3081c6a` 的独立审查后，同源 closure 补齐 `RISSurface.id` 的 non-empty string
构造/loader 与 engine preflight 校验，拒绝旧 truthiness 曾放行的非字符串及事后 mutation。
外部非法 RIS ID 须显式赋名并更新 pattern key；不新增 TX/RX、RIS/global uniqueness 校验。
第三轮对 `9c9499e` 的外部独立最终审查 PASS，已关闭全部 C1 blockers。本轮仅做 Markdown/status
closure，不修改实现或启动 C2；前轮实现、兼容修复和回归数字保留为历史证据。

## Foundation 0.1.1C Definition of Ready（历史记录）

2026-09-03 已建立 focused
[Foundation 0.1.1C Work Item](docs/work_items/foundation_0_1_1_c.md)，并完成 C1 PropagationProfile
与 C2 Minimum Experiment Provenance 的 Ready Review：**Ready / blocking ambiguity 0**。

本轮在基线 `d9ab04a502055af3b519a781629e6e83f0ded9d8` 上只修改 Markdown，冻结：

- 五个 path roles、只读 context、Profile finite/exception contract、默认不可变确定性 Profile 和
  tagged-canonical-JSON/SHA-256 跨进程 identity；
- direct、reflection before/after、RIS incident/scattered 的统一接入，以及 carrier-only reflection
  path、有效 `Gamma_wall`、两段 modifier 的唯一应用点；
- reflecting wall 只按唯一 wall ID 自排除；duplicate wall ID 在 Profile/reflection 求值前明确失败；
- Controller/Ground Truth 先建立显式 working geometry，Profile 不接收 model/seed/error callback，
  不读取或选择隐藏 realization；不实现最终 coefficient builder；
- 最小 `finite_wall_single_bounce_image/1` reflection model 契约，不建立插件系统；
- `airmirror_experiment_provenance/1`、partial/complete 与 pending-contract 规则、只读 legacy 分类和
  exclusive no-overwrite run directory；FND-PHY-NB/FND-QA-AP/FND-QA-CC 未签署的 identity 不得
  伪造为 Verified/default provenance；
- `FND-T15` 及 legacy/pending/no-overwrite 子项已补入 test strategy traceability。

`AMF-SIM-005`、`AMF-EXP-006` 和 C1/C2 仅由 Planned 提升为 **Ready**；该段为历史记录，没有 Python/tests/results/
GUI/Scene 变化，也没有功能状态提升。Foundation overall 保持 **In Progress**，P1A gate 保持关闭。
本轮未发现需要新 ADR 的高影响歧义；ADR-0011/0012 的所有权决定不变。

## Foundation 0.1.1B verification/status closure

2026-09-03 已完成 Foundation 0.1.1B verification/status closure。B implementation 及补充测试/可视化
修复 commits `c08c8bd81972119abf88bbee279cc29a7a45d820`、`7c4a33bb2a108cfff798045b53016999e13abc1c`
和 `be52a60f6a06e80620869096700cd21ad453c657` 的独立审查为 **PASS，blocking issues = 0**；真实 GUI
人工验收和 RIS Gain visualization review 亦为 PASS。

| 状态项 | before → after | 依据 |
|---|---|---|
| `AMF-RIS-008` | Implemented → Verified | A1 Focus evidence + B GUI default/alternate Focus smoke；真实 GUI 与 external independent review PASS |
| `AMF-RIS-009` | Implemented → Verified | A2 semantic evidence + B equivalent-patch pitch/λ read-only 接线；真实 GUI 与 external independent review PASS |
| `AMF-OPT-004` | Implemented → Verified | B1 search-level/hardware-state/reproducibility tests；§14.3 hardware/search gate；independent review PASS |
| `AMF-UI-007` | Implemented → Verified | B2 Pending/Apply/Optimize、preset confirm/cancel、Customized tests；真实 GUI 清单 PASS |
| `AMF-UI-008` | Implemented → Verified | B3 Pattern metadata/states/error/legend 与 RIS Gain visualization tests；真实 GUI 清单 PASS |
| Foundation 0.1.1B Work Item | Implemented → Verified | §14.3 Exit Gate + §14.4 checkpoint evidence；all B subitems independently PASS，blocking 0 |
| Foundation 0.1.1A parent | In Progress → Verified | A1/A2/A3 已 Verified；§14.2 五项门禁、DoD Capability criteria 与依赖均满足 |

Foundation 0.1.1 overall **保持 In Progress**。本轮不实现 C，不执行 FND-QA-AP、FND-PHY-NB 或
FND-QA-CC，不解除 P1A gate；C2 provenance、最终 Foundation gate 及其余 cross-cutting 依赖仍未闭合。
本轮仅修改 Markdown/status 事实源，未修改 Python、tests、physics、GUI、results 或 Scene。

## Foundation 0.1.1 A/B Interim Checkpoint（历史记录）

2026-09-03 已按 [A/B Interim Checkpoint Work Item](docs/work_items/foundation_0_1_1_ab_checkpoint.md)
完成 §14.4 checkpoint。完整 pytest、Current/Advanced/Future fast headless、隔离 Phase Resolution
复算与 `git diff --check` 均通过；Phase Resolution 输出位于
`results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/`，未覆盖 `results/phase_bits/`
legacy。B1/B2/B3 implementation independent review、真实 GUI 人工验收与 RIS Gain visualization
修复审查均为外部提供的通过证据，并非本次 Codex 自行完成的人工验收。

该 checkpoint 明确标记为 **checkpoint / non-formal provenance**，在 C2 provenance 完成前不得
作为正式 Foundation experiment 发布。Foundation 仍为 **In Progress**；不进入 C，不解除 P1A
门禁。该 checkpoint 不包含 B verification 签署；后续 closure 见本页顶部。无真实 blocker。

## Foundation 0.1.1B implementation handoff（历史记录）

Foundation 0.1.1B 的 Ready Review 已于 2026-09-03 重新完成，blocking ambiguity 为 0。两项冻结
决策为：continuous Physics Focus initial + finite `search_levels` feedback refinement；以及
Generation pending 状态的 confirm-discard / cancel-preserve。

B1/B2/B3 在本次历史 handoff 已达到 implementation-level；当前已由顶部 closure 标记为 Verified：

- `AMF-OPT-004`：hardware phase bits 与 optimizer search levels 分离；finite-bit 候选固定为合法
  `2**phase_bits`，continuous search levels 可配置并进入 `OptimizationResult` metadata；
- `AMF-RIS-008`：GUI 默认接入 Coherent Target Focus，同时保留 RIS-only Physics Focus 入口；
- `AMF-RIS-009`：GUI 只读显示 equivalent patch pitch、运行波长与 pitch/λ，不提供无来源阈值；
- `AMF-UI-007`：Pending/Apply/Optimize 门禁、Customized 派生显示和 Generation 覆盖提示；
- `AMF-UI-008`：Pattern Grid/Hardware Phase/Allowed-Used States/Source/Actual error/legend，以及
  准确的 Geometry Position Error 与 Feedback Measurement Noise 标签。

对应 combined Work Item：[Foundation 0.1.1B](docs/work_items/foundation_0_1_1_b.md)。当时仅同步到
Implemented、等待独立审查；后续 B verification/status closure 与 A/B checkpoint 见本页顶部。
该历史 handoff 不涉及 C、QA、cache、P1 或新场景。

## Foundation / FND-FIX-WALL verification/status closure（历史记录）

FND-FIX-WALL（Wall Geometry Closure）已完成独立人工验收并达到 **Verified**：

- 验收对象为 implementation commit `8841ef286e8e4c3a6ecea04592f69d9306a80fa1`；
- Gate 结果：G0–G8 全部 PASS；
- blocking issues：0；
- 本次 verification/status closure 仅同步 Markdown 状态事实源，未修改功能代码、测试逻辑、
  物理模型、Scene schema 或后续阶段内容。

实现与 Ready Review 证据：

- Ready 结论为 blocking ambiguity 0；endpoint z 冻结为公共绝对容差
  `WALL_ENDPOINT_Z_ATOL_M=1e-9 m`，不使用相对容差；
- `Wall` 构造和 Scene v1 loader 通过同一数据边界拒绝超容差 z，错误包含 wall id、具体字段、
  实际值、floor-anchor 原因和显式归零迁移指引；容差内原值 round-trip 不被裁剪；
- Ground Truth 仍生成三维 position delta，但 engine 对每堵墙只采样一次且只消费 XY，以同一个
  `[dx,dy,0]` 刚体平移两个端点；墙长、朝向和 `height_m` 不变；
- LOS blockage 和 single-wall reflection 消费同一个 perturbed working-scene Wall，继续统一采用
  `[0,height_m]`；TX/RX/RIS/obstacle 的既有三维误差语义不变；
- Scene schema version 保持 1。兼容审计覆盖仓库唯一受支持 Scene、内建 Smart Space、相关测试
  与 Scene Git 历史，未发现非零-z 依赖；超容差外部 v1 文件需显式归零，不能静默迁移；
- 未修改 GUI 代码、场景、results、cache、反射公式、A1/A2/A3 或任何后续能力。

本机 Windows / Python 3.14.3 实现门禁：

| 门禁 | 结果 |
|---|---|
| FND-T19 + blockage/reflection/scene 定向回归 | `13 passed` |
| wall/GT/scene + physics/RIS/A1/A3/optimization 相关回归 | `79 passed` |
| documentation tests | `9 passed` |
| 完整 pytest | `103 passed in 3.59s` |
| Current v0.1 fast headless | `-46.5879 dBm`，RIS Gain `+8.6874 dB`，场图 `3.045 s` |
| Advanced v0.1 fast headless | `-30.1257 dBm`，RIS Gain `+25.1496 dB`，场图 `3.869 s` |
| Future v0.1 fast headless | `-19.3118 dBm`，RIS Gain `+35.9636 dB`，场图 `9.370 s` |
| `git diff --check` | PASS |

三代目标值与 A1/A2/A3 基线显示到四位小数完全一致。兼容性收紧仅影响此前会被接受、但从未
有已验证计算语义的超容差 Wall endpoint z，以及 XY 重合而仅 z 不同的退化墙段。

状态边界：A1/A2/A3、AMF-RIS-010、FND-FIX-WALL 与 AMF-SIM-006 保持 Verified；Foundation
0.1.1A 和 Foundation 0.1.1 保持 In Progress；B/C、FND-QA-AP、FND-PHY-NB、FND-QA-CC、
cache 和新场景均未改变。

## Foundation 0.1.1A / A3 final verification closure（历史记录）

Deliverable A3（Commanded Pattern hardware boundary）已完成独立人工验收并达到
**Verified**：

- 验收对象：implementation commit `fb5ec093e78e588a65a661abf3b32d744d04ae04`；
- Gate 结果：G0–G8 全部 PASS；
- blocking issues：0；
- 状态边界（本历史记录时点）：A1/A2 保持 Verified；Foundation 0.1.1A 和 Foundation 0.1.1 仍为 In Progress；
  其他 Planned/In Progress 能力不变。

本次 verification/status closure 仅修改 Markdown 状态事实源；documentation tests `9 passed`、
完整 pytest `96 passed`、`git diff --check` 通过。未修改功能代码、测试逻辑、物理模型或后续
阶段内容。

- [A3 Work Item](docs/work_items/foundation_0_1_1_a3.md) 已完成 Definition of Ready，
  blocking ambiguity 为 0；A3 未触发新 ADR，也不改变 Scene JSON v1；
- 新增公共 `validate_commanded_pattern()` 与 `COMMANDED_PHASE_ATOL_RAD=1e-6`：严格要求一维、
  长度匹配、real/finite；离散状态按模 `2π` 的绝对容差验证，continuous 接受 finite 未 wrap
  表达；接受值不 wrap、snap 或 silent quantize；
- `compute_channel()`、`compute_field_map()` 和低层公开 RIS scattering 入口共用同一 validator；
  engine 还拒绝未知/歧义 RIS key，field map 在像素循环外只验证一次；
- validation 位于 Ground Truth 扰动之前；actual phase/efficiency error 在验证后加入传播且不再
  量化；
- `RISSurface.phase_bits` 收紧为正整数或 None，bool、小数和非正值拒绝；合法既有生成器、
  optimizer、GUI/headless pattern 行为保持不变；
- 共享纯实现位于 `core/pattern_contract.py`，由 `ris`/顶层 API 导出，physics 和 simulation
  复用而不产生反向依赖。

本机 Windows / Python 3.14.3 实现门禁：

| 门禁 | 结果 |
|---|---|
| A3 定向 pytest | `22 passed` |
| A3 + RIS/scene/A1/optimization 相关回归 | `63 passed` |
| documentation tests | `9 passed` |
| 完整 pytest | `96 passed in 2.81s` |
| Current v0.1 fast headless | `-46.5879 dBm`，RIS Gain `+8.6874 dB`，场图 `2.130 s` |
| Advanced v0.1 fast headless | `-30.1257 dBm`，RIS Gain `+25.1496 dB`，场图 `2.406 s` |
| Future v0.1 fast headless | `-19.3118 dBm`，RIS Gain `+35.9636 dB`，场图 `7.944 s` |
| `git diff --check` | PASS |

三代目标功率和 RIS Gain 与 A1/A2 基线显示到四位小数完全一致；A3 不改变物理公式，因此合法
command 没有数值迁移。兼容性变化仅是此前可能被接受的未知/歧义 key、二维 reshape、非有限/
complex/off-grid phase 和非法 `phase_bits` 类型现在明确失败。

状态边界：A1/A2/A3 与 AMF-RIS-010 为 Verified；Foundation 0.1.1A 和 Foundation 0.1.1
保持 In Progress。FND-FIX-WALL 的后续 Verified 状态见本页最新快照；B/C、FND-QA-AP、
FND-PHY-NB、FND-QA-CC、cache 和其他后续能力未改变。

## Foundation physics/algorithm master-plan integration（历史记录）

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

## Foundation aperture quadrature governance update（历史记录）

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

## Foundation 0.1.1A / A2 最终验收快照（历史记录）

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
  B 阶段，因此 `AMF-RIS-009` 在本历史记录时点仍为 In Progress；当前状态见顶部 closure。

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
Foundation 0.1.1A、AMF-RIS-009 和 Foundation 0.1.1 均为 In Progress（本历史记录时点）。

## Foundation 0.1.1A / A1 最终验收快照（历史记录）

Deliverable A1（Focus objective）已完成最终人工验收并达到 **Verified**：

- 验收依据：closure commit `87495ec91a490d5cd5331ad9c4a0a2e863c10b40`；
- Gate 结果：G0–G8 全部 PASS；
- blocking issues：0；
- 状态边界（本历史记录时点）：Foundation 0.1.1A、AMF-RIS-008 和 Foundation 0.1.1 仍为 In Progress。

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
Target 新默认。A2/A3 已 Verified；Foundation 0.1.1A 仍有后续状态门禁，因此仍不能标为
Implemented/Verified。

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

- GUI 默认使用 Coherent Target Focus，RIS-only Physics Focus 仍可选；CLI、Physics-Guided 和
  legacy experiment 为兼容性继续使用 RIS-only objective；
- `nx/ny` 的 equivalent patch 语义已冻结，但仍同时承担控制与中心点求积；GUI 已接入
  A2 只读 pitch/波长诊断；最小独立求积有效性进入 Foundation final exit 前的 FND-QA-AP，
  P1C 保留完整 aperture/field-map/适用域研究；
- A3 commanded hardware-state validation、B1/B2/B3 及其五个 B requirements 已 Verified；
- C1 Profile/Reflection 接入与稳定 Profile identity 已 Verified，不代表后续 coefficient/physics gate 已签署；
- C2 provenance/no-overwrite 尚未实现；自定义复数 Profile 不构成最终 Focus/coefficient consistency
  签署，仍须 FND-QA-CC 与必要的独立 production migration；
- `frequency_hz/bandwidth_hz` 的 flat-channel 语义已由 ADR-0010 冻结，但 model ID、标签和
  provenance closure 尚未实现；
- FND-FIX-WALL 已 Verified：floor-anchored Wall/XY-only Ground Truth 语义当前仍不支持悬空/倾斜墙；
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

1. 后续另行授权后，按 [Foundation 0.1.1C Work Item](docs/work_items/foundation_0_1_1_c.md)
   独立实现/评审 C2 minimum experiment provenance；本次不开始；
2. 执行 FND-QA-AP，冻结 production quadrature policy；若要求改变 production，先走独立迁移；
3. 完成 FND-PHY-NB 和 FND-QA-CC，冻结 frequency/coefficient/cache identity；
4. Foundation final verification 通过后再进入 P1A 几何系数缓存与矩阵求值；
5. 随后完成相位误差和 P1C 扩展孔径研究，再扩展 XR/Factory/City。

阶段顺序、entry/exit gate 和工作颗粒度以 [docs/roadmap.md](docs/roadmap.md) 为准。本页只
记录状态，不新增需求或改变优先级。
