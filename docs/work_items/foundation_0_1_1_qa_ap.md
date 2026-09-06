# Work Item：Foundation / Minimum Aperture Quadrature Validity

- 层级：L4 Task（cross-cutting QA）
- Task ID：FND-QA-AP
- Requirement IDs：AMF-RIS-011
- 状态：Ready
- 父项：Foundation 0.1.1 Final Exit Gate；下游为 FND-QA-CC
- 依赖：A2 Verified；ADR-0008 Accepted；正式执行依赖 A3、B、C Implemented 和 experiment
  provenance 可用
- 不属于：A2 重开、A4、P1A cache 实现、P1C 完整 aperture research

## 目标与用户结果

在 Foundation 最终验收和 P1A 缓存之前，用可重放的代表性数值实验确定当前 control-level
RIS coefficient `a_n` 的求积构造是否满足声明精度，并冻结 production quadrature policy 的
identity/version。完成后，新开发者可以明确区分：

```text
A2 patch semantic contract = Verified
Aperture discretization accuracy = Verified only within the signed QA domain
Electromagnetic/full-wave accuracy = Not claimed
```

本工作项只签署 `a_n` 的 quadrature policy，不签署 Focus 与 simulator 的最终组合一致性。后者
由 [ADR-0011](../adr/0011-controller-coefficient-focus-consistency.md) 和
[FND-QA-CC](foundation_0_1_1_coefficient_consistency.md) 在必要 production migration 后完成。

## Definition of Ready / Final Ready Review

2026-09-05 完成 FND-QA-AP-01 independent final Ready Review：preregistration、physics、
numerical 和 contract review 均 **PASS**，blocking issues **0**。签署配置为
`configs/foundation_0_1_1/fnd_qa_ap_01_preregistration_v1.json`，config identity 为
`sha256:94dd4bf50ff0a5c5246980577ef4731e2e5d8504fa44fa1f56c4282ff4113cf7`。
FND-QA-AP-01 preregistration 已 signed/frozen；本 Work Item 状态为 **Ready**，表示
QA-AP-02 implementation 可以开始，不表示 runner、正式 QA matrix、production quadrature
或 AMF-RIS-011 已 Implemented/Verified。

## 状态与授权边界

- 本工作项已达到 Ready；本文档和签署配置冻结的是 runner/测试/policy 的实现契约，不是
  runner、正式 QA matrix 或 production policy 已实现的证据；
- 创建本文档不改变 A1/A2、Foundation 0.1.1A、AMF-RIS-009 或 Foundation 0.1.1 的状态；
- 只有后续 QA-AP-02..06 的自动证据、版本化结果和最终人工复核全部通过后，AMF-RIS-011
  才能由 Implemented 提升为 Verified；
- 若候选 policy 均未通过，Foundation 保持 In Progress，P1A 不得开始；
- 不修改当前 `.py`、GUI、场景或默认 1×1 行为，除非后续独立 implementation Work Item 和 ADR
  明确授权。
- 本工作项 Ready 不自动授权 P1A；FND-PHY-NB、FND-QA-CC 与 Foundation final review 仍须完成。

## In / Out

包含：

- 独立于 control grid 的内部 quadrature sampling；
- midpoint successive refinement 和 Gauss–Legendre 交叉检查；
- 三代、代表性几何、三类 pattern 和固定 random seeds；
- complex/power/phase/RIS Gain 指标及深相消数值保护；
- runtime、memory、配置和 model provenance；
- 基于预注册容差的 production policy 决策和 cache identity 输入。

不包含：

- 重开或降级 A2；
- 真实 meta-atom、fill factor、互耦、极化、材料色散或全波模型；
- per-sample/per-region blockage；
- 完整 field-map convergence、aperture sweep 或上千组合研究；
- P1A 矩阵缓存、增量 Greedy 或性能重写；
- 未经证据直接把默认值改成 `16×16 everywhere`。

## 接口与数据

QA runner 应是 experiments/QA 层的 headless 入口，不应从 GUI 驱动。正式命令、模块名和输出
schema 在进入 Ready 前冻结；在代码尚未实现时不得在 README 宣称入口可运行。

每条结果至少包含：

| 字段 | 类型/单位 | 语义 |
|---|---|---|
| `qa_schema_version` | str | QA 输出 schema |
| C2 `profile_*`、`reflection_model_*`、`world_model_*` | str/JSON | 本次实际 Profile/Reflection/world 身份 |
| `channel_frequency_model_id` | str | center-frequency/wideband contract identity |
| `scene_id`、`geometry_case` | str | 固定几何配置和用途 |
| `generation` | str | Current/Advanced/Future |
| `frequency_hz` | Hz | operating frequency |
| `width_m,height_m,nx,ny` | SI/int | 实体 aperture 与 control grid |
| `pattern_class`、`pattern_hash` | str | 固定 commanded pattern 身份 |
| `random_seed` | int/empty | C2 world/scene seed；Controller 主门禁中必须记录实际整数，不以 0 代替未适用 |
| `pattern_seed` | int/empty | 独立 random legal pattern seed；Focus 行为空值，不能覆盖或重解释 C2 `random_seed` |
| `quadrature_rule` | str | midpoint/Gauss–Legendre |
| `quadrature_order_x/y` | int | 每个 control patch 内 order |
| `quadrature_policy_id/version` | str | 候选或最终 policy 身份 |
| `coefficient_model_identity` | str | 候选 coefficient identity；最终签署属于 FND-QA-CC |
| `h_ris_real/imag` | complex parts | 原始复数 RIS coefficient |
| `complex_abs_error` | amplitude | 相对内部 reference 的绝对误差 |
| `complex_robust_rel_error` | ratio/null | 带预登记 scale/floor 的误差 |
| `magnitude_error_db` | dB/null | `20log10` 幅度比，零值受保护 |
| `phase_error_rad` | rad/null | 深衰落时 null |
| `ris_only_power_dbm` | dBm/null | 具有完整链路预算时 |
| `total_received_power_dbm` | dBm | baseline+RIS 复场结果 |
| `ris_gain_db` | dB/null | baseline 稳定时；否则 null+reason |
| `runtime_s`、`peak_memory_mb` | s/MB | C2/legacy 成本记录；QA-AP raw 使用 scoped fields below |
| `quadrature_runtime_s`,`quadrature_peak_rss_mb` | s/MB | one quadrature-row evaluation and its child-process peak RSS |
| `series_runtime_s`,`series_peak_rss_mb` | s/MB | one generation × geometry × pattern series, including one-time Focus/pattern setup, midpoint ladder and required GL checks |
| `run_runtime_s`,`run_peak_rss_mb` | s/MB | complete base minimum matrix from exclusive directory allocation through output flush |
| `reference_label` | str | internal refined numerical reference |
| `status/reason` | enum/str | pass/fail/ill-conditioned/not-applicable |

不得使用 `ground_truth`、`EM truth` 或 `exact` 命名内部细化参考。

该 runner 必须复用 C2 `airmirror_experiment_provenance/1` 的 run-level 字段和 no-overwrite 规则。
FND-QA-AP 尚未签署时，候选 `quadrature_policy_id/version` 和
`coefficient_model_identity` 即使非空，`FND-QA-AP`/`FND-QA-CC` 仍留在
`pending_contracts_json`，结果保持 `partial`；不得把 candidate 记录成 Verified/default policy。

## 物理/算法约束

### 固定量

一个 refinement series 内必须固定：实体孔径、control grid、patch flatten 顺序、频率、TX/RX、
朝向、效率、Profile、ControllerModel world/scene realization、C2 `random_seed`、baseline、
commanded `Gamma_control` 及其 pattern hash。QA-AP 主 gating world 仅为
`ControllerModel`; `GroundTruthModel` 不进入主门禁。用于 random legal pattern 的
`pattern_seed` 是独立命名空间，不得覆盖或重解释 C2 `random_seed`。

严禁在 order 改变时调用 Focus 生成器重新生成更细 pattern。subpoint 必须继承其
`parent_control_index` 的同一个 complex command coefficient。

### 求积层级与参考

- midpoint：`1×1、2×2、4×4、8×8、16×16`；必要时 `32×32`；
- cross-rule：至少一个匹配或更高阶的 tensor-product Gauss–Legendre；
- reference 由 successive refinement 和 cross-rule 一致性共同选择，不固定宣称 16×16 为真值；
- reference 未收敛时该 case 为 blocking failure，不得从汇总中删除。

### 代表性矩阵

最小矩阵：

```text
3 generations
× 4 geometry cases
× (RIS-only Focus + Coherent Target Focus + 5 seeded random legal patterns)
× 5 midpoint orders
+ cross-rule reference checks
```

四类几何至少包括 default target、近场、斜入射和 off-focus receiver。每类必须保存实际坐标、
aperture/frequency 和解释标签所需的无量纲几何量。禁止只写 `near`/`far` 而没有数值定义。

本 signed preregistration 的 geometry policy 已获 maintainer/physics review，作为 frozen
记录（enclosing config 已 signed/frozen，最终 Ready Review PASS），为 Smart Space 房间
`10×8×3 m`、RIS center `(5.0,7.9,1.5) m`、yaw `-π/2`、frequency `5 GHz`：

| case | TX (m) | `focus_target_rx` (m) | `evaluation_rx` (m) | 约束检查 |
|---|---|---|---|---|
| `default_target` | `(1.0,4.0,2.4)` | `(8.5,4.0,1.2)` | `(8.5,4.0,1.2)` | TX/RIS center 5.659 m；RIS/RX 5.249 m |
| `near_field` | `(1.0,4.0,2.4)` | `(6.5,6.4,1.5)` | `(6.5,6.4,1.5)` | TX/RIS 5.659 m；RIS/RX 2.121 m |
| `oblique_incidence` | `(1.0,6.0,2.4)` | `(8.5,4.0,1.2)` | `(8.5,4.0,1.2)` | TX/RIS 4.519 m；RIS/RX 5.249 m |
| `off_focus_receiver` | `(1.0,4.0,2.4)` | `(8.5,4.0,1.2)` | `(8.5,6.5,1.2)` | focus/evaluation are distinct; RIS/eval 3.782 m |

All distances are far above `MIN_DISTANCE_M=1e-6 m`. Candidate paths must be checked before
execution for no partial-aperture blockage and for a positive clearance from the `partition`
blockage edge; the runner records `blockage_mode="uniform_scalar_or_none"` and rejects any
case whose acceptance depends on per-patch blockage. In `off_focus_receiver`, Focus is generated
once for `focus_target_rx`; evaluation at `evaluation_rx` reuses the exact commanded pattern and
never calls Focus again.

The frozen fixed random pattern seeds are
`pattern_seed = [1101, 2203, 3307, 4409, 5511]`. Each seed must deterministically generate one
legal commanded pattern for the fixed RIS and be recorded with its canonical pattern hash. The
list remains preregistered and is not a measured result.

### 遮挡边界

本工作项不验证 partial-aperture blockage。几何必须远离遮挡边界，或明确使用当前统一 scalar
attenuation。结果元数据必须记录 blockage mode，不能把统一中心路径衰减描述为空间分辨遮挡。

## 预注册验收规则

进入 Ready 前，维护者和物理审查者必须在本 Work Item 或随附配置中签署：

1. reference convergence tolerance；
2. production-adequacy tolerance；
3. robust normalization scale/floor；
4. runtime/memory budget；
5. geometry 坐标和 random seed 列表；
6. 汇总规则，以及是否允许个别 case 仅作 ill-conditioned 排除。

For the required per-control coefficient check, let `a(q)` be the complex coefficient vector in
fixed `parent_control_index` order at quadrature level `q`, and let `a(ref)` be the selected
internal refined numerical reference. The minimum deterministic candidate metric is

```text
e_a(q, ref) = ||a(q)-a(ref)||_∞ / max(||a(ref)||_∞, a_floor)
```

The report must also include `a_inf_abs_error`, `a_inf_robust_rel_error`,
`reference_a_inf_norm` and a reference coefficient artifact identity. A single positive,
finite `a_floor` is shared by the preregistration; per-element self-normalization is forbidden
because zero/small coefficients would otherwise dominate with artificial infinite ratios. The
same fixed parent ordering is used for every order. The aggregate gates are evaluated separately
for `h_RIS` and `h_total`; passing only the aggregate channel cannot waive a failing `a_n` gate.
`a_floor` is a numerical normalization guard, not a physical or engineering pass/fail threshold.
Whenever it is selected by a denominator, the output records `normalization_floor_active`; floor
activation never grants an acceptance exemption and cannot by itself produce PASS. The complete
`a_n` vector is not placed in the ordinary summary CSV/JSON: summary fields contain only the
deterministic metrics (`a_inf_abs_error`, `a_inf_robust_rel_error`, `reference_a_inf_norm` and
the reference artifact identity). If retained, the ordered complex vector is a separate raw
artifact with `parent_control_index`, rule/order, pattern hash, reference row ID and SHA-256.
The metric and guard semantics are signed/frozen; the runner must not reinterpret them at
implementation time.

For aggregate `h_RIS` and `h_total`, the robust denominator is a fixed reference-only scale and
must never depend on candidate quadrature values. With the fixed commanded coefficient vector
`Gamma_control`, selected reference vector `a(ref)`, fixed non-RIS baseline `h_baseline`, and the
declared aggregate floor, define:

```text
S_RIS   = max(sum_n(abs(a(ref)_n * Gamma_control_n)), abs(h_RIS(ref)), aggregate_floor)
S_total = max(abs(h_baseline) + sum_n(abs(a(ref)_n * Gamma_control_n)),
              abs(h_total(ref)), aggregate_floor)
e_h(q, ref) = abs(h(q)-h(ref)) / S_{RIS|total}
```

`reference_deep_null` is `abs(h(ref))/S <= deep_null_ratio`; `candidate_deep_null` is
`abs(h(q))/S <= deep_null_ratio`. If either applicable value is deep-null, phase/magnitude/gain
fields are null with an explicit reason. Complex robust errors remain finite and continue to be
gated. The reference-only scale prevents an inaccurate coarse candidate from changing its own
normalization or null classification.

Runtime and memory have three distinct scopes. `quadrature_runtime_s` and
`quadrature_peak_rss_mb` describe one raw quadrature row; `series_runtime_s` and
`series_peak_rss_mb` describe one generation × geometry × pattern series including its one-time
Focus/pattern setup, complete midpoint ladder, and required GL checks; `run_runtime_s` and
`run_peak_rss_mb` describe the complete base minimum matrix from exclusive run-directory
allocation through raw/summary/run-metadata flush. The per-generation 120/240/600 second limits
apply to `series_runtime_s`; the 8-hour limit applies to `run_runtime_s`. Conditional 32×32 and
GL32 measurements are recorded separately and cannot alter numerical thresholds or the base budget.

### Pattern snapshot and series identity

`pattern_hash` identifies only the commanded phase snapshot: phase values in fixed control order,
`phase_bits`, shape, flatten order, phase/control semantics and the required control-grid identity.
Its bytes are UTF-8 canonical JSON with lexicographically sorted object keys, declared array order,
`ensure_ascii=false`, compact separators, and rejection of NaN/Infinity; the exact payload is
`{control_grid_identity, domain_separator, flatten_order, ordered_phase_binary64_be_hex, phase_bits,
phase_control_semantics, schema_version, shape}`. `domain_separator` is the literal ASCII
`airmirror_fnd_qa_ap_commanded_pattern`, `schema_version` is integer `1`, and
`phase_control_semantics` is the literal ASCII `commanded_complex_gamma_from_phase_radians_v1`.
Each phase is encoded as 16 lowercase hexadecimal characters for its raw IEEE-754 binary64 bytes
in big-endian order (exactly `struct.pack('>d', phase).hex()`), in `parent_control_index` order;
no decimal-float serialization is used. It must not include
`generation`, `geometry_case`, `pattern_seed` or other experiment context. Those fields, together
with the `pattern_hash`, belong to `series_identity`/C2 provenance. Thus the same commanded phase
snapshot has one pattern identity even when reused in different geometry or generation contexts.

The random generator digest is also byte-defined. Let `B` be the concatenation of UTF-8 ASCII
`fnd_qa_ap_pattern_v1\\0`, `pack('<I', len(generation_utf8))`, `generation_utf8`,
`pack('<I', len(geometry_case_utf8))`, `geometry_case_utf8`, `pack('<Q', pattern_seed)` and
`pack('<Q', parent_control_index)`; SHA-256 is applied to `B`. Finite-state mapping uses the first
eight digest bytes as uint64 little-endian modulo `2**phase_bits`, then correctly-rounded binary64
of `tau_binary64*k/2**phase_bits`; continuous mapping uses `r=uint64_le(digest[0:8])`,
`m=r>>11`, `u=binary64(m*2**-53)` and then binary64 `u*tau_binary64`. Since
`0<=m<=2**53-1`, this is strictly in `[0,tau_binary64)`, where `tau_binary64` is the exact
binary64 constant `0x1.921fb54442d18p+2`.
All arithmetic is round-to-nearest, ties-to-even binary64 with no fused multiply-add and no
locale-dependent formatting. For `series_identity` and any future config identity, scalar values use
the C1 tagged forms (`int` as base-10 string and finite float as `float64_hex` using `value.hex()`);
raw decimal JSON numbers are forbidden in identity payloads. The `series_identity` is
`sha256:<64 lowercase hexadecimal characters>` over its declared canonical tagged fields object.

The literal control flatten token is `ris_cell_centers_meshgrid_xy_c_v1`: it means the existing
`RISSurface.cell_centers()` `meshgrid(indexing="xy")` result flattened in C order, with x-index
fastest and `parent_control_index = iy*nx + ix`.

### FND-QA-AP-01 preregistration closure boundary

The signed/frozen preregistration freezes the engineering contract and records the accepted policy;
the enclosing config and Work Item are Ready after final independent Ready Review. It defines:

- runner module/entry point, complete-run-directory `--output`, default no-overwrite root,
  schema ID/version, raw/summary filenames, row granularity, and reference/raw linkage;
- Controller-only main gate, separate C2 `random_seed` and `pattern_seed`, and the complete
  generation/geometry/focus/random matrix;
- midpoint `1×1/2×2/4×4/8×8/16×16`, conditional `32×32` only on preregistered convergence or
  cross-rule failure, and at least one tensor-product Gauss–Legendre cross-check; GL16×16 is the
  base cross-rule, while GL32×32 is additionally required only when midpoint32 is triggered;
- fixed `parent_control_index`, deterministic subpoint ordering, inherited command coefficient,
  and no Focus/quantization/search regeneration when order changes;
- frozen numerical values and rationale, null/deep-cancellation/ill-conditioned handling,
  aggregation/pass-fail rule, and the frozen performance measurement
  contract and budgets;
- C2 schema v1, `provenance_status="partial"`, mandatory pending
  `FND-PHY-NB/FND-QA-AP/FND-QA-CC`, candidate policy identity only, and no-overwrite.

The runner contract and frozen values are recorded in
`configs/foundation_0_1_1/fnd_qa_ap_01_preregistration_v1.json`; this file is explicitly
`signed_frozen`/`Ready` and is not a baseline configuration, runner implementation, formal QA matrix
result, production migration, or evidence of Verified status.

这些数值必须在查看正式结果之前冻结。正式结果失败后只能修复算法/模型，或通过 ADR 说明为何
原阈值/适用域错误；不得静默放宽。

## Tasks

| Task | 状态 | 预计颗粒度 | 完成输出 |
|---|---|---:|---|
| `FND-QA-AP-01` 冻结矩阵、坐标、seeds、容差和 floor | Ready | 0.5–1 天 | signed QA config/review；independent final Ready Review PASS，blocking issues 0 |
| `FND-QA-AP-02` 实现内部 QuadratureSpec/parent mapping | Implemented | 1–2 天 | 非 GUI、可测试内部 API；实现位于 `ris/quadrature.py` |
| `FND-QA-AP-03` 实现 midpoint/GL runner 和 metrics | Implemented | 1–2 天 | versioned CSV/JSON summary；实现位于 `experiments/fnd_qa_ap_01.py` |
| `FND-QA-AP-04` 增加 FND-T16..18 | Implemented | 1–2 天 | `tests/test_fnd_qa_ap.py` 定向契约/收敛/provenance 测试 |
| `FND-QA-AP-05` 运行矩阵并审查异常 | Planned | 1 天 | results + review record |
| `FND-QA-AP-06` 冻结 production policy/cache identity | Planned | 0.5–1 天 | PASS decision 或 blocking ADR |

若 implementation 需要改变生产散射公式，必须另建独立 Work Item；不得把 runner、生产迁移和
P1A cache 混在一个提交中。迁移完成后还必须执行 FND-QA-CC，不能仅凭本 QA 结果推断 Focus
已自动使用同一 integrated coefficient。

## 验收证据

- `FND-T16`：同一 series 中 aperture/control/pattern hash 不变，只有 quadrature rule/order 变化；
- `FND-T17`：successive refinement 和 cross-rule 参考选择可复现，未收敛 case 明确失败；
- `FND-T18`：深相消指标返回 null/reason 而非 Inf/NaN，输出含完整 provenance 和 policy identity；
- runner 在三代最小矩阵上完成，无静默跳过或非有限输出；
- production decision 对每个失败/例外 case 有记录；
- 完整 pytest、三代 headless 和文档链接检查通过；
- 项目维护者与物理审查者人工确认 0 blocking issues 后才能签署 Verified。

## 风险与回退

| 风险 | 检测 | 安全回退 |
|---|---|---|
| 1×1 在部分适用域误差过大 | 预注册矩阵 | 保持 Foundation In Progress；评审低阶/adaptive policy |
| 16×16 仍未收敛 | successive + GL | 扩到 32×32 或缩小声明适用域；不称 truth |
| Future 计算/内存爆炸 | runtime/memory telemetry | 分块 streaming；不生成全量 point×patch×subpoint 张量 |
| random pattern 偶然代表性不足 | 固定不少于 5 seeds | 扩 seed；不选择性删除失败 seed |
| 深相消相对误差爆炸 | absolute + robust metrics | 标记 ill-conditioned，不用单一相对误差判决 |
| blockage 边缘污染结论 | geometry review | 移除边缘 case，另建 spatial blockage Work Item |
| policy 改变旧结果 | model/policy version | 保留 legacy，禁止无版本覆盖 |

## 文档影响

- [x] requirements：新增 AMF-RIS-011，校准 AMF-RIS-005 措辞；
- [x] ADR：ADR-0008；
- [x] Foundation plan、roadmap、status：增加 final gate 和顺序；
- [x] physics、architecture、data/API、limitations：记录当前/目标边界；
- [x] test、experiment、DoD：记录 QA 方法和 provenance；
- [x] FND-QA-CC：记录 policy 签署后的 coefficient/Focus 一致性下游门禁；
- [ ] GUI/scene schema：本工作项无修改；
- [x] code/tests：QA-AP-02..04 已 Implemented；正式 QA-AP-05 full matrix 与 production policy decision 仍未执行。
- [ ] results：正式 QA-AP-05 矩阵结果尚未生成；当前仅完成 lightweight runner smoke。
