# 数据模型契约

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation A1-A2 additive contracts |
| 权威实现 | `src/airmirror_future/core/types.py` |

## 1. 通用规则

- 所有物理字段使用 SI；字段名带 `_m/_hz/_w/_rad/_db` 时不得传入显示单位；
- 标识符 `id` 在同类实体列表中必须稳定，patterns 以 RIS id 关联；
- dataclass 构造阶段执行范围校验；从 UI 修改时使用 `dataclasses.replace` 重新校验；
- `Vec3` 和 `RISGeneration` 是冻结值对象，其余场景对象可由会话层替换；
- 结果 dataclass 由计算层创建，调用者视为只读；
- NumPy pattern 一律是一维 `[cell_count]`，显示时 reshape `[ny,nx]`。

## 2. 几何和实体类型

### `Vec3`

| 字段 | 类型 | 单位 | 约束 |
|---|---|---|---|
| `x,y,z` | float | m | finite |

方法：`as_array()->float64[3]`；`distance_to(other)->float`。`distance_to` 可以返回零，
传播函数负责拒绝零距离。

### `Transmitter`

| 字段 | 类型 | 默认 | 约束 |
|---|---|---|---|
| `id` | str | required | 非空 |
| `position` | Vec3 | required | finite |
| `power_w` | float | 0.1 W / 20 dBm | finite，`≥0` |
| `gain_linear` | float | 1.0 | finite，`>0` |

### `Receiver`

| 字段 | 类型 | 默认 | 约束 |
|---|---|---|---|
| `id` | str | required | 非空 |
| `position` | Vec3 | required | finite |
| `gain_linear` | float | 1.0 | finite，`>0` |
| `noise_figure_db` | float | 7.0 dB | finite |

### `Wall`

| 字段 | 类型 | 默认/单位 | 约束 |
|---|---|---|---|
| `id` | str | required | 应在 walls 内唯一 |
| `start,end` | Vec3 | m | 端点不同；z 代表墙底几何参考 |
| `height_m` | float | 3.0 m | finite，`>0` |
| `attenuation_db` | float | 30 dB | finite，`≥0` |
| `reflection_magnitude` | float | 0.4 | `[0,1]` |
| `reflection_phase_rad` | float | π rad | finite |
| `blocks_los` | bool | true | false 时仍可反射 |

派生属性 `reflection_coefficient=rho*exp(j*phase)`。

### `Obstacle`

| 字段 | 类型 | 默认/单位 | 约束 |
|---|---|---|---|
| `id` | str | required | 应在 obstacles 内唯一 |
| `min_corner,max_corner` | Vec3 | m | 每个 min 分量严格小于 max |
| `attenuation_db` | float | 20 dB | finite，`≥0` |
| `fully_blocking` | bool | false | true 使用 300 dB 数值衰减 |

## 3. RIS 类型

### `RISGeneration`

冻结元数据：`name ∈ {Current,Advanced,Future}`、非空中文显示名和
`future_assumption`。它描述 preset，不锁定用户后续编辑的 Surface 参数。

### `RISSurface`

| 字段 | 类型 | 默认/单位 | 约束/语义 |
|---|---|---|---|
| `id` | str | required | patterns key |
| `position` | Vec3 | m | 孔径中心 |
| `yaw_rad` | float | rad | 正面法向方位角 |
| `width_m,height_m` | float | m | finite，`>0`；实体孔径的唯一尺寸事实源 |
| `nx,ny` | int | — | 正整数；沿 width/height 的等效可控孔径 patch 数 |
| `phase_bits` | int或None | 1 | 正整数；None=continuous |
| `reflection_efficiency` | float | 0.7 | `[0,1]` |
| `update_rate_hz` | float | 10 Hz | `>0` |
| `self_sensing` | bool | false | 能力标志，不改变 v0.1 公式 |
| `generation` | str | Current | 显示/追踪标签 |
| `enabled` | bool | true | false 时无 RIS 贡献 |
| `active` | bool | false | true 在 v0.1 拒绝计算 |
| `direction_exponent` | float | 1.0 | finite，`≥0` |

`nx/ny` 的规范含义是 **system-level equivalent controllable aperture patches**。每个 patch
拥有一个 commanded phase，当前又同时承担中心点求积采样；它不是经过器件建模或校准的
真实 meta-atom。旧代码标识符 `cell_count/cell_area_m2/cell_centers` 为兼容保留，语义均按
equivalent patch 解释。

派生值：

- `cell_count=nx*ny`；
- `cell_area_m2=width*height/cell_count`；
- `normal=[cos(yaw),sin(yaw),0]`；
- `cell_centers()->float64[cell_count,3]`。

修改 nx/ny 会使已有 pattern 失效，调用层必须立即重新生成，不能 resize 或截断旧数组。

### `EquivalentPatchDiagnostics`

由纯函数 `equivalent_patch_diagnostics(ris, frequency_hz)` 创建的冻结、只读 SI 结果：

| 字段 | 单位/类型 | 含义 |
|---|---|---|
| `aperture_width_m,aperture_height_m` | m | 从 RIS 复制的实体孔径尺寸 |
| `aperture_area_m2` | m² | `width_m*height_m` |
| `patch_count_x,patch_count_y,patch_count_total` | int | `nx,ny,nx*ny` |
| `effective_pitch_x_m,effective_pitch_y_m` | m | `width_m/nx`、`height_m/ny` |
| `operating_frequency_hz` | Hz | 本次运行频率 |
| `operating_wavelength_m` | m | `c/frequency_hz` |
| `pitch_x_over_wavelength,pitch_y_over_wavelength` | ratio | 只作适用性透明度 |

诊断函数不修改 RIS/Scene，不参与传播，也不返回有效/无效阈值。改变频率只改变波长和比例，
不得反向改写 `width_m/height_m`。A2 不公开 patch 内 phase-span；原因和未来拆网格触发条件见
[ADR-0007](adr/0007-equivalent-controllable-aperture-patches.md)。

## 4. `Scene`

| 字段 | 类型 | 必需/默认 | 约束 |
|---|---|---|---|
| `name` | str | required | 场景显示名 |
| `room_size` | Vec3 | required | 三个分量 `>0` |
| `frequency_hz` | float | required | finite，`>0` |
| `bandwidth_hz` | float | required | finite，`>0` |
| `transmitters` | list[Transmitter] | required | v0.1 GUI 使用首个 |
| `receivers` | list[Receiver] | required | v0.1 GUI 使用首个 |
| `walls` | list[Wall] | [] | — |
| `obstacles` | list[Obstacle] | [] | — |
| `ris_surfaces` | list[RISSurface] | [] | engine 可叠加，GUI/optimizer v0.1 使用一块 |
| `z_eval_m` | float | 1.2 m | `[0,room_size.z]` |
| `coverage_threshold_db` | float | 10 dB | Smart Space 文件设为 35 dB |
| `random_seed` | int | 20260901 | 可重放入口 |
| `schema_version` | int | 1 | reader 仅支持 1 |

`transmitter(id=None)` 和 `receiver(id=None)` 返回首个或指定实体；没有实体时抛
`ValueError`。调用多用户功能前必须扩展 API，不依赖“首个实体”的隐式规则。

## 5. 配置与结果

### `SimulationConfig`

| 字段 | 默认 | 约束 |
|---|---|---|
| `grid_width` | 80 | `≥2` |
| `grid_height` | 60 | `≥2` |
| `map_quantity` | power | power/snr/ris_gain |
| `coverage_threshold_db` | None | None 时使用 Scene |
| `batch_size` | 256 | `>0`；为未来矩阵分块保留 |

### `ChannelResult`

包含 `total_channel`、`los_channel`、`wall_channel`、`ris_channel` 四个 complex，
`received_power_w/dbm`、`noise_power_dbm`、`snr_db`、`shannon_capacity_bps` 和用于显式
射线/诊断的 `path_details`。`path_details` 不是稳定持久化 schema。

### `FieldMapResult`

- `x_m[grid_width]`、`y_m[grid_height]`；
- 四个 `[grid_height,grid_width]` float 数组：received power、SNR、baseline power、
  RIS gain；
- `coverage_percent`、`dead_zone_percent`、`runtime_s`。

所有数组索引 `[row,column]` 分别对应 `y_m[row],x_m[column]`。GUI 显示时翻转图像 y，
数值数组本身保持 y 从小到大。

### `OptimizationResult`

`patterns: dict[ris_id,array]`、最终 `objective_db`、`iterations`（measurement 次数）、
`runtime_s`、每个已接受 tile 后的 `history_db` 和 `cancelled`。

## 6. 模型误差类型

`ControllerModel` 定义无误差行为。`GroundTruthModel` 继承接口并增加六个非负 sigma：RIS
相位、RIS 效率、墙幅度、墙相位、位置、测量噪声，以及整数 seed。sigma 的统计含义见
[physics_model.md](physics_model.md#11-controller-model-与-ground-truth)。
