# 软件架构规范

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + FND-FIX-WALL + Foundation Profile/coefficient/frequency contract |
| 对应需求 | AMF-ENG-002、AMF-SIM-001..006、AMF-RIS-012、AMF-UI-003 |

## 1. 架构目标

架构首先保护物理可信度，其次才是 GUI 开发速度。核心引擎必须能够在没有 Qt、没有
Matplotlib 交互后端和没有网络时运行。新增功能应沿已有边界扩展，不得在 GUI 事件中
复制传播公式，也不得让优化器直接读取 Ground Truth 内部误差。

## 2. 依赖方向

```text
core
 ├─> physics
 ├─> ris
 └─> scene
       └─> simulation
              ├─> optimization
              ├─> scenarios / experiments
              └─> gui
```

允许关系以 Python import 为准：

| 包 | 职责 | 可依赖 | 禁止依赖 |
|---|---|---|---|
| `core` | SI 数据类型、单位、纯几何与跨层纯数据验证 | NumPy、标准库 | Qt、场景、优化 |
| `physics` | 单条物理路径和噪声公式 | core | GUI、优化、场景 preset |
| `ris` | 相位、孔径 preset、pattern | core、physics 基础常数 | GUI、Ground Truth |
| `scene` | JSON 边界 | core | GUI、SimulationEngine |
| `simulation` | 路径编排、结果与误差模型 | core、physics、ris、scene | GUI |
| `optimization` | oracle 驱动算法 | core、ris、simulation 公共 API | GUI、Ground Truth 私有参数 |
| `scenarios` | 构造可运行场景 | core、ris | GUI |
| `experiments` | 可复现批处理和结果落盘 | 公共仿真/优化 API | GUI 私有方法 |
| `gui` | 输入、显示、任务调度 | 上述公共 API、PySide6 | 自定义传播公式 |

若出现反向 import，先提取接口或纯数据类型，不使用运行时延迟 import 掩盖循环依赖。
`Scene.save/load` 中的局部 import 是为保持 Scene 便利 API 的已接受例外，记录于 ADR-0002。

## 3. 核心运行数据流

### 单链路

```text
Scene + TX + RX + patterns + Model
  -> resolve and validate entities
  -> validate commanded pattern key/shape/finite/hardware state
  -> optional Ground Truth geometry perturbation
  -> LOS attenuation and complex channel
  -> valid one-bounce wall paths
  -> each enabled single-hop RIS contribution
  -> complex coherent sum
  -> Pt*|h|²
  -> noise, SNR, Shannon upper bound
  -> ChannelResult
```

`ChannelResult` 是数值结果边界；GUI 不重新计算指标。

FND-FIX-WALL 后，Ground Truth 的三维 position realization 对 Wall 只消费 XY 分量：engine 对
每堵墙取得一次 delta，以同一 `[dx,dy,0]` 平移两个端点，并将生成的同一个 working-scene Wall
交给 LOS blockage 和 reflection。Wall 数据构造先执行 floor-anchor 容差验证；physics 层无需
再次猜测 endpoint z 含义。

Foundation C1 已 Verified（外部独立最终审查 PASS）；它在不改变上述用户级流程的前提下引入
engine-owned `IndoorDeterministicProfile`。按
[ADR-0012](adr/0012-wall-reflection-coefficient-ownership.md)，它只提供 environment modifier，
不拥有 Friis carrier、`Gamma_wall`、RIS device、Ground Truth 或 noise；Scene JSON v1 不保存
Python Profile 类名。ADR-0009 已被取代。精确 Protocol/context/identity 见
[C Work Item](work_items/foundation_0_1_1_c.md)；channel 与 field map 均已接入 Profile，C2 provenance
与最终 coefficient builder 仍未实现。

五个固定环境 role 为 `direct`、`reflection_before`、`reflection_after`、`ris_incident`、
`ris_scattered`。engine 先建立所选 Controller/GT world 的显式 working geometry，再向 Profile
传入 Scene 与只读 role/start/end/相关 wall 或 RIS ID context；不传 Model、seed、sigma、error
callback 或 oracle。Profile 可以对显式 working geometry 求环境 modifier，但不读取或选择
隐藏 realization。Profile 返回 finite complex value 和只读诊断 blocker IDs；只有 value 进入
复信道乘法。RIS 两段仍按 surface center 各调用一次，不随 patch/quadrature 点调用。

一次墙反射的内部调用图冻结为：

```text
single_wall_reflection_path -> point + total distance + h_FS carrier
selected world model        -> one effective Gamma_wall
Profile reflection_before   -> one m_before_env
Profile reflection_after    -> one m_after_env
engine                      -> carrier * Gamma_wall * before * after
```

carrier-only helper 不查询 blocker、不应用墙系数。反射墙只通过唯一 wall ID 从两个 leg 查询排除；
duplicate wall ID 在任何 Profile/reflection 求值前抛 `ValueError`，不按对象地址、列表位置或坐标
回退。Wall/Obstacle/RISSurface non-empty string ID 也在构造/loader 与 engine preflight 明确校验，防止非法 ID
到 context/blocker 才失败；这些经兼容审计的 validation tightening 不增加 Scene v1 字段。
零反射幅值墙继续由 engine 按 v0.1 规则跳过；carrier-only helper 不拥有墙系数。context 不收紧
路径最小距离接受域，reflection 总长和 RIS-to-cell 等有效性仍由既有 physics kernels 校验。

### 场图

```text
Scene + SimulationConfig + fixed patterns
  -> regular x/y grid at z_eval
  -> per evaluation point: shared LOS/wall/RIS components
  -> with-RIS and baseline power from the same non-RIS field
  -> power/SNR/RIS-gain arrays
  -> threshold aggregation
  -> FieldMapResult
```

baseline 与 with-RIS 必须使用相同几何和 Ground Truth realization。不能分别随机采样误差，
否则 RIS Gain 会混入两个世界的差异。

### 反馈优化

```text
Controller Model -> initial pattern
Ground Truth -> MeasurementOracle.measure(patterns) -> noisy scalar dBm
Optimizer -> candidate tile changes -> only oracle feedback -> OptimizationResult
```

oracle 是隔离边界。优化器不得访问 `GroundTruthModel.ris_phase_offsets`、墙体误差或位置
扰动函数。

## 4. 状态所有权

| 状态 | 所有者 | 生命周期 | 复制/共享规则 |
|---|---|---|---|
| `Scene` | 调用者或 MainWindow | 当前会话/JSON | worker 启动时 deep copy |
| RIS commanded patterns | MainWindow / optimizer | 几何或目标变化前 | key 为 RIS id，数组长度严格匹配 |
| RIS actual patterns | Ground Truth + simulation | 单次可重放 world realization | 只在 commanded validation 后加入误差，不重新量化 |
| Ground Truth 参数 | 实验或 MainWindow | 一次可复现实验 | worker deep copy；seed 不变 |
| 场图结果 | MainWindow | 最新 task version | immutable-by-convention，不回写 engine |
| worker cancellation | worker | 单次任务 | `threading.Event`，只单向设置 |
| task version | MainWindow | 单调递增 | 结果版本不等于当前值时丢弃 |

核心包不得引入全局可变 scene、pattern 或随机生成器。MeasurementOracle 的 RNG 属于单个
oracle 实例，以保证同一调用序列可重放。

公共 `validate_commanded_pattern` 由 `ris` API 导出，纯实现位于 `core`，使 engine 和低层
physics scattering 复用同一契约而不产生 `physics -> ris` 反向依赖。Engine 对整个 map 做
key/歧义检查并取得已验证快照；field map 在像素循环外只执行一次，内部传播内核不得重复量化或
验证 Actual error。

## 5. GUI 并发契约

1. `compute_field_map` 和 feedback optimize 必须在 `QThreadPool` worker 中运行；
2. 每个任务获得创建时的 scene/pattern/model 快照和整数 version；
3. 用户拖动或应用参数时立即增加 version 并请求取消当前任务；
4. debounce 只减少任务数量，不承担正确性；正确性由 version 检查保证；
5. worker 定期检查 cancellation，不允许从工作线程修改 QWidget；
6. 只有 version 等于当前值的结果可写入 `latest_field` 或 patterns；
7. 关闭窗口后信号源销毁属于正常生命周期，worker 安全忽略该信号错误。

## 6. 缓存与失效

v0.1 当前只保留 `SimulationEngine` 缓存接口，尚未启用完整几何矩阵缓存。P1 性能实现必须
采用显式 key，不得按对象 id 隐式复用：

```text
coefficient_geometry_key = (
  channel_frequency_model_id, frequency,
  tx_position, evaluation_points, tx_gain, rx_gain,
  ris_position, yaw, width, height, nx, ny, direction_exponent,
  reflection_model_identity, wall_geometry_and_coefficients,
  obstacle_geometry_and_attenuation,
  world_model_geometry_environment_identity,
  profile_identity, quadrature_policy_identity
)

link_metric_key = (
  coefficient_geometry_key, transmit_power,
  bandwidth, noise_figure, coverage_threshold
)
```

| 变化 | 必须失效 |
|---|---|
| frequency | 所有传播相位和波长相关项 |
| TX/RX/评价网格位置 | 相应距离、方向图、阻挡和反射 |
| RIS 几何/朝向/网格 | cell centers、d1/d2、方向图、patterns |
| quadrature rule/order/policy version | control-level `a_n`、几何 A 和对应 benchmark reference |
| wall geometry / Reflection Model / `Gamma_wall` / effective wall truth state | 反射点、wall channel 和依赖它的 baseline；不得只失效 Profile identity |
| obstacles / Profile parameters | 对应 LOS、反射路径段和 RIS legs 的 environment modifier |
| phase pattern | 只失效 `A @ Gamma` 结果，不失效几何 A |
| noise/bandwidth/NF | SNR/capacity/coverage，不失效 `h(fc)` 或 control coefficient |

缓存实现必须配套命中/失效测试；没有测试前不声称“已缓存”。

P1A 不得把“每个 control patch 一个中心点”作为无版本的永久系数定义。Foundation
FND-QA-AP 已签署并冻结 `quadrature_policy_id/version`；P1A 缓存的是该 policy 积分得到的
control-level `a_n`。若 policy 改变，cache 必须失效，旧实验必须通过 model/policy version 保留。

若 QA 需要多点求积，候选内部数据流为：

```text
Gamma_control[N_control]
QuadratureSpec -> subpoints + weights + parent_control_index
subpoint field -> reduce to a_control[N_control]
h_RIS = A_control @ Gamma_control
```

FND-QA-AP-02 的内部候选 `QuadratureSpec` 至少携带 `rule`、`order_x`、`order_y`、确定性
`sample_coordinates`、`weights` 和 `parent_control_index`；coordinates/weights/index 按
parent-major、row-major 的稳定顺序排列。每个 subpoint 继承 parent control patch 的同一
command coefficient，quadrature order 变化不得触发 Focus、量化、搜索或 pattern/hash 重建。
这是内部 QA/implementation 边界，不改变 public phase-array API 或 `ris_patterns` shape。

控制维度保持 `N_control=nx*ny`，quadrature samples 不获得独立 commanded phase。当前尚无公共
`QuadratureSpec` 类型；rule/order/weights/version 和 blockage sampling ownership 必须由后续
implementation Work Item 冻结。不得构造不可控的 `N_points×N_control×N_subpoints` 全量张量；
优先分块/streaming reduction。

### 6.1 Planned Profile 与 coefficient 数据流

ADR-0011/0012 冻结以下目标所有权；它不表示当前代码或缓存已经实现：

```text
direct: Physics carrier * Profile direct modifier
wall:   Physics carrier * Reflection Model Gamma_wall
                          * Profile before/after modifiers

RIS geometry carrier + Profile incident/scattered modifiers
  -> a_control^Controller[N_control]
commanded phase + nominal efficiency
  -> Gamma_command[N_control]
h_RIS^Controller = dot(a_control^Controller, Gamma_command)

Ground Truth geometry/environment
  -> a_control^GT
command + actual phase/efficiency errors
  -> Gamma_actual
h_RIS^GT = dot(a_control^GT, Gamma_actual)
```

`Gamma_wall` 与 RIS 的 `Gamma_command/Gamma_actual` 是不同物理对象：前者是墙反射路径响应，由
Wall/Reflection Model 拥有；后者是 RIS control patch 状态，由 RIS Model 拥有。Profile 对两者均
无所有权。反射墙自身必须从其 before/after blocker 查询中排除。

RIS-only/Coherent Focus、SimulationEngine、FND-QA-AP 与未来 P1A 必须共享同一 Controller
coefficient builder 或有等价证明。`a^GT` 只能留在 Ground Truth/oracle 路径。FND-QA-CC 在
production quadrature policy 签署后执行；若 QAP 要求多点生产求积，应先创建独立迁移工作项，
不得把迁移夹进缓存实现。

## 7. 错误与数值策略

- 公共数据构造时完成范围校验，错误包含字段名；
- 同一点传播、非正频率、非正孔径/网格、非法效率必须拒绝；
- 极小功率只在 dBm 转换边界使用 `MIN_POWER_W` floor；不得提前截断复场相消；
- active RIS 明确抛 `NotImplementedError`，不退化成无源或隐藏增益；
- 可取消计算抛 `SimulationCancelled`，UI 不将其显示为失败；
- JSON schema 不支持时拒绝，不猜测字段含义；
- 未处理 NaN/Inf 属 P0 缺陷。

## 8. 新功能扩展顺序

每项 Capability 必须按以下顺序进入架构：

1. 在 requirements 分配稳定 ID，写清输入、输出和物理边界；
2. 如改变既有决定，先建立 ADR；
3. 扩展纯数据模型和 JSON schema；
4. 实现 headless 物理/算法垂直切片；
5. 增加单元、性质和集成测试；
6. 记录性能和已知限制；
7. 最后接入 GUI，并增加 worker/交互验收。

XR 不得在现有 engine 中加入仅供动画使用的随机 SNR；Factory 不得在单用户接口外层简单
循环后声称完成联合优化；City 不得使用手绘走廊替代复场。

## 9. 可观测性和实验记录

计算结果必须能记录 scene、center frequency、bandwidth、channel frequency model、generation、
RIS geometry、algorithm、Profile、quadrature/coefficient identity、seed、runtime 和 objective。
核心函数不直接写文件；experiments 层负责 CSV/PNG。GUI 日志只记录任务
开始、完成、取消和错误，不记录每个 cell 的高频信息。
