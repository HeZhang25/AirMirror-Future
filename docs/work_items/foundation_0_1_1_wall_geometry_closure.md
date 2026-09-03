# Work Item：Foundation / Wall Geometry Closure

- 层级：L4 Task（physics/data contract fix）
- Task ID：FND-FIX-WALL
- Requirement IDs：AMF-SIM-006
- 状态：Verified（2026-09-03）
- 父项：Foundation 0.1.1 Final Exit Gate
- 依赖：当前 v0.1 geometry/reflection/blockage 行为审计完成
- 不属于：新墙体格式、倾斜/悬空墙、多面体建筑、空间分辨 RIS blockage

## 目标与用户结果

消除 `Wall.start/end.z`、`height_m` 与 Ground Truth 三维位置扰动之间的歧义，把 v0.1 实际使用
的“地面锚定竖直墙”变成可验证契约。完成后，加载、阻挡、反射和误差扰动对墙底/墙高的解释
一致，不会接受一个 z 值却在计算时忽略它。

## Definition of Ready 结论

2026-09-03 完成 Ready review，结论为 **Ready / blocking ambiguity 0**：

- `AMF-SIM-006`、目标/非目标、SI 单位、shape、异常所有者、物理边界和 FND-T19 已预先定义；
- A1/A2/A3 已 Verified，本项位于 A 后、B 前，不依赖 B/C、FND-QA-AP、FND-PHY-NB、
  FND-QA-CC、cache 或新场景；
- endpoint z 采用公共绝对容差 `WALL_ENDPOINT_Z_ATOL_M=1e-9 m`。该量级只吸收浮点/JSON
  交换噪声，相对米级场景可忽略；它不是可配置物理墙底或 height tolerance，比较不使用相对
  容差；
- 容差内 z 原值只被接受，不 snap/crop；writer 原样保存。任一 endpoint 超差时抛
  `ValueError`，错误必须包含 wall id、`start.z` 或 `end.z`、实际值、Scene v1 floor-anchor 原因，
  以及“显式把 `start.z/end.z` 设为 0”的迁移指引；
- 仓库唯一受支持的 `scenes/smart_room.json`、内建 Smart Space、相关测试及该 Scene 的完整 Git
  历史中，所有 Wall endpoint z 均为 0；未发现受支持外部文件依赖非零 z，因此保持 schema
  version 1，不触发 schema/ADR 升级；
- Ground Truth 继续为 key 生成三维 position delta，以保持公共返回 shape 和 XY 随机序列；engine
  对每堵墙只取样一次并仅使用 `[dx,dy,0]`，TX/RX/RIS/obstacle 的既有三维语义不变；
- 墙段必须在 XY 非退化；否则二维阻挡/反射平面没有定义，构造时以带 wall id 的 `ValueError`
  拒绝；
- 随机 seed、重放方式、Scene v1 兼容策略、自动测试、三代 headless、documentation/full pytest
  和 `git diff --check` 门禁均已明确；本项不需要 GUI 实现或新人工交互步骤。

上述选择是对既有 v1 实际计算语义的最小闭环，不改变层依赖、Scene 结构、反射公式或误差
分布，故不触发新 ADR。

## 实现前事实与已实现契约

实现前基线：

- 墙体平面由 `start/end` 的 XY 线段与 `height_m` 表示；
- 求交高度按绝对区间 `[0,height_m]` 判断，没有使用 `start.z/end.z` 作为墙底；
- Ground Truth position delta 是三维向量，并被同时加到墙两个端点；
- 仓库内现有 Scene 墙端点 z 均为 0，因此默认场景没有暴露该冲突。

已实现的 v1 契约：

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

- `Wall.start/end` 继续使用 `Vec3` 保持 Scene v1 结构兼容，z 必须 finite 且各自满足
  `|z|≤WALL_ENDPOINT_Z_ATOL_M=1e-9 m`；保存时不裁剪容差内原值；
- 对不符合契约的外部 Scene v1，加载/构造时抛包含 wall id/字段的 `ValueError`；迁移方式是显式
  将端点 z 设为 0，不能猜测用户意图；
- `GroundTruthModel.position_delta("wall:<id>")` 的公共返回形状保持 3D，但 engine 只对墙
  使用 `[dx,dy,0]`；Ready review 决定直接在 working-scene 构造边界消费该值，不增加新的公共
  helper；
- Scene schema version 保持 1，因为这是对当前计算语义的显式收紧；兼容影响必须写入状态页。
  Ready review 未发现受支持外部文件依赖非零 wall z；未来若出现新的兼容证据或需要悬空墙，
  必须升级为 schema/ADR 评审，不得静默改变本契约。

## 物理/算法约束

- 墙体平移必须为刚体平移，不改变墙段长度、反射平面方向或 `height_m`；
- 同一 seed/scene/model 的 XY 偏移可重放；
- blockage 和 reflection 必须使用同一 perturbed wall geometry；
- 墙 z 误差不得被静默映射为墙高度误差；若未来需要楼板/悬空墙，应建 schema v2 与独立 ADR。

## Tasks

| Task | 状态 | 预计 | 输出 |
|---|---|---:|---|
| `FND-FIX-WALL-01` 冻结 z 容差、错误和迁移契约 | Implemented | 0.5 天 | data/schema/API Ready review 记录 |
| `FND-FIX-WALL-02` 实现 floor-anchor 验证与 XY-only rigid delta | Implemented | 0.5–1 天 | `core/types.py`、`simulation/engine.py` |
| `FND-FIX-WALL-03` 增加阻挡/反射/seed/round-trip 测试 | Implemented | 0.5–1 天 | `tests/test_wall_geometry.py` FND-T19 |
| `FND-FIX-WALL-04` 完整回归与三代 headless | Implemented | 0.5 天 | implementation compatibility report |

## 验收证据

- FND-T19a：超出绝对 `1e-9 m` 容差的 `start.z/end.z` 被明确拒绝，不能被计算层忽略；
- FND-T19b：Ground Truth wall delta 的 z 分量不改变墙底/墙顶，XY 平移保持墙长与朝向；
- FND-T19c：同一 perturbed wall 同时用于 LOS blockage 和 reflection，固定 seed 可重放；
- 默认 Smart Space JSON round-trip、完整 pytest、三代 fast headless 通过；
- 人工核对 data/physics/schema/status 文案没有声称墙体存在 3D vertical position error；GUI
  代码和最终人工文案由后续 B3 验收。

自动门禁通过后的 implementation handoff 已将本 Work Item 与 `AMF-SIM-006` 提升为
Implemented；Verified 由独立人工验收决定。

2026-09-03 本机 Windows / Python 3.14.3 实现证据：FND-T19 + 既有 blockage/reflection/scene
定向回归 `13 passed`；wall/GT/scene + physics/RIS/A1/A3/optimization 相关回归 `79 passed`；
documentation tests `9 passed`；完整 pytest `103 passed in 3.59s`；`git diff --check` 通过。
Current/Advanced/Future fast headless 的目标功率依次为
`-46.5879/-30.1257/-19.3118 dBm`，RIS Gain 依次为
`+8.6874/+25.1496/+35.9636 dB`，与 A1/A2/A3 基线一致。场图运行时间依次为
`3.045/3.869/9.370 s`，仅作同机参考。

兼容审计确认仓库唯一受支持 Scene、内建 Smart Space、测试 fixture 和该 Scene 历史均为 z=0；
schema version 1、默认数值与 Ground Truth XY 随机序列不变。兼容收紧只影响超容差 endpoint z
和 XY 重合而仅 z 不同的退化墙段。未修改 Scene、results、cache、GUI、B/C 或其他后续能力。

2026-09-03 独立人工审查已完成：验收对象为 implementation commit
`8841ef286e8e4c3a6ecea04592f69d9306a80fa1`，G0–G8 全部 PASS，blocking issues 为 0。本次
verification/status closure 仅更新 Markdown 状态事实源；FND-FIX-WALL 与 `AMF-SIM-006` 提升为
Verified。A1/A2/A3 保持 Verified；Foundation 0.1.1A / Foundation 0.1.1 保持 In Progress；B/C、
FND-QA-AP、FND-PHY-NB、FND-QA-CC 及其他 Planned/In Progress 能力不变。

## 风险与回退

| 风险 | 检测 | 安全回退 |
|---|---|---|
| 外部 v1 文件使用非零 wall z | loader fixture / release note | 明确拒绝并给出迁移说明，不静默改值 |
| 只改阻挡未改反射 | 同场景分路径测试 | 保持任务 In Progress，统一 geometry 后再签署 |
| seed 数值变化影响旧默认结果 | z=0/no-error reference | 默认无误差基线必须等价；有误差结果按 model version 区分 |
| 需求扩大到悬空墙 | scope review | Deferred 到 schema v2，不在本任务加字段 |

## 文档影响

- [x] requirements、Foundation plan、roadmap、status：同步 Verified 独立验收结论与状态边界；
- [x] physics、data model、public API、schema、architecture、GUI、glossary、limitations、test/DoD：
  同步 floor-anchor、容差、错误、XY-only 和限制；
- [x] code/tests：完成最小 data/engine 修改与 FND-T19；
- [x] scene/results/cache：确认本工作项未修改。
