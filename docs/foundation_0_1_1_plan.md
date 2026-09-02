# Foundation 0.1.1：物理模型契约与改进计划

| 属性 | 值 |
|---|---|
| 文档状态 | Operational / Normative for sequencing |
| 当前实现基线 | v0.1 Verified，commit `edfa43c` |
| 目标版本 | v0.1.1 Foundation |
| 当前计划状态 | In Progress；A1 Implemented，A2/A3 与 B/C 尚未完成 |
| 父级路线 | v0.1 Smart Space → Foundation 0.1.1 → P1A |
| 主要责任 | 项目维护者、物理仿真负责人、GUI/测试负责人 |
| 最后复核 | 2026-09-02（A1 verification closure） |

本文是 AirMirror Future 在 v0.1 后的首个模型契约改进计划。它把当前代码事实、已发现的
物理/算法/交互问题、目标架构、实施顺序、测试证据和退出门禁集中到同一个工作入口，供
第一次接触工程的开发者快速建立共同上下文。

本文负责**阶段顺序和工作边界**，不替代现有规范：当前有效公式以
[physics_model.md](physics_model.md) 为准，当前优化行为以
[optimization_spec.md](optimization_spec.md) 为准，当前数据/API 以
[data_model.md](data_model.md)、[public_api.md](public_api.md) 和
[scene_schema.md](scene_schema.md) 为准。目标行为只有在 ADR、需求、测试、代码和下游文档
同步完成后，才能从 Planned 变为 Implemented/Verified。

## 1. 新参与者先读什么

若此前完全不了解项目，建议按以下最短路径阅读：

1. [project_baseline.md](project_baseline.md)：产品是什么、不能做什么、哪些物理原则不可破坏；
2. [glossary.md](glossary.md)：统一术语、符号、单位和状态词；
3. 本文第 2–5 节：当前能力、为何暂停原 P1A、Foundation 要解决什么；
4. [physics_model.md](physics_model.md)：当前实际传播和 RIS 公式；
5. [architecture.md](architecture.md)：当前模块边界和数据流；
6. 本文第 6–12 节：Deliverables、测试、风险、提交顺序和退出门禁；
7. [requirements.md](requirements.md) 与 [roadmap.md](roadmap.md)：稳定编号和后续依赖；
8. [../DEVELOPMENT_STATUS.md](../DEVELOPMENT_STATUS.md)：此刻做到哪里。

阅读时必须区分：

- **Current / 当前事实**：v0.1 代码、测试和规范已经实现的行为；
- **Target / 目标契约**：Foundation 0.1.1 计划建立但尚未实现的行为；
- **Future / 后续研究**：不进入本次 Foundation 的能力。

## 2. 项目背景和当前基线

AirMirror Future 是物理约束的系统级 RIS 数字孪生与未来场景推演平台，不是 CST/HFSS
替代品，也不是依靠美术效果制造“信号变强”的展示程序。当前 v0.1 已经交付一个可运行的
Smart Space 垂直切片，核心定位是：

> 确定性、窄带、SISO、有限孔径、系统级电磁传播近似。

当前已经实现：

- 复数 Friis LOS、几何墙体/障碍物衰减和一次墙面镜面反射；
- 二维有限孔径 RIS、面积归一化逐 patch 复场叠加、前向方向图和无源效率；
- continuous 与 1/2/3/4-bit 相位量化；
- RIS-only 几何相位共轭 Focus、Feedback Greedy 和 Physics-Guided Feedback；
- Controller Model、Ground Truth、Measurement Oracle 和固定 seed；
- 功率、SNR、RIS Gain、Coverage、Dead Zone、场图和中文 GUI；
- JSON 场景、headless 入口、后台取消、过期结果丢弃和 Phase Resolution 实验；
- 需求追踪、ADR、测试策略、完成定义和开发状态文档。

当前总信道仍遵循 [physics_model.md](physics_model.md) 的 v0.1 定义：LOS、一次墙反射和每块
单跳 RIS 的复数贡献先相加，再由发射功率计算接收功率。Foundation 不推翻这条主链路，
而是校准“Focus 优化的到底是什么”“RIS 网格代表什么”“硬件命令在哪里受约束”以及
“未来场景怎样选择传播模型”。

## 3. 为什么 Foundation 必须排在 P1A 前

原路线准备直接进入 P1A Geometry Cache and Matrix Evaluation。代码目前只有尚未使用的
cache 容器，复杂的系数矩阵、失效键和增量更新尚未实现，因此现在调整契约的迁移成本最低。

Foundation 前置有四个直接原因：

1. **优化目标尚未对齐**：当前 Focus 最大化 RIS 自身相干幅度，但规范目标是单 RX 总接收
   功率。即使某个场景中的数值收益很小，objective contract 仍必须正确，不能把一次演示增益
   当成采用新算法的理由或验收阈值。
2. **RIS 网格语义未冻结**：`nx/ny` 同时参与独立相位控制和孔径数值离散。若先按旧语义
   写缓存，后续拆分或改名会影响矩阵 shape、cache key 和实验解释。
3. **Pattern 硬件边界不完整**：Phase Bits 目前约束 pattern 生成器和优化候选，但传播入口
   只检查长度，不能阻止非法离散命令进入 1-bit/2-bit RIS。
4. **传播模型没有 Profile 身份**：未来不同场景若都进入同一引擎，缓存无法区分环境模型
   或参数版本；先稳定 Profile 契约才能定义可信的缓存失效规则。

审计备注：commit `edfa43c` 的默认 Smart Room 中，1-bit pattern 加入公共相位 offset 后，
目标点曾比现有 RIS-only Focus 改善约 `5.02 dB`。该数值只说明 objective 错位具有可观测影响，
不得进入跨版本门禁；目标算法落地后应由带 model provenance 的新基准取代。

因此本阶段顺序固定为：

```text
v0.1 Verified
  → Foundation 0.1.1A：物理与算法契约
  → Foundation 0.1.1B：优化器与 GUI 语义
  → Foundation 0.1.1C：PropagationProfile 接口
  → P1A Geometry Cache and Matrix Evaluation
  → P1B/P1C 统计与孔径实验
  → XR / Factory / City
```

不得用“缓存只改性能”为理由跳过本阶段，因为 cache identity、invalidation 和数值参考都
依赖这里要冻结的契约。

## 4. 本阶段目标、非目标和成功定义

### 4.1 目标

Foundation 0.1.1 完成后，项目必须做到：

- 明确区分 RIS-only Focus 与 total-channel Coherent Target Focus；
- GUI 默认优化目标、规范中的 objective 和测试测量量一致；
- 明确 `nx/ny` 是系统级等效可控孔径 patch，并记录其同时承担中心点求积离散的限制；
- 显示 effective pitch、运行波长比例和可解释的适用性提示；
- 对 Commanded Pattern 执行硬件状态验证，Ground Truth Actual Phase 保持可偏离命令状态；
- 将硬件相位分辨率与优化器搜索分辨率分开；
- 让用户区分 UI 中待应用值、仿真实际值和 generation preset/customized 状态；
- 让 Ground Truth 参数名称准确表达影响范围；
- 建立最小 PropagationProfile 契约，并用一个默认 IndoorDeterministicProfile 复现 v0.1；
- 为后续 cache、统计实验和场景扩展提供稳定的 ID、版本和结果 provenance。

### 4.2 非目标

本阶段明确不实现：

- XR、Factory、City、Tunnel、UAV 或模块化建筑的可运行场景；
- Rayleigh/Rician fading、log-normal shadowing、Doppler、宽带抽头或 OFDM；
- MIMO/MISO/SIMO、波束赋形或多流；
- 真实 meta-atom、互耦、材料色散、极化或全波模型；
- 自动把 RIS 实体尺寸绑定运行频率；
- 两套控制网格/积分网格的完整高保真实现；
- P1A 几何矩阵缓存、增量 Greedy 或性能重写；
- 对历史实验结果进行无版本覆盖。

### 4.3 成功定义

本阶段不是以“新增文件或按钮”判定完成，而以以下用户结果判定：

- 新开发者能从文档判断当前 Focus 与目标 Focus 的差异；
- 任意 pattern 在进入传播前都能证明符合目标 RIS 的 commanded hardware states；
- 用户能看到当前应用中的 Phase Bits、搜索状态数、Pattern 来源和是否有未应用参数；
- 当前 Smart Room 可由默认 Profile 重放，结果变化均能解释为已接受的算法变化；
- 新增 Profile 或缓存时不需要重新定义 Scenario、Ground Truth 和 RIS 的职责；
- 旧 Phase Resolution 结果仍可识别其 model/focus 版本，不与新结果混用。

## 5. 目标模型契约

### 5.1 Focus 目标契约

#### Current：RIS-Only Phase-Conjugate Focus

当前 `generate_focus_pattern()` 根据 TX–patch–RX 的名义总路径相位生成命令并量化，使各 RIS
patch 在目标点相互相干。它不读取 baseline 复相位，因此优化的是 RIS 自身贡献幅度，而不是
总接收功率。该算法必须保留，用于：

- 孔径/相位共轭教学；
- 固定孔径面积归一化和细分稳定性质测试；
- 与历史 Phase Resolution 实验保持可解释兼容；
- 作为新算法的明确对照，而不是被静默改写。

#### Target：Coherent Target Focus

新增算法以 Controller Model 的 nominal baseline 为参考，在量化前引入全局公共相位 offset，
使 RIS 合成贡献与 baseline 尽量同相。有限 bit 情况不假设“先量化再整体旋转”等价，而在一个
低维公共 offset 候选集合中，以 nominal target received power 选择最佳命令。

该算法属于**基于名义模型的系统目标优化**，不是单纯 RIS 几何相位函数。层级职责冻结为：

- `ris/phase.py` 只保留 RIS-only 相位共轭、相位量化、量化前公共 offset 等纯 helper；
- `optimization/coherent_focus.py`（名称可由 ADR 最终确定）负责读取公开 Scene 与 Controller
  Model、取得 nominal baseline、比较候选并输出 Coherent Target pattern；
- `simulation` 只提供可复用的 nominal channel/component 计算，不在 Engine 内硬编码 Focus
  策略，也不得让 `ris` 反向依赖 `simulation`；
- 当前 `Optimizer` 基类面向 Measurement Oracle。Coherent Target Focus 不得为了复用名称而
  强行继承不相符的反馈优化接口；若要统一接口，必须另行评审 model-based 与 feedback 两类
  optimizer 的公共抽象。

详细相位符号、退化分支和有限 bit 搜索方法必须由新的 objective ADR 决定，并同步更新
[physics_model.md](physics_model.md) 与 [optimization_spec.md](optimization_spec.md)。最低边界：

- 只能读取 Controller Model 和公开 Scene；不得读取 Ground Truth 私有误差；
- baseline 幅度近零时回退到 RIS-only 或 ADR 规定的确定性行为；
- RIS 贡献近零时不得用不稳定 angle assertion 判定失败；
- continuous、单 RIS、相位命令不改变反射幅度的 nominal 模型中，应直接验证
  `|h_total| ≈ |h_baseline| + |h_RIS|`；该保证不得外推到 Ground Truth、幅相耦合或多 RIS；
- finite-bit 公共 offset 候选集合必须**精确包含 `delta=0`**，并使用与旧算法相同的量化器；
  因而在同一个确定性 nominal total-power objective 下，新搜索不得差于未偏置候选；
- finite-bit 相同 objective 的候选必须有稳定 tie-break；固定角度网格若未覆盖所有量化边界，
  只能声明“候选集中最优”，不能声称全局最优；
- GUI 必须显示当前 Pattern Source；
- 更改 GUI 默认算法时必须保留旧算法的公开可访问方式和实验标签。

### 5.2 RIS 网格语义契约

Foundation 推荐把 `nx/ny` 定义为：

> System-level equivalent controllable aperture patches，系统级等效可控孔径 patch。

每个 patch：

- 拥有一个 commanded phase；
- 使用孔径总面积除以 patch 数得到等效面积；
- 用中心点近似该 patch 在当前系统级散射积分中的贡献；
- 不宣称等于一个真实物理 meta-atom。

当前公式进一步等价于“满填充孔径的中心点求积”：没有 patch 内积分、fill factor、真实
meta-atom 子结构或 patch factor。`effective_pitch` 表示等效 patch 尺寸/中心间距，不得据此
直接推导真实阵列的栅瓣、互耦或制造可行性。

必须同时记录一个重要限制：当前同一组 `nx/ny` 既决定控制自由度，也决定中心点求积的离散
分辨率。固定孔径细分测试保护的是面积归一化和不发散/稳定趋势，但增加 patch 也会增加独立
控制自由度。第一版接受这一合并近似，未来若进入器件级或严格数值收敛研究，再拆成：

- control grid；
- integration/quadrature grid；
- physical meta-atom layout。

Foundation 应新增派生显示或公共 helper：

- `effective_pitch_x = width / nx`；
- `effective_pitch_y = height / ny`；
- operating wavelength；
- `pitch_x / wavelength`、`pitch_y / wavelength`。

这些值是透明度信息，不得把 `pitch > wavelength/2` 直接判为系统级模型错误。若提供
“离散过粗”提示，Foundation 最多提供 advisory diagnostic，例如对未 wrap 的
`k*(d1+d2)` 在 patch 中的角点/边中点跨度或一阶切向相位梯度估计。该指标不是物理有效性
证明：驻相点附近还可能受二阶 Fresnel 曲率、幅度变化、方向图和遮挡边缘影响。本阶段不得设置
无来源的 `45°`、`0.2 dB` 等全局硬阈值。

当前 8×8→16×16→32×32 测试同时增加中心求积点和独立 commanded phase 自由度，只保护
面积归一化、结果稳定和“不随 patch 数无界增益”，不能证明粗 patch 已达到物理/求积收敛。
真正的数值有效性验证推迟到 P1C：固定实体孔径、control grid 和 commanded pattern，只细化
每个 control patch 内的 quadrature grid，并比较复数 `h_RIS` 误差与功率差。

`design_frequency_hz` 在 Foundation 0.1.1 明确 **Deferred**：Scene v1 不新增该字段。当前
operating `frequency_hz` 继续决定 `k`、波长和 `pitch/wavelength` 展示，但不自动缩放实体孔径。
只有真正引入 `Gamma_n(f)`、`eta(f)`、硬件工作带宽或 beam-squint 后才重新触发 ADR；届时该
参数更可能属于每块 RIS 的 hardware model/preset，而不是全局 Scene 标签。

### 5.3 Commanded → Actual 硬件边界

统一状态链必须是：

```text
Ideal phase
  → hardware quantization
  → Commanded Pattern
  → commanded-state validation
  → add Ground Truth phase/efficiency errors
  → Actual Pattern
  → propagation
```

验证要求：

- pattern key 必须对应明确 RIS，长度必须等于 `nx*ny`；
- 所有值必须 finite；
- 离散 RIS 的 commanded phase 在模 `2π` 意义下必须接近合法均匀状态；
- 比较必须使用文档化浮点容差；
- 非法 commanded state 直接抛出 `ValueError`，不得 silent quantize；
- continuous 允许任意 finite 相位和等价的未 wrap 表达；
- Ground Truth error 加入后的 Actual 不再量化，否则会抹掉要研究的硬件误差；
- optimizer、GUI、headless 和外部公共 API 都必须经过同一验证边界。

权威 enforcement point 进一步规定为：

- validator 本体属于 RIS pattern contract，可放在独立 `ris/pattern_contract.py`；
- `SimulationEngine.compute_channel()` 与 `compute_field_map()` 都必须在进入 Ground Truth 扰动
  和内部 `_components()` 前调用；Field Map 必须在像素循环前只验证一次；
- optimizer/GUI 可提前调用以改善错误提示，但不能取代 SimulationEngine 防线；
- 若 `ris_channel_for_points()` 继续列为低层公共 API，它也必须复用同一单 RIS validator；
  否则应通过公共 API 评审明确降级为内部函数；
- 未知 RIS key、严格 shape、NaN/Inf、模 `2π` 合法状态和 tolerance 都属于统一错误契约。

### 5.4 Hardware Resolution 与 Search Resolution

`phase_bits` 只描述 RIS 硬件命令状态：

- 离散硬件有 `2^bits` 个合法相位；
- continuous 硬件不受离散状态约束。

反馈优化器另有 `search_levels`：

- 对离散硬件，候选必须是硬件合法状态，不能由 search 参数产生非法相位；
- 对 continuous 硬件，允许用 8/16/32 等有限候选近似搜索；
- 结果和 GUI 必须显示“continuous hardware + N-level search”；
- 实验必须记录 `search_levels`，不能只记录 `phase_bits`；
- Physics-Guided 的连续 initial pattern 与离散反馈修改是否允许混合，必须在 optimizer 规格中
  明确，不能依赖实现偶然行为。

### 5.5 GUI Pending、Preset 与 Pattern 语义

普通参数保持显式 Apply，不采用每次 spinbox 变化都重算高质量场图。目标状态机：

```text
Applied
  → 用户编辑任意参数
Pending / Modified — Apply required
  → Apply
Applied + invalidate old workers + regenerate pattern/results
```

规则：

- Pending 时禁止 Optimize，或弹出明确的“请先 Apply”提示；
- Pending 时指标和 Pattern 明确标注仍来自已应用模型；
- Generation 切换明确表示“加载整套 preset”，有未应用修改时不得无提示覆盖；
- 手动偏离 preset 后只在显示层标记 `Current/Advanced/Future · Customized`；
- 不把 `Customized` 写入受限的 `generation` 数据字段；
- Pattern 面板至少显示 Grid、Hardware Phase、Allowed/Used States、Pattern Source、Phase Error
  和固定的循环相位图例；
- Actual 标签说明其包含 Ground Truth phase error，不能用颜色数量判断硬件命令状态。

### 5.6 Ground Truth 参数命名

当前 Position Error 同时平移 TX、RX、RIS、每堵墙和每个 obstacle，因此 GUI 改名为：

- `Geometry Position Error σ / 几何位置误差 σ`。

tooltip 必须说明这是每个实体由固定 seed 产生的三维固定偏移，不是仅 RX localization error。

当前 Measure Noise 只作用于 Measurement Oracle，因此改名为：

- `Feedback Measurement Noise σ / 反馈测量噪声 σ`。

本阶段不拆多个独立位置误差字段，避免扩大 Scene/GUI/实验契约；未来研究确有需要时再通过
新 requirement 和 schema 评审拆分。

### 5.7 PropagationProfile 契约

目标职责分离：

```text
Scenario / Scene
  → PropagationProfile
      → direct propagation
      → blockage / LOS-NLOS classification
      → reflections
      → optional fading hook (Foundation uses None)
  → RIS model
  → coherent effective channel
  → received power / noise / SNR

Controller Model / Ground Truth Model
  → describes nominal-vs-truth uncertainty
  → does not choose the environment propagation law
```

Foundation 只实现或设计一个默认 `IndoorDeterministicProfile`，完整复用 v0.1 的 Friis、几何
遮挡、一次墙反射和有限孔径 RIS。Profile 必须有：

- 稳定 ID；
- model/profile version；
- 可序列化或可稳定哈希的参数摘要；
- 明确职责，不成为包含 Scene、Ground Truth、RIS、噪声和 GUI 的 God object；
- 默认行为与 v0.1 reference 在声明容差内一致。

Profile 必须一致参与 direct path、每条 reflection leg、TX→RIS incident leg 和 RIS→RX
scattered leg；不能只替换 direct path 而让 RIS 两段继续绕过场景传播规则。同时：

- Profile 负责环境传播，RIS model 仍负责孔径、方向图、效率和 commanded/actual phase；
- ADR 必须明确 Profile 的 path response 是“完整复传播响应”还是“自由空间之外的环境修正”，
  防止与 `ris_channel` 已包含的距离扩散和传播相位重复计算；
- Foundation 初次接入保持 v0.1 的 RIS 面板中心阻挡近似，以便分路径等价复现；逐 patch
  阻挡是独立物理改进，不能夹带进 Profile 重构；
- 最小接口可使用小型 Protocol/strategy 和有限 path-role context，不建立插件注册中心、通用
  射线图 DSL、事件总线或 provider system。

Scene 是否直接持有 profile 配置、还是由 scenario/engine 参数注入，必须由 architecture/schema
ADR 决定。不得把 Python 类名直接作为持久化协议。未来 cache key 至少包含 profile identity、
version、parameters 和所有影响系数的场景状态。

## 6. Requirement 映射

本计划对应以下 Planned requirement IDs，权威状态见 [requirements.md](requirements.md)：

| Requirement | 目标 |
|---|---|
| `AMF-RIS-008` | 区分 RIS-only 与 Coherent Target Focus，并对齐 nominal objective |
| `AMF-RIS-009` | 冻结 equivalent controllable patch 语义和有效 pitch 透明度 |
| `AMF-RIS-010` | 在传播前验证 commanded hardware states |
| `AMF-OPT-004` | 分离 hardware phase resolution 与 optimizer search levels |
| `AMF-SIM-005` | 建立 PropagationProfile 和默认 IndoorDeterministicProfile |
| `AMF-UI-007` | 建立 pending/apply/preset/customized 状态语义 |
| `AMF-UI-008` | Pattern 元数据、相位图例和准确 Ground Truth 标签 |
| `AMF-EXP-006` | 实验记录 focus/profile/model/search provenance，保留历史可比性 |

这些条目在测试和实现完成前保持 Planned，不得因本文存在而改为 Implemented。

## 7. Capability 和 Deliverables

### 7.1 Foundation 0.1.1A — Physics and Algorithm Contract

#### Deliverable A1：Focus objective ADR

- 状态：**Implemented（2026-09-02）**；Foundation 0.1.1A 仍为 In Progress，A2/A3 未开始；

- Requirement：`AMF-RIS-008`；
- 输入：当前 Focus、nominal baseline、Controller Model、phase bits；
- 输出：两个具名算法、公共 offset 规则、退化行为和 objective 测试；
- 预计文档：ADR、physics、optimization、glossary、public API；
- 预计代码：`ris/phase.py` 中的纯 helper、`optimization/coherent_focus.py` 中的名义目标策略，
  以及必要且通用的 simulation component API；
- 验收：continuous nominal RIS 与非零 baseline 相位对齐且满足解析总幅关系；目标功率不低于
  no-RIS；finite-bit 搜索精确包含 `delta=0` 且不差于未偏置候选；旧 RIS-only/random 性质
  继续通过。
- 实现证据：[ADR-0006](adr/0006-coherent-target-focus-objective.md)、
  [A1 Work Item](work_items/foundation_0_1_1_a1.md)、`tests/test_coherent_focus.py`；
- 兼容结果：`generate_focus_pattern()` 保持 v0.1 RIS-only 语义；GUI/CLI/legacy experiment
  默认未在 A1 中改变。

#### Deliverable A2：RIS aperture patch semantic contract

- Requirement：`AMF-RIS-009`；
- 输入：`width/height/nx/ny/frequency`；
- 输出：术语、派生 pitch/波长比例、适用性说明和未来拆网格触发条件；
- 预计文档：ADR、data model、physics、limitations、GUI spec；
- 预计代码：优先纯派生 helper，不改变现有实体孔径事实源；
- 验收：固定孔径细分不产生无界 patch-count gain；改变 operating frequency 不改变实体宽高；
  UI/结果不把 patch 宣称为真实 meta-atom；`pitch/wavelength` 与相位跨度均只作透明度信息，
  不声称已完成独立 quadrature convergence。

#### Deliverable A3：Commanded Pattern hardware boundary

- Requirement：`AMF-RIS-010`；
- 输入：RIS、commanded phase array；
- 输出：统一验证函数、公共错误契约和所有入口调用；
- 预计文档：public API、physics、data model、test strategy；
- 预计代码：优先独立 `ris/pattern_contract.py`，并接入 `compute_channel`、`compute_field_map` 和
  保留为公共 API 的低层散射入口；
- 验收：离散非法状态失败、模 `2π` 等价状态通过、continuous finite 通过、Actual error 不被
  再量化。

### 7.2 Foundation 0.1.1B — Optimizer and GUI Semantics

#### Deliverable B1：Search resolution contract

- Requirement：`AMF-OPT-004`；
- 输入：hardware phase bits、search levels、initial pattern；
- 输出：显式 optimizer 参数、结果元数据和 CLI/GUI 文案；
- 预计文档：optimization、public API、experiment spec；
- 预计代码：`optimization/greedy.py`、`physics_guided.py`、worker/CLI wiring；
- 验收：离散硬件候选全部合法；continuous 的候选数可配置且被记录；固定 seed 可重放。

#### Deliverable B2：Pending/apply/preset state

- Requirement：`AMF-UI-007`；
- 输入：当前 applied Scene、编辑控件、generation preset；
- 输出：dirty 状态、Apply/Optimize 门禁、Customized 派生标签和覆盖提示；
- 预计文档：gui spec、data model、manual acceptance；
- 预计代码：`gui/main_window.py`，不得把传播公式复制到 GUI；
- 验收：编辑 Phase Bits 后 UI 明确 pending；未 Apply 不用旧值静默 Optimize；Apply 后 pattern
  和 worker version 同步；切换 preset 不无提示丢弃待应用值。

#### Deliverable B3：Pattern transparency and Ground Truth labels

- Requirement：`AMF-UI-008`；
- 输入：RIS、commanded/actual arrays、pattern source、误差配置；
- 输出：相位图例和 Pattern/误差元数据；
- 预计文档：gui spec、glossary、limitations；
- 预计代码：`gui/pattern_view.py`、`main_window.py`；
- 验收：1/2/3/4-bit 的 Allowed/Used States 正确；Actual 误差说明准确；两个误差标签与真实
  作用范围一致。

### 7.3 Foundation 0.1.1C — PropagationProfile Boundary

#### Deliverable C1：Profile ADR and minimal implementation

- Requirement：`AMF-SIM-005`；
- 输入：Scene、TX/RX、Model、RIS patterns；
- 输出：最小 Profile 协议、默认 IndoorDeterministicProfile、稳定 identity/version；
- 预计文档：ADR、architecture、public API、scene schema decision、limitations；
- 预计代码：新的轻量 profile 模块和 `SimulationEngine` 编排调整；
- 验收：默认 Profile 在未改变 Focus 的 reference 模式下复现 v0.1 分路径复信道；direct、
  reflection、RIS incident/scattered legs 均不能绕过 Profile；Profile 不依赖 GUI/optimizer，
  不吞并 RIS device model；未来 cache key 能引用稳定 identity；未实现 Profile 明确拒绝而非
  回退。

#### Deliverable C2：Minimum experiment provenance

- Requirement：`AMF-EXP-006`；
- 输入：focus mode、profile ID/version、search levels、model contract version；
- 输出：Foundation 最小可解释实验 schema 和新的结果目录规则；
- 预计文档：experiment spec、test strategy、results README；
- 预计代码：实验字段和 schema test；
- 验收：旧 `results/phase_bits` 不被覆盖；新旧结果能通过字段判断采用何种 Focus 和 Profile；
  缺失 provenance 的历史文件被明确标记 legacy，而不是伪造默认值。

完整历史迁移工具、结果索引和统计报告治理可在 P1B 完善，但上述最小字段、legacy 标记和
不覆盖规则不得推迟到 P1B，也不能仅用 `results/v0.1.1/` 目录名代替。

## 8. L4 Tasks 和建议顺序

每项控制在约 0.5–2 个开发日。L4 Task 是追踪单元，不等于 Git commit；依赖满足的任务可并行，
但每项仍必须有独立状态和完成证据：

| 顺序 | Task | 状态 | 完成输出 |
|---:|---|---|---|
| 1 | `FND-DOC-01` 建立 objective/geometry/profile 三个 ADR 草案 | Planned | 决策选项、后果、否决方案 |
| 2 | `FND-DOC-02` 冻结 equivalent patch、诊断量和 Deferred 边界 | Planned | data/physics/limitations 同步 |
| 3 | `FND-TEST-01` 定义 Focus objective 契约测试 | Implemented | FND-T01..T05、错误契约、tie-break 和 1/2/3/4-bit 回归 |
| 4 | `FND-TEST-02` 定义 commanded pattern 契约测试 | Planned | bits、modulo、tolerance、Actual error |
| 5 | `FND-PHY-01` 实现两个具名 Focus | Implemented | RIS-only 保留、Coherent 新增且分层正确；ADR-0006 |
| 6 | `FND-PHY-02` 实现 commanded validator | Planned | 所有公共传播入口共用且 Field Map 只验证一次 |
| 7 | `FND-OPT-01` 增加 search levels 与结果元数据 | Planned | discrete/continuous 语义分离 |
| 8 | `FND-UI-01` 建立 pending/apply/Optimize 门禁 | Planned | GUI 状态机 smoke tests |
| 9 | `FND-UI-02` 增加 Customized、Pattern 信息和准确标签 | Planned | 可人工验收界面 |
| 10 | `FND-QA-AB` A/B 中期验收与人工复核 | Planned | 三代 headless、GUI、临时隔离实验和审查记录 |
| 11 | `FND-ARCH-01` 接入默认 PropagationProfile | Planned | 全路径角色调用、当前分量等价复现 |
| 12 | `FND-EXP-01` 加入最小实验 provenance | Planned | versioned CSV/PNG、legacy 和 no-overwrite |
| 13 | `FND-QA-01` 全量回归、headless、GUI 和实验验收 | Planned | Foundation final exit evidence |

若任务实际超过两天，应继续拆分；不得把“完成 ChannelProfile”与“实现城市传播模型”合并。

## 9. 预计文件影响

以下是规划范围，不表示每个文件都必须修改；实施者应在 Work Item 中确认最小变更集。

| 范畴 | 预计文件 | 目的 |
|---|---|---|
| 决策 | `docs/adr/0006-*.md`、`0007-*.md`、`0008-*.md` | objective、patch semantic、profile ADR |
| 规范 | `physics_model.md`、`optimization_spec.md` | 目标算法和搜索/验证契约 |
| 数据/API | `data_model.md`、`public_api.md`、必要时 `scene_schema.md` | 派生值、错误、兼容策略 |
| 架构 | `architecture.md`、`limitations.md` | Profile 边界和适用域 |
| GUI | `gui_spec.md`、`glossary.md` | pending/customized/pattern/误差文案 |
| 实验 | `experiment_spec.md`、`results/README.md` | provenance 和历史结果保留 |
| 追踪 | `requirements.md`、`roadmap.md`、`DEVELOPMENT_STATUS.md` | 状态闭环 |
| 代码 | `ris/phase.py`、`simulation/engine.py`、`optimization/*`、`gui/*` | 后续实现，不在本文档提交中完成 |
| 测试 | `test_ris.py`、`test_scene_engine.py`、`test_optimization.py`、`test_gui_smoke.py`、`test_documentation.py` | 性质、集成、GUI 和 schema |

## 10. 测试设计和验收矩阵

建议测试名称可在实现时调整，但保护的性质不得弱化：

| Test ID | 建议测试 | 必须保护的性质 |
|---|---|---|
| FND-T01 | `test_ris_only_focus_preserves_legacy_phase_conjugation` | 旧算法保留且仍优于随机中位数 |
| FND-T02 | `test_continuous_coherent_focus_aligns_with_nominal_baseline` | 非退化场景中 RIS/baseline 相位对齐 |
| FND-T02b | `test_continuous_coherent_focus_reaches_analytic_total_amplitude` | nominal 单 RIS 中 `|h_total|≈|h_baseline|+|h_RIS|` |
| FND-T03 | `test_coherent_focus_does_not_reduce_nominal_target_below_baseline` | continuous nominal target 不差于 No RIS |
| FND-T04 | `test_quantized_common_offset_beats_unshifted_candidate` | finite-bit 候选精确包含 `delta=0`，同一 nominal objective 下不差于未偏置候选 |
| FND-T05 | `test_zero_baseline_focus_has_deterministic_fallback` | baseline 近零不产生 NaN/不稳定 angle |
| FND-T06 | `test_commanded_pattern_rejects_off_grid_phase` | 1/2/3/4-bit 非法状态抛错 |
| FND-T07 | `test_commanded_pattern_accepts_modulo_equivalent_states` | `2π` 等价和浮点容差正确 |
| FND-T08 | `test_actual_phase_error_is_not_requantized` | Ground Truth 误差完整进入传播 |
| FND-T09 | `test_effective_pitch_changes_without_resizing_aperture` | 改 nx/ny 只改变派生 pitch；改 fc 不改尺寸 |
| FND-T10 | `test_search_levels_are_distinct_from_hardware_bits` | continuous search 可配置、离散候选合法 |
| FND-T11 | `test_pending_parameters_block_optimize_until_apply` | UI 不用旧模型静默优化 |
| FND-T12 | `test_generation_customized_is_display_only` | 数据 generation 保持合法 preset 值 |
| FND-T13 | `test_default_profile_matches_v01_reference_components` | 默认 Profile 分路径复信道等价 |
| FND-T13b | `test_profile_is_used_by_all_environment_path_roles` | direct、reflection 和 RIS 两段均不能绕过 Profile |
| FND-T14 | `test_profile_identity_changes_with_version_or_parameters` | 影响系数的 Profile 版本/参数改变稳定身份，供未来 cache key 使用 |
| FND-T15 | `test_experiment_schema_records_model_provenance` | 结果可判断 focus/profile/search/model version |

物理/算法实现完成后至少运行：

```powershell
python -m pytest
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Advanced --quality fast
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Future --quality fast
```

实验迁移完成后在新目录运行 Phase Resolution；不得覆盖 v0.1 legacy 输出。GUI 变更按
[gui_spec.md](gui_spec.md) 的人工清单验收，并记录未执行项。

现有 `test_fixed_aperture_subdivision_converges_without_cell_gain` 继续作为面积归一化和细分不发散
保护，不把它升级成“粗 control patch 已达到物理收敛”的证据。真正的验证属于 P1C：新增独立
quadrature grid，在固定 control grid/pattern 下逐级细化，至少比较复数相对误差
`|h_2q-h_q|/max(|h_2q|,h_floor)` 和 `20*log10(|h_2q|/|h_q|)`，并要求连续细化趋势改善。
工程容差必须由代表性近场、远场、斜入射和遮挡边缘实验建立，不能在 Foundation 预设通用
`0.2 dB` 阈值。

## 11. 实验、兼容和版本策略

### 11.1 历史结果

当前 `results/phase_bits` 测量的是 v0.1 RIS-only Focus。Foundation 后它仍是合法历史结果，
但不能与 Coherent Target Focus 的绝对 dBm/gain 直接混合。原则：

- 不覆盖、不伪造新字段、不回填未经记录的默认值；
- 在 `results/README.md` 标明 legacy model contract；
- 新输出使用版本化目录或 run ID；
- 报告趋势时同时声明 Focus mode、Profile、phase bits、search levels 和 seed。

### 11.2 公共 API

- 旧 RIS-only 行为必须有明确公开名称；
- 若 `generate_focus_pattern` 改变默认语义，应提供兼容/弃用策略并记录 ADR；
- validator 的异常类型和 tolerance 属于公共错误契约；
- PropagationProfile 的引入优先保持 `SimulationEngine.compute_channel/field_map` 的主调用方式
  可迁移，避免让 GUI、CLI 和实验同时大改。

### 11.3 Scene Schema

仅新增可选且有确定语义的字段时，才考虑保持 v1 向后兼容。Profile 若改变场景解释，必须明确：

- 缺失字段的默认行为；
- 保存/加载 round-trip；
- 未知 Profile 的拒绝行为；
- 是否需要 schema version 升级；
- 老场景如何映射到 `IndoorDeterministicProfile`。

Foundation 不向 Scene v1 写入 `design_frequency_hz`；该问题已 Deferred，不属于本次 schema
兼容选择。

## 12. 风险、检测和安全回退

| 风险 | 检测方式 | 安全回退 |
|---|---|---|
| 新 Focus 改变演示和实验绝对数值 | Current/Advanced/Future reference + provenance diff | 保留 RIS-only 模式，版本化新默认 |
| 公共 offset 搜索变慢 | 单目标计时和候选数记录 | continuous 解析对齐；离散使用有限候选/边界方法 |
| validator 误拒绝浮点合法相位 | modulo/tolerance 性质测试 | 调整有理论依据的 tolerance，不 silent quantize |
| `nx/ny` 语义仍被误读为 meta-atoms | UI 文案、Model Info、报告检查 | 显示 Equivalent Patch 和限制说明 |
| 相位跨度或网格细分被误称为物理有效性证明 | 文案审查、P1C 独立求积测试 | Foundation 只作 advisory；不设无来源硬阈值 |
| Customized 污染 generation schema | JSON round-trip、枚举校验 | Customized 仅作派生显示 |
| Profile 抽象过度设计 | 默认 Profile 代码规模和依赖审查 | 只保留最小 protocol/strategy，不建插件系统 |
| Profile 接入造成数值漂移 | 分路径 complex reference comparison | 继续调用原 physics 纯函数，逐步迁移编排 |
| Profile 与 RIS 公式重复计算距离损耗/相位 | path-response 契约测试和分量对照 | ADR 明确 full transfer 或 environment modifier，禁止混用 |
| 新实验覆盖旧结果 | 输出目录存在检查、metadata test | 默认拒绝覆盖或创建新 run 目录 |
| Foundation 扩展到新场景/衰落/MIMO | Work Item scope review | 移回 roadmap，不在当前分支实现 |

回退不能通过删除失败测试、放宽无物理依据阈值、恢复隐藏增益或把错误行为改名来完成。

## 13. ADR、提交和评审顺序

### 13.1 候选 ADR

编号在文件创建时按 [decisions.md](decisions.md) 登记，本文不以标题代替正式决定：

1. Physics Focus objective、baseline phase alignment 与 model-based optimizer 分层；
2. Equivalent controllable aperture patch semantics；
3. PropagationProfile ownership、path-response 语义、identity 和 Scene binding。

Commanded validation、search levels 和 GUI dirty state 如果不改变层依赖/schema major，可作为
上述 ADR 的后果和 requirements 实现；若评审发现存在新的高影响选择，再单独建 ADR。

### 13.2 建议集成顺序

以下是依赖顺序，不要求与 L4 Task 或最终 commit 数量一一对应：

1. `docs: freeze focus, equivalent-patch and profile contracts`
2. `feat: add coherent target focus with contract tests`
3. `feat: enforce commanded hardware states with contract tests`
4. `feat: separate hardware and search resolution`
5. `ui: clarify applied state, pattern metadata and ground-truth labels`
6. **A/B checkpoint：暂停功能扩展并完成人工复核**
7. `refactor: introduce default propagation profile`
8. `experiment: add minimum foundation provenance`
9. `docs/qa: close foundation evidence and status`

可以在本地 TDD 过程中先看到红灯，但不得把“只有失败测试”的提交作为可交付历史推送或合并；
测试应与最小实现组成绿色提交，或在合并前 squash。每个交付提交必须可评审、测试通过并更新
对应文档状态。不得为了凑固定 commit 数量拆坏原子变更，也不得在一个提交中夹带 City 场景、
缓存矩阵或 GUI 重设计。

## 14. Entry Gate、Exit Gate 和完成证据

### 14.1 Foundation Global Entry Gate

开始任何代码实现前必须满足：

- `AMF-RIS-008..010`、`AMF-OPT-004`、`AMF-SIM-005`、`AMF-UI-007..008`、
  `AMF-EXP-006` 已在 requirements 中保持 Planned/Ready；
- 当前要进入的子 Capability 对应 ADR 选项、影响和否决方案已评审；
- 第 10 节相关行为测试已经设计；红灯可存在于本地 TDD 过程，但交付 commit 必须保持绿色；
- 明确旧实验、公共 API 和 Scene v1 的兼容策略；
- 当前 v0.1 完整 pytest 与 headless baseline 有记录；
- 工作项不包含 P1A、新场景、MIMO 或随机 fading。

### 14.2 Foundation 0.1.1A Exit Gate

- 两个 Focus 名称、objective 和退化行为一致；
- commanded validator 覆盖 `compute_channel`、`compute_field_map` 和仍声明为公共的低层散射
  入口；Field Map 不在每个像素重复验证；
- equivalent patch 语义和限制进入规范；
- 物理性质测试与三代 headless 通过；
- 旧行为差异有 ADR 和版本记录。

### 14.3 Foundation 0.1.1B Exit Gate

- hardware/search resolution 分离并可追踪；
- GUI pending/apply/Optimize/preset 状态不歧义；
- Pattern 元数据、图例和误差标签准确；
- GUI smoke 和人工清单通过；
- A/B checkpoint 临时结果进入隔离目录且不覆盖 legacy；在 C2 provenance 完成前不得作为正式
  Foundation 实验发布。

### 14.4 A/B Interim Checkpoint

- 完整 pytest 与 Current/Advanced/Future 三代 headless 通过；
- GUI Pending/Apply/Optimize、Pattern Source、Allowed/Used States 和两个 Ground Truth 标签经
  人工清单验收；
- Phase Resolution 只在新隔离目录复算，明确标注 checkpoint/非正式 provenance；
- 项目维护者和物理审查者共同确认 Focus objective、Commanded/Actual 边界和 GUI 表达无歧义；
- 该 checkpoint 允许评审 A/B 演示，但不把整个 Foundation 标为 Verified，也不解除 P1A 门禁。

### 14.5 Foundation 0.1.1C and Final Exit Gate

- 默认 IndoorDeterministicProfile 可复现 v0.1 reference 物理组件；
- direct、reflection、RIS incident/scattered path roles 均经过同一 Profile 契约，且没有与 RIS
  距离扩散/相位公式重复计算；
- Profile identity/version/parameters 有稳定契约；
- Controller/GroundTruth、RIS 和 Profile 职责没有互相吞并；
- Scene/schema 决策和迁移策略完整；
- P1A cache key 所需 identity 已冻结；
- FND-T15、最小 experiment provenance、legacy 标记和 no-overwrite 规则完成；
- requirements、ADR、README、roadmap、status 和测试证据闭环。

全部完成后，Foundation Capability 才能由 Implemented 经人工验收升为 Verified，P1A 才能
进入 In Progress。

## 15. 后续路线

Foundation 之后按以下顺序推进：

1. **P1A Geometry Cache and Matrix Evaluation**：在稳定 Profile/geometry/pattern contract 上
   做数值等价的性能优化；
2. **P1B Phase Error Robustness**：多 seed 比较 RIS-only、Coherent、Feedback 和
   Physics-Guided，报告分位数；
3. **P1C Aperture Sweep and Quadrature Validity**：除固定控制网格/固定等效密度实验外，拆分
   control grid 与 integration/quadrature grid；固定命令只细化求积，建立复数误差和功率差的
   适用域证据；
4. **v0.2 XR**：先定义动态时间、人体阻挡和对应 Profile 行为；
5. **v0.3 Factory**：多 RX、多 RIS、objective 和 pattern ownership；
6. **v0.4 City/Low-Altitude**：城市几何、NLoS、车辆/UAV 和独立传播 Profile；
7. 后续再考虑 fading、MIMO、OFDM、active/STAR RIS 和全波/测量校准。

一个 Profile 接口的存在不表示这些场景模型已经实现；每个新场景仍必须先完成有来源、可测试
的 headless 物理纵向切片。

## 16. 新开发者开始工作前的检查单

- [ ] 我能解释 AirMirror Future 为什么是系统级近似而不是全波求解器；
- [ ] 我知道 v0.1 当前 Focus 是 RIS-only，而 Coherent Target Focus 仍是 Planned；
- [ ] 我知道 `nx/ny` 当前同时承担控制和求积离散，不能直接称真实 meta-atoms；
- [ ] 我知道现有 8/16/32 测试保护面积归一化/不发散，不证明粗 patch 已物理收敛；
- [ ] 我知道 Commanded 与 Actual 的区别，且误差不能被重新量化；
- [ ] 我知道 `phase_bits` 与 `search_levels` 是不同维度；
- [ ] 我知道 Generation 是 preset 来源，Customized 只能是派生显示；
- [ ] 我知道 Controller/GroundTruth 与 PropagationProfile 职责不同；
- [ ] 我确认没有在 Foundation 中实现缓存、新场景、MIMO 或 fading；
- [ ] 我已找到 requirement ID、ADR 触发条件、测试和 Exit Gate；
- [ ] 我会在同一变更中同步 requirements、规范、测试和 DEVELOPMENT_STATUS。

## 17. 已关闭与仍需 ADR 决定的问题

已关闭：Foundation 0.1.1 不向 Scene v1 加入 `design_frequency_hz`，保持 Deferred，等待真实
RIS 频率响应模型触发新的 ADR。

以下问题在正式实现前不得由单个开发者静默选择：

1. `generate_focus_pattern` 保持旧语义、弃用，还是指向新的 GUI 默认算法；
2. 有限 bit 公共 offset 使用固定角度网格、量化边界候选还是等价解析方法；
3. baseline 近零、RIS 近零和多 RIS 场景的确定性退化行为；
4. Foundation advisory phase-span 使用角点/边中点、局部梯度还是仅展示 pitch；真正的
   quadrature convergence 固定进入 P1C，不再作为本项选择；
5. PropagationProfile 由 Scene 持有、scenario 注入还是 engine 显式参数传入，以及 path
   response 返回 full transfer 还是 environment-only modifier；
6. continuous Physics-Guided 是否允许连续 initial 与离散搜索结果混合；
7. 历史结果目录的版本命名和默认覆盖策略。

未决项存在不表示计划阻塞；它们是对应 ADR/Work Item 进入 Ready 前必须关闭的选择。
