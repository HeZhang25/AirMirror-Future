# 需求基线与追踪矩阵

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation A1-A2 + physics/algorithm master-plan integration |
| 编号规则 | `AMF-<DOMAIN>-<NNN>`；删除后不复用 |

状态含义见 [glossary.md](glossary.md)。证据列必须是测试、命令或人工验收步骤；仅有源码
文件名不构成验证证据。

## 核心与物理

| ID | 需求/验收结果 | 状态 | 实现位置 | 验证证据 |
|---|---|---|---|---|
| AMF-CORE-001 | 内部统一 SI，三维有限坐标；非法值明确报错 | Implemented | `core/types.py`, `core/units.py` | `tests/test_free_space.py`, `tests/test_scene_engine.py` |
| AMF-CORE-002 | 距离、功率转换有数值下限，不输出未处理 NaN/Inf | Implemented | `core/constants.py`, `core/units.py` | `test_invalid_distance_is_rejected`, Smart Space integration test |
| AMF-PHY-001 | LOS 使用含相位的复数 Friis 信道 | Implemented | `physics/free_space.py` | `test_distance_doubled_drops_power_by_about_six_db`, wavelength test |
| AMF-PHY-002 | 所有路径复场相加后由 `Pt|h|²` 求功率 | Implemented | `simulation/engine.py` | `test_complex_field_interference`, integration test |
| AMF-PHY-003 | 噪声为 `-174+10log10(B)+NF`；容量标注 Shannon 上界 | Implemented | `physics/noise.py`, GUI Model Info | `test_noise_and_shannon_upper_bound_are_finite` |
| AMF-PHY-004 | 墙体采用有限线段 image method 一次反射，`|Γ_wall|≤1`；墙系数由 Wall/Reflection Model 拥有并在每条反射路径恰好应用一次 | Implemented | `physics/reflections.py`、[ADR-0012](adr/0012-wall-reflection-coefficient-ownership.md) | `test_image_method_finds_specular_point_on_finite_wall`；C1 FND-T13c/T13d 补所有权回归 |
| AMF-PHY-005 | 墙/矩形障碍物求交后按 dB 施加幅度衰减 | Implemented | `physics/blockage.py` | `test_complete_los_path_applies_wall_attenuation` |
| AMF-PHY-006 | v0.1 明确不包含衍射、高阶反射、互耦和极化 | Verified | docs、Model Info | `docs/limitations.md`, GUI smoke |
| AMF-PHY-007 | `frequency_hz` 明确为中心频率，信道在 `bandwidth_hz` 内采用平坦窄带近似；容量与 provenance 不得误称宽带/真实吞吐 | Planned | [ADR-0010](adr/0010-narrowband-center-frequency-flat-channel.md)、[FND-PHY-NB](work_items/foundation_0_1_1_narrowband_contract.md) | FND-T20、Model Info/实验字段人工复核 |

## RIS

| ID | 需求/验收结果 | 状态 | 实现位置 | 验证证据 |
|---|---|---|---|---|
| AMF-RIS-001 | RIS 是有限实体孔径，cell center 为 NumPy 数组，面积总和等于孔径 | Implemented | `core/types.py` | aperture subdivision test |
| AMF-RIS-002 | 无源效率限制 `[0,1]`；active 无功率/噪声模型时拒绝 | Implemented | `RISSurface`, `ris_scattering.py` | `test_passive_efficiency_above_one_is_rejected` |
| AMF-RIS-003 | 支持 continuous 与 1/2/3/4-bit 均匀相位量化 | Implemented | `ris/phase.py` | `test_phase_quantization_states` |
| AMF-RIS-004 | Physics Focus 遵循统一相位符号并显著优于随机中位数 | Implemented | `ris/phase.py` | `test_physics_focus_beats_random_pattern_median` |
| AMF-RIS-005 | 固定孔径在面积归一化下细分 control grid 不产生无界 patch-count 增益，并表现稳定趋势；增大实体孔径通常提升理想聚焦 | Implemented | area-normalized scattering | PHY-T11 no-unbounded-gain test、larger-aperture test；不作为独立 quadrature convergence 证据 |
| AMF-RIS-006 | RIS 背面方向贡献为零，默认余弦方向图 `q=1` | Implemented | `physics/ris_scattering.py` | `test_back_side_receiver_gets_no_ris_field` |
| AMF-RIS-007 | 三代 preset 是可编辑假设；Future 显式标记 | Implemented | `ris/generations.py`, GUI | headless generation runs、GUI smoke |
| AMF-RIS-008 | 区分 RIS-only 与 Coherent Target Focus；GUI 默认算法与 nominal target objective 一致 | In Progress | A1: `ris/phase.py`, `optimization/coherent_focus.py`；GUI 接入待 B 阶段 | `tests/test_coherent_focus.py` FND-T01..05；ADR-0006 |
| AMF-RIS-009 | `nx/ny` 定义为 equivalent controllable aperture patches，并显示有效 pitch/波长比例和限制 | In Progress | A2: `ris/aperture.py`、ADR-0007；GUI 只读接入待 B 阶段 | `tests/test_aperture_diagnostics.py` FND-T09；[A2 Work Item](work_items/foundation_0_1_1_a2.md) |
| AMF-RIS-010 | 传播前验证 commanded pattern 符合 phase bits；Actual Ground Truth error 不再量化 | Planned | — | `foundation_0_1_1_plan.md` FND-T06..08 |
| AMF-RIS-011 | 在 Foundation final exit/P1A 前固定 aperture/control/pattern、仅细化独立 quadrature，冻结可重放的 coefficient policy 和声明适用域 | Planned | [ADR-0008](adr/0008-minimum-aperture-quadrature-validity-gate.md)、[FND-QA-AP](work_items/foundation_0_1_1_qa_ap.md) | FND-T16..18、versioned QA matrix、人工 policy 签署；不等同 EM/full-wave truth |
| AMF-RIS-012 | 最终 production policy 下，RIS-only/Coherent Focus 与 Controller simulator 使用同一 control-level 复系数定义；Ground Truth 系数不得泄漏给 Focus | Planned | [ADR-0011](adr/0011-controller-coefficient-focus-consistency.md)、[FND-QA-CC](work_items/foundation_0_1_1_coefficient_consistency.md) | FND-T21..22、Controller/GT boundary 与 identity review |

## 仿真、数据与优化

| ID | 需求/验收结果 | 状态 | 实现位置 | 验证证据 |
|---|---|---|---|---|
| AMF-SIM-001 | `compute_channel` 返回分路径复信道、功率、噪声、SNR、容量 | Implemented | `simulation/engine.py` | Smart Space integration test |
| AMF-SIM-002 | `compute_field_map` 返回 power/SNR/baseline/gain/coverage/dead-zone | Implemented | `simulation/engine.py` | `test_small_field_map_has_consistent_shape_and_coverage` |
| AMF-SIM-003 | Ground Truth 误差由固定 seed 可重放 | Implemented | `simulation/ground_truth.py` | `test_fixed_ground_truth_seed_is_reproducible` |
| AMF-DATA-001 | Scene JSON 带 `schema_version=1`，保存/加载后语义一致 | Implemented | `scene/serialization.py` | `test_scene_json_round_trip` |
| AMF-OPT-001 | Feedback 优化只通过 oracle.measure 获取目标功率 | Implemented | `optimization/measurement.py`, `greedy.py` | optimization test + code boundary review |
| AMF-OPT-002 | Physics-Guided 使用 Focus 初始化再反馈修正 | Implemented | `optimization/physics_guided.py` | `test_physics_guided_feedback_returns_valid_pattern` |
| AMF-OPT-003 | 大 RIS 优化使用 tile grouping，支持取消与进度 | Implemented | `greedy.py`, `gui/workers.py` | GUI smoke；人工 Optimize/Cancel 步骤 |
| AMF-SIM-004 | 固定几何预计算 `a_n`、多点分块矩阵和增量贪心 | Planned | — | 进入 P1 性能里程碑前补基准测试 |
| AMF-OPT-004 | hardware phase resolution 与 optimizer search levels 分离并进入结果元数据 | Planned | — | `foundation_0_1_1_plan.md` FND-T10 |
| AMF-SIM-005 | 建立不含 carrier、`Gamma_wall` 或 RIS response 的 environment-only PropagationProfile 和默认 IndoorDeterministicProfile；保持 Profile、Reflection、RIS 与 Ground Truth 所有权分离 | Planned | [ADR-0012](adr/0012-wall-reflection-coefficient-ownership.md) | `foundation_0_1_1_plan.md` FND-T13..14 |
| AMF-SIM-006 | v1 Wall 冻结为地面锚定竖直墙；端点 z 为 0，Ground Truth 只对墙施加刚体 XY 平移 | Planned | [FND-FIX-WALL](work_items/foundation_0_1_1_wall_geometry_closure.md) | FND-T19、默认 Scene round-trip 与阻挡/反射一致性 |

## 场景与 GUI

| ID | 需求/验收结果 | 状态 | 实现位置 | 验证证据 |
|---|---|---|---|---|
| AMF-SCN-001 | Smart Space 参数、内墙和 RIS 几何与 baseline 一致 | Implemented | `scenarios/smart_space.py`, scene JSON | JSON round-trip、headless run |
| AMF-SCN-002 | Coverage 使用场景阈值；默认 `SNR≥35 dB` | Implemented | scene JSON, field-map engine | field-map test、headless output |
| AMF-UI-001 | 主画布显示并可拖动 TX/RX/RIS，显示墙和障碍物 | Implemented | `gui/scene_view.py` | GUI smoke + 人工拖动验收 |
| AMF-UI-002 | 显示 power/SNR/RIS Gain、pattern、coverage 和主要指标 | Implemented | GUI view/panels | GUI screenshot + smoke |
| AMF-UI-003 | 热图和反馈优化在 worker 中，可取消并忽略旧版本 | Implemented | `gui/workers.py`, `main_window.py` | `test_stale_field_result_is_ignored` + 人工 Cancel |
| AMF-UI-004 | 所有可编辑参数有单位、范围校验和错误反馈 | Implemented | `gui/main_window.py`, dataclasses | GUI smoke + 参数异常测试 |
| AMF-UI-005 | 未实现场景不提供可运行假入口 | Verified | GUI roadmap label | GUI smoke、人工检查 |
| AMF-UI-006 | Model Info 显示传播/RIS/噪声假设和限制 | Implemented | `MainWindow._show_model_info` | 人工 Model Info 验收 |
| AMF-UI-007 | 参数编辑具有 pending/apply/Optimize 门禁；preset 覆盖和 Customized 状态可辨认 | Planned | — | `foundation_0_1_1_plan.md` FND-T11..12 |
| AMF-UI-008 | Pattern 显示 grid/bits/states/source/error/legend；Ground Truth 标签与真实作用范围一致 | Planned | — | Foundation GUI smoke + 人工清单 |

## 工程、实验与文档

| ID | 需求/验收结果 | 状态 | 实现位置 | 验证证据 |
|---|---|---|---|---|
| AMF-ENG-001 | Python 3.11+ 可 editable install，CPU/离线运行 | Verified | `pyproject.toml` | `pip install -e ".[dev]"`, headless run |
| AMF-ENG-002 | GUI 与物理分层，GUI 不定义传播公式 | Verified | package architecture | architecture review + imports audit |
| AMF-EXP-001 | Phase Resolution 固定孔径扫 1/2/3/4/continuous，输出 CSV/PNG | Implemented | `experiments/phase_bits.py` | generated `results/phase_bits/*` |
| AMF-EXP-006 | 实验分开记录 focus mode、profile/reflection/channel model version、search levels，且不覆盖 legacy 结果 | Planned | — | `foundation_0_1_1_plan.md` FND-T15 |
| AMF-DOC-001 | Future 假设、模型限制和术语均有规范文档 | Verified | docs | `tests/test_documentation.py` |
| AMF-DOC-002 | 需求、测试和状态可追踪，文档链接无断链 | Implemented | requirements、test strategy | `tests/test_documentation.py` |

## 后续场景需求

| ID | 能力 | 状态 | 进入实现前必须补齐 |
|---|---|---|---|
| AMF-XR-001 | 人体遮挡、动态用户、SNR(t)、outage | Planned | 时间步契约、轨迹 schema、验收基线 |
| AMF-FAC-001 | 多 RX、多 RIS、average/min-user SNR | Planned | 多用户 objective、pattern 所有权、性能预算 |
| AMF-CITY-001 | 建筑 NLoS、车辆/UAV、立面 RIS、电磁走廊 | Planned | 城市几何层级、轨迹、覆盖走廊定义 |
| AMF-EXP-002 | Aperture sweep | Planned | 控制变量和物理适用域 |
| AMF-EXP-003 | Phase Error robustness 三算法对比 | Planned | Ground Truth 配置表和统计口径 |
| AMF-EXP-004 | RIS Count sweep | Planned | 多 RIS 单跳实现 |
| AMF-EXP-005 | Dynamic User | Planned | XR 动态引擎 |
