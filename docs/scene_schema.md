# Scene JSON Schema v1

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| Schema version | 1 |
| 示例 | `scenes/smart_room.json` |

## 1. 编码和兼容规则

- UTF-8 JSON；写出时 `ensure_ascii=false`、两空格缩进；
- 所有数值为 SI；JSON 中不得使用 `NaN`、`Infinity`；
- `schema_version` 写出时必有且为整数 1；reader 缺省时暂按 1 读取；
- reader 对未知字段采取 forward-compatible 忽略策略，但 writer 不保留未知字段；
- 不支持的 schema version 必须拒绝，不能自动猜测迁移；
- 新增可选字段可保持 v1；改变含义、单位、必需性或结构必须升 schema version 并提供迁移。

## 2. 顶层对象

| 字段 | 类型 | 必需 | 默认 | 说明 |
|---|---|---|---|---|
| `schema_version` | integer | 建议必有 | 1 | 当前只支持 1 |
| `name` | string | 是 | — | 场景名 |
| `room_size` | Vec3 | 是 | — | 正三维尺寸 |
| `frequency_hz` | number | 是 | — | `>0`；中心频率 `fc` |
| `bandwidth_hz` | number | 是 | — | `>0`；等效占用/接收噪声带宽，不表示频率网格 |
| `transmitters` | array | 否 | [] | v0.1 GUI 要求至少一个 |
| `receivers` | array | 否 | [] | v0.1 GUI 要求至少一个 |
| `walls` | array | 否 | [] | Wall 对象 |
| `obstacles` | array | 否 | [] | Obstacle 对象 |
| `ris_surfaces` | array | 否 | [] | RISSurface 对象 |
| `z_eval_m` | number | 否 | 1.2 | 位于 room 高度内 |
| `coverage_threshold_db` | number | 否 | 10 | SNR coverage 门限 |
| `random_seed` | integer | 否 | 20260901 | 重放 seed |

`Vec3` 统一为：

```json
{"x": 1.0, "y": 2.0, "z": 1.2}
```

## 3. Transmitter / Receiver

```json
{
  "id": "tx-1",
  "position": {"x": 1.0, "y": 4.0, "z": 2.4},
  "power_w": 0.1,
  "gain_linear": 1.0
}
```

TX 的四个字段写出时均存在。RX 对应字段为 `id`、`position`、`gain_linear`、
`noise_figure_db`；reader 对后二者默认 1.0 和 7.0。

## 4. Wall

```json
{
  "id": "partition",
  "start": {"x": 5, "y": 2, "z": 0},
  "end": {"x": 5, "y": 6, "z": 0},
  "height_m": 3.0,
  "attenuation_db": 30.0,
  "reflection_magnitude": 0.45,
  "reflection_phase_rad": 2.6,
  "blocks_los": true
}
```

`id/start/end` 必需。其他 reader 默认依次为 3.0、30.0、0.4、π、true。

`AMF-SIM-006` 在保持 schema version 1 的前提下把 Wall 冻结为 floor-anchored vertical wall：
`start.z/end.z` 必须 finite 且各自满足 `|z|≤1e-9 m`，占据高度固定为 `[0,height_m]`。容差内
原值 round-trip 时不裁剪；超差输入抛包含 wall id、具体字段、实际值和显式归零迁移指引的
`ValueError`，不会猜测为悬空墙。保持 v1 的依据是仓库唯一受支持的 Scene、内建场景、相关
测试及其 Git 历史均使用精确 z=0，非零 z 从未有已验证计算语义。实现与兼容证据见
[FND-FIX-WALL](work_items/foundation_0_1_1_wall_geometry_closure.md)。

Foundation 不向 Scene v1 增加 `profile`、`channel_frequency_model_id` 或 Python 类名字段。
Profile 与 frequency-model identity 属于运行/实验 provenance；若未来需要场景持久化选择，应
通过新的 schema/ADR 评审，而不是依赖 reader 忽略未知字段。

C1 Ready contract 不增加 Wall 字段，但将 `walls[*].id` 收紧为数组内必须唯一，以保证 reflecting
wall self-exclusion 只排除一堵墙。实现后 duplicate wall ID 在 Scene 构造/加载时抛包含重复值的
`ValueError`，engine 还会防御可变 list 的事后重复；不自动改名、选首项或按对象 identity 回退。
该 validation tightening 尚未实现，仓库受支持 scene 已审计为无重复值，因此保持 schema v1。

## 5. Obstacle

```json
{
  "id": "cabinet",
  "min_corner": {"x": 7, "y": 1.5, "z": 0},
  "max_corner": {"x": 8, "y": 2.5, "z": 2.2},
  "attenuation_db": 20.0,
  "fully_blocking": false
}
```

`id/min_corner/max_corner` 必需。min 每个分量严格小于 max。

## 6. RISSurface

```json
{
  "id": "ris-1",
  "position": {"x": 5, "y": 7.9, "z": 1.5},
  "yaw_rad": -1.5707963267948966,
  "width_m": 0.8,
  "height_m": 0.8,
  "nx": 8,
  "ny": 8,
  "phase_bits": 1,
  "reflection_efficiency": 0.7,
  "update_rate_hz": 10.0,
  "self_sensing": false,
  "generation": "Current",
  "enabled": true,
  "active": false,
  "direction_exponent": 1.0
}
```

前八个字段（到 `phase_bits`）是 v1 reader 必需字段；continuous 写 JSON `null`。其他字段
有与 dataclass 一致的默认值。patterns 不保存在 v1 Scene 中；加载后由控制策略重新生成。

## 7. 标识符和引用

- 同一数组中的 id 必须唯一；推荐全 scene 唯一以便日志定位；
- 当前 v0.1 reader 尚未自动检查重复 id；C1 Ready target 只把 wall ID 的构造/reader/engine
  enforcement 纳入本轮后续实现，其他数组仍按既有显式引用边界校验；
- JSON 不存对象引用，patterns/metrics 只在运行时按 id 关联；
- 修改 id 是破坏性场景变更，会使外部实验记录无法关联。

## 8. v2 触发条件

以下任何一项出现时必须建立 v2 与迁移器：轨迹/时间轴、材料库引用、多用户目标、保存
patterns、非轴对齐体积障碍物、宽带频点数组、RIS tile aggregation 的新结构或单位变化。
不能把这些内容塞入未知 dict 并继续标 v1。
