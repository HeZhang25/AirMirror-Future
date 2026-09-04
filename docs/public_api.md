# 公共 API 与兼容契约

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| API 基线 | 0.1 + Foundation A1-A3/FND-FIX-WALL/B + C1 Verified + planned closure boundaries |
| Python | 3.11+ |

## 1. 稳定性政策

v0.x 期间允许有记录的破坏性变化，但不得静默发生。改变签名、单位、数组形状、默认值或
异常类型时，必须更新本文件、requirements、测试和 ADR；至少在一个 release 的
`DEVELOPMENT_STATUS.md` 中列迁移说明。

顶层 `airmirror_future` 导出公共数据类型、`SimulationEngine`、Controller/Ground Truth、
MeasurementOracle、`generate_ris_only_focus_pattern`、`generate_coherent_target_pattern`、
`EquivalentPatchDiagnostics`、`equivalent_patch_diagnostics`、`validate_commanded_pattern` 和
`COMMANDED_PHASE_ATOL_RAD`、`WALL_ENDPOINT_Z_ATOL_M`。以下划线开头的成员、GUI 私有槽和
`path_details` 内部字典不是
稳定 API。

## 2. SimulationEngine

```python
SimulationEngine.compute_channel(
    scene: Scene,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris_patterns: Mapping[str, np.ndarray] | None = None,
    model: ControllerModel | GroundTruthModel | None = None,
) -> ChannelResult
```

契约：

- `tx/rx=None` 使用 Scene 首个实体；str 按 id 查找；
- `ris_patterns=None/{}` 表示 No RIS，未出现在 map 的 RIS 不贡献；
- 每个 pattern 是 finite real radians 一维数组，长度严格等于对应 `cell_count`；离散硬件必须
  在模 `2π` 意义下位于合法状态的 `1e-6 rad` 绝对容差内；
- 每个 key 必须唯一对应 Scene 中一块 RIS；未知或歧义 key 抛 `ValueError`；
- validator 在任何 Ground Truth 扰动前运行；输入在容差内只被接受，不被 wrap、snap 或量化；
- `model=None` 等价 ControllerModel；
- 结果包含同一 world realization 下的所有路径与指标；
- 四个 complex channel 都是在 Scene 中心频率 `fc` 处计算；`bandwidth_hz` 不创建频率维；
- active RIS、零距离或非法 pattern 明确抛异常。

C1 已实现 Scene wall ID 在每次 channel/map 计算的任何 Profile/reflection 求值前必须唯一；
duplicate 值抛含 ID 的 `ValueError`。Scene 构造/加载也执行同一校验，不改变 v1 JSON 结构。
Wall/Obstacle/RISSurface ID 必须为 non-empty string；实体构造/loader 拒绝空或非字符串 ID，Scene 构造和
channel/map preflight 在 world/Profile/physics 求值前复核事后修改。错误包含实体类型、实际 ID
和显式赋名指引；不 trim、自动赋名或过滤 blocker ID。该经兼容审计的 closure 保持 schema v1，
外部空 ID 输入须显式赋名，详见 [Scene schema](scene_schema.md#7-标识符和引用)。
RISSurface 的旧 truthiness 校验现也拒绝 truthy non-string ID（如 `1`）；构造后 mutation 即使
disabled/uncommanded 也在 preflight 失败。外部非法 RIS ID 须显式赋名并更新 pattern key；
RIS uniqueness 仍只在既有 pattern 引用边界检查，不扩展 TX/RX 或全局唯一性。

```python
SimulationEngine.compute_field_map(
    scene: Scene,
    config: SimulationConfig,
    ris_patterns: Mapping[str, np.ndarray] | None = None,
    model: ControllerModel | GroundTruthModel | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> FieldMapResult
```

契约：在 `z_eval_m` 建立规则网格；每行开始检查 cancel，取消时抛
`SimulationCancelled`；baseline 与 with-RIS 共享非 RIS 复场和随机 realization。commanded
patterns 在像素循环前只验证一次。

## 3. RIS API

```python
validate_commanded_pattern(
    ris: RISSurface,
    phase_rad: np.ndarray,
) -> np.ndarray
```

返回保留输入数值表达的独立 `float64[ris.cell_count]` 验证快照，不 wrap 或 quantize。输入必须
严格一维、长度匹配、real 且 finite。`phase_bits=None` 接受任意 finite 未 wrap 表达；离散硬件
按 `2**phase_bits` 个均匀状态检查循环距离。公共常量
`COMMANDED_PHASE_ATOL_RAD=1e-6` 是绝对弧度容差，比较使用 `rtol=0`。任何失败抛带 RIS id/原因的
`ValueError`。

`RISSurface.phase_bits` 必须是正整数或 `None`；bool、小数和非正值均拒绝。validator 对容差内原值
只接受不修正。Ground Truth phase error 在 commanded validation 后加入 Actual Pattern，且 Actual
不再量化。

```python
quantize_phase(phi_rad: float | np.ndarray, bits: int | None)
```

返回类型与输入标量/数组形态一致，范围 `[0,2π)`；bits 必须为正整数或 None。

```python
generate_ris_only_focus_pattern(
    ris: RISSurface,
    tx: Transmitter | Vec3,
    rx: Receiver | Vec3,
    frequency_hz: float,
) -> np.ndarray
```

返回 `[ris.cell_count]` 弧度数组，已按 surface `phase_bits` 量化；只使 RIS patch 相互同相，
不读取 baseline。`generate_focus_pattern()` 在 A1 中是行为完全相同的兼容别名。Foundation B 后
GUI 默认使用 Coherent Target Focus 并保留 RIS-only 选项；CLI、feedback 初始化和 legacy
experiment 继续使用该 RIS-only 兼容入口。

```python
apply_common_phase_offset(
    phase_rad: np.ndarray,
    common_phase_offset_rad: float,
    bits: int | None,
) -> np.ndarray

generate_unquantized_ris_only_focus_pattern(
    ris: RISSurface,
    tx: Transmitter | Vec3,
    rx: Receiver | Vec3,
    frequency_hz: float,
) -> np.ndarray

common_phase_offset_candidates(
    phase_rad: np.ndarray,
    bits: int,
) -> np.ndarray
```

`generate_unquantized_ris_only_focus_pattern` 返回量化前的几何相位；
`apply_common_phase_offset` 在量化前加入公共 offset；`common_phase_offset_candidates` 返回
finite-bit 公共 offset 候选，精确 `0.0` 永远为首项，其余项覆盖所有量化 transition 区间。
phase array 必须是一维、非空且有限；offset 必须有限；非法输入抛 `ValueError`。

```python
generation_preset(
    generation: str,
    *,
    identifier: str = "ris-1",
    position: Vec3 = Vec3(5, 7.9, 1.5),
    yaw_rad: float = -pi/2,
) -> RISSurface
```

只接受 Current/Advanced/Future（大小写不敏感），返回新的可编辑 surface。

```python
equivalent_patch_diagnostics(
    ris: RISSurface,
    frequency_hz: float,
) -> EquivalentPatchDiagnostics
```

返回只读 SI 诊断：实体宽高/面积、`nx/ny/total`、两个 effective pitch、运行频率/波长以及
两个 `pitch/wavelength` 比值。函数无副作用，不修改 RIS/Scene、不生成 pattern、不参与传播，
也不提供物理有效性 pass/fail。`frequency_hz` 必须 finite 且大于零；RIS 尺寸必须 finite 且
为正，`nx/ny` 必须是正整数。改变运行频率不会改变实体孔径。A2 不公开 phase-span；适用域见
[ADR-0007](adr/0007-equivalent-controllable-aperture-patches.md)。

ADR-0008 新增的是 Foundation/P1A sequencing 和 QA 契约，不是当前公共 API。当前调用者不得
假设存在 `QuadratureSpec`、`quadrature_order` 或自动 adaptive policy。若后续 QA 选择多点
production policy，公共/内部接口、默认兼容、异常、policy identity/version 和缓存失效必须由
独立 Work Item 文档化；`Gamma` 的公共 shape 仍保持 `[nx*ny]`，quadrature subpoints 不增加
commanded phase 自由度。

ADR-0012 的 Profile/Reflection ownership 与注入已由 C1 实现；ADR-0011 的最终 `a_n/Gamma_n`
builder 仍未实现。Profile 类型与 helper 位于 `airmirror_future.simulation.profiles`，公共构造边界为：

```python
SimulationEngine(profile: PropagationProfile | None = None)

class PropagationProfile(Protocol):
    @property
    def profile_id(self) -> str: ...
    @property
    def profile_version(self) -> str: ...
    @property
    def canonical_parameters(
        self,
    ) -> tuple[tuple[str, bool | int | float | str | None], ...]: ...
    def environment_modifier(
        self,
        *,
        scene: Scene,
        context: PropagationPathContext,
    ) -> PropagationModifier: ...
```

`PropagationPathContext` 是 frozen/slots 值对象，字段为 role、`start/end`、可选且受 role 约束的
`reflecting_wall_id/ris_id`；role 只能是 `direct`、`reflection_before`、`reflection_after`、
`ris_incident`、`ris_scattered`。`None` 在 engine 构造时解析为不可变
`IndoorDeterministicProfile()`；不提供运行中 Profile setter。Profile 返回 finite 无量纲 complex
`PropagationModifier.value`；同一 frozen result 的 `blocker_ids: tuple[str,...]` 只作诊断，不参与
第二次衰减。非法 context/config/output 抛 `ValueError`，不支持必需 role 时不得静默回退。
context 不施加通用 minimum-distance 检查；direct/反射总长/RIS-to-cell 继续由既有 kernel 校验。
engine 只读 `profile` / `profile_identity` 暴露构造时选定的 Profile 与其身份，不提供 setter。

模块级 `profile_identity(profile)` 按
[C Work Item](work_items/foundation_0_1_1_c.md) 的 tagged canonical JSON + SHA-256 计算，不能使用
Python `hash()`、对象地址或类名。`Gamma_wall` 继续通过 Wall/Reflection Model 进入反射路径，
不成为 Profile 返回值。Scene JSON v1 不保存 Python 类名；本边界不建立 Profile/Reflection 插件
注册中心。internal coefficient 不替换 `ris_patterns: Mapping[str,np.ndarray]` 的 commanded phase
API，C1 不实现最终 coefficient builder。

内部聚合 `physics.reflections.single_wall_reflection` 已移除；carrier-only
`single_wall_reflection_path` 返回 `WallReflectionPath(point,total_distance_m,carrier)`，完整 wall
贡献只由 engine 组合。模块常量 `reflection_model_id="finite_wall_single_bounce_image"`、
`reflection_model_version="1"` 与 Profile identity 分离，不是完整 coefficient/world hash。

低层 `ris_channel_for_points` 是物理层 API，输入 receiver array 形状 `[N,3]`，输出
complex `[N]`；它与 `ris_channel` 都先复用同一 commanded validator，再加入可选 actual phase/
efficiency error。调用者通常应使用 SimulationEngine 以获得阻挡、反射和指标。

## 4. Scene API

`Wall` 是 Scene v1 floor-anchored vertical wall。公共绝对容差
`WALL_ENDPOINT_Z_ATOL_M=1e-9 m` 仅用于接受数值交换噪声；`start.z/end.z` 任一超差时，构造与
`Scene.load()` 均抛包含 wall id、具体字段、实际值和显式归零迁移指引的 `ValueError`。两个端点
必须在 XY 不同。容差内 z 保留原数值，`Scene.save()` 不裁剪。Ground Truth 的
`position_delta()` 仍返回三维数组，但 engine 对 Wall 只使用一次采样的 `[dx,dy,0]`，保持墙长、
朝向和 `height_m`。

```python
Scene.save(path: str | Path) -> None
Scene.load(path: str | Path) -> Scene
create_smart_space_scene(generation: str = "Current") -> Scene
```

`save` 写 UTF-8、缩进 JSON 并创建父目录；`load` 只接受 schema v1。格式细节见
[scene_schema.md](scene_schema.md)。

## 5. 优化 API

```python
generate_coherent_target_pattern(
    scene: Scene,
    controller_model: ControllerModel | None = None,
    *,
    engine: SimulationEngine | None = None,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris: RISSurface | str | None = None,
) -> np.ndarray

coherent_common_phase_offset(
    baseline_channel: complex,
    ris_channel: complex,
) -> float
```

返回 single-target Coherent Target commanded pattern。默认选择 Scene 首个 TX/RX；RIS 未指定时
要求恰好一个 enabled surface。该函数只接受 nominal Controller Model，显式拒绝
GroundTruthModel；它不读取 MeasurementOracle。unknown/disabled/ambiguous RIS 和非法模型抛
`ValueError`。continuous 使用解析相位对齐；finite bit 在公共 offset 候选中最大化 nominal
`received_power_w`。纯 helper `coherent_common_phase_offset` 实现相同 continuous 对齐和
`delta=0` 退化规则，并拒绝非有限复分量。完整 objective 与退化规则见
[ADR-0006](adr/0006-coherent-target-focus-objective.md)。

FND-QA-CC 将在最终 production quadrature policy 下证明该策略与 Controller simulator 使用同一
control-level coefficient。该门禁尚未实现；A1 Verified 只证明当前 1×1 nominal objective，
不得据此假设未来多点 quadrature/complex Profile 已自动一致。完整边界见
[ADR-0011](adr/0011-controller-coefficient-focus-consistency.md)。

```python
MeasurementOracle.measure(patterns: dict[str, np.ndarray]) -> float
```

返回目标 RX 的 noisy dBm；每次调用增加 measurement 计数。算法不得访问 oracle 的
`ground_truth` 属性，即使 Python 技术上可见。

```python
Optimizer.optimize(
    controller_model,
    measurement_oracle,
    objective="received_power_dbm",
    **algorithm_options,
) -> OptimizationResult
```

v0.1 只支持单 RIS 和 `received_power_dbm`。Feedback Greedy 额外接受
`initial_patterns`、`search_levels`、`cancel_check`、`progress(done,total,value)`；Physics-Guided
自动以 RIS-only Physics Focus 初始化。continuous hardware 使用 finite search-level refinement，
finite-bit 候选固定为 `2**phase_bits` 合法状态。`OptimizationResult` 记录 algorithm、
hardware_phase_bits、search_levels、pattern_source 和 metadata。

## 6. CLI

```text
python -m airmirror_future
python -m airmirror_future --headless [--scene PATH]
  [--generation Current|Advanced|Future]
  [--quality fast|balanced|high]
```

质量固定映射：Fast `80×60`、Balanced `120×90`、High `200×160`。Headless stdout 是
UTF-8 JSON，字段为 model、generation、future_assumption、baseline/focused power、
target gain、SNR、coverage/dead-zone、runtime 和 grid。错误写 stderr 并返回非零状态。

当前 `shannon_capacity_bps` 采用 `h(fc)` 在 `B` 内平坦的上界语义；Foundation provenance
计划使用 `channel_frequency_model_id=narrowband_center_frequency_flat_v1`。在 FND-PHY-NB
完成前，不得声称现有 CLI 已输出该新字段。

实验入口：

```text
python -m airmirror_future.experiments.phase_bits --output PATH
```

C2 runner 将 `PATH` 定义为必须不存在的完整 run directory；默认根为
`results/foundation_0_1_1/phase_bits/<run_id>/`，已存在时在计算前抛 `FileExistsError`，不提供
`--force`。当前 runner 已实现该收紧，不得把 tracked `results/phase_bits` 用作复算目标。

## 7. 异常契约

| 情况 | 异常 |
|---|---|
| 字段范围/shape/版本非法 | `ValueError` |
| active RIS 无模型 | `NotImplementedError` |
| 长计算被取消 | `SimulationCancelled` |
| JSON 文件不存在/不可读 | 标准 `OSError`/JSON decode error |
| id 不存在 | 当前为 `StopIteration`；计划统一为带 id 的 `ValueError` |

最后一项是已知 API 粗糙点；调用者不应依赖 `StopIteration`，修复时按兼容流程记录。
