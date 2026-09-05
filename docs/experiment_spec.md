# 实验与结果数据规格

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation 0.1.1C Verified provenance contract |
| 当前实验 | Phase Resolution |

## 1. 可复现性规则

每次实验必须固定并记录：scene、center frequency、bandwidth、channel frequency model、geometry、
generation、algorithm、Profile、Ground Truth sigma、random seed、控制变量、评价指标、quadrature/
coefficient policy/version 和 runtime。对照组只能改变声明的控制变量；改变
孔径和 cell 数的实验不能被称为“纯相位位数对比”。

当前 v0.1 runner 的 `--output` 会创建目录并覆盖同名 CSV/PNG；这是 legacy 行为，不是 Foundation
允许的归档策略。C2 实现后，Foundation run 必须使用 §3.2 的 exclusive no-overwrite 目录；
`results/phase_bits` 保持只读历史，不再作为新运行默认目标。

## 2. Phase Resolution v0.1

入口：

```text
python -m airmirror_future.experiments.phase_bits --output results/phase_bits
```

这是历史入口示例，不应再次对 tracked `results/phase_bits` 执行；需要复核当前 runner 时必须指定
新的隔离目录。C2 实现后改用 §3.2 的默认/显式 no-overwrite run directory。

固定条件：Smart Space、Advanced 几何、`1.6×1.2 m`、`24×24`、效率 0.85、同一 TX/RX、
Controller Model、v0.1 RIS-only Physics Focus、seed 20260901。控制变量依次为
1、2、3、4、continuous。

每个点输出目标 RX power/SNR/RIS Gain，并用 Fast 80×60 场图计算 Coverage。PNG 横轴为
phase resolution，纵轴为 target RIS gain dB，用于观察收益递减。

## 3. CSV 最小字段（Foundation target；v0.1 legacy exception）

下表是 Foundation 新实验输出的目标最小字段。当前 `results/phase_bits` 仍是 v0.1 legacy，缺少
后续 provenance 字段不构成数据损坏；它只能被明确标为 legacy，不能回填推测值。

| 字段 | 单位/类型 | 说明 |
|---|---|---|
| `provenance_schema_id` | str | Foundation 固定 `airmirror_experiment_provenance`；legacy 缺失 |
| `provenance_schema_version` | int | Foundation 固定 `1`；未知非空版本拒绝 |
| `provenance_status` | partial/complete | 由 pending contracts 决定；新输出不写 legacy |
| `pending_contracts_json` | JSON array[str] | 尚未签署的 owner Work Item IDs，排序且无重复 |
| `run_id` | str | 等于 no-overwrite run directory basename |
| `software_version` | str | 实际 package version，不从目标 release 猜测 |
| `timestamp` | ISO-8601 UTC | 行生成时间 |
| `scenario` | str | 场景名 |
| `frequency_hz` | Hz | 载频 |
| `bandwidth_hz` | Hz | 等效占用/接收噪声带宽 |
| `channel_frequency_model_id` | str/empty | 由 FND-PHY-NB 拥有；未接入时不得从 ADR 目标值回填 |
| `profile_id`,`profile_version` | str | 实际注入的 Foundation 环境传播身份 |
| `profile_parameters_json`,`profile_identity` | canonical JSON / str | C1 tagged parameter array 与 helper 计算的 SHA-256 identity |
| `reflection_model_id`,`reflection_model_version` | str | 墙反射几何/系数模型身份；与 Profile 身份分离，legacy 可缺失且不得回填 |
| `world_model_id`,`world_model_version` | str | `controller_nominal/1` 或 `ground_truth_stochastic/1` |
| `world_model_parameters_json` | JSON object | 实际六个 GT sigma；Controller 为 `{}`；key 排序且禁止 NaN/Inf |
| `generation` | str | preset 标签 |
| `ris_count` | int | 场景 RIS 数 |
| `ris_width_m`,`ris_height_m` | m | 实体孔径 |
| `nx`,`ny` | int | 等效可控孔径 patch 网格；不表示真实 meta-atom 布局 |
| `phase_bits` | int/continuous | 控制变量 |
| `efficiency` | ratio | `[0,1]` |
| `phase_error_sigma_rad` | rad | Ground Truth 参数 |
| `algorithm` | str | 算法名 |
| `focus_mode_id`,`focus_mode_version` | str | `ris_only_phase_conjugate/1` 或 `coherent_target/1` |
| `search_levels` | int/empty | 仅 continuous feedback search 适用；不适用为空 |
| `rx_x_m`,`rx_y_m`,`rx_z_m` | m | 目标位置 |
| `received_power_dbm` | dBm | 目标结果 |
| `ris_gain_db` | dB | 相对同一 realization baseline |
| `snr_db` | dB | 目标 SNR |
| `coverage_percent` | % | 带记录阈值的场图 coverage |
| `coverage_threshold_db` | dB | 场景 threshold |
| `iterations` | int | Focus 固定为 1 |
| `runtime_s` | s | legacy/C2 row runtime；QA-AP raw rows 使用 `quadrature_runtime_s` 表示单次求积 evaluation |
| `random_seed` | int/empty | 实际使用或显式声明的整数 seed；不适用为 CSV 空单元格；0 仅表示实际 seed 0 |
| `pattern_seed` | int/empty | QA-AP random legal pattern 的独立 seed；Focus 行为空值，不替代 C2 world/scene `random_seed` |
| `quadrature_policy_id`,`quadrature_policy_version` | str/empty | FND-QA-AP owner；未签署不伪造 production default |
| `coefficient_model_identity` | str/empty | FND-QA-CC owner；builder/identity 未完成时为空 |

Profile 字段只描述 environment modifier 规则。墙几何、名义反射参数及 Ground Truth 有效墙状态
必须进入未来总体 coefficient/world-model identity，不能伪装成 `profile_id/version` 变化。
`finite_wall_single_bounce_image/1` 只标识 C1 的反射算法/因子所有权，不是插件名或完整 world hash。
Ground Truth parameter JSON 必须包含当前模型的六个 sigma，而不是只包含 sweep 控制变量；固定 key
见 [C Work Item](work_items/foundation_0_1_1_c.md)。

新增实验可增加列，不得删除这些共同追踪字段；不适用的指标应为空并在实验文档解释，
不能填零冒充测量值。

### 3.1 Completeness、future identity 与 legacy

C2 schema ID/version 固定为：

```text
provenance_schema_id = airmirror_experiment_provenance
provenance_schema_version = 1
```

C2 初次实现时，FND-PHY-NB、FND-QA-AP、FND-QA-CC 仍未签署，必须列入
`pending_contracts_json`；其 owner 字段保持空。若某后续 QA runner 正在评价显式 candidate，
可以记录 candidate ID/version，但 owner 仍留在 pending list，结果仍为 `partial`。只有 pending
为空且本 run 必需 identity 均由 owner closure 签署并非空时才能写 `complete`。不得用 `default`、
类名、ADR 目标值、0 或当前行为猜测 future identity/Verified provenance。

只有已确认的 `results/phase_bits/` v0.1 历史输出由 reader/report 派生为
`legacy_v0_1_unversioned`。`results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/` 保持
`checkpoint / non-formal provenance`，不能因缺少 schema 而重分类为 v0.1 legacy。
Foundation 新 run（含默认目录及显式 `--output`）缺少或空置 schema ID/version 任一字段时，
必须按 malformed provenance 明确失败；未知来源的 schema-less 文件保持未分类，不能猜为
v0.1 legacy 或作为 Foundation provenance。未知的非空 schema ID/version 明确拒绝，不降级 legacy。
旧文件不回写、不补默认 Profile/Reflection/channel/quadrature/coefficient identity。
legacy、checkpoint、partial 和 complete 不能无标签聚合为同一证据等级。

完整 canonical/profile 字段、pending owner 和异常规则见
[C Work Item](work_items/foundation_0_1_1_c.md)。

### 3.2 Foundation run directory / no-overwrite

Foundation Phase Resolution 默认写入：

```text
results/foundation_0_1_1/phase_bits/<run_id>/
```

`run_id` 为 UTC `YYYYMMDDTHHMMSS.ffffffZ-<8 lowercase uuid4 hex>`。显式 `--output DIR` 表示完整
run directory，而不是可复用容器。目标必须不存在并 exclusive create；已存在时在计算/写文件前
抛 `FileExistsError`。不提供 `--force`，不删除/清空/合并目录，也不覆盖 legacy。每个 run 的
CSV/PNG 共处一目录，CSV 的 `run_id` 必须与目录名一致并作为同目录 PNG 的 provenance。
repo 内解析后的 `results/phase_bits/` 是保留路径，即使不存在也拒绝作为 Foundation
`--output`。

失败留下的 partial directory 不自动复用或删除。完整历史迁移、结果索引和 artifact store 留给
P1B，不是 C2 的前置实现。

## 4. 统计比较规则

- 无随机误差的参数 sweep 若声明 seed，可用单 seed 并记录实际值；seed 不适用时按 §3 留空；
- 有随机误差的算法对比至少使用一组预先声明 seeds，报告 median 和分位区间；
- 三算法必须共享每个 seed 的 Ground Truth realization；
- performance recovery 必须相对同一 no-error 或 oracle 对照定义；
- 不选择性删除失败 seed；数值异常单独记录并视作缺陷调查对象。

## 5. 后续实验 Definition of Ready

| 实验 | 唯一控制变量 | 必须先实现 |
|---|---|---|
| Aperture | W/H | 保持 cell density/phase/eta 的对照策略 |
| Phase Error | sigma_phase | 三算法、共享 seeds、统计汇总 |
| RIS Count | 0/1/2/4 | 多 RIS 单跳和 pattern ownership |
| Dynamic User | time/trajectory | 时间步、静态/自适应更新策略 |

实验未满足上述前置项时保持 Planned，不创建输出看似完整但数据来自占位逻辑的脚本。

## 6. Foundation FND-QA-AP（Ready，非当前可运行实验）

FND-QA-AP 是 Foundation final exit evidence，不是 P1C 完整 Aperture experiment，也不是当前
已实现命令。FND-QA-AP-01 preregistration 已 signed/frozen，Work Item 已 Ready；后续
QA-AP-02..06 负责实现、运行和验证。不得在 README 提供可运行命令或生成占位结果。

唯一控制变量是每个 fixed control patch 内的 quadrature rule/order。一个 refinement series
必须固定 aperture、`nx/ny`、commanded pattern hash、frequency、geometry、Profile、
`ControllerModel` world/scene realization、C2 `random_seed` 和 baseline。QA-AP 主门禁不使用
`GroundTruthModel`；禁止随 order 重新生成 Focus。

最小输出除第 3 节可复用字段外，还必须记录：

- `qa_schema_version`、`geometry_case`、实际 TX/RX/RIS 坐标；
- `profile_id/version/parameters/identity`、`reflection_model_id/version`、
  `world_model_id/version/parameters`、`channel_frequency_model_id`、
  `quadrature_policy_id/version`、候选 `coefficient_model_identity` 和 C2 pending contracts；
- `pattern_class/hash`、预登记 random seed；
- `quadrature_rule/order_x/order_y`；
- `a_n` 的 `a_inf_abs_error`、`a_inf_robust_rel_error`、`reference_a_inf_norm` 和 reference
  artifact identity；`h_RIS`/`h_total` real/imag、absolute/robust normalized error、magnitude/phase error；
- RIS-only/total power、RIS Gain 及 ill-conditioned/not-applicable reason；
- reference label、successive difference、runtime 和 peak memory。

### 6.1 FND-QA-AP-01 signed/frozen runner/output contract

本节是 FND-QA-AP-01 preregistration 的 signed/frozen contract，不表示 runner
已实现、正式 QA matrix 已运行或 production quadrature 已迁移。建议的 headless 入口为：

```text
python -m airmirror_future.experiments.fnd_qa_ap_01 --output DIR
```

`--output DIR` 表示完整 run directory；不传时使用新的
`results/foundation_0_1_1/qa_ap/<run_id>/`，两者均 exclusive-create、no-overwrite，目标
存在时在 scene/engine/simulation 之前失败。不允许 `--force`、复用、清空或覆盖。raw 明细
写入 `fnd_qa_ap_01_raw.csv`，汇总写入 `fnd_qa_ap_01_summary.json`；两者同目录且均含
`run_id`。raw 的一行代表一个
`(generation, geometry_case, focus_or_random_pattern, pattern_seed, quadrature_rule, order_x, order_y)`
组合；reference 行通过 `reference_label` 和 `reference_row_id` 指向同一 raw 文件中的
internal refined numerical reference。summary 按 geometry × generation × pattern 汇总，
报告 `a_n` 的确定性误差字段（不直接内嵌完整向量）、`h_RIS`、`h_total` 三类 gate 的确定性误差字段、reference artifact identity、
null/ill-conditioned 原因及 pass/fail。完整 Future `a_n` 向量如需保留，写入独立 artifact，
不得塞入普通 summary CSV/JSON 单元格。

输出复用 `airmirror_experiment_provenance/1` 的字段与 no-overwrite 规则。签署后的 QA policy
identity 可写入 `quadrature_policy_id/version`；`provenance_status` 必须为 `partial`，且
`pending_contracts_json` 必须继续包含 `FND-PHY-NB`、`FND-QA-AP`、`FND-QA-CC`；coefficient
identity 仍由 FND-QA-CC 拥有，不能伪造成 production default。

主 gating world 仅为 `ControllerModel`。`random_seed` 是 C2 scene/world seed；random legal
pattern 使用独立 `pattern_seed`，固定候选列表由 preregistration 提供。off-focus pattern
针对 `focus_target_rx` 只生成一次，evaluation 使用 `evaluation_rx` 且不重新 Focus。
同一 refinement series 固定 aperture/control grid/geometry/frequency/Profile/world/baseline/
commanded pattern/hash；`pattern_hash` 只表示 commanded phase snapshot，generation、geometry
和 seed 等上下文进入独立 `series_identity`；order 改变只改变 quadrature。subpoint 按确定性 parent-major 顺序，
继承 parent control patch 的同一 command coefficient。

### 6.2 Performance measurement contract (approved/frozen candidate)

正式 runner 必须记录 reference environment：Intel Core Ultra 9 275HX、24 logical processors、
34,019,852,288 bytes RAM、OS kernel `10.0.26100.0`、Python 3.14.3、NumPy 2.4.4；采用
single process、single BLAS thread、no parallel series，并记录实际 BLAS/OpenMP 环境变量。
使用 `time.perf_counter()` 分别记录 `quadrature_runtime_s`（单个 quadrature row）、
`series_runtime_s`（一个 generation × geometry × pattern 的完整 midpoint ladder 与必需 GL，
包括一次性 Focus/pattern setup）和 `run_runtime_s`（整个 base minimum matrix 从目录分配到
raw/summary/run metadata flush）。peak memory 使用 child-process peak RSS/Windows working-set
equivalent，并在 quadrature、series、run scope 记录 MiB。Current/Advanced/Future 的
120/240/600 s 预算适用于 `series_runtime_s`；8 h 预算适用于 `run_runtime_s`。base minimum
matrix 仅包括 midpoint 1×1/2×2/4×4/8×8/16×16 和固定 GL16×16 cross-check，不包括 conditional
midpoint 32×32 或 GL32×32；触发时额外运行 midpoint32 与 GL32，并单独记录 conditional 32 runtime/RSS，且不得修改 numerical
thresholds。物理核心数若无法由 runner 可靠报告，必须显式记录 unavailable，不得改变上述
single-threaded budget contract。

正式结果写入新的版本化目录并默认 no-overwrite。reference 只能标为 internal refined numerical
reference，不得标为 Ground Truth/EM truth。一次隔离审计中的 `0.430–0.848 dB` 只用于说明
工作项必要性，不得回填为正式 CSV 或 PASS evidence。
