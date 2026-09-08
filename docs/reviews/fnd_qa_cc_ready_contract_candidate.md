# FND-QA-CC Ready 实施契约候选（C 提交独立 D 复核）

| 属性 | 值 |
|---|---|
| Work Item | `FND-QA-CC` / `AMF-RIS-012` |
| 作者角色 | C / Coefficient Consistency Owner |
| Contract base SHA | `87d2dea8c3ca40774f754271d7b21743cefcc133` |
| 当前集成基线 | `origin/main@a7271648d3d6d98d6af953eadcc4784b7776222f`（PR #23/#22） |
| 本稿状态 | **READY PASS；D evidence `73fc59fa`，blocking findings 0；阶段二已获维护者授权** |
| 允许范围 | 阶段一实施契约和验证计划；不迁移 production，不提升状态，不进入 P1A |

## 1. 证据来源和纠正边界

此前 C 前置审计包固定在旧 SHA `275fedfe6a8a4a1d8a45d3045cf6334e4d4202e2`，位于仓库外，
其 ZIP SHA-256 为
`5B5EBF98CE72221A2B6D5B40810A371460C9B8CAABC658733E756B0A6B450EAC`。该包只能作为历史风险
复现，不能与本基线数值混合。包内 `REPORT.md` 的旧 “D 已复跑/无阻断” 段落已被
`HANDOFF_CORRECTION.md` 撤销。现有本机 `d_*` 目录和 Codex 子代理回复不构成真正独立 D 审查。

本稿尚未取得真正 D 的独立电脑、独立 checkout、命令日志或签署。真正 D 必须从本 task branch
取得本稿和机器契约，在自己的环境审查同一 commit；C 不代签，不把代理模拟称为独立审查。

PR #23 merge `6bc64c5` 已在 main 正式签署 FND-PHY-NB Verified、
`channel_frequency_model_id=narrowband_center_frequency_flat_v1`，以及 production M8 canonical
identity `midpoint_8x8_per_control_patch/1`。本稿只消费该 authoritative closure，不替外部 owner
扩大范围；QA-AP runner 的历史 `fnd_qa_ap_candidate/1` 仍不得冒充 production identity。

## 2. 当前生产分叉（本轮不重复开放式审计）

当前实际调用图为：

```text
ris.phase.generate_*                      # cell-center phase seed
  -> optimization.coherent_focus          # baseline + engine objective
       -> SimulationEngine.compute_channel
            -> physics.ris_scattering      # production midpoint 8x8

experiments.fnd_qa_ap_01.evaluate_quadrature
  -> physics.ris_scattering private sample helper
  -> 独立重算 control reduction/Gamma
```

production M8 的单 sample 公式在 `physics/ris_scattering.py`，但 control-level reduction 在 engine
散射路径和 QA runner 中分别编排；Focus 仍以 cell center `k(d1+d2)` 生成相对相位。旧 2x2 研究
fixture 已证明这种定义差异可观察，但没有覆盖 production grids，也没有构造 M8-derived Coherent
comparator，因此不能签署 FND-T21/T22。

## 3. 冻结候选：共享 coefficient source 与依赖方向

### 3.1 唯一低层 source

阶段二只允许从现有 `physics.ris_scattering` 公式**抽取**一个 control-level pure reduction，禁止
复制第二套公式。候选内部签名：

```python
def reduce_ris_control_coefficients(
    tx: Transmitter,
    rx_position: Vec3,
    receiver_gain_linear: float,
    ris: RISSurface,
    frequency_hz: float,
    *,
    quadrature_spec: QuadratureSpec,
    incident_modifier: complex,
    scattered_modifier: complex,
) -> np.ndarray:
    """Return complex a[control_count], excluding RIS efficiency and phase."""
```

冻结输入/输出契约：

- 输出为一维 `complex128 [ris.cell_count]`，只读或返回独立快照；非有限输入/输出明确失败；
- `quadrature_spec.control_count == ris.cell_count`；production engine 仍强制 signed midpoint `8x8`；
- control flatten token 固定为 `ris_cell_centers_meshgrid_xy_c_v1`：`parent=iy*nx+ix`，x index fastest；
- subpoint 顺序固定为 parent-major、local-y、local-x；每个 parent 的 normalized weights 和为 1；
- `cell_area_m2 = width_m*height_m/(nx*ny)` 在 pure reduction 内恰好乘一次；它是派生值，不是第二
  canonical source；
- `incident_modifier`/`scattered_modifier` 已由 simulation 编排层在 RIS-center path context 下求值，
  pure physics 不导入 `simulation`、Profile 或 world model；
- 函数不接受 commanded pattern、phase bits、efficiency、TX power、bandwidth、noise figure、coverage、
  measurement/oracle RNG 或 GUI 状态。

`physics.ris_scattering` 的 scalar/points 传播入口必须由这个 reduction（或共享同一更低层 sample
kernel 加唯一 reduction）构造 `a`，再单独构造 `Gamma` 并求和。QA-AP evaluator 改为调用同一
reduction 并传显式 `QuadratureSpec`；其历史 artifacts、signed policy 和候选顺序不回填。

### 3.2 simulation 编排层

`SimulationEngine` 继续唯一负责：解析 TX/RX/RIS、A3 command validation、Controller/GT working
geometry、五类 Profile context、wall/reflection baseline、world realization 以及 link metrics。
候选内部 scene-aware seam：

```python
@dataclass(frozen=True, slots=True)
class ControllerFocusTerms:
    coefficients: np.ndarray       # a^C, shape [N]
    baseline_channel: complex      # h_LOS^C + h_wall^C
    coefficient_identity: str      # candidate until closure
    baseline_identity: str

def controller_focus_terms(
    self,
    scene: Scene,
    tx: Transmitter | str | None = None,
    rx: Receiver | str | None = None,
    ris: RISSurface | str | None = None,
    model: ControllerModel | None = None,
) -> ControllerFocusTerms:
    ...
```

该 seam 必须显式拒绝 `GroundTruthModel`，不得调用 MeasurementOracle；`optimization` 可以依赖
`simulation`，`simulation` 可以依赖 `physics/ris/core`，但 `ris` 和 `physics` 不得反向依赖
`simulation/optimization/experiments/gui`。

最终调用图冻结为：

```text
Scene + ControllerModel
  -> SimulationEngine orchestration
       -> Profile modifiers + working nominal geometry
       -> pure reduce_ris_control_coefficients -> a^C
       -> baseline composition               -> h_baseline^C
  -> scene-aware Focus consumes exact same terms
  -> A3 validates phi_cmd
  -> Gamma_cmd builder
  -> dot(a^C, Gamma_cmd)

GroundTruthModel
  -> SimulationEngine working truth geometry -> same pure reduction -> a^GT
  -> Gamma_actual builder (actual efficiency + phase error)
  -> dot(a^GT, Gamma_actual)
```

## 4. 冻结候选：因子所有权

| 因子 | `a^C/a^GT` | `Gamma_cmd` | `Gamma_actual` | baseline | metric/oracle |
|---|---|---|---|---|---|
| `1/(4*pi*d1*d2)`、`exp(-jk(d1+d2))` | 一次 | 否 | 否 | 各自 carrier | 否 |
| TX/RX gain `sqrt(Gt*Gr)` | 一次 | 否 | 否 | carrier 一次 | 否 |
| control patch area | reduction 一次 | 否 | 否 | 否 | 否 |
| direction factor | reduction 一次 | 否 | 否 | 否 | 否 |
| Profile RIS incident/scattered modifier | 一次 | 否 | 否 | 否 | 否 |
| nominal RIS efficiency `sqrt(eta_nominal)` | 否 | 一次 | nominal base only | 否 | 否 |
| GT efficiency scale | 否 | 否 | 与 nominal 合并、clip 后一次 | 否 | 否 |
| commanded phase | 否 | `exp(j*phi_cmd)` 一次 | base command 一次 | 否 | 否 |
| GT phase error | 否 | 否 | `exp(j*epsilon_phi)` 一次，不重新量化 | 否 | 否 |
| `Gamma_wall` | 否 | 否 | 否 | Reflection/Wall 一次 | 否 |
| wall before/after Profile modifier | 否 | 否 | 否 | 每 leg 一次 | 否 |
| TX power `Pt` | 否 | 否 | 否 | 否 | received power/objective 一次 |
| `B/NF` | 否 | 否 | 否 | 否 | noise/SNR/capacity only |
| coverage threshold/grid | 否 | 否 | 否 | 否 | coverage/report only |
| measurement noise | 否 | 否 | 否 | 否 | MeasurementOracle only |

`a^GT` 与 `a^C` 共享数学 source，但使用各自 working geometry、Profile/world inputs；共享 source
不等于共享值。`Gamma_actual` 不能回流到 nominal Focus。

## 5. Focus 兼容迁移和 finite-bit 语义

### 5.1 保留的 legacy 公共 API

以下 API、签名、shape、异常和 v1 center-path 数组语义保持不变：

- `generate_focus_pattern()`；
- `generate_ris_only_focus_pattern()`；
- `generate_unquantized_ris_only_focus_pattern()`；
- `ris_patterns[id] == phase_rad[nx*ny]`；
- `validate_commanded_pattern()` 不 wrap、不 snap、不 silent quantize。

它们继续用于历史兼容和教学解释，不被改名为 M8-consistent production evidence。

### 5.2 新的 scene-aware production RIS-only 路径（ADR-0013 方案 A，已获维护者批准）

新增 optimization/simulation 层内部 callable（最终名称由代码审查确认，不顶层 export）：

```text
base_phase_n = wrap(-arg(a_n^C))
continuous command = base_phase
finite command = Q(base_phase + delta), delta in ADR-0006 candidates
```

RIS-only 的 Foundation 语义仍是 phase-conjugate，不读取 baseline。有限 bit 下，本 Work Item 的
连续解析目标为 `P_RIS=Pt*|sum(a_n^C*Gamma_cmd,n)|^2`，continuous `-arg(a^C)` 在幅度不随
phase 变化时使各项同相。有限 bit 使用 ADR-0006 既有公共 offset 候选生成器：`delta=0` 精确为
首项，随后保持既有边界排序/环形中点顺序，仅以既有 strict-better 规则替换 incumbent，平局
first-wins。目标只在该公共 offset 可达候选族内最优，不宣称任意逐 patch 离散组合的全局最优。

逐元素 `a_n^C == 0` 使用确定性 `base_phase_n=0.0` 后进入同一量化器；不新增容差。aggregate
RIS 退化继续使用 ADR-0006 的精确 `0.0` fallback。任一 coefficient、phase、channel 或 offset
含 NaN/Inf 均按既有输入校验抛 `ValueError`，不得静默替换或放宽错误语义。

因此兼容关系明确为：legacy API 继续 `Q(center-path)`；新增 production scene-aware path 使用
`Q(-arg(a^C)+delta)`。legacy API 不声明 common-offset 保证；两者在 M8/complex Profile 下可以不同，差异必须在 release note/provenance 中
显式记录，不能伪装为数组兼容。

### 5.3 Coherent 路径

`generate_coherent_target_pattern()` 的公共签名、Controller-only 边界和 total received-power
objective 保持不变，但相对 phase seed 迁移为同一 `a^C`：

- continuous：`phi_n = wrap(arg(h_baseline^C) - arg(a_n^C))`；
- finite-bit：以 `base_phase=-arg(a^C)` 生成 ADR-0006 的 common-offset 可达候选；
- 候选 0 必须精确为 `delta=0`；之后仍按已有唯一边界排序和环形区间中点顺序；
- 每个 candidate 必须先经 A3 validator，再由同一 Controller engine objective 评价；
- incumbent 为 `delta=0`；仅沿用 `_strictly_better` 的 `8*eps*scale` 严格超过才替换；平局
  first-wins；
- baseline/RIS 非有限值失败；ADR-0006 `64*eps` 相对退化判断和精确 `0.0` fallback 不变。

这里改变的是 ADR-0011 已要求的 coefficient basis，不改变 ADR-0006 的 total-power objective、
candidate ordering、strict comparison、first-wins 或 degenerate semantics。若 reviewer 认为相对
phase basis 的迁移仍需新增 ADR，则该项是 Ready blocker，实施不得开始。

## 6. coefficient identity 候选（等待 D 冻结）

所有 identity 使用 domain-separated tagged canonical JSON + SHA-256，UTF-8、key 排序、数组保序、
binary64 用 `float.hex()`，禁止对象地址、`repr()` 和 Python `hash()`。

### 6.1 `ris_transfer_coefficient_identity`

包含：

- namespace/schema、Controller 或 GT world namespace；
- `channel_frequency_model_id`、`frequency_hz`；
- TX/RX working positions 和 gains；
- RIS position/yaw/width/height/nx/ny/direction exponent；
- flatten token、parent mapping、signed quadrature policy ID/version/rule/orders；
- Profile identity、两个 path context（含 `ris_id`）、实际 complex modifiers；
- 对默认 Profile：实际相交/影响 RIS 两段的 ordered environment entities 及几何/attenuation；
- 对未声明 dependency projection 的 custom Profile：保守纳入完整 canonical environment collection。

排除：RIS phase/efficiency、pattern hash、phase bits、Pt、B/NF、coverage、measurement RNG、GUI、
generation label、update rate/self-sensing。`cell_area` 只从 width/height/nx/ny 派生，不重复编码。

实体 ID 规则：`ris.id` 当前实际进入 `PropagationPathContext.ris_id`，必须纳入；相关 wall ID 影响
self-exclusion，必须纳入；相关 obstacle/wall ID 对 custom Profile 可能有语义，纳入 environment
projection。TX/RX ID 当前不进入 RIS Profile context 或公式，只作为 selection/provenance，不进入
数值 transfer identity。同几何改 RIS ID 时 default Profile 数值可能不变，但 identity 必须失效；
测试不得错误断言每个 identity mutation 都必须改变数值。

### 6.2 `baseline_transfer_identity`

包含 frequency model/frequency、working TX/RX geometry/gains、direct Profile evaluation、Reflection
Model ID/version、每条有效 wall 的 ID/geometry/有效 `Gamma_wall`、before/after contexts/modifiers 和
relevant blockers，以及 Controller/GT namespace。排除 RIS command/efficiency、Pt、B/NF、coverage
和 measurement noise。

### 6.3 `commanded_gamma_identity`

包含 RIS ID、control shape/order、phase-control/quantizer version、phase bits、ordered commanded
phase snapshot/pattern hash、nominal efficiency/calibration。它不替代 transfer coefficient identity。

### 6.4 GT 与结果分层

- `ground_truth_physical_realization_identity`：seed/version、position deltas、wall effective state、
  RIS phase/efficiency realization；不包含 measurement sequence；
- `measurement_oracle_identity`：physical result identity、noise model/version/sigma、measurement
  seed 和 sequence/call index；不得进入 nominal Focus；
- `received_power_objective_identity`：baseline/coefficient/Gamma identities + TX `power_w`；
- `link_metric_identity`：received-power identity + `B`、NF、noise/capacity model；
- `coverage_result_identity`：field/link identities + evaluation grid、coverage threshold和 map quantity。

### 6.5 mutation 规则

测试拆成两类，不能再用“identity 变化且数值必变”的过强组合断言：

1. identity invalidation：model/policy/profile version、RIS context ID 等语义 mutation 即使特定 fixture
   数值恰好相同，identity 仍必须变化；
2. physics sensitivity：只对 frequency、positions、gains、aperture/control、direction、有效 modifier
   等预期改变数值的字段另断言 `a` 变化。

负 mutation 必须覆盖：pattern、phase bits、B/NF、Pt、coverage、measurement RNG 不改变 transfer
identity；默认 Profile 下非相交 blocker/无关 wall 不改变 RIS transfer identity；但 relevant baseline
wall 必须改变 baseline identity。custom ID-sensitive Profile 下改 RIS ID 必须能够改变 modifier/`a`。

production canonical quadrature policy ID 已由 PR #23 签署；完整 coefficient identity 仍须在
QA-CC 阶段二实现和验证。不得把 `fnd_qa_ap_candidate/1` 提升成 production 值。

## 7. 正式验证计划

### 7.1 三代矩阵

至少覆盖 QA-AP 已登记的四组明确几何，不复用其充分性 pass/fail 容差：default、near-field、
oblique、off-focus。production grids 固定为：Current `8x8/1-bit`，Advanced `24x24/3-bit`，Future
`64x48/continuous`。off-focus 只在 focus target 生成一次 command，evaluation receiver 重用命令。

每组分别记录：legacy RIS-only、scene-aware RIS-only、M8-derived Coherent、最终 production
Coherent；continuous 与 finite-bit 不做跨模式差值作为验收。Current/Advanced 的
`finite_coherent_minus_continuous_center` 若保留，只能标 descriptive cross-mode，不能作为 T22 gate。

### 7.2 FND-T21

- 从 production source 获取 `a^C`，并用独立 scalar oracle 在至少一个小型解析 fixture 重算 M8；
- continuous scene-aware command 对每个非零 coefficient 满足
  `wrap(arg(a_n^C)+phi_n)=0`，并验证各 `a_n^C*Gamma_cmd,n` 同相；
- finite scene-aware command 枚举 ADR-0006 候选，首项精确为 `Q(-arg(a^C))` 的 `delta=0`；命令全部通过 A3；
- `dot(a^C,Gamma_cmd)` 与 production engine `h_RIS` 一致；
- legacy API 数组、顶层 export、shape、异常继续由现有兼容测试锁定；不要求 legacy center pattern
  等于 M8 production pattern。

### 7.3 FND-T22

- continuous 使用同一 `a^C/h_baseline^C` 解析构造，并验证 aggregate RIS 与 baseline 相位对齐；
- finite 从 `-arg(a^C)` 生成现有 candidate helper；逐候选保存 offset/order/pattern/objective；
- 独立枚举 oracle 验证候选覆盖所有 common-offset 可达 patterns，`delta=0` 首项、strict-better、
  first-wins 与 production result 一致；
- 精确覆盖 baseline=0、RIS=0、relative-near-zero、非有限输入和 equal-objective tie fixture；
- spy/monkeypatch 证明 Coherent 只取得 Controller focus terms，不访问 `a^GT`、GT seed/sigma、
  `ris_phase_offsets`、`ris_efficiency_scale` 或 MeasurementOracle。

### 7.4 数值容差依据

QA-AP 的 `1e-2/0.1 dB/0.05 rad` 是 production adequacy 容差，**禁止**用于 QA-CC 等价。
QA-CC 将两类比较分开：共享-source 消费者不得各自重算；它们应复用同一 coefficient/Gamma
composer，能比较相同返回数组时用 exact array equality。只有“独立 scalar formula oracle 与
production vectorized evaluation”允许数值容差。该容差候选使用 operation-count-aware binary64
forward-error bound：

```text
u = np.finfo(float).eps / 2
gamma(k) = k*u / (1-k*u)
dot_bound = gamma(2*N + 8) * sum(abs(a_n*Gamma_n)) + tiny
M8_parent_bound = gamma(8*8*16 + 32) * sum_q(abs(term_q)) + tiny
```

`dot_bound` 只覆盖固定顺序的 complex multiply/reduction；若最终实现调用 BLAS、pairwise reduction
或 FMA，必须在 Ready review 中按实际算法替换 operation budget，不能把该式直接当保证。
`M8_parent_bound` 只覆盖 64 项 complex reduction；norm、sqrt、power、exp/sin/cos 等 elementary
functions 的跨实现误差不由 `gamma(k)` 自动覆盖。正式 oracle 必须使用与 production 相同的
binary64 elementary kernels、只独立展开公式和循环；否则在运行正式矩阵前另行预注册 ULP 上限和
平台范围。独立 D 必须复核 operation budget，不能看结果后放宽。相位只在幅度不退化时验证，
以对应 complex residual/scale 推导角度界，不使用固定 QA-AP `0.05 rad`。命令数组、candidate
ordering、`delta=0`、first-wins 和 public API compatibility 使用 exact equality；ADR-0006 的退化
和 `_strictly_better` 容差原值不变。

### 7.5 implementation 后必跑（本稿均未执行）

1. 新 FND-T21/T22、formula oracle、identity mutation、GT no-leak、public API tests；
2. 现有 coherent/pattern/production-quadrature/profile/reflection/narrowband/provenance tests；
3. 完整 `python -m pytest`；
4. Current/Advanced/Future Fast headless；
5. C2 provenance/documentation/diff-check；
6. 非作者 D 在独立环境审查代码、原始 logs、三代 evidence 和 identity matrix。

阶段一当前只实际运行：

```powershell
.venv\Scripts\python.exe -m pytest -q `
  tests/test_coherent_focus.py `
  tests/test_production_quadrature.py `
  tests/test_narrowband_frequency.py `
  tests/test_experiment_provenance.py `
  tests/test_pattern_contract.py
```

实际收集并通过 `83` 项（30 + 8 + 5 + 18 + 22）；这不是 FND-T21/T22、完整 pytest 或 closure。

## 8. 受控实施拆分（Ready 后且仅在维护者明确授权后）

1. **CC-01 pure source**：只抽 coefficient/Gamma source 与等价测试；production output 必须保持；
2. **CC-02 scene-aware Focus**：保留 legacy API，迁移 production RIS-only/Coherent，加入 T21/T22；
3. **CC-03 identity/boundary**：实现非缓存 identity helper、mutation、GT no-leak 和 provenance candidate
   接线；不宣称 complete；
4. **CC-04 closure evidence**：完整回归、三代 headless、provenance/docs、外部 D review。

可能修改文件限于 `physics/ris_scattering.py`、`simulation/engine.py`、
`optimization/coherent_focus.py`、必要的新内部 identity 模块、QA evaluator 和相关 tests/docs。
`ris/phase.py` 只允许保持/补兼容说明，不改变 legacy 数组行为。禁止 P1A cache、matrix storage、
chunking、incremental Greedy、signed M8 policy、Scene v1、历史 results 和共享状态抢写。

## 9. XR Adaptive 与历史结果风险

scene-aware Focus migration 可能改变 Current/Advanced/Future commanded pattern，因此所有依赖旧
Focus 的 Adaptive pattern/hash/CSV/field/截图/性能证据均保持历史只读、标记旧 coefficient identity。
实施 closure 后必须在新唯一输出目录重新生成受影响 artifacts，并记录 old/new SHA、focus mode
version、quadrature/coefficient identity；不得覆盖、回填或把旧结果重新标成 formal evidence。

## 10. Ready review 请求与最小待决策项

真正独立 D 请只聚焦以下冻结项：

1. pure reduction 签名、control/subpoint ordering 和 dependency direction 是否足以避免第二公式；
2. factor ownership 与 Controller/GT boundary 是否完整；
3. legacy API + scene-aware production migration 是否符合 ADR-0006/0011；
4. ADR-0013 方案 A 的 RIS-only `P_RIS` common-offset family 与 Coherent total-power family 是否正确分离；
5. identity 分层、RIS/context entity IDs、relevant geometry 与 custom Profile fallback 是否安全；
6. T21/T22 oracle 和 forward-error tolerance 是否可在结果前冻结。

外部门禁已由 PR #23 关闭：FND-PHY-NB Verified，production M8 identity 为
`midpoint_8x8_per_control_patch/1`。QA-CC 不重新选择 policy，只在阶段二消费并验证其接线。

任一项有异议时，D 应给出最小 blocking decision，不参与 builder 核心实现后再充当独立 reviewer。
D 已在 `73fc59fa37ccc0668d3da9db2c46bae482b41d92` 对 `86fb9ce` 签署 **READY PASS**，
blocking findings `0`，且维护者已授权进入既定阶段二。FND-T21/T22、builder、migration 与完整
回归仍是阶段二 closure 证据，不得因 Ready PASS 提前报告为完成。
