# ADR-0008：最小孔径求积有效性门禁

- 状态：Accepted
- 日期：2026-09-02
- Supersedes：无；补充 ADR-0007，不重开或替代 A2
- 关联需求：AMF-RIS-005、AMF-RIS-009、AMF-RIS-011
- 关联工作项：FND-QA-AP、Foundation 0.1.1 Final Exit Gate、P1A、P1C

## 背景

ADR-0007 已把 `nx/ny` 冻结为 system-level equivalent controllable aperture patches，并明确
当前一个 patch 同时承担一个 commanded phase 和一个中心点求积采样。该决定解决的是语义、
实体孔径所有权和透明度问题，不证明一个中心点足以精确积分整个 patch。

一次隔离的数值审计固定实体孔径、control grid 和 commanded pattern，只将每个 control patch
的 midpoint quadrature 从 `1×1` 逐级细化到 `16×16`。默认 Smart Space 目标链路中，`1×1`
相对该次内部细化参考的 RIS 复场幅度差约为 Current `+0.848 dB`、Advanced `+0.430 dB`、
Future `+0.639 dB`。这些数值证明风险不是纯理论担忧，但它们尚未由版本化 runner、代表性矩阵、
交叉求积规则和正式 provenance 固化，因此不是验收基准，也不是 electromagnetic truth。

P1A 将预计算并缓存 control-level coefficient `a_n`。若在 P1A 之后才决定 `a_n` 应由多个
quadrature samples 积分得到，则 coefficient 构造、matrix `A`、cache identity、invalidation
和性能基准都会改变。先缓存未经验证的系数再研究其数值含义，会造成可避免的返工和错误精度
声明。

## 决定

### 1. 状态边界

- Foundation A2 semantic contract 保持 **Verified**；不重开 A2，也不把新工作项命名为 A4；
- aperture discretization accuracy 保持 **Not Verified**，直到 AMF-RIS-011 取得正式证据；
- `AMF-RIS-009` 仍因 B 阶段 GUI 只读接入而保持 In Progress；
- Foundation 0.1.1、Foundation 0.1.1A 和 P1A 的既有状态不因本 ADR 自动提升；
- `FND-QA-01` 已用于 Foundation final regression，不复用。新增 cross-cutting L4 工作项
  `FND-QA-AP`，Requirement 使用 RIS 域的 `AMF-RIS-011`。

### 2. 门禁位置

`FND-QA-AP` 必须在 Foundation 0.1.1 最终人工验收之前完成；Foundation 未 Verified 时 P1A
不得进入 In Progress。正式依赖顺序为：

```text
A3
  -> B
  -> A/B Interim Checkpoint
  -> C
  -> FND-QA-AP Minimum Aperture Quadrature Validity
  -> Foundation Final Exit Gate
  -> P1A Geometry Cache and Matrix Evaluation
  -> P1C Full Aperture Sweep and Quadrature Research
```

QA 契约和测试矩阵可以提前冻结，但正式 runner 必须使用完成 C 后稳定的 Profile identity、
path-role 和 experiment provenance。

### 3. 最小 QA 的唯一控制变量

每个对照必须固定：

- 实体 aperture `width_m/height_m`、位置、朝向和效率；
- control grid `nx/ny` 及其 flatten 顺序；
- operating frequency、TX/RX 几何、天线 gain 和传播 Profile；
- commanded pattern `Gamma_control`，包括量化后的离散状态；
- `ControllerModel` world/scene realization、C2 `random_seed` 和非 RIS baseline；
- `GroundTruthModel` 不进入 QA-AP 主门禁。任何 GroundTruth 对照只能作为未来诊断，不得改变
  本门禁的 commanded pattern、coefficient 或 pass/fail 结果；random legal pattern 使用独立
  `pattern_seed`，不得把它写回或重解释为 C2 `random_seed`；
- 当前统一标量 blockage factor（若使用）。

只允许改变每个 control patch 内的 quadrature rule/order。求积细化时禁止重新生成 Focus、
重新量化 pattern、改变 control count 或移动 TX/RX；否则结果混合了控制自由度与数值积分精度。

### 4. 参考层级和术语

求积层级至少包含 midpoint `1×1、2×2、4×4、8×8、16×16`，必要时增加 `32×32`。基础
cross-rule 固定为 tensor-product Gauss–Legendre `GL16×16`；仅当 `16×16` successive
convergence 或 midpoint-vs-GL16 cross-rule 失败时，才增加 midpoint `32×32`，并同时运行
匹配阶的 `GL32×32`。conditional reference 只有在 midpoint16→midpoint32 和 midpoint32↔GL32
均通过时才能成立。

Aggregate robust normalization 必须由 reference-only decomposition 构成，不能把 candidate
quadrature values 纳入 scale。对固定 commanded `Gamma_control`、reference `a(ref)`、baseline
`h_baseline` 和 aggregate floor，使用
`S_RIS=max(sum(abs(a(ref)*Gamma_control)),abs(h_RIS(ref)),floor)` 以及
`S_total=max(abs(h_baseline)+sum(abs(a(ref)*Gamma_control)),abs(h_total(ref)),floor)`；
candidate/reference deep-null 均相对于该固定 scale 判断。

最后一个稳定层级只能称为 **internal refined numerical reference**。它仍属于同一个系统级
标量模型，不得称为 ground truth、electromagnetic truth、full-wave result 或 measurement。

### 5. 最小代表性矩阵

正式矩阵至少覆盖：

- Current、Advanced、Future 三代代表性 aperture/control grid；
- default target、近场、斜入射、off-focus receiver 四类明确坐标几何；
- RIS-only Focus、Coherent Target Focus、seeded random legal pattern 三类命令；
- random pattern 使用预先登记且不少于 5 个固定 seeds；
- 单目标复信道为主；完整场图、遮挡边缘和大规模 aperture sweep 留在 P1C。

“near-field/oblique”不能只写标签，结果必须记录实际坐标、aperture 尺寸、频率和用于解释适用域
的无量纲几何量。第一轮不扩展到上千组合；若发现异常趋势，再由 P1C 扩大矩阵。

### 6. 指标和数值保护

每组至少报告：

- complex `h_RIS` absolute error；
- 使用预先登记 floor/scale 的 robust normalized complex error；
- `|h_RIS|` 幅度差和 dB 差；
- phase error；参考幅度接近 floor 时标为 not applicable，不输出误导角度；
- RIS-only power、total received power 和 RIS Gain；
- No-RIS 或 total reference 接近 floor 时，RIS Gain/相对误差必须标记 ill-conditioned；
- successive refinement difference、quadrature rule、order、runtime 和 peak memory。

正式执行前必须预先登记 reference convergence tolerance、production-adequacy tolerance 和
数值 floor；查看结果后不得通过放宽阈值取得 PASS。阈值变化需要审查记录；若改变模型声明或
默认 policy，需要后续 ADR。

### 7. Blockage 边界

当前 obstruction 通过 TX→RIS center 和 RIS center→RX 的几何检查得到标量衰减，再作用于整块
RIS contribution。FND-QA-AP 可以验证均匀未阻挡或当前统一标量衰减下的求积，但必须避开
“孔径一部分被挡、一部分未挡”的边界几何。

quadrature refinement 不等于 spatially resolved blockage。per-sample/per-region blockage 是
独立模型能力，不得为了完成本门禁顺带实现。

### 8. Production policy 决策

本 ADR 不预设 `16×16 everywhere`，也不承诺 1×1、2×2、4×4 或 adaptive quadrature。正式 QA
只能产生以下结论之一：

1. `1×1` 在预先登记适用域和容差内通过：保留当前 production policy，并记录声明精度；
2. 某个低阶固定 policy 通过：在 P1A 前用独立实现工作项接入，并将 policy identity/version
   纳入 coefficient 和 cache identity；
3. 适用域相关：经新 ADR 决定 preview/authoritative 或 adaptive policy；
4. 没有候选 policy 通过：Foundation 保持 In Progress，P1A 被阻断。

若接入多点求积，首选架构保持控制维度不变：

```text
Gamma_control[N_control]

QuadratureSpec
  -> subpoints + weights + parent_control_index
  -> integrate subpoint field to control-level a_n

h_RIS = A_control @ Gamma_control
```

`QuadratureSpec` 当前只是候选架构，不是已实现公共 API。任何实现都必须另行冻结 rule、order、
weights、坐标约定、policy version 和 blockage sampling ownership。

### 9. 与 P1C 的边界

FND-QA-AP 只回答：“P1A 接下来缓存的 control-level `a_n` 应怎样计算，才能满足当前声明的
数值可靠性？”

P1C 不取消，继续负责完整 aperture research：aperture sweep、固定 density/固定 control-count
对照、convergence map、phase-span、frequency/angle/near-field sensitivity、场图指标以及在独立
blockage 模型就绪后的遮挡边缘研究。

## 后果

- A2 的语义验收不受影响，当前代码和默认 1×1 center-point 数值暂不改变；
- Foundation final exit 增加一项可审计的数值有效性证据，不再仅凭面积归一化测试进入缓存；
- P1A cache key 设计必须等待 quadrature policy identity/version 冻结；
- 当前三代 dBm 可以作为“current scalar center-point model”输出展示，但不得宣称精确到四位
  小数或把单一目标点的代际排序推广到整个场图；
- 一次隔离审计的 `0.430–0.848 dB` 只作为创建工作项的风险证据，不能直接签署 PASS/FAIL；
- 若 QA 证明需要多点求积，会增加运行成本；是否保留 preview 1×1 由后续 policy ADR 决定。

## 候选与否决理由

- **重开 A2**：否决。A2 从未声称独立 quadrature accuracy 已验证；语义契约仍正确。
- **保持原顺序，P1A 后再做 P1C**：否决。会先缓存可能需要重定义的 `a_n`。
- **立即改成 16×16**：否决。单一几何下稳定不等于代表性适用域，且 Future 场图成本可能增加
  数百倍。
- **把 `pitch>lambda/2` 作为替代门禁**：否决。equivalent control patch 不是 physical
  meta-atom，不能用物理阵元间距经验替代数值求积验证。
- **在最小 QA 中实现空间分辨遮挡**：否决。它是独立物理模型扩展，会使本工作项失去边界。

## 验证

- [FND-QA-AP Work Item](../work_items/foundation_0_1_1_qa_ap.md) 定义输入矩阵、指标、输出和
  状态提升条件；
- FND-T16 验证固定 control/pattern、只细化 quadrature 的所有权边界；
- FND-T17 验证 successive refinement、内部参考选择和独立求积规则交叉检查；
- FND-T18 验证结果 provenance、深相消数值保护和 production policy 决策记录；
- Foundation final human review 必须确认 AMF-RIS-011 有可重放结果、0 blocking issues，并且
  cache identity 已包含最终 quadrature policy。
