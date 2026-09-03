# Work Item：Foundation 0.1.1A / A3 Commanded Pattern Hardware Boundary

- 层级：L3 Deliverable
- Requirement IDs：AMF-RIS-010
- 状态：Verified
- 父项：Foundation 0.1.1A — Physics and Algorithm Contract
- 依赖：v0.1 Verified、A1 Verified、A2 Verified、ADR-0003、ADR-0006、ADR-0011

## 目标与用户结果

任何 RIS commanded phase array 在进入传播和 Ground Truth 扰动前，都由同一硬件契约证明其
shape、有限性和离散状态合法；调用者的非法命令得到明确 `ValueError`，而 Ground Truth actual
phase error 保持为真实扰动，不被重新量化或静默抹除。

## Definition of Ready 结论

2026-09-03 完成 Ready review，结论为 **Ready / blocking ambiguity 0**：

- `AMF-RIS-010`、A3 输入/输出、Commanded→Actual 顺序和 FND-T06..08 已由 Foundation 计划定义；
- A1/A2 已 Verified；A3 不改变两项既有语义，也不依赖 B/C 或 cross-cutting Planned 能力；
- validator 的公共 ownership/导出属于 `ris` pattern contract；共享纯实现放在 `core`，使 engine
  和低层公开散射 API 复用同一单 RIS validator；依赖方向符合 architecture；
- commanded 输入是 radians、严格一维 `[ris.cell_count]`；非法 key、歧义 key、shape、长度、
  NaN/Inf 或离散 off-grid state 均抛 `ValueError`；
- 离散比较采用模 `2*pi` 的最近均匀状态距离，绝对容差固定为 `1e-6 rad`、`rtol=0`。该容差覆盖
  float32 和常规十进制交换舍入，同时相对最小受支持 4-bit 状态间隔仍可忽略；容差内只接受原值，
  不 wrap、不 snap、不 quantize；
- continuous hardware 接受任意 finite、未 wrap phase；Ground Truth phase error 只在验证后相加，
  Actual 不再次进入 validator/quantizer；
- 无新增随机过程；FND-T08 使用确定性 actual error 隔离重放边界；
- Scene JSON v1 不保存 pattern，本项不改 schema、不迁移历史数据；
- 自动测试、三代 headless、documentation tests、完整 pytest 和 `git diff --check` 已定义；A3 不含
  GUI/search resolution/Profile/wall/quadrature/coefficient/cache 等后续工作；
- 上述选择落实既有 requirement，不改变层依赖、Scene major 或物理公式，因此不触发新 ADR。

## In / Out

包含：公共单 RIS commanded validator、固定 tolerance、严格 phase-bits 类型边界、engine map
key/shape/state validation、field-map 循环外单次验证、低层散射入口复用、FND-T06..08 和状态文档
闭环。

不包含：FND-FIX-WALL、hardware/search resolution 分离、GUI pending/pattern metadata、
PropagationProfile、实验 provenance、独立 quadrature、coefficient builder、一致性签署、cache、
新 Scene 字段、新场景、MIMO 或 fading。

## 接口与数据

```python
validate_commanded_pattern(
    ris: RISSurface,
    phase_rad: np.ndarray,
) -> np.ndarray
```

- 返回保留原数值表达的独立 `float64[cell_count]` 验证快照；不 wrap、不 quantize；
- `COMMANDED_PHASE_ATOL_RAD = 1e-6` 是公共绝对容差；
- `SimulationEngine.compute_channel/compute_field_map` 对非 `None` 输入要求 Mapping，key 必须唯一
  对应 Scene 中一块 RIS；未知或歧义 id 抛带 id 的 `ValueError`；
- map 中未出现的 RIS 仍表示不贡献；`None/{}` 仍表示 No RIS；禁用 RIS 若显式收到 pattern，命令
  仍先按其硬件契约验证；
- `RISSurface.phase_bits` 必须是正整数或 `None`，bool 和小数拒绝；
- Scene schema 与 pattern flatten order 不变。

## 物理/算法约束

合法离散状态为 `k*2*pi/(2**phase_bits)`。validator 只计算 commanded phase 到最近状态的循环
距离；不得调用量化器修正输入。传播仍使用原 commanded 数值，因此容差只决定接受/拒绝，不改变
复场。Ground Truth 继续按 ADR-0003 生成 actual phase/efficiency，且 actual phase 不再经过硬件
状态验证或量化。A3 不改变散射公式、面积标度、方向图、Focus 或随机采样。

## Tasks

- [x] 建立公共 pattern contract、固定 tolerance 和严格 `phase_bits` 类型校验；
- [x] 在 `compute_channel`、`compute_field_map` 与低层公开 RIS scattering 入口接入同一 validator；
- [x] 保证 field map 在像素循环前只做一次 commanded validation；
- [x] 实现 FND-T06..08 及 unknown/ambiguous key、strict shape、finite、public export 回归；
- [x] 同步 requirements、API/data/physics/architecture/test、plan/roadmap/status；
- [x] 运行定向、相关回归、documentation、完整 pytest、三代 headless 和 diff check；
- [x] 完成 A3 focused implementation commit，保持 Verified 由独立审查决定。

## 验收证据

- `tests/test_pattern_contract.py`：FND-T06..08、类型/shape/key/finite、入口和单次 field-map validation；
- `tests/test_ris.py`：量化、RIS-only、面积归一化、孔径、背面方向回归；
- `tests/test_coherent_focus.py`：A1 objective/候选/Controller 边界回归；
- `tests/test_scene_engine.py`：Scene、Ground Truth、单链路和场图集成回归；
- `tests/test_documentation.py`；
- `python -m pytest`；
- Current/Advanced/Future fast headless；
- `git diff --check`。

自动门禁通过后的 implementation handoff 只将本 Work Item 提升为 Implemented；Verified 必须由
独立人工验收决定。

2026-09-03 本机 Windows / Python 3.14.3 实现证据：A3 定向 `22 passed`；A3 + RIS +
scene/engine + A1 coherent + optimization 相关回归 `63 passed`；documentation tests
`9 passed`；完整 pytest `96 passed`；`git diff --check` 通过。Current/Advanced/Future fast
headless 的目标功率依次为 `-46.5879/-30.1257/-19.3118 dBm`，RIS Gain 依次为
`+8.6874/+25.1496/+35.9636 dB`，与 A2/A1 兼容基线一致。运行时间只作同机参考。

2026-09-03 完成独立人工验收：验收对象为 implementation commit
`fb5ec093e78e588a65a661abf3b32d744d04ae04`，G0–G8 全部 PASS，blocking issues 为 0。本次
签署将 A3 Deliverable 与 `AMF-RIS-010` 提升为 Verified；A1/A2 保持 Verified，Foundation
0.1.1A 和 Foundation 0.1.1 仍保持 In Progress，其他 Planned/In Progress 能力不变。
本次 verification/status closure 仅修改 Markdown 状态事实源；documentation tests `9 passed`、
完整 pytest `96 passed`、`git diff --check` 通过。

## 风险与回退

- 合法浮点状态被误拒绝：用 modulo、正负多周和容差边界测试；只通过有依据的契约变更调整
  tolerance，不调用 quantizer 兜底；
- field map 每像素重复验证：以调用次数测试锁定循环外 enforcement；
- engine 与低层 API 分叉：两者调用同一公共 validator，传播内核只接受已验证快照；
- Actual error 被抹除：确定性非网格误差测试直接比较 Controller/Actual RIS 复相位；
- 更严格输入暴露旧调用方问题：报告带 RIS id 的 `ValueError`，不 reshape、截断或 silent quantize。

## 文档影响

- [x] requirements / Foundation plan / roadmap
- [x] data model / public API
- [x] physics / architecture / glossary
- [x] test strategy
- [x] development status / root README
- [x] scene schema（确认无变化）
- [x] ADR（Ready review 确认不需要新增）
