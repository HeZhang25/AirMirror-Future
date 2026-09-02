# Work Item：Foundation / Minimum Aperture Quadrature Validity

- 层级：L4 Task（cross-cutting QA）
- Task ID：FND-QA-AP
- Requirement IDs：AMF-RIS-011
- 状态：Planned
- 父项：Foundation 0.1.1 Final Exit Gate
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

## 状态与授权边界

- 本工作项当前仅为 Planned；本文档不是 runner、测试或 policy 已实现的证据；
- 创建本文档不改变 A1/A2、Foundation 0.1.1A、AMF-RIS-009 或 Foundation 0.1.1 的状态；
- 只有自动证据、版本化结果和最终人工复核全部通过后，AMF-RIS-011 才能由 Implemented 提升为
  Verified；
- 若候选 policy 均未通过，Foundation 保持 In Progress，P1A 不得开始；
- 不修改当前 `.py`、GUI、场景或默认 1×1 行为，除非后续独立 implementation Work Item 和 ADR
  明确授权。

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
| `model_version`、`profile_id/version` | str | 本次系统级物理身份 |
| `scene_id`、`geometry_case` | str | 固定几何配置和用途 |
| `generation` | str | Current/Advanced/Future |
| `frequency_hz` | Hz | operating frequency |
| `width_m,height_m,nx,ny` | SI/int | 实体 aperture 与 control grid |
| `pattern_class`、`pattern_hash` | str | 固定 commanded pattern 身份 |
| `random_seed` | int/null | random legal pattern 的预登记 seed |
| `quadrature_rule` | str | midpoint/Gauss–Legendre |
| `quadrature_order_x/y` | int | 每个 control patch 内 order |
| `quadrature_policy_id/version` | str | 候选或最终 policy 身份 |
| `h_ris_real/imag` | complex parts | 原始复数 RIS coefficient |
| `complex_abs_error` | amplitude | 相对内部 reference 的绝对误差 |
| `complex_robust_rel_error` | ratio/null | 带预登记 scale/floor 的误差 |
| `magnitude_error_db` | dB/null | `20log10` 幅度比，零值受保护 |
| `phase_error_rad` | rad/null | 深衰落时 null |
| `ris_only_power_dbm` | dBm/null | 具有完整链路预算时 |
| `total_received_power_dbm` | dBm | baseline+RIS 复场结果 |
| `ris_gain_db` | dB/null | baseline 稳定时；否则 null+reason |
| `runtime_s`、`peak_memory_mb` | s/MB | 成本记录 |
| `reference_label` | str | internal refined numerical reference |
| `status/reason` | enum/str | pass/fail/ill-conditioned/not-applicable |

不得使用 `ground_truth`、`EM truth` 或 `exact` 命名内部细化参考。

## 物理/算法约束

### 固定量

一个 refinement series 内必须固定：实体孔径、control grid、patch flatten 顺序、频率、TX/RX、
朝向、效率、Profile、Ground Truth realization、baseline 和 commanded `Gamma_control`。

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
× (RIS-only Focus + Coherent Focus + 5 seeded random legal patterns)
× 5 midpoint orders
+ cross-rule reference checks
```

四类几何至少包括 default target、近场、斜入射和 off-focus receiver。每类必须保存实际坐标、
aperture/frequency 和解释标签所需的无量纲几何量。禁止只写 `near`/`far` 而没有数值定义。

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

这些数值必须在查看正式结果之前冻结。正式结果失败后只能修复算法/模型，或通过 ADR 说明为何
原阈值/适用域错误；不得静默放宽。

## Tasks

| Task | 状态 | 预计颗粒度 | 完成输出 |
|---|---|---:|---|
| `FND-QA-AP-01` 冻结矩阵、坐标、seeds、容差和 floor | Planned | 0.5–1 天 | signed QA config/review |
| `FND-QA-AP-02` 实现内部 QuadratureSpec/parent mapping | Planned | 1–2 天 | 非 GUI、可测试内部 API |
| `FND-QA-AP-03` 实现 midpoint/GL runner 和 metrics | Planned | 1–2 天 | versioned CSV/JSON summary |
| `FND-QA-AP-04` 增加 FND-T16..18 | Planned | 1–2 天 | contract/convergence/provenance tests |
| `FND-QA-AP-05` 运行矩阵并审查异常 | Planned | 1 天 | results + review record |
| `FND-QA-AP-06` 冻结 production policy/cache identity | Planned | 0.5–1 天 | PASS decision 或 blocking ADR |

若 implementation 需要改变生产散射公式，必须另建独立 Work Item；不得把 runner、生产迁移和
P1A cache 混在一个提交中。

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
- [ ] GUI/scene schema：本工作项无修改；
- [ ] code/tests/results：Planned，尚未实现。
