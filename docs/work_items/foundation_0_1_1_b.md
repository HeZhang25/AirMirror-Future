# Work Item：Foundation 0.1.1B Optimizer and GUI Semantics

- 层级：L3 Deliverable
- Requirement IDs：AMF-RIS-008、AMF-RIS-009、AMF-OPT-004、AMF-UI-007、AMF-UI-008
- 状态：Implemented
- 父项：Foundation 0.1.1
- 依赖：A1 Verified、A2 Verified、A3 Verified、FND-FIX-WALL Verified

## Definition of Ready / Ready Review

2026-09-03 Ready Review 结论：**Ready / blocking ambiguity 0**。

已冻结两项决策：

1. Continuous Physics-Guided Feedback 使用 continuous Physics Focus initial pattern，再用
   可配置的 finite `search_levels` 候选做 tile refinement。候选不能严格改善时保留原连续值，
   改善时替换为 search-grid 值；最终 pattern 可混合两者。`search_levels` 不是 hardware state
   数，不得额外量化 initial/final pattern。Finite-bit RIS 始终使用 `2**phase_bits` 个合法硬件状态。
2. Generation 有 pending 编辑时采用 confirm-discard / cancel-preserve：Confirm 丢弃 pending
   并加载 preset；Cancel 恢复原 applied generation、保留全部 pending 控件值并继续 Pending。

## Scope and implementation

### B1 Search resolution contract

- `FeedbackGreedyOptimizer` 和 `PhysicsGuidedFeedbackOptimizer` 接受正整数 `search_levels`；
- continuous RIS 使用配置的搜索级数；finite-bit RIS 忽略覆盖值并使用 `2**phase_bits` 合法状态；
- `OptimizationResult` 记录 `algorithm`、`hardware_phase_bits`、`search_levels`、`pattern_source`
  和 metadata；`search_levels` 只适用于 continuous，finite-bit 另记录 hardware-owned
  `candidate_levels=2**phase_bits`；initial pattern 经过 A3 validator，但不被静默量化。

### B2 Pending/apply/preset state

- GUI 控件编辑进入 Pending，Apply 前 Optimize 被禁用并显示明确状态；
- Apply 重建并校验 applied Scene、重置 GroundTruth、失效旧 worker、重新生成 pattern/results；
- pending Generation 切换弹出丢弃提示，Cancel 保留 pending，Confirm 只替换 preset-owned 字段；
- `Customized` 是 applied RIS 与其 generation preset 的派生显示，不写入 Scene generation。
- GUI 默认 Focus 接入 A1 的 Coherent Target objective，同时保留 RIS-only Physics Focus 作为可选对照；

### B3 Pattern transparency and labels

- Pattern view 显示 Grid、Hardware Phase、Allowed/Used States、Pattern Source、phase error 和循环相位图例；
- Actual 明确表示 Ground Truth phase error 加入后的传播态，不再量化；
- Ground Truth 标签明确区分 Geometry Position Error 与 Feedback Measurement Noise，并说明
  floor-anchored wall 只使用刚体 XY 偏移；
- A2 effective pitch、运行波长和 pitch/λ 作为只读透明度诊断显示，不提供 pass/fail。

## 验收证据

- `tests/test_optimization.py`：continuous search levels 可配置、finite-bit 候选保持硬件合法、
  Physics-Guided 未改善时保留 continuous initial、固定 seed/options 可重放；
- `tests/test_gui_smoke.py`：窗口构造/关闭、取消和 stale version 回归；
- `tests/test_documentation.py`：文档集合、需求追踪、链接和 schema 回归；
- 完整 pytest、三代 fast headless、GUI offscreen smoke、`git diff --check`。

## 明确未包含

C/Profile、FND-QA-AP、FND-PHY-NB、FND-QA-CC、cache、P1、新场景、多 RIS/MIMO/fading、A/B Interim
Checkpoint 和任何 A1/A2/A3/FND-FIX-WALL 重开均不在本 Work Item。

Implementation handoff 只将本 Work Item 和五个 requirements 标记为 Implemented；Verified 需独立审查。
