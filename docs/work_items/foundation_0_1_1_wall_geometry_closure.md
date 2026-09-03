# Work Item：Foundation / Wall Geometry Closure

- 层级：L4 Task（physics/data contract fix）
- Task ID：FND-FIX-WALL
- Requirement IDs：AMF-SIM-006
- 状态：Planned
- 父项：Foundation 0.1.1 Final Exit Gate
- 依赖：当前 v0.1 geometry/reflection/blockage 行为审计完成
- 不属于：新墙体格式、倾斜/悬空墙、多面体建筑、空间分辨 RIS blockage

## 目标与用户结果

消除 `Wall.start/end.z`、`height_m` 与 Ground Truth 三维位置扰动之间的歧义，把 v0.1 实际使用
的“地面锚定竖直墙”变成可验证契约。完成后，加载、阻挡、反射和误差扰动对墙底/墙高的解释
一致，不会接受一个 z 值却在计算时忽略它。

## 当前事实与目标契约

当前实现：

- 墙体平面由 `start/end` 的 XY 线段与 `height_m` 表示；
- 求交高度按绝对区间 `[0,height_m]` 判断，没有使用 `start.z/end.z` 作为墙底；
- Ground Truth position delta 是三维向量，并被同时加到墙两个端点；
- 仓库内现有 Scene 墙端点 z 均为 0，因此默认场景没有暴露该冲突。

目标 v1 契约：

```text
Wall is floor-anchored and vertical
start.z = end.z = 0
occupied height interval = [0, height_m]
Ground Truth wall perturbation = one rigid XY translation (dx,dy,0)
```

墙两个端点必须共享同一 XY 偏移，保持长度和朝向；不得分别随机扰动。TX、RX、RIS 和 obstacle
继续使用现有三维误差语义，本工作项只校准 Wall。

## In / Out

包含：

- 在数据模型/Scene v1 reader 边界拒绝非零或不一致的 wall endpoint z；
- 阻挡与一次反射统一使用 `[0,height_m]`；
- Ground Truth 对墙只取 position delta 的 XY 分量；
- 既有 z=0 场景 round-trip 与数值兼容；
- 向 B3 提供准确术语：“Geometry Position Error：墙体仅 XY，其他实体按其模型维度”。

不包含：

- `base_z/top_z` 新字段或 schema v2；
- 倾斜、悬空、分层、曲面或有厚度墙体；
- per-face material、Fresnel 极化或高阶反射；
- 修改现有场景几何来制造新的演示结果。
- GUI 代码接线；由 B3 / AMF-UI-008 使用本任务已验证的术语。

## 接口与数据

- `Wall.start/end` 继续使用 `Vec3` 保持 Scene v1 结构兼容，但 z 必须 finite 且在文档化容差内为
  0；保存时不得静默裁剪任意非零 z；
- 对不符合契约的外部 Scene v1，加载/构造时抛包含 wall id/字段的 `ValueError`；迁移方式是显式
  将端点 z 设为 0，不能猜测用户意图；
- `GroundTruthModel.position_delta("wall", id)` 的公共返回形状可以保持 3D，但 engine 应只对墙
  使用 `[dx,dy,0]`；是否增加专用 helper 由实现评审决定；
- Scene schema version 保持 1，因为这是对当前计算语义的显式收紧；兼容影响必须写入状态页。
  若 Ready review 发现已有受支持外部文件依赖非零 wall z，本决定必须升级为 schema/ADR 评审，
  不得直接破坏读取兼容。

## 物理/算法约束

- 墙体平移必须为刚体平移，不改变墙段长度、反射平面方向或 `height_m`；
- 同一 seed/scene/model 的 XY 偏移可重放；
- blockage 和 reflection 必须使用同一 perturbed wall geometry；
- 墙 z 误差不得被静默映射为墙高度误差；若未来需要楼板/悬空墙，应建 schema v2 与独立 ADR。

## Tasks

| Task | 状态 | 预计 | 输出 |
|---|---|---:|---|
| `FND-FIX-WALL-01` 冻结 z 容差、错误和迁移契约 | Planned | 0.5 天 | data/schema/API 评审记录 |
| `FND-FIX-WALL-02` 实现 floor-anchor 验证与 XY-only rigid delta | Planned | 0.5–1 天 | 最小 geometry/engine 修改 |
| `FND-FIX-WALL-03` 增加阻挡/反射/seed/round-trip 测试 | Planned | 0.5–1 天 | FND-T19 证据 |
| `FND-FIX-WALL-04` 完整回归与三代 headless | Planned | 0.5 天 | compatibility report |

## 验收证据

- FND-T19a：非零 `start.z/end.z` 被明确拒绝，不能被计算层忽略；
- FND-T19b：Ground Truth wall delta 的 z 分量不改变墙底/墙顶，XY 平移保持墙长与朝向；
- FND-T19c：同一 perturbed wall 同时用于 LOS blockage 和 reflection，固定 seed 可重放；
- 默认 Smart Space JSON round-trip、完整 pytest、三代 fast headless 通过；
- 人工核对 data/physics/schema/status 文案没有声称墙体存在 3D vertical position error；GUI
  代码和最终人工文案由后续 B3 验收。

## 风险与回退

| 风险 | 检测 | 安全回退 |
|---|---|---|
| 外部 v1 文件使用非零 wall z | loader fixture / release note | 明确拒绝并给出迁移说明，不静默改值 |
| 只改阻挡未改反射 | 同场景分路径测试 | 保持任务 In Progress，统一 geometry 后再签署 |
| seed 数值变化影响旧默认结果 | z=0/no-error reference | 默认无误差基线必须等价；有误差结果按 model version 区分 |
| 需求扩大到悬空墙 | scope review | Deferred 到 schema v2，不在本任务加字段 |

## 文档影响

- [x] requirements、Foundation plan、roadmap、status：登记 Planned gate；
- [x] physics、data model、schema、GUI、limitations、test/DoD：冻结目标和现状差异；
- [ ] code/tests：Planned，尚未实现；
- [ ] scene/results/cache：本工作项不修改。
