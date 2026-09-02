# 公共 API 与兼容契约

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| API 基线 | 0.1 + Foundation A1 additive API |
| Python | 3.11+ |

## 1. 稳定性政策

v0.x 期间允许有记录的破坏性变化，但不得静默发生。改变签名、单位、数组形状、默认值或
异常类型时，必须更新本文件、requirements、测试和 ADR；至少在一个 release 的
`DEVELOPMENT_STATUS.md` 中列迁移说明。

顶层 `airmirror_future` 导出公共数据类型、`SimulationEngine`、Controller/Ground Truth、
MeasurementOracle、`generate_ris_only_focus_pattern` 和
`generate_coherent_target_pattern`。以下划线开头的成员、GUI 私有槽和 `path_details` 内部
字典不是稳定 API。

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
- 每个 pattern 是弧度一维数组，长度严格等于对应 `cell_count`；
- `model=None` 等价 ControllerModel；
- 结果包含同一 world realization 下的所有路径与指标；
- active RIS、零距离或非法 pattern 明确抛异常。

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
`SimulationCancelled`；baseline 与 with-RIS 共享非 RIS 复场和随机 realization。

## 3. RIS API

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
不读取 baseline。`generate_focus_pattern()` 在 A1 中是行为完全相同的兼容别名，现有 GUI、CLI、
feedback 初始化和 legacy experiment 尚未迁移。

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

低层 `ris_channel_for_points` 是物理层 API，输入 receiver array 形状 `[N,3]`，输出
complex `[N]`；调用者通常应使用 SimulationEngine 以获得阻挡、反射和指标。

## 4. Scene API

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
`initial_patterns`、`cancel_check`、`progress(done,total,value)`；Physics-Guided 自动以
Physics Focus 初始化。

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

实验入口：

```text
python -m airmirror_future.experiments.phase_bits --output PATH
```

## 7. 异常契约

| 情况 | 异常 |
|---|---|
| 字段范围/shape/版本非法 | `ValueError` |
| active RIS 无模型 | `NotImplementedError` |
| 长计算被取消 | `SimulationCancelled` |
| JSON 文件不存在/不可读 | 标准 `OSError`/JSON decode error |
| id 不存在 | 当前为 `StopIteration`；计划统一为带 id 的 `ValueError` |

最后一项是已知 API 粗糙点；调用者不应依赖 `StopIteration`，修复时按兼容流程记录。
