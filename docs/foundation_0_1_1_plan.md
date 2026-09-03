# Foundation 0.1.1：物理模型契约与改进计划

| 属性 | 值 |
|---|---|
| 文档状态 | Operational / Normative for sequencing |
| 当前实现基线 | v0.1 Verified，commit `edfa43c` |
| 目标版本 | v0.1.1 Foundation |
| 当前计划状态 | Foundation 0.1.1 In Progress；Foundation 0.1.1A、A1/A2/A3、FND-FIX-WALL、B1/B2/B3 Verified；C、FND-QA-AP、FND-PHY-NB、FND-QA-CC 尚未完成 |
| 父级路线 | v0.1 Smart Space → Foundation 0.1.1 → P1A |
| 主要责任 | 项目维护者、物理仿真负责人、GUI/测试负责人 |
| 最后复核 | 2026-09-03（Foundation 0.1.1B verification/status closure；Profile ownership 仍以 ADR-0012 为准） |

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

Foundation 前置有八个直接原因：

1. **优化目标尚未对齐**：当前 Focus 最大化 RIS 自身相干幅度，但规范目标是单 RX 总接收
   功率。即使某个场景中的数值收益很小，objective contract 仍必须正确，不能把一次演示增益
   当成采用新算法的理由或验收阈值。
2. **v0.1 的 RIS 网格语义未冻结**：`nx/ny` 同时参与独立相位控制和孔径数值离散。A2 已用
   ADR-0007 冻结 equivalent patch 语义；未来缓存必须遵守该决定和拆网格触发条件。
3. **Pattern 硬件边界不完整**：Phase Bits 目前约束 pattern 生成器和优化候选，但传播入口
   只检查长度，不能阻止非法离散命令进入 1-bit/2-bit RIS。
4. **传播模型没有 Profile 身份**：未来不同场景若都进入同一引擎，缓存无法区分环境模型
   或参数版本；先稳定 Profile 契约才能定义可信的缓存失效规则。
5. **待缓存的孔径系数尚无独立求积有效性证据**：当前每个 control patch 只取一个中心点；
   一次隔离审计已观察到默认目标链路存在约 `0.430–0.848 dB` 的幅度差，但该结果尚未经过
   版本化 runner、代表性矩阵和正式 provenance。P1A 前必须通过 FND-QA-AP 冻结 `a_n` 的
   production quadrature policy，不能先缓存再验证。
6. **墙体 z 语义与误差维度冲突（已由 FND-FIX-WALL 实现闭环）**：实现前墙面求交按绝对
   `[0,height]` 处理而忽略端点 z，Ground Truth 却对墙应用三维 position delta。默认 z=0 场景
   可运行，但这种偶然兼容不能描述成已定义的三维墙模型。
7. **中心频率/带宽语义未形成稳定身份**：当前只计算 `h(fc)`，带宽只进入 noise 和 Shannon
   公式；若不显式冻结 flat-channel 近似，100 MHz 容易被误读为已完成宽带/OFDM 仿真。
8. **Focus 与待缓存 coefficient 可能在未来分叉**：当前 1×1 实数 modifier 下中心路径 Focus 与
   复系数相位共轭等价；复杂 Profile 或多点 quadrature 后不必然等价，必须在 P1A 前证明
   Controller simulator 和 Focus 共享同一 `a_n^C`。

审计备注：commit `edfa43c` 的默认 Smart Room 中，1-bit pattern 加入公共相位 offset 后，
目标点曾比现有 RIS-only Focus 改善约 `5.02 dB`。该数值只说明 objective 错位具有可观测影响，
不得进入跨版本门禁；目标算法落地后应由带 model provenance 的新基准取代。

因此本阶段顺序固定为：

```text
v0.1 Verified
  → Foundation 0.1.1A：物理与算法契约
  → FND-FIX-WALL：floor-anchored wall geometry closure
  → Foundation 0.1.1B：优化器与 GUI 语义
  → A/B Interim Checkpoint
  → Foundation 0.1.1C：PropagationProfile 接口
  → FND-QA-AP：Minimum Aperture Quadrature Validity
  → conditional production quadrature migration（仅当 QA 要求）
  → FND-PHY-NB：Narrowband Frequency Contract
  → FND-QA-CC：Controller Coefficient Consistency
  → Foundation Final Exit Gate
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
- 将 Foundation Profile 冻结为 environment-only modifier，不重复 Friis/RIS carrier；
- 冻结 v1 Wall 为 floor-anchored vertical wall，并只施加刚体 XY Ground Truth 偏移；
- 明确 `frequency_hz=fc`、`bandwidth_hz=B` 和 center-frequency flat-channel capacity 语义；
- 在 Foundation final exit 前固定 aperture/control/pattern、只细化独立 quadrature，确定
  control-level `a_n` 的 production policy、声明适用域和 cache identity；
- 证明 RIS-only/Coherent Focus 与最终 Controller simulator 使用同一 `a_n^C`，且 Ground Truth
  coefficient 不泄漏；
- 为后续 cache、统计实验和场景扩展提供稳定的 ID、版本和结果 provenance。

### 4.2 非目标

本阶段明确不实现：

- XR、Factory、City、Tunnel、UAV 或模块化建筑的可运行场景；
- Rayleigh/Rician fading、log-normal shadowing、Doppler、宽带抽头或 OFDM；
- MIMO/MISO/SIMO、波束赋形或多流；
- 真实 meta-atom、互耦、材料色散、极化或全波模型；
- 自动把 RIS 实体尺寸绑定运行频率；
- P1C 的完整 aperture sweep、convergence map、field-map quadrature research 或空间分辨遮挡；
- 预先指定 `16×16 everywhere`，或在没有预注册适用域/容差时静默改变 production quadrature；
- frequency-selective channel、PathEnsemble、delay spread、beam squint 或宽带容量积分；
- 悬空/倾斜墙、墙厚、多层楼板或空间分辨 aperture blockage；
- P1A 几何矩阵缓存、增量 Greedy 或性能重写；
- 对历史实验结果进行无版本覆盖。

### 4.3 成功定义

本阶段不是以“新增文件或按钮”判定完成，而以以下用户结果判定：

- 新开发者能从文档判断当前 Focus 与目标 Focus 的差异；
- 任意 pattern 在进入传播前都能证明符合目标 RIS 的 commanded hardware states；
- 用户能看到当前应用中的 Phase Bits、搜索状态数、Pattern 来源和是否有未应用参数；
- 当前 Smart Room 可由默认 Profile 重放，结果变化均能解释为已接受的算法变化；
- 新增 Profile 或缓存时不需要重新定义 Scenario、Ground Truth 和 RIS 的职责；
- 新增缓存前能证明它缓存的 `a_n` 来自已签署的 quadrature policy；若候选 policy 不通过，
  Foundation 保持 In Progress 而不是降低阈值；
- 同一个最终 production policy 下，Focus 与 Controller channel 对 `a_n^C` 的定义没有分叉；
- 使用者能从标签和 provenance 判断结果是 `h(fc)` 的 flat-channel 上界，而不是 OFDM/真实吞吐；
- Wall 的 z/height/position error 不再存在“字段被接受但计算忽略”的歧义；
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

A2 通过 ADR-0007 把 `nx/ny` 冻结为：

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

A2 已新增公共纯派生 helper，B 阶段可将其接入只读显示：

- `effective_pitch_x = width / nx`；
- `effective_pitch_y = height / ny`；
- operating wavelength；
- `pitch_x / wavelength`、`pitch_y / wavelength`。

这些值是透明度信息，不得把 `pitch > wavelength/2` 直接判为系统级模型错误。A2 明确不
输出“离散过粗”结论或 patch 内 phase-span：可靠数值还需要定义角点/求积采样、二阶 Fresnel
曲率、幅度变化、方向图和遮挡边缘处理。本阶段不得设置无来源的 `45°`、`0.2 dB` 等全局
硬阈值。

当前 8×8→16×16→32×32 测试同时增加中心求积点和独立 commanded phase 自由度，只保护
面积归一化、结果稳定趋势和“不随 patch 数无界增益”，不能证明粗 patch 已达到物理/求积
收敛。`AMF-RIS-005` 的验收措辞按这一边界解释，不得简称为独立 quadrature convergence。

数值有效性分成两层：

1. **Foundation FND-QA-AP 最小门禁**：在 final exit/P1A 前固定实体孔径、control grid、
   commanded pattern、Profile 和几何，只细化每个 control patch 内的 quadrature rule/order；
   使用 successive refinement、独立求积规则和代表性矩阵，冻结 production `a_n` policy、
   identity/version 和声明适用域；
2. **P1C 完整研究**：在最小 policy 已冻结后扩展 aperture/density/control-count、field-map、
   phase-span、frequency/angle/near-field sensitivity 和更广适用域，不承担 P1A 前置系数定义。

内部最后稳定层级只能称为 internal refined numerical reference，不是 Ground Truth、EM truth、
full-wave 或 measurement。求积细化时禁止重新生成 Focus；否则会重新混合控制自由度与数值积分
精度。完整决定见 [ADR-0008](adr/0008-minimum-aperture-quadrature-validity-gate.md)。

当前 production 仍是每 patch `1×1` midpoint。本计划不依据一次审计立即改成 `16×16`；正式
QA 根据预注册容差决定保留 1×1、采用某个低阶固定 policy、建立适用域相关 policy，或阻断
Foundation。partial-aperture blockage 不属于该门禁；当前 RIS center scalar attenuation 不能
因 quadrature refinement 被描述为空间分辨遮挡。

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

Position Error 会为 TX、RX、RIS、每堵墙和每个 obstacle 生成三维固定 delta，因此 GUI 总标签
仍改名为：

- `Geometry Position Error σ / 几何位置误差 σ`。

FND-FIX-WALL 已冻结消费边界：wall geometry 按 endpoint XY 和绝对 `[0,height_m]` 处理，engine
只消费该三维 delta 的 XY 分量，并把同一个刚体偏移用于两个端点。因此 B3 最终 tooltip 必须
说明：TX/RX/RIS/obstacle 按各自三维模型处理；v1 floor-anchored wall 仅使用同一个刚体 XY
偏移。不能再笼统声称每类实体均有三维位置误差。

当前 Measure Noise 只作用于 Measurement Oracle，因此改名为：

- `Feedback Measurement Noise σ / 反馈测量噪声 σ`。

本阶段不拆多个独立 sigma 字段。`AMF-SIM-006` / FND-FIX-WALL 只修正了 wall 的消费语义和验证，
未新增 Scene 字段；未来悬空墙、楼板或独立位置误差确有需要时再通过 schema/ADR 评审。

### 5.7 PropagationProfile 契约

目标职责分离：

```text
Scenario / Scene
  → Physics Kernel: Friis carrier / propagation phase
  → Reflection Model: image geometry / Gamma_wall
  → PropagationProfile: direct and per-leg environment modifiers
  → RIS Model: aperture / direction / commanded-or-actual reflection state
  → coherent effective channel
  → received power / noise / SNR

Controller Model / Ground Truth Model
  → describes nominal-vs-truth uncertainty
  → does not choose the environment propagation law
```

Foundation 只实现或设计一个默认 `IndoorDeterministicProfile`，让 engine 在不改变 v0.1 Friis、
一次墙反射、几何阻挡和有限孔径 RIS 数值的前提下抽出环境 modifier。Profile 必须有：

- 稳定 ID；
- model/profile version；
- 可序列化或可稳定哈希的参数摘要；
- 明确职责，不成为包含 Scene、Ground Truth、RIS、噪声和 GUI 的 God object；
- 默认行为与 v0.1 reference 在声明容差内一致。

Profile 必须一致参与 direct path、每条 wall-reflection 的 before/after legs、TX→RIS incident leg
和 RIS→RX scattered leg；不能只替换 direct path 而让 RIS 或反射路径段绕过环境规则。一次墙
反射必须保持以下唯一分解：

```text
h_wall = h_FS(L_reflection) * Gamma_wall * m_before_env * m_after_env
```

其中 Reflection Model 拥有反射几何和 `Gamma_wall`，Profile 只拥有两段 environment modifier，
且反射墙自身必须从两段 blocker 查询中排除；不得再返回包含墙系数的聚合
`wall_reflection` multiplier。
同时：

- Physics Kernel 负责 Friis carrier/传播相位，Reflection Model 负责反射几何/墙系数，Profile
  负责环境 modifier，RIS model 负责孔径、方向图、效率和 commanded/actual phase；
- ADR-0012 已冻结 Profile path response 为“自由空间/几何 carrier 和 `Gamma_wall` 之外的
  environment-only complex modifier”，不得包含重复的距离扩散、传播相位、天线 gain、墙面
  复反射系数或 RIS device response；
- Foundation 初次接入保持 v0.1 的 RIS 面板中心阻挡近似，以便分路径等价复现；逐 patch
  阻挡是独立物理改进，不能夹带进 Profile 重构；
- 最小接口可使用小型 Protocol/strategy 和有限 path-role context，不建立插件注册中心、通用
  射线图 DSL、事件总线或 provider system。

ADR-0012 同时冻结：Foundation 不修改 Scene JSON v1；Profile 由 `SimulationEngine` 构造时注入，
缺省为 `IndoorDeterministicProfile`。不得把 Python 类名直接作为持久化协议。未来 cache key 至少
分层包含稳定的 profile ID/version/canonical parameters、Reflection Model ID/version、墙几何/
名义反射参数、所选 world model 的有效墙状态，以及所有其他影响系数的场景状态。墙系数不进入
`profile_identity`，但不能从总体 coefficient/world-model identity 省略。能够生成 delay/angle/
Doppler 多路径集合的 PathEnsemble 是后续独立能力，不能把 Profile modifier 静默扩成 God object。

### 5.8 中心频率窄带与容量契约

当前实际计算只在 `frequency_hz=fc` 处产生复信道，并把该值视为 `bandwidth_hz=B` 内的平坦
响应。`B` 只进入 noise、SNR、coverage 与 `B*log2(1+SNR)`；它不会生成子载波或频率轴。
Foundation 按 ADR-0010 冻结：

- 修改 `fc` 重算 `lambda/k`、所有路径相位和 aperture diagnostics；
- 只修改 `B` 不改变 `h(fc)`，但重算 link metrics；
- capacity 的准确标签是 center-frequency flat-channel Shannon upper bound；
- provenance 使用 `channel_frequency_model_id=narrowband_center_frequency_flat_v1`；
- Scene v1 不新增该 identity 字段，legacy 结果不伪造回填；
- 不以无来源的固定 `B/fc` 或 `B*delay` 阈值冒充场景有效性证明。

完整执行由 [FND-PHY-NB](work_items/foundation_0_1_1_narrowband_contract.md) 负责；本计划不实现
OFDM、beam squint、`Gamma(f)` 或 frequency-selective fading。

### 5.9 Controller coefficient 与 Focus 一致性

Foundation 最终 production policy 下的内部目标形式为：

```text
a_n^C = sum_q w_nq*K_geom(r_nq)*m_in^C(r_nq)*m_out^C(r_nq)
Gamma_cmd,n = sqrt(eta_nominal,n)*exp(j*phi_cmd,n)
h_RIS^C = sum_n a_n^C*Gamma_cmd,n
```

RIS-only Focus 使用 `-arg(a_n^C)`，Coherent Focus 使用
`arg(h_baseline^C)-arg(a_n^C)` 并继续遵守 ADR-0006 的 finite-bit 搜索。Ground Truth 使用
`a_n^GT/Gamma_actual`，只能通过 oracle 反馈，不能进入 model-based Focus。

该分解首先是内部所有权契约，不改变 public phase-array API，不授权改变 efficiency/area 数值。
FND-QA-AP 先决定 quadrature policy：若保持 1×1，则用测试证明当前中心路径实现等价；若采用
多点或复相位 modifier，则必须先完成独立 production migration，让 simulator 与 Focus 共享同一
coefficient builder。最后由 [FND-QA-CC](work_items/foundation_0_1_1_coefficient_consistency.md)
签署一致性。该门禁不重开 A1/A2，也不实现 P1A cache。

## 6. Requirement 映射

本计划对应以下 requirement IDs，权威状态见 [requirements.md](requirements.md)：

| Requirement | 目标 |
|---|---|
| `AMF-RIS-008` | 区分 RIS-only 与 Coherent Target Focus，并对齐 nominal objective |
| `AMF-RIS-009` | 冻结 equivalent controllable patch 语义和有效 pitch 透明度 |
| `AMF-RIS-010` | 在传播前验证 commanded hardware states |
| `AMF-RIS-011` | 在 Foundation final exit/P1A 前验证独立求积并冻结 coefficient policy |
| `AMF-RIS-012` | 最终 production policy 下对齐 Controller coefficient、Focus 与 simulator |
| `AMF-OPT-004` | 分离 hardware phase resolution 与 optimizer search levels |
| `AMF-SIM-005` | 建立 PropagationProfile 和默认 IndoorDeterministicProfile |
| `AMF-SIM-006` | 冻结 floor-anchored Wall 和 XY-only rigid Ground Truth perturbation |
| `AMF-PHY-007` | 冻结 center-frequency flat-channel、容量标签与模型身份 |
| `AMF-UI-007` | 建立 pending/apply/preset/customized 状态语义 |
| `AMF-UI-008` | Pattern 元数据、相位图例和准确 Ground Truth 标签 |
| `AMF-EXP-006` | 实验分开记录 focus/profile/reflection/model/search provenance，保留历史可比性 |

这些 requirement IDs 的状态必须按各自实现与验收证据更新，不得因本文的汇总表述整体提升。

## 7. Capability 和 Deliverables

### 7.1 Foundation 0.1.1A — Physics and Algorithm Contract

状态：**Verified（2026-09-03）**；A1/A2/A3 均已 Verified，§14.2 Exit Gate 与依赖均满足。

#### Deliverable A1：Focus objective ADR

- 状态：**Verified（2026-09-02）**；验收依据 commit `87495ec`，G0–G8 PASS，
  blocking issues 0；Foundation 0.1.1A 现为 Verified，A2/A3 亦已 Verified；

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

- 状态：**Verified（2026-09-02）**；验收依据 implementation commit `974885fc5b1864ecd9c303e56400308cbaa316fa`，
  G0–G8 PASS，blocking issues 0；A2 的剩余 GUI/只读接线已由 B verification closure 补齐，
  `AMF-RIS-009` 当前为 Verified；
- Requirement：`AMF-RIS-009`；
- 输入：`width/height/nx/ny/frequency`；
- 输出：术语、派生 pitch/波长比例、适用性说明和未来拆网格触发条件；
- 文档：ADR、data model、physics、limitations、GUI spec；
- 代码：纯派生 helper，不改变现有实体孔径事实源；
- 验收：固定孔径细分不产生无界 patch-count gain；改变 operating frequency 不改变实体宽高；
  UI/结果不把 patch 宣称为真实 meta-atom；`pitch/wavelength` 只作透明度信息；A2 明确不
  输出未验证的 phase-span，也不声称已完成独立 quadrature convergence。
- 实现证据：[ADR-0007](adr/0007-equivalent-controllable-aperture-patches.md)、
  [A2 Work Item](work_items/foundation_0_1_1_a2.md)、`tests/test_aperture_diagnostics.py`；
- 兼容结果：Scene v1、散射公式、GUI/CLI 默认和代际 preset 数值不变；GUI 只读诊断接入
  已在 B verification closure 中完成，`AMF-RIS-009` 不再保留为待接线状态。

#### Deliverable A3：Commanded Pattern hardware boundary

- 状态：**Verified（2026-09-03）**；implementation commit
  `fb5ec093e78e588a65a661abf3b32d744d04ae04` 已完成独立人工验收，G0–G8 PASS、blocking
  issues 0；工作范围与 Ready/Done/verification 证据见
  [A3 Work Item](work_items/foundation_0_1_1_a3.md)；
- Requirement：`AMF-RIS-010`；
- 输入：RIS、commanded phase array；
- 输出：统一验证函数、公共错误契约和所有入口调用；
- 预计文档：public API、physics、data model、test strategy；
- 实现代码：公共 ownership/导出保持在 RIS pattern API；共享纯 validator 位于
  `core/pattern_contract.py`，并接入 `compute_channel`、`compute_field_map` 和保留为公共 API 的
  低层散射入口，从而遵守 physics 只依赖 core 的分层方向；
- 验收：离散非法状态失败、模 `2π` 等价状态通过、continuous finite 通过、Actual error 不被
  再量化。
- 兼容结果：Scene JSON v1、Focus、散射公式和合法既有 pattern 数值不变；新增错误只针对此前
  会被静默接受的未知/歧义 RIS key、非一维/非有限/off-grid command 和非法 phase-bits 类型。

### 7.2 Foundation 0.1.1B — Optimizer and GUI Semantics

#### Deliverable B1：Search resolution contract

- 状态：**Verified（2026-09-03）**；B1 自动回归、§14.3 hardware/search gate 与外部
  independent review 均 PASS，blocking issues 0；详见 [B Work Item](work_items/foundation_0_1_1_b.md)；
- Requirement：`AMF-OPT-004`；
- 输入：hardware phase bits、search levels、initial pattern；
- 输出：显式 optimizer 参数、结果元数据和 CLI/GUI 文案；
- 预计文档：optimization、public API、experiment spec；
- 预计代码：`optimization/greedy.py`、`physics_guided.py`、worker/CLI wiring；
- 验收：离散硬件候选全部合法；continuous 的候选数可配置且被记录；固定 seed 可重放。

#### Deliverable B2：Pending/apply/preset state

- 状态：**Verified（2026-09-03）**；B2 GUI offscreen/真实 GUI 人工清单与 §14.3 state gate 均 PASS，
  blocking issues 0；详见 [B Work Item](work_items/foundation_0_1_1_b.md)；
- Requirement：`AMF-UI-007`；
- 输入：当前 applied Scene、编辑控件、generation preset；
- 输出：dirty 状态、Apply/Optimize 门禁、Customized 派生标签和覆盖提示；
- 预计文档：gui spec、data model、manual acceptance；
- 预计代码：`gui/main_window.py`，不得把传播公式复制到 GUI；
- 验收：编辑 Phase Bits 后 UI 明确 pending；未 Apply 不用旧值静默 Optimize；Apply 后 pattern
  和 worker version 同步；切换 preset 不无提示丢弃待应用值。

#### Deliverable B3：Pattern transparency and Ground Truth labels

- 状态：**Verified（2026-09-03）**；B3 metadata/label/legend 回归、真实 GUI 人工清单、RIS Gain
  visualization review 与 §14.3 label gate 均 PASS，blocking issues 0；详见
  [B Work Item](work_items/foundation_0_1_1_b.md)；
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
- 输出：不含 `Gamma_wall` 的 environment-only modifier Profile 协议、默认
  IndoorDeterministicProfile、engine 构造注入、稳定 identity/version；
- 预计文档：ADR、architecture、public API、scene schema decision、limitations；
- 预计代码：新的轻量 profile 模块和 `SimulationEngine` 编排调整；
- 验收：默认 Profile 在未改变 Focus 的 reference 模式下复现 v0.1 分路径复信道；direct、
  reflection before/after、RIS incident/scattered legs 均不能绕过 Profile；Reflection Model 独立且
  只应用一次 `Gamma_wall`，反射墙不作为自身路径 blocker；Profile 不依赖 GUI/optimizer，
  不吞并 carrier/墙系数/RIS device/Ground Truth/noise；profile identity 与 reflection/world-model
  identity 分层明确；Scene v1 不保存 Python 类名；未实现 Profile 明确拒绝而非回退。

#### Deliverable C2：Minimum experiment provenance

- Requirement：`AMF-EXP-006`；
- 输入：focus mode、profile ID/version、reflection model ID/version、channel frequency model ID、
  search levels、model/quadrature/coefficient contract version；
- 输出：Foundation 最小可解释实验 schema 和新的结果目录规则；
- 预计文档：experiment spec、test strategy、results README；
- 预计代码：实验字段和 schema test；
- 验收：旧 `results/phase_bits` 不被覆盖；新旧结果能通过字段判断采用何种 Focus 和 Profile；
  缺失 provenance 的历史文件被明确标记 legacy，而不是伪造默认值。

完整历史迁移工具、结果索引和统计报告治理可在 P1B 完善，但上述最小字段、legacy 标记和
不覆盖规则不得推迟到 P1B，也不能仅用 `results/v0.1.1/` 目录名代替。

### 7.4 Foundation Cross-Cutting QA — Aperture Quadrature Gate

#### FND-QA-AP：Minimum Aperture Quadrature Validity

- 状态：**Planned**；不改变 A2 Verified 或整个 Foundation In Progress 的当前边界；
- Requirement：`AMF-RIS-011`；
- 依赖：A2 Verified、ADR-0008 Accepted；正式执行依赖 A3/B/C Implemented 和 C2 provenance；
- 输入：固定 aperture/control grid/commanded pattern/Profile/geometry，候选 quadrature
  rule/order 和预注册容差；
- 输出：versioned QA matrix、internal refined numerical reference、误差/成本报告、最终
  `quadrature_policy_id/version` 或 blocking decision；
- 验收：FND-T16..18、三代最小矩阵、successive refinement 与独立求积规则交叉检查、无
  非有限/静默跳过、项目维护者和物理审查者共同签署；
- 边界：不重开 A2，不实现 partial-aperture blockage，不把内部 reference 称 EM truth，不
  顺带实现 P1A cache 或 P1C 完整研究；
- 详细契约：[ADR-0008](adr/0008-minimum-aperture-quadrature-validity-gate.md) 和
  [FND-QA-AP Work Item](work_items/foundation_0_1_1_qa_ap.md)。

### 7.5 Foundation Cross-Cutting Closure — Geometry, Frequency and Coefficients

#### FND-FIX-WALL：Wall Geometry Closure

- 状态：**Verified（2026-09-03）**；Requirement `AMF-SIM-006`；implementation commit `8841ef2`
  已完成独立人工验收，G0–G8 PASS、blocking issues 0；
- 依赖：v0.1 wall/blockage/reflection audit；可在 A3 后、B 前独立实施；
- 输入：Wall endpoint/height、Ground Truth position delta、Scene v1；
- 输出：floor-anchored wall、`start.z=end.z=0` 验证、同一刚体 XY perturbation；
- 验收：FND-T19、z=0 round-trip、阻挡/反射同几何和三代兼容回归；
- 边界：不实现悬空/倾斜墙、新 schema 字段或空间分辨 aperture blockage；
- 兼容结果：Scene v1 不升级；仓库唯一受支持 Scene 与历史均为 z=0，默认三代数值不变；外部
  超过 `1e-9 m` 的 endpoint z 现在以带迁移指引的 `ValueError` 明确拒绝；
- 详细契约：[FND-FIX-WALL Work Item](work_items/foundation_0_1_1_wall_geometry_closure.md)。

#### FND-PHY-NB：Narrowband Frequency Contract

- 状态：**Planned**；Requirement `AMF-PHY-007`；
- 依赖：ADR-0010 Accepted、C2 provenance 可用；
- 输入：`fc`、`B`、noise figure、center-frequency channel；
- 输出：flat-channel capacity 标签、`channel_frequency_model_id`、legacy 规则；
- 验收：FND-T20 与 GUI/CLI/实验人工文案检查；
- 边界：不实现频率轴、OFDM、delay spread、beam squint 或 `Gamma(f)`；
- 详细契约：[ADR-0010](adr/0010-narrowband-center-frequency-flat-channel.md) 和
  [FND-PHY-NB Work Item](work_items/foundation_0_1_1_narrowband_contract.md)。

#### FND-QA-CC：Controller Coefficient Consistency

- 状态：**Planned**；Requirement `AMF-RIS-012`；
- 依赖：C1 Profile、FND-QA-AP signed policy、FND-PHY-NB、必要时先完成独立 production migration；
- 输入：最终 `a_n^C`、`Gamma_cmd`、baseline、两种 Focus、Controller/GT boundary；
- 输出：Focus/simulator/QAP 一致性证据和分层 coefficient identity；
- 验收：FND-T21/T22、Ground Truth 不泄漏、identity mutation matrix、三代回归；
- 边界：不重开 A1/A2，不实现 cache，不让 Focus 读取 `a_n^GT`；
- 详细契约：[ADR-0011](adr/0011-controller-coefficient-focus-consistency.md) 和
  [FND-QA-CC Work Item](work_items/foundation_0_1_1_coefficient_consistency.md)。

## 8. L4 Tasks 和建议顺序

每项控制在约 0.5–2 个开发日。L4 Task 是追踪单元，不等于 Git commit；依赖满足的任务可并行，
但每项仍必须有独立状态和完成证据：

| 顺序 | Task | 状态 | 完成输出 |
|---:|---|---|---|
| 1 | `FND-DOC-01` 建立 Foundation objective/geometry/profile/frequency/coefficient ADR | Implemented | ADR-0006..0011 的决定、后果与否决方案 |
| 2 | `FND-DOC-02` 冻结 equivalent patch、诊断量和 Deferred 边界 | Implemented | ADR-0007、data/physics/limitations/API 同步；FND-T09 |
| 3 | `FND-TEST-01` 定义 Focus objective 契约测试 | Implemented | FND-T01..T05、错误契约、tie-break 和 1/2/3/4-bit 回归 |
| 4 | `FND-TEST-02` 定义 commanded pattern 契约测试 | Implemented | bits、modulo、tolerance、Actual error |
| 5 | `FND-PHY-01` 实现两个具名 Focus | Implemented | RIS-only 保留、Coherent 新增且分层正确；ADR-0006 |
| 6 | `FND-PHY-02` 实现 commanded validator | Implemented | 所有公共传播入口共用且 Field Map 只验证一次 |
| 7 | `FND-FIX-WALL` 冻结 floor-anchored Wall/XY perturbation | Verified | FND-T19、schema/error/compatibility evidence；独立验收 G0–G8 PASS |
| 8 | `FND-OPT-01` 增加 search levels 与结果元数据 | Implemented | `docs/work_items/foundation_0_1_1_b.md`；discrete/continuous 语义分离与 optimizer tests |
| 9 | `FND-UI-01` 建立 pending/apply/Optimize 门禁 | Implemented | `docs/work_items/foundation_0_1_1_b.md`；GUI smoke tests |
| 10 | `FND-UI-02` 增加 Customized、Pattern 信息和准确标签 | Implemented | `docs/work_items/foundation_0_1_1_b.md`；Pattern metadata/GUI smoke 与人工清单 |
| 11 | `FND-QA-AB` A/B 中期验收与人工复核 | Verified | 三代 headless、GUI、临时隔离实验和独立审查记录；§14.4 checkpoint PASS |
| 12 | `FND-ARCH-01` 接入 environment-only PropagationProfile | Planned | 全路径角色调用、当前分量等价复现、稳定 identity |
| 13 | `FND-EXP-01` 加入最小实验 provenance | Planned | versioned CSV/PNG、legacy 和 no-overwrite |
| 14 | `FND-QA-AP` 最小孔径求积有效性门禁 | Planned | FND-T16..18、versioned matrix、signed coefficient policy |
| 15 | `FND-PHY-NB` 冻结 center-frequency flat-channel contract | Planned | FND-T20、model ID 与准确标签 |
| 16 | `FND-QA-CC` 验证 Controller coefficient/Focus 一致性 | Planned | FND-T21..22、identity/boundary review |
| 17 | `FND-QA-01` 全量回归、headless、GUI 和实验验收 | Planned | Foundation final exit evidence |

若任务实际超过两天，应继续拆分；不得把“完成 ChannelProfile”与“实现城市传播模型”合并。

## 9. 预计文件影响

以下是规划范围，不表示每个文件都必须修改；实施者应在 Work Item 中确认最小变更集。

| 范畴 | 预计文件 | 目的 |
|---|---|---|
| 决策 | `docs/adr/0006-*.md` 至 `0011-*.md` | objective、patch、quadrature、Profile、narrowband、coefficient |
| 规范 | `physics_model.md`、`optimization_spec.md` | 目标算法和搜索/验证契约 |
| 数据/API | `data_model.md`、`public_api.md`、必要时 `scene_schema.md` | 派生值、错误、兼容策略 |
| 架构 | `architecture.md`、`limitations.md` | Profile、frequency/coefficient identity、适用域 |
| GUI | `gui_spec.md`、`glossary.md` | pending/customized/pattern/误差文案 |
| 实验 | `experiment_spec.md`、`results/README.md` | provenance 和历史结果保留 |
| 追踪 | `requirements.md`、`roadmap.md`、`DEVELOPMENT_STATUS.md` | 状态闭环 |
| 代码 | `ris/phase.py`、`simulation/engine.py`、`optimization/*`、`gui/*` | 后续实现，不在本文档提交中完成 |
| 测试 | `test_ris.py`、`test_scene_engine.py`、`test_optimization.py`、`test_gui_smoke.py`、`test_documentation.py` | 性质、集成、GUI 和 schema |

2026-09-03 的本轮 master-plan integration 仅修改 Markdown；不修改上表中的 Python、tests、GUI、
scene、results、cache、production quadrature 或 Focus。后续每个 Work Item 仍需按自己的授权范围
提交最小变更。

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
| FND-T13b | `test_profile_is_used_by_all_environment_path_roles` | direct、reflection before/after 和 RIS 两段均不能绕过 Profile；modifier 不含 carrier/`Gamma_wall` |
| FND-T13c | `test_wall_coefficient_and_profile_modifiers_are_applied_once` | 独立缩放 `Gamma_wall` 或任一 leg modifier，只产生一次对应幅度缩放 |
| FND-T13d | `test_reflecting_wall_is_excluded_from_reflection_leg_blockers` | 反射墙不同时成为自身 blocker，其他阻挡仍按对应路径段生效 |
| FND-T14 | `test_profile_identity_changes_with_version_or_parameters` | Profile identity 只跟随 Profile；墙系数另行失效总体 coefficient/world-model identity |
| FND-T15 | `test_experiment_schema_records_model_provenance` | 结果可判断 focus/profile/search/model version |
| FND-T16 | `test_quadrature_refinement_keeps_control_pattern_fixed` | series 中 aperture/control/pattern hash 不变，只改变 rule/order |
| FND-T17 | `test_quadrature_reference_uses_successive_and_cross_rule_evidence` | reference 不固定冒充 16×16 truth；未收敛 case 明确失败 |
| FND-T18 | `test_quadrature_report_guards_nulls_and_records_policy_identity` | 深相消不输出 Inf/误导 phase/gain；provenance 和 policy 完整 |
| FND-T19 | `test_floor_anchored_wall_uses_rigid_xy_truth_delta` | 非零 wall z 被拒绝；阻挡/反射共享 floor-anchor 与 XY 刚体误差 |
| FND-T20 | `test_narrowband_frequency_and_bandwidth_dependencies` | `fc` 重算 h；`B` 只改变 noise/link metrics；model ID 稳定 |
| FND-T21 | `test_ris_only_focus_matches_controller_coefficients` | 最终 policy 下 RIS-only Focus 与同一 `a_n^C` 相位共轭；1×1 保持兼容 |
| FND-T22 | `test_coherent_focus_uses_controller_simulator_coefficients` | Coherent objective 与 engine 共用 `a_n^C/h_b^C`，且不读取 Ground Truth |

物理/算法实现完成后至少运行：

```powershell
python -m pytest
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Advanced --quality fast
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Future --quality fast
```

实验迁移完成后在新目录运行 Phase Resolution；不得覆盖 v0.1 legacy 输出。GUI 变更按
[gui_spec.md](gui_spec.md) 的人工清单验收，并记录未执行项。

现有 `test_fixed_aperture_subdivision_converges_without_cell_gain` 继续作为面积归一化和 control-grid
细分不发散保护，不把它升级成“粗 control patch 已达到物理收敛”的证据。FND-QA-AP 必须新增
独立 quadrature grid，在固定 control grid/pattern 下逐级细化，并同时报告 absolute、robust
normalized complex error、幅度/功率差和有保护的 phase/RIS Gain。reference convergence 和
production adequacy 容差必须在正式结果前预注册；不得在失败后放宽。最小 QA 避开 partial
blockage boundary；P1C 再扩大 frequency/angle/near-field、field-map 和遮挡边缘适用域。

FND-T19 已独立关闭并验证 wall 几何语义，不把 z delta 映射成 wall height。FND-T20 只验证当前
center-frequency flat-channel 合同，不借机加入频率轴。
FND-T21/T22 必须在 FND-QA-AP 签署 production policy 后执行；若 QAP 要求多点 production，先
完成独立 migration，再验证 Focus、simulator 和 QA runner 共用 coefficient。FND-T20..22 仍为
Planned，不因文档测试设计而提前通过。

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
| 相位跨度或 control-grid 细分被误称为物理有效性证明 | 文案审查、FND-QA-AP/P1C 独立求积 | 保持 A2 语义与数值精度分层；不设无来源硬阈值 |
| P1A 缓存未验证的 center-point `a_n` | final gate 检查 AMF-RIS-011 和 policy identity | Foundation 不升 Verified，P1A 保持门禁 |
| 一次 16×16 结果被称为 truth | 术语/provenance 审查 | 只允许 internal refined numerical reference；需要 successive+cross-rule |
| quadrature 被误当空间分辨遮挡 | 遮挡 mode 与 geometry review | 最小 QA 避开边缘；per-sample blockage 另建能力 |
| Customized 污染 generation schema | JSON round-trip、枚举校验 | Customized 仅作派生显示 |
| Profile 抽象过度设计 | 默认 Profile 代码规模和依赖审查 | 只保留最小 protocol/strategy，不建插件系统 |
| Profile 接入造成数值漂移 | 分路径 complex reference comparison | 继续调用原 physics 纯函数，逐步迁移编排 |
| Profile 与 RIS 公式重复计算距离损耗/相位 | path-response 契约测试和分量对照 | ADR 明确 full transfer 或 environment modifier，禁止混用 |
| Wall endpoint z 被接受后计算忽略 | loader/geometry/FND-T19 | 收紧 v1 为 floor anchor，墙只用刚体 XY delta |
| 100 MHz 被误称已做宽带/OFDM | 标签、FND-T20、provenance review | 固定 flat-channel model ID，不做无来源自动有效性判定 |
| quadrature/Profile 升级后 Focus 仍用中心路径 | FND-T21/T22 coefficient comparison | 独立 production migration；未闭环则阻断 Foundation/P1A |
| coefficient identity 漏掉 gain/direction/world model | mutation matrix / cache design review | 分层补齐 canonical identity，未完成前不启用 cache |
| 新实验覆盖旧结果 | 输出目录存在检查、metadata test | 默认拒绝覆盖或创建新 run 目录 |
| Foundation 扩展到新场景/衰落/MIMO | Work Item scope review | 移回 roadmap，不在当前分支实现 |

回退不能通过删除失败测试、放宽无物理依据阈值、恢复隐藏增益或把错误行为改名来完成。

## 13. ADR、提交和评审顺序

### 13.1 候选 ADR

编号在文件创建时按 [decisions.md](decisions.md) 登记，本文不以标题代替正式决定：

1. ADR-0006：Physics Focus objective、baseline phase alignment 与 model-based optimizer 分层；
2. ADR-0007：Equivalent controllable aperture patch semantics；
3. ADR-0008：最小 aperture quadrature validity gate、A2/P1A/P1C 边界；
4. ADR-0009：历史 Profile 决定，已由 ADR-0012 完整取代；
5. ADR-0010：center-frequency flat-channel、带宽/容量标签与 model ID；
6. ADR-0011：Controller `a_n^C/Gamma_cmd` 分解、Focus 一致性与条件迁移顺序；
7. ADR-0012：Profile environment modifier 与 Reflection Model `Gamma_wall` 的唯一所有权、engine
   注入和分层 identity。

ADR-0006..0008、0010..0012 已 Accepted；ADR-0009 已 Superseded。Wall floor-anchor 是对当前
v1 计算歧义的最小 closure，由稳定 requirement
和 FND-FIX-WALL 跟踪；若未来支持悬空/倾斜墙或改变 schema 结构，再新建 ADR。

Commanded validation、search levels 和 GUI dirty state 如果不改变层依赖/schema major，可作为
上述 ADR 的后果和 requirements 实现；若评审发现存在新的高影响选择，再单独建 ADR。

### 13.2 建议集成顺序

以下是依赖顺序，不要求与 L4 Task 或最终 commit 数量一一对应：

1. `docs: freeze Foundation physics/algorithm contracts`（本轮只完成治理，不提升能力状态）
2. `feat: enforce commanded hardware states with contract tests`（A3）
3. `fix: close floor-anchored wall geometry and XY truth delta`（FND-FIX-WALL）
4. `feat: separate hardware and search resolution`
5. `ui: clarify applied state, pattern metadata and ground-truth labels`
6. **A/B checkpoint：暂停功能扩展并完成人工复核**
7. `refactor: introduce environment-only default propagation profile`
8. `experiment: add minimum foundation provenance`
9. `qa: establish minimum aperture quadrature validity and freeze coefficient policy`
10. 若 QA 要求，先建立并完成独立 production quadrature migration；若保留 1×1 则跳过迁移
11. `physics/docs: close narrowband frequency/model identity contract`（FND-PHY-NB）
12. `qa: prove Controller coefficient and Focus consistency`（FND-QA-CC）
13. `docs/qa: close foundation evidence and status`

可以在本地 TDD 过程中先看到红灯，但不得把“只有失败测试”的提交作为可交付历史推送或合并；
测试应与最小实现组成绿色提交，或在合并前 squash。每个交付提交必须可评审、测试通过并更新
对应文档状态。不得为了凑固定 commit 数量拆坏原子变更，也不得在一个提交中夹带 City 场景、
缓存矩阵或 GUI 重设计。

## 14. Entry Gate、Exit Gate 和完成证据

### 14.1 Foundation Global Entry Gate

开始任何代码实现前必须满足：

- `AMF-RIS-008..012`、`AMF-PHY-007`、`AMF-OPT-004`、`AMF-SIM-005..006`、`AMF-UI-007..008`、
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

Foundation A exit 后、B 开始前的 FND-FIX-WALL 已完成独立验收并达到 Verified；A1/A2/A3 的
Verified 状态不受该独立 closure 影响。Foundation final gate 仍受 FND-PHY-NB、FND-QA-AP、
FND-QA-CC 及其他既有门禁阻断。

### 14.3 Foundation 0.1.1B Exit Gate

- hardware/search resolution 分离并可追踪；
- GUI pending/apply/Optimize/preset 状态不歧义；
- Pattern 元数据、图例和误差标签准确；
- GUI smoke 和人工清单通过；
- A/B checkpoint 临时结果进入隔离目录且不覆盖 legacy；在 C2 provenance 完成前不得作为正式
  Foundation 实验发布。

2026-09-03 verification/status closure：B1/B2/B3 与 `AMF-RIS-008/009`、`AMF-OPT-004`、
`AMF-UI-007/008` 的自动和外部人工证据均完整，independent review / real GUI / RIS Gain
visualization 均 PASS，blocking issues 0；上述五个 requirements 与 B Deliverable 已提升为 Verified。

### 14.4 A/B Interim Checkpoint

- 完整 pytest 与 Current/Advanced/Future 三代 headless 通过；
- GUI Pending/Apply/Optimize、Pattern Source、Allowed/Used States 和两个 Ground Truth 标签经
  人工清单验收；
- Phase Resolution 只在新隔离目录复算，明确标注 checkpoint/非正式 provenance；
- 项目维护者和物理审查者共同确认 Focus objective、Commanded/Actual 边界和 GUI 表达无歧义；
- 该 checkpoint 允许评审 A/B 演示，但不把整个 Foundation 标为 Verified，也不解除 P1A 门禁。

### 14.5 Foundation 0.1.1C Exit Gate

- 默认 IndoorDeterministicProfile 可复现 v0.1 reference 物理组件；
- direct、reflection、RIS incident/scattered path roles 均经过同一 Profile 契约，且没有与 RIS
  距离扩散/相位公式重复计算；
- Profile 返回 environment-only complex modifier；自由空间 carrier、RIS device、Ground Truth 和
  noise 的所有权未被吞并；
- Profile identity/version/parameters 有稳定契约；
- Controller/GroundTruth、RIS 和 Profile 职责没有互相吞并；
- Scene/schema 决策和迁移策略完整；
- FND-T15、最小 experiment provenance、legacy 标记和 no-overwrite 规则完成；
- C 的实现和 provenance 足以支持 FND-QA-AP 正式 runner。

### 14.6 FND-QA-AP and Foundation Final Exit Gate

- aperture、control grid、commanded pattern、Profile、geometry 和 seed 在每个 refinement series
  内固定；只有 quadrature rule/order 改变；
- midpoint successive refinement 与独立求积规则交叉检查完成，内部参考不冒充 EM truth；
- 三代、四类代表性几何、两个 Focus 和不少于 5 个固定 random seeds 的最小矩阵可重放；
- FND-T16..18、深相消数值保护、runtime/memory 和无静默跳过检查通过；
- reference/production tolerance 在正式结果前登记，结果失败后未通过放宽阈值取得 PASS；
- production `quadrature_policy_id/version` 已签署；若需要改变散射实现，独立 implementation
  Work Item 已完成并重新运行三代回归；
- FND-FIX-WALL/FND-T19 已关闭 wall endpoint z、height 和 Ground Truth XY perturbation 歧义；
- FND-PHY-NB/FND-T20 已冻结 `narrowband_center_frequency_flat_v1`，标签/provenance 不把
  `h(fc)` 平坦上界误称宽带或真实吞吐；
- FND-QA-CC/FND-T21..22 已证明 RIS-only/Coherent Focus、Controller simulation 与 QA runner
  使用同一最终 `a_n^C` 或等价实现，且没有 Ground Truth coefficient 泄漏；
- partial-aperture blockage 明确不在本门禁声明范围，当前 scalar blockage 未被误称空间分辨；
- P1A cache key 所需 frequency model、Profile、geometry/gains/direction、world model 和 quadrature
  policy identity 已冻结；pattern/B/NF/measurement noise 的不同所有权也已记录；
- requirements、ADR、README、roadmap、status 和测试证据闭环。

全部完成后，Foundation Capability 才能由 Implemented 经人工验收升为 Verified，P1A 才能
进入 In Progress。

## 15. 后续路线

Foundation 之后按以下顺序推进：

1. **P1A Geometry Cache and Matrix Evaluation**：在稳定 Profile/geometry/pattern/quadrature
   policy contract 上做数值等价的性能优化；
2. **P1B Phase Error Robustness**：多 seed 比较 RIS-only、Coherent、Feedback 和
   Physics-Guided，报告分位数；
3. **P1C Aperture Sweep and Extended Quadrature Research**：保留完整孔径研究；除固定控制网格/
   固定等效密度实验外，扩大 control/quadrature、field-map、phase-span、frequency/angle/
   near-field sensitivity 和后续遮挡边缘的适用域证据，不重新承担 P1A 前的最小 policy 定义；
4. **v0.2 XR**：先定义动态时间、人体阻挡和对应 Profile 行为；
5. **v0.3 Factory**：多 RX、多 RIS、objective 和 pattern ownership；
6. **v0.4 City/Low-Altitude**：城市几何、NLoS、车辆/UAV 和独立传播 Profile；
7. 后续再考虑 fading、MIMO、OFDM、active/STAR RIS 和全波/测量校准。

一个 Profile 接口的存在不表示这些场景模型已经实现；每个新场景仍必须先完成有来源、可测试
的 headless 物理纵向切片。

## 16. 新开发者开始工作前的检查单

- [ ] 我能解释 AirMirror Future 为什么是系统级近似而不是全波求解器；
- [ ] 我知道 Foundation B 后 GUI 默认是 Coherent Target Focus；RIS-only 仍可选，CLI、
  Physics-Guided 和 legacy experiment 为兼容性继续使用 RIS-only；
- [ ] 我知道 `nx/ny` 当前同时承担控制和求积离散，不能直接称真实 meta-atoms；
- [ ] 我知道现有 8/16/32 测试保护面积归一化/不发散，不证明粗 patch 已物理收敛；
- [ ] 我知道 A2 semantic contract 已 Verified，但 aperture discretization accuracy 尚未 Verified；
- [ ] 我知道内部 16×16 等细化结果只能称 numerical reference，且求积细化不得重新生成 Focus；
- [ ] 我知道 FND-QA-AP 在 Foundation final exit/P1A 前，P1C 则保留完整孔径研究；
- [ ] 我知道 quadrature refinement 不会自动获得 spatially resolved blockage；
- [ ] 我知道 Commanded 与 Actual 的区别，且误差不能被重新量化；
- [ ] 我知道 `phase_bits` 与 `search_levels` 是不同维度；
- [ ] 我知道 Generation 是 preset 来源，Customized 只能是派生显示；
- [ ] 我知道 Controller/GroundTruth 与 PropagationProfile 职责不同；
- [ ] 我知道 Foundation Profile 是 environment-only modifier，不重复距离/传播相位或
  `Gamma_wall`；墙系数由 Wall/Reflection Model 拥有且每条反射路径只应用一次；未来
  PathEnsemble 是独立能力；
- [ ] 我知道 `frequency_hz` 是中心频率，`bandwidth_hz` 不会生成频率轴，容量只是 flat-channel
  Shannon 上界；
- [ ] 我知道 v1 Wall 已实现 floor-anchored/XY-only truth delta，超出 `1e-9 m` 的 endpoint z 会明确失败；
- [ ] 我知道 A1 objective Verified 不等于未来 quadrature/Profile 下 Focus/coefficient 自动一致；
- [ ] 我知道 FND-QA-AP 先选 production policy，必要时独立迁移，最后 FND-QA-CC 才签一致性；
- [ ] 我确认没有在 Foundation 中实现缓存、新场景、MIMO 或 fading；
- [ ] 我已找到 requirement ID、ADR 触发条件、测试和 Exit Gate；
- [ ] 我会在同一变更中同步 requirements、规范、测试和 DEVELOPMENT_STATUS。

## 17. 已关闭与仍需 ADR 决定的问题

已关闭：

- Foundation 0.1.1 不向 Scene v1 加入 `design_frequency_hz`，保持 Deferred，等待真实 RIS
  频率响应模型触发新的 ADR；
- A1 的旧 API 兼容、finite-bit boundary candidates 和确定性退化行为由 ADR-0006 冻结；
- A2 由 ADR-0007 选择只展示 effective pitch/波长比例，不输出未验证的 phase-span；
- ADR-0008 保持 A2 Verified，并把最小 coefficient quadrature validity 放到 Foundation final
  exit/P1A 前；P1C 保留更完整的 aperture research。
- ADR-0012 取代 ADR-0009，保留 environment-only Profile、engine 构造注入和 Scene v1 不持有
  Profile 类名，同时把 `Gamma_wall` 唯一归属 Wall/Reflection Model；
- ADR-0010 冻结 center-frequency flat-channel 语义和稳定 model ID，不建立自动窄带阈值；
- ADR-0011 冻结 Controller `a_n^C/Gamma_cmd` 所有权、Ground Truth 隔离和条件 production
  migration 顺序。
- FND-FIX-WALL Ready review 冻结 endpoint z 为 `1e-9 m` 绝对容差；超差 v1 输入的错误包含
  wall id、具体字段、实际值和显式归零迁移指引。兼容审计未发现受支持的非零-z Scene，故
  schema version 保持 1，不触发新 ADR；implementation commit `8841ef2` 后的独立审查 G0–G8
  PASS、blocking issues 0，已提升为 Verified。

以下问题在正式实现前不得由单个开发者静默选择：

1. continuous Physics-Guided 是否允许连续 initial 与离散搜索结果混合；
2. 历史结果目录的版本命名和默认覆盖策略；
3. C1 Profile context/canonical parameter 的具体 Python 类型和序列化编码；所有权和 modifier
   语义已经关闭，不得重新选择 full transfer，也不得把 `Gamma_wall` 并回 Profile；
4. FND-QA-AP 的预注册 reference/production tolerance、最终 fixed/adaptive policy 和是否需要
   production migration；这些必须在 Work Item 进入 Ready/查看正式结果前关闭，不能静默选择。
5. FND-QA-CC coefficient builder 的具体内部模块/类型；公共 phase-array API 和因子所有权已关闭。

未决项存在不表示计划阻塞；它们是对应 ADR/Work Item 进入 Ready 前必须关闭的选择。
