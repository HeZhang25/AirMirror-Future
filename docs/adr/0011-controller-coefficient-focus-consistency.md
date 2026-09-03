# ADR-0011：Controller 名义系数与 Focus 目标一致性

- 状态：Accepted
- 日期：2026-09-03
- Supersedes：无；补充 ADR-0006 与 ADR-0008，不重开 A1/A2
- 关联需求：AMF-RIS-008、AMF-RIS-011、AMF-RIS-012
- 关联工作项：[FND-QA-AP](../work_items/foundation_0_1_1_qa_ap.md)、
  [FND-QA-CC](../work_items/foundation_0_1_1_coefficient_consistency.md)

## 背景

A1 已验证两种 Focus 的 objective 和公共 offset 行为；A2 已冻结 equivalent control patch 语义；
FND-QA-AP 将决定一个 control patch 的 production coefficient 应使用哪种 quadrature policy。
当前 `1×1`、实数方向/阻挡因子的模型中，按中心总路径 `k(d1+d2)` 生成相位与按复系数相位共轭
等价。但一旦 Profile modifier 含复相位或 production quadrature 汇聚多个 subpoint，中心路径
相位可能不再等于 simulator 实际使用的 control-level coefficient 相位。

若缓存、传播和 Focus 各自重算近似系数，软件可能在“算法测试通过”的同时优化另一个模型。
另一方面，Ground Truth 本来就应包含未知误差，不能要求 Controller Focus 使用真实系数。

## 决定

### 1. 统一的 Controller 系数分解

在已签署 quadrature policy 下，第 n 个 control patch 的 Controller nominal coefficient 定义为：

```text
a_n^C = sum_q w_nq * K_geom(r_nq)
                    * m_in^C(r_nq) * m_out^C(r_nq)

K_geom(r) = sqrt(Gt*Gr) * A_control/(4*pi*d1*d2)
            * D(r) * exp[-j*k*(d1+d2)]

Gamma_cmd,n = sqrt(eta_nominal,n) * exp(j*phi_cmd,n)
h_RIS^C = sum_n a_n^C * Gamma_cmd,n
```

`w_nq` 为 patch 内 normalized quadrature weights，满足 `sum_q w_nq=1`；当前 production
`1×1` midpoint 是 `q=1,w=1` 的特例。面积只在 `K_geom` 中出现一次。Profile modifier 的边界
遵循 ADR-0012，不得重复传播 carrier。Foundation 默认 blocker 仍按 RIS center 得到统一标量并
复用于各 q；写成 `m(r_nq)` 不表示已获得 spatially resolved blockage。

Ground Truth 使用自己的几何/环境系数和 actual reflection state：

```text
Gamma_actual,n = sqrt(eta_actual,n)
                 * exp[j*(phi_cmd,n+epsilon_phi,n)]
h_RIS^GT = sum_n a_n^GT * Gamma_actual,n
```

`a^GT` 与 `Gamma_actual` 可以因位置、墙/环境、效率和相位误差不同于 Controller。Feedback 只经
MeasurementOracle 观察结果；不得把 `a^GT` 泄漏给 model-based Focus。

### 2. Focus 必须使用同一组 `a^C`

对于相位不改变幅度的 Controller model：

```text
RIS-only: phi_n = -arg(a_n^C)
Coherent: phi_n = arg(h_baseline^C) - arg(a_n^C)
```

finite-bit 仍按 ADR-0006 在量化前加入公共 offset，并用同一 Controller simulator objective 比较。
Focus、单链路传播、FND-QA-AP runner 和未来 P1A `A @ Gamma` 必须调用同一 coefficient builder
或由测试证明数学/数值等价；不得维护四份近似公式。

### 3. 公共 API 和兼容边界

- `a_n`/`Gamma` 首先是 simulation/physics 内部契约，不替换当前公共 phase-array API；
- `ris_patterns` 仍是 `[nx*ny]` commanded phase 数组，A3 继续负责硬件状态验证；
- `generate_focus_pattern()` 的 RIS-only 兼容名称和 A1 Verified 状态不改变；
- 效率因子在内部重排到 `Gamma` 时必须保持复信道数值等价，不得借机改变校准；
- 不增加 cache，不改变 Scene v1，不实现幅相耦合。

### 4. 与 FND-QA-AP 的条件顺序

本 ADR 不预先改变 production quadrature：

1. FND-QA-AP 先签署 control-level coefficient policy；
2. 若 policy 保持 `1×1`，FND-QA-CC 只需证明中心路径 Focus 与 `a^C` 形式等价并锁定回归；
3. 若 policy 需要 `>1×1` 或带复相位 modifier，必须先创建独立 production-migration Work Item，
   让 simulator 与 Focus 共同使用新 coefficient builder；
4. 迁移、完整回归和 provenance 通过后，才能执行 FND-QA-CC 最终签署；
5. 任一路径未闭环时 Foundation 保持 In Progress，P1A 不得开始。

该顺序不重开 A1/A2：A1 验证的是 objective contract，A2 验证的是 patch semantic contract；
FND-QA-CC 验证的是两个已接受契约在最终 production coefficient 下仍然一致。

### 5. 稳定系数身份

未来 `coefficient_model_identity` 至少分层包含：

```text
channel_frequency_model_id
profile_identity
quadrature_policy_identity
geometry/aperture/control-grid identity
frequency, TX/RX gains, direction exponent
blockage/reflection state relevant to the selected world model
controller_or_ground_truth_model_identity
```

pattern phase、commanded state 和 measurement noise 不属于几何 coefficient identity；它们分别
作用于 `Gamma` 或 oracle 输出。上述是身份契约，不授权本轮或 Foundation 实现 cache。

## 后果

- Focus 和 simulator 不会在未来 Profile/quadrature 升级后悄悄优化不同模型；
- Controller 与 Ground Truth 的差异被保留，不会以“一致性”为由泄漏真值；
- 当前 API 和 A1/A2 状态保持稳定；若 1×1 通过，可能只需增加等价证据；
- 若 QA 选择多点 production policy，需要一次明确迁移，而不是仅改缓存或仅改 Focus；
- 内部 coefficient builder 会成为 P1A 的可信输入，但其存在不代表数值已缓存。

## 候选与否决理由

- **继续让 Focus 只看中心路径、simulator 单独升级 quadrature**：否决。复系数相位可能不一致。
- **Focus 使用 Ground Truth coefficient**：否决。违反 ADR-0003 和反馈实验隔离。
- **立即把 `a_n` 暴露为公共稳定 API**：否决。Foundation 尚未签署 quadrature 与数据布局。
- **把 efficiency 同时放进 `a_n` 和 `Gamma_n`**：否决。会重复计算功率效率。
- **以 A1 已 Verified 为由跳过一致性检查**：否决。A1 没有承诺未来 quadrature/Profile 实现。

## 验证

- FND-T21：RIS-only Focus 使用同一 `a^C` 相位，continuous nominal 下各项同相；
- FND-T22：Coherent Focus 使用同一 `a^C` 与 `h_baseline^C`，并保持 ADR-0006 的退化、量化和
  tie-break 行为；
- Controller/GT 边界测试证明 model-based Focus 不读取 `a^GT`；
- 若 production policy 迁移，旧/新 coefficient、三代 headless、field map 和 experiments 按
  已签署容差与 provenance 完整复核；
- Foundation 最终人工审查确认 coefficient identity 的每个影响项有唯一所有者。
