# 软件架构规范

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 |
| 对应需求 | AMF-ENG-002、AMF-SIM-001..004、AMF-UI-003 |

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
| `core` | SI 数据类型、单位、纯几何 | NumPy、标准库 | Qt、场景、优化 |
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
| Ground Truth 参数 | 实验或 MainWindow | 一次可复现实验 | worker deep copy；seed 不变 |
| 场图结果 | MainWindow | 最新 task version | immutable-by-convention，不回写 engine |
| worker cancellation | worker | 单次任务 | `threading.Event`，只单向设置 |
| task version | MainWindow | 单调递增 | 结果版本不等于当前值时丢弃 |

核心包不得引入全局可变 scene、pattern 或随机生成器。MeasurementOracle 的 RNG 属于单个
oracle 实例，以保证同一调用序列可重放。

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
geometry_key = (
  frequency, tx_position, evaluation_points,
  ris_position, yaw, width, height, nx, ny,
  wall_geometry, obstacle_geometry, model_position_seed
)
```

| 变化 | 必须失效 |
|---|---|
| frequency | 所有传播相位和波长相关项 |
| TX/RX/评价网格位置 | 相应距离、方向图、阻挡和反射 |
| RIS 几何/朝向/网格 | cell centers、d1/d2、方向图、patterns |
| walls/obstacles | LOS、反射点、路径衰减 |
| phase pattern | 只失效 `A @ Gamma` 结果，不失效几何 A |
| noise/bandwidth/NF | SNR/coverage，不失效复信道 |

缓存实现必须配套命中/失效测试；没有测试前不声称“已缓存”。

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

计算结果必须能记录 scene、frequency、generation、RIS geometry、algorithm、seed、runtime
和 objective。核心函数不直接写文件；experiments 层负责 CSV/PNG。GUI 日志只记录任务
开始、完成、取消和错误，不记录每个 cell 的高频信息。

