# Work Item：XR Dynamic Room Adaptive Prototype Extension

- 层级：L3 non-release prototype deliverable
- Work Item / Task ID：`XR-ADAPT-01`
- Requirement IDs：`AMF-XR-001` prototype evidence only；formal requirement 保持 Planned
- 状态：Ready（实现授权仅限本 Work Item，不构成正式 gate/status 授权）
- 父项：[XR Dynamic Room MVP](xr_dynamic_room_mvp.md)
- 基线：`origin/main@275fedfe6a8a4a1d8a45d3045cf6334e4d4202e2`
- 依赖：已合并的 headless/GUI MVP、signed production midpoint M8、ControllerModel、
  `generate_coherent_target_pattern`、C2 provenance/no-overwrite contract
- 后续重验：FND-PHY-NB、FND-QA-CC；Adaptive 结果在两项关闭前均为 provisional

## 目标与用户结果

在原 11 点确定性室内轨迹上增加 Adaptive RIS：每个离散 sample 通过现有 Controller
Coherent Target Focus 生成一个合法 commanded pattern，并由同一 production
SimulationEngine 评价。headless 输出可重放的三模式 CSV/PNG；现有 XR GUI 可播放与当前
sample command 对应的真实场图，且不在播放线程运行物理计算。

本项是 ideal instantaneous reconfiguration 的 non-release prototype，不表示真实控制时延、
硬件更新率、连续时间 tracking、Foundation closure、P1A 或 formal v0.2 XR。

## In / Out

In：

- 保留原 Current Smart Space scene 与 `p(t)=(8.5-0.3t, 4.0+0.3t, 1.2)`；
  `t=0,0.5,...,5.0 s`，共 11 点；
- No RIS 使用空 pattern mapping；Static 在 `t=0` 生成一次命令并冻结；Adaptive 每点重新
  调用现有 `generate_coherent_target_pattern`；
- 三模式共享 Scene/TX/RX trajectory/frequency/bandwidth/Profile/power/noise/ControllerModel；
- 每行保存实际 command 的不可变 snapshot、SHA-256 identity、channel components、模型与
  C2 canonical partial provenance；No RIS 使用显式无 command 语义；
- exclusive no-overwrite run directory 内生成 CSV/PNG；
- GUI 在一个 versioned worker 中分步计算 link states 和有界 field cache，发布可验证的部分结果；
- Fast `80×60` 默认 field budget：No RIS 由 Static field 的 baseline 派生、Static 只算一次、
  Adaptive 按 command identity 懒加载并缓存当前 sample 的真实 field；相同 command 可复用。

Out：

- Ground Truth oracle、Adaptive 优于 Static 的保证或结果挑选；
- production coefficient/Focus/M8/objective/tie-break 修改；
- P1A、`A @ Gamma`、矩阵/增量 cache 或 generalized cache framework；
- Scene v1 动态 schema、formal v0.2、人体/头部、真实控制时延、28/60 GHz formal support；
- wideband/OFDM、fading/Doppler、多 RIS、Factory/City、动态高分辨率场图；
- Foundation、P1A、FND-PHY-NB、FND-QA-CC 或共享 status promotion。

## 接口与数据

- 保持 `create_mvp_scene()`、`build_trajectory()`、旧 `compute_mvp()` 和 No RIS/Static 行为兼容；
- 新三模式计算返回每个 `(sample_index, mode)` 的 immutable command snapshot：
  No RIS 为 `None`，Static/Adaptive 为只读 float64 `[nx*ny]`；hash 不能代替 snapshot；
- CSV 使用一行一个 sample/mode，增加 command kind/hash/values 和 LOS/wall/RIS/total complex
  components，并复用 `airmirror_experiment_provenance/1`；`channel_frequency_model_id` 与
  `coefficient_model_identity` 保持 canonical builder 的当前 pending/empty 语义，不猜 owner 字段；
- GUI field cache key 至少包含 scene/model/Profile identity、command identity、grid dimensions 与
  evaluation height。缓存只保存完整真实 `FieldMapResult`；取消、失败或旧 version 不进入 cache；
- GUI 不写传播公式；No RIS SNR 只由同一 Static solve 的 baseline power 与项目 noise helper 派生。

## 物理/算法约束

- Focus 只接受 `ControllerModel`，不读取 Ground Truth；
- 每个 command 必须通过现有 commanded-pattern validator，复制后设为只读；
- `t=0` 的 Static/Adaptive 使用相同输入，command/hash/评价必须完全一致；
- production midpoint `8×8`、Profile/reflection ownership、center-frequency flat-channel behavior
  保持不变；FND-QA-CC 关闭前所有 Adaptive 结果标记 provisional，并记录 Focus/engine/policy identity；
- 不要求 Adaptive 在任一 sample 或 aggregate 上优于 Static。

## Tasks

1. `XR-ADAPT-01A`：headless result/command/provenance extension 与确定性测试；
2. `XR-ADAPT-01B`：真实三模式 run、CSV/PNG replay evidence；
3. `XR-ADAPT-01C`：GUI worker 分步取消/版本隔离和有界 field cache；
4. `XR-ADAPT-01D`：三模式 playback、snapshot consistency、restore 与显示规格；
5. `XR-ADAPT-01E`：focused/full regression、三代 fast smoke、性能记录与 PR。

## 验收证据

- trajectory 重建相同；同配置重复运行数值、command 与 hash 相同；
- Static 全程同一 snapshot/hash；Adaptive 每步 snapshot 合法且与其 channel/field 对应；
  No RIS 没有 command 且 RIS channel 为零；
- `t=0` Static/Adaptive command、hash 和 link result 一致；三模式非 RIS 条件相同且全部有限；
- CSV 可无损重建命令，schema/sample count/provenance/run_id 正确，目标存在时计算前失败；PNG 成功；
- GUI No/Static 固定 field 不重复算；Adaptive 只为请求 sample 计算真实 field，按完整 identity
  缓存；mode/quantity/playback/slider 不同步运行 physics；未就绪显示明确；
- worker cancellation、partial/late result、stale version、退出恢复和 Smart Space 回归通过；
- focused RIS/Focus/engine/M8/Profile、full pytest、Current/Advanced/Future fast headless、
  documentation tests 与 `git diff origin/main --check` 通过；
- 真实 Windows GUI 鼠标验收由有显示能力的执行者完成；offscreen 结果不得冒称真人验收。

## 风险与回退

- Current M8 Fast field 单张需数秒；默认只预取 Static 一张，Adaptive 按需串行计算，UI 显示
  pending，避免无界 11 张启动等待。若预算仍不可接受，回退为仅 link playback，不显示假 field；
- FND-QA-CC 可能改变 Focus/coefficient seam；关闭后必须重新生成 pattern/hash/CSV/field，旧结果
  不作为正式证据；
- FND-PHY-NB owner 后续提供 canonical model ID 时由独立集成更新；本项不抢写其字段；
- 回退本 task commit 可恢复已合并的两模式 MVP，不迁移或覆盖任何历史 result。

## Ownership / forbidden paths

Owned：本 Work Item、`experiments/xr_dynamic_room_mvp.py`、`gui/main_window.py`、
`gui/workers.py`、必要的 `gui/scene_view.py`、XR-focused tests，以及与本行为直接相关的
`gui_spec.md` / `experiment_spec.md`。

Forbidden：production physics/RIS coefficient、quadrature、Focus objective、Scene schema、
Foundation/P1A work items、`requirements.md`、`DEVELOPMENT_STATUS.md`、roadmap、tracked results、
历史 QA/checkpoint artifacts。

## Ready review

高影响选择已冻结：无新物理公式、无 schema major、无 GT oracle、无 P1A cache；三模式对照、
command snapshot、provisional provenance、field identity、取消/版本边界和资源预算均有明确测试。
Blocking ambiguity：0。该 Ready 只授权本 prototype 实现，不提升任何正式状态。
