# 测试与验证策略

| 属性 | 值 |
|---|---|
| 文档状态 | Normative / Operational |
| 基线版本 | v0.1 + Foundation A1-A3/FND-FIX-WALL/B + C Ready and final gates plan |
| 测试框架 | pytest 9+，pytest-qt |

## 1. 目标

测试不是为了冻结某组好看的 dBm，而是保护以下性质：公式约定、单位、能量/孔径标度、
随机可复现性、数据兼容、层间契约和交互并发。任何测试阈值都必须能解释其物理或工程
来源，不能在失败后反复放宽直到通过。

## 2. 测试层级

| 层级 | 目录/方式 | 目的 | 每次变更 |
|---|---|---|---|
| L1 纯函数单元 | physics/core/ris tests | 公式、量化、几何、校验 | 必跑 |
| L2 性质测试 | aperture/focus/seed | 不变量和趋势，不绑定偶然数值 | 必跑 |
| L3 集成 | scene + engine + optimizer | 层间数据与结果有限性 | 必跑 |
| L4 GUI smoke | Qt offscreen | 构造、取消、版本丢弃 | GUI 变更必跑 |
| L5 人工验收 | `gui_spec.md` 清单 | 拖动、视觉、文案、交互响应 | release 必跑 |
| L6 实验回归 | headless experiments | 研究输出格式与趋势 | 物理/算法 release 必跑 |

默认命令：

```powershell
python -m pytest
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast
python -m airmirror_future.experiments.phase_bits --output results/checkpoints/<new-unique-run-directory>
```

最后一条在 C2 实现前仍是 legacy runner，只能使用新的隔离目录，不能指向 tracked
`results/phase_bits`；C2 后按 versioned/exclusive run-directory contract 执行。

## 3. 必须保护的物理性质

| Test ID | 性质 | 容差/判据 | 当前测试 |
|---|---|---|---|
| PHY-T01 | Friis 距离加倍 | power `-6.0206±0.01 dB` | `test_distance_doubled...` |
| PHY-T02 | 一波长相位 | `kλ=2π` | `test_one_wavelength...` |
| PHY-T03 | 同相等幅 | amplitude 恰为 2 倍 | `test_complex_field_interference` |
| PHY-T04 | π 反相 | residual `<1e-12` | 同上 |
| PHY-T05 | passive eta | `>1` 构造失败 | `test_passive_efficiency...` |
| PHY-T06 | 1-bit states | 仅 0/π | `test_phase_quantization_states` |
| PHY-T07 | 2-bit states | 仅四均匀状态 | 同上 |
| PHY-T08 | Focus vs random | focus > 100 random median 的 4 倍 | `test_physics_focus...` |
| PHY-T09 | fixed seed | complex result 完全一致 | `test_fixed_ground_truth_seed...` |
| PHY-T10 | wall blockage | 幅度衰减换算为 `-30±0.01 dB` | `test_complete_los...` |
| PHY-T11 | fixed-aperture area normalization / no cell-count gain | 8/16/32 spread `<0.5 dB` | subdivision test |
| PHY-T12 | aperture growth | larger focused amplitude > smaller | larger aperture test |
| PHY-T13 | back face | RIS contribution exactly zero | back side test |
| FND-T01 | legacy RIS-only compatibility | 显式名称与 `generate_focus_pattern` 数组完全一致；既有 random median 门禁继续通过 | `test_ris_only_focus_preserves_legacy_phase_conjugation` |
| FND-T02/T02b | continuous coherent alignment | 相位差 `<1e-12 rad` 且 `|h_total|` 满足解析幅度和 | `test_continuous_coherent_focus_*` |
| FND-T03 | nominal no-RIS lower bound | Coherent target `received_power_w >= baseline` | `test_coherent_focus_does_not_reduce...` |
| FND-T04 | finite-bit common offset | 候选首项精确 `0.0`；结果不差于 unshifted | `test_quantized_common_offset_beats...` |
| FND-T05 | degenerate deterministic fallback | 零/相对近零分量返回 `delta=0`，不产生 NaN/Inf | `test_zero_baseline_focus...` |
| FND-T06 | commanded hardware grid | 1/2/3/4-bit off-grid command 抛 `ValueError`；不得 silent quantize | `test_commanded_pattern_rejects_off_grid_phase` |
| FND-T07 | modulo/tolerance contract | 正负多周等价状态和 `1e-6 rad` 内输入通过，容差外失败且原值不被修正 | `test_commanded_pattern_accepts_modulo_equivalent_states`、tolerance test |
| FND-T08 | Actual phase ownership | 确定性非网格 Ground Truth error 完整改变 RIS 复相位，不重新量化 | `test_actual_phase_error_is_not_requantized` |
| FND-T09 | equivalent patch diagnostics | 改 `nx/ny` 只改变 pitch；改 `fc` 不改变实体孔径 | `test_effective_pitch_changes_without_resizing_aperture` |
| FND-T13/T13b | default Profile / all environment roles | 分路径复现 v0.1；direct、reflection before/after、RIS 两段均调用 Profile，且 modifier 不含 carrier/`Gamma_wall` | Ready：C1（未实现） |
| FND-T13c | wall/Profile factor ownership | 独立缩放 `Gamma_wall` 或任一 reflection-leg modifier 时，wall amplitude 恰好缩放一次 | Ready：C1（未实现） |
| FND-T13d | reflecting-wall exclusion | 反射墙不作为自身路径 blocker；其他阻挡仍只作用于命中的路径段 | Ready：C1（未实现） |
| FND-T14 | Profile/reflection identity layering | Profile 参数只改变 profile identity；墙系数改变总体 coefficient/world identity 而不冒充 Profile 变化 | Ready：C1（未实现） |
| FND-T15 | minimum experiment provenance schema | schema ID/version 与实际 focus/profile/reflection/world/search 一致；canonical Profile identity 可复算 | Ready：C2（未实现） |
| FND-T15b | unsigned future identity boundary | 未签署 FND-PHY-NB/FND-QA-AP/FND-QA-CC 时保持 partial/pending，不伪造 Verified/default identity | Ready：C2（未实现） |
| FND-T15c | legacy classification | 缺 schema 的旧文件只派生 legacy 且 bytes/mtime 不变；未知 schema 拒绝 | Ready：C2（未实现） |
| FND-T15d | experiment no-overwrite | existing run directory 在计算前失败；legacy hash 不变；新 CSV/PNG 只写唯一 run directory | Ready：C2（未实现） |
| FND-T16 | quadrature ownership boundary | 固定 aperture/control/pattern/Profile，只改变 rule/order | Planned：FND-QA-AP |
| FND-T17 | refined reference construction | successive refinement + independent rule；未收敛明确失败 | Planned：FND-QA-AP |
| FND-T18 | quadrature report/provenance guards | 深相消不输出 Inf/误导 phase/gain；policy identity 完整 | Planned：FND-QA-AP |
| FND-T19 | floor-anchored wall geometry | 超出 `1e-9 m` 的 endpoint z 拒绝；Ground Truth wall 仅刚体 XY 平移；blockage/reflection 同几何 | `tests/test_wall_geometry.py` |
| FND-T20 | center-frequency flat-channel contract | `fc` 改变 h；`B` 不改变 h(fc) 但改变 noise/SNR/capacity；model ID 稳定 | Planned：FND-PHY-NB |
| FND-T21 | RIS-only coefficient consistency | Focus 与最终 Controller `a_n^C` 相位共轭；1×1 时与历史中心路径等价 | Planned：FND-QA-CC |
| FND-T22 | Coherent coefficient consistency | Focus objective 与 Controller simulation 共用 `a_n^C/h_baseline^C`，保留 A1 量化/退化规则 | Planned：FND-QA-CC |

若更换物理近似导致这些容差不再适用，必须先提交 ADR 解释新性质，并加入等价或更强的
测试；不得先删除失败测试。

FND-T01..T05 只验收 Foundation A1 的 nominal、单 RIS、单目标契约。FND-T02/T03 的解析保证
只适用于 continuous 且命令相位不改变反射幅度；finite-bit 额外以小数组 dense sampling 验证
边界候选覆盖全部公共-offset 可达 patterns。它们不构成 Ground Truth、任意逐 patch 离散组合
或多 RIS 全局最优证据。

PHY-T11 同时细化当前耦合的 control/integration grid，只证明面积归一化后没有随 patch 数量
产生无界增益，并提供当前测试几何下的稳定趋势证据；不得把它描述成真实 meta-atom 或粗 patch
已经达到物理收敛。FND-QA-AP 必须在 Foundation final exit/P1A 前固定 control grid 和
commanded pattern、只细化独立 quadrature，并冻结最小 production coefficient policy；P1C
保留更完整的孔径、场图和适用域研究。

FND-T09 验证 A2 的所有权边界，而不是证明真实阵元满足 `lambda/2` 或当前 patch 已数值收敛。
补充测试覆盖非法频率、非有限孔径、非整数 patch 数以及三代 preset 诊断全为有限正值。

FND-T06..T08 同时覆盖 strict shape、NaN/Inf、unknown/ambiguous RIS key、continuous 未 wrap
phase、非法 `phase_bits` 类型、低层公开 scattering 入口和 engine-before-Ground-Truth 顺序。
Field Map 另以 validator 调用次数锁定为像素循环外一次。测试只验证 Commanded/Actual 边界，
不引入 B 阶段 search levels 或 GUI 状态语义。

FND-T13..T14 验证 ADR-0012 的因子分解，而不只验证最终 wall-channel 数字碰巧相等。测试必须
分别扰动 `Gamma_wall`、before modifier 和 after modifier，防止重复与遗漏互相抵消；还必须验证
Controller/Ground Truth 的有效墙系数由 Reflection Model 消费，隐藏 truth realization 不进入
Profile identity 或 nominal Focus。

具体 C1 contract tests 还必须覆盖五个 role 的 direction/ID/call count、Profile 非 finite/non-scalar
返回和 context 错误、默认 Profile frozen/deterministic、tagged canonical identity 的类型敏感 mutation
以及两个 subprocess 的稳定性。duplicate wall ID 必须在 Profile 调用前 `ValueError`，不能让 ID
self-exclusion 排除多堵墙。数值兼容基准固定为 commit
`d9ab04a502055af3b519a781629e6e83f0ded9d8`，分量复数容差为 `rtol=1e-12, atol=1e-15`；该测试不
签署 quadrature 或 coefficient builder。

FND-T15..T15d 是 C2 的完整 traceability，不可只检查“新增了若干列”。测试必须从实际 engine/
Focus/world inputs 构造 provenance，复算 Profile identity，并验证
`airmirror_experiment_provenance/1` 的 partial/complete 规则。未签署 future owner 的字段只能为空或
显式 candidate 且 owner 仍在 `pending_contracts_json`。legacy fixture 在测试前后比较 bytes/mtime；
existing output directory 必须在任何 simulation call 前失败。精确 schema 和 run directory 见
[C Work Item](work_items/foundation_0_1_1_c.md)。

### 3.1 FND-QA-AP 独立求积验证规则

FND-QA-AP 是 cross-cutting Foundation final gate，不是 A2 的重新验收。正式 runner 必须：

1. 固定 aperture、control grid、flatten order、commanded pattern hash、Profile、几何和 seed；
2. midpoint 至少运行 `1×1、2×2、4×4、8×8、16×16`，必要时 `32×32`；
3. 以 successive differences 判断 reference 是否稳定，并用 tensor-product Gauss–Legendre
   或另一独立规则交叉检查；不能先指定 16×16 就是真值；
4. 覆盖三代、default/near-field/oblique/off-focus 几何、RIS-only/Coherent Focus 和不少于 5 个
   预登记 random legal pattern seeds；
5. 报告 complex absolute error、robust normalized error、magnitude/power dB、phase、RIS-only/
   total power、RIS Gain、runtime 和 peak memory；
6. reference 接近 floor 时将 phase/relative/gain 标为 ill-conditioned 或 not applicable，不输出
   NaN/Inf 或依赖爆炸相对误差判决；
7. 在正式运行前登记 reference tolerance、production tolerance、floor、geometry 和 seeds；
   失败后不得通过放宽阈值取得 PASS；
8. 避开 partial-aperture blockage boundary，并记录当前 scalar blockage mode。

内部最后稳定层级只叫 internal refined numerical reference，不构成 EM/full-wave/measurement
truth。若当前 1×1 不通过，测试本身不静默切换 production；必须由独立 implementation Work
Item 和必要 ADR 接入 policy，再重跑完整回归。

### 3.2 Foundation final physics/algorithm closure

FND-T19..22 是相互独立但都位于 Foundation final exit 前的门禁：

1. **FND-T19 / wall**：构造与 Scene loader 都不能接受随后被 geometry 忽略的超容差 wall z；
   同一 seed 的 wall XY delta 必须刚体、可重放，并同时进入 blockage/reflection；
2. **FND-T20 / narrowband**：比较时固定除一个变量外的所有输入。改变 `fc` 必须重算
   `lambda/k/h`；只改变 `B` 时 LOS/wall/RIS/total complex channel 必须不变，noise/SNR/capacity
   按 ADR-0010 变化；
3. **FND-T21/T22 / coefficient**：必须在 FND-QA-AP 签署 production policy 后运行。若保持
   `1×1`，验证 center-path 与 `a_n^C` 等价；若改为多点，先完成独立 migration，再验证 Focus、
   engine 和 QA runner 共用 coefficient；
4. coefficient test 只能读取 Controller nominal values。改变隐藏 Ground Truth realization 不得
   改变 model-based pattern，但可以改变 oracle measurement；
5. identity mutation matrix 必须区分 coefficient inputs 与 link-metric-only inputs：frequency、
   gain、geometry、direction exponent、Reflection Model/`Gamma_wall`、Profile/quadrature/world
   model 影响 coefficient；pattern、
   `B`、NF、measurement noise 不应被误当成同一层的几何 coefficient。

这些测试不能因 A1/A2 已 Verified 而省略，也不能用它们重开 A1/A2；它们验证的是最终
Foundation 组合契约。

## 4. 数据与 API 测试

- Scene 保存/加载后名称、几何、cell count 和默认语义一致；
- schema version 不支持时拒绝；后续应增加未知/缺失字段和重复 id tests；
- 所有公共参数边界至少有一个非法值测试；
- pattern shape、active RIS、空 TX/RX 和 id 不存在需要逐步补错误契约测试；
- Wall v1 floor-anchor 收紧必须有旧 z=0 round-trip 与非零 z migration/error 测试；
- Foundation provenance 必须区分 Profile、frequency model、quadrature 与 coefficient identities；
- Foundation C2 provenance 必须区分 complete/partial/legacy，记录 pending owner，并拒绝未知 schema；
- FieldMap 四个数组形状一致，coverage+dead-zone 约 100%；
- public top-level exports 能导入。

JSON golden file 只用于结构兼容；物理数值不写入 golden JSON，以免默认场景变动与公式
回归混在同一次失败中。

## 5. 随机与优化测试

- 使用显式 `np.random.default_rng(seed)`，不依赖全局 NumPy RNG；
- 随机 patterns 数量和 seed 固定；
- Ground Truth 误差是固定 realization，measurement noise 是固定调用序列；
- 无噪声贪心的 accepted objective 不应下降；有噪声时允许 measured history 偏差；
- 测试不能读取 Ground Truth 后直接构造“最优”反馈结果；
- 算法比较应在同一组 seeds 上配对，报告分位数。

## 6. GUI 与并发测试

自动 smoke 使用 `QT_QPA_PLATFORM=offscreen`：

- MainWindow 可构造/关闭；
- Cancel 不抛未处理异常；
- stale version 结果不写 `latest_field`；
- CJK 字体加载属于人工/截图验收，因为 offscreen font database 依赖主机。

后续应补：拖动坐标 round-trip、worker cancellation latency、错误对话框、Save/Load 控件同步
和 coverage overlay。涉及 Qt 线程的测试必须等待明确 signal，禁止依赖固定 sleep 作为唯一
同步条件。

Foundation B 增加的自动 smoke 覆盖：Pending 编辑会禁用 Optimize 并要求 Apply；Generation
切换在 pending 时验证 confirm-discard / cancel-preserve；Pattern 元数据显示 Grid、Hardware
Phase、Allowed/Used States、Pattern Source、Actual phase-error 说明和循环图例；Ground Truth
tooltip 区分 Geometry Position Error 与 Feedback Measurement Noise，并说明 floor-anchored
wall 的刚体 XY 作用范围。continuous `search_levels` 与 finite-bit `2**phase_bits` 候选分别由
optimizer 定向测试锁定。

RIS Gain 场图 smoke 还必须锁定 robust `Gmax` 的对称 `[-Gmax, +Gmax]` normalization、负/零/正
diverging colors 和 numeric legend；切回 Power/SNR 时不得残留 RIS Gain legend，且两者原有
percentile normalization 保持不变。

## 7. 性能测试

绝对秒数只记录为参考，不作为跨机器硬门禁。每个 release 记录：CPU/OS/Python/NumPy、
Current/Advanced/Future 的 Fast 场图时间、最大内存、feedback measurement 数。性能退化
超过同机基线 30% 时调查。

硬门禁是：GUI 主线程不运行场图/feedback；可取消；无单次 `N_points×N_cells` 全量矩阵
导致不可控内存。P1 矩阵优化应增加内存上界和 cache invalidation 测试。

## 8. 缺陷优先级

| 级别 | 示例 | 发布处理 |
|---|---|---|
| P0 | 违反无源能量约束、相位不计算、随机伪造成功、数据损坏 | 阻断所有发布 |
| P1 | stale 结果覆盖、seed 不可复现、JSON 不兼容、GUI 卡死 | 阻断当前 release |
| P2 | 标签/tooltip 缺失、非关键布局、性能轻微退化 | 可带记录延期 |
| P3 | 文案或内部清理 | 进入 backlog |

## 9. 合并证据格式

完成报告至少记录：测试命令、通过数量、headless 关键指标、人工验收项目、未跑项目及原因。
“测试应该能过”不构成证据。requirements 中的 Implemented 条目必须能定位到证据。
