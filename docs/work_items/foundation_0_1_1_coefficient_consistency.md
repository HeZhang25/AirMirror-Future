# Work Item：Foundation / Controller Coefficient Consistency Gate

- 层级：L4 Task（cross-cutting QA/architecture closure）
- Task ID：FND-QA-CC
- Requirement IDs：AMF-RIS-012
- 状态：Planned
- 父项：Foundation 0.1.1 Final Exit Gate
- 依赖：ADR-0011 Accepted；C1 Profile；FND-QA-AP signed production policy；FND-PHY-NB；如需要
  则先完成独立 production quadrature migration
- 不属于：重开 A1/A2、缓存实现、Ground Truth-aware Focus、幅相耦合、MIMO/OFDM

## 目标与用户结果

证明 model-based Focus 优化的正是 Controller simulator 最终用于传播的 control-level 复系数，
并冻结供 P1A 使用的 coefficient identity。完成后，改变 Profile 或 quadrature 不会出现
“simulator 用一套系数、Focus 用另一套中心路径相位”的隐性分叉。

## 状态与授权边界

- 当前为 Planned；ADR 和本文不表示 coefficient builder、迁移或测试已实现；
- A1/A2 保持 Verified，AMF-RIS-008/009 和 Foundation 状态不因规划提升；
- 本工作项不修改 production behavior。若 FND-QA-AP 决定改变 production quadrature，必须先由
  另一个经批准的 implementation Work Item 完成迁移；
- FND-QA-CC 负责验证最终 production 状态，不负责偷偷选择或迁移 policy；
- 任一一致性 case 失败时 Foundation 保持 In Progress，P1A 门禁关闭。

## In / Out

包含：

- 冻结 Controller `a_n^C`、`Gamma_cmd`、Ground Truth `a_n^GT/Gamma_actual` 的所有权；
- RIS-only/Coherent Focus 与 simulation coefficient 的公共来源或等价证明；
- Profile/quadrature/geometry/gain/direction/blockage 的 identity 依赖审计；
- 1×1 保留路径和条件性多点 production 路径的测试策略；
- Ground Truth 不泄漏和 public phase-array API 兼容回归。

不包含：

- P1A cache、matrix storage、chunking 或增量 Greedy；
- 重新定义 ADR-0006 objective、量化候选或 tie-break；
- 把 internal coefficient 暴露成未经评审的公共 API；
- 用 `a^GT` 生成 Focus 或把 measurement noise 放入 coefficient；
- 为通过测试而改变 QAP 已签署的 production policy。

## 接口与数据

权威内部关系见 ADR-0011：

```text
h_RIS^C  = sum_n a_n^C  * Gamma_cmd,n
h_RIS^GT = sum_n a_n^GT * Gamma_actual,n
```

- public `ris_patterns` 继续保存 commanded phase，shape `[nx*ny]`；
- A3 validator 先验证 `phi_cmd`，再构造 `Gamma_cmd`；
- coefficient builder 的具体名称/模块可在 Ready review 冻结，但 Focus、engine、QA runner 与未来
  P1A 必须共享或证明等价；
- `coefficient_model_identity` 必须由 canonical、跨进程稳定字段组成，不能依赖对象地址或
  Python randomized hash；
- pattern hash、measurement RNG 和 link-metric-only `B/NF` 不得错误混入几何 coefficient identity。

## 物理/算法约束

- 面积、天线 gain、direction factor、efficiency 各出现一次；
- ADR-0009 environment modifier 不重复距离扩散或传播相位；
- continuous RIS-only 使非退化 `a_n^C*Gamma_cmd,n` 同相；
- continuous Coherent 使其合成与 `h_baseline^C` 同相；
- finite-bit 保留 ADR-0006 公共 offset 搜索和 A3 合法 hardware state；
- Ground Truth 位置/环境/效率/相位误差可以改变真实结果，但不能改变 nominal Focus 输入。

## 条件执行路径

```text
FND-QA-AP signed policy
  -> policy == 1x1 midpoint
       -> prove center-path and a_n^C equivalence
  -> policy requires >1x1/complex modifier
       -> create and complete separate production-migration Work Item
       -> simulator and Focus share integrated a_n^C
  -> run FND-QA-CC
  -> Foundation final review
```

## Tasks

| Task | 状态 | 预计 | 输出 |
|---|---|---:|---|
| `FND-QA-CC-01` 冻结 coefficient builder/identity dependency table | Planned | 0.5–1 天 | reviewed internal contract |
| `FND-QA-CC-02` 审计 simulator/Focus/QAP coefficient call graph | Planned | 0.5 天 | no-duplicate-formula report |
| `FND-QA-CC-03` 实现或补齐一致性测试 | Planned | 1–2 天 | FND-T21/T22 |
| `FND-QA-CC-04` 验证 Controller/GT 隔离与 API 兼容 | Planned | 0.5–1 天 | boundary regressions |
| `FND-QA-CC-05` 完整回归、三代 headless、人工签署 | Planned | 0.5–1 天 | closure evidence |

## 验收证据

- FND-T21：对代表性几何，RIS-only pattern 与同一 `a^C` 的解析相位关系成立；若保留 1×1，另证
  明与历史中心路径 pattern 等价；
- FND-T22：Coherent pattern 的 objective evaluation 与最终 Controller simulation 使用完全相同
  coefficient，并保留 continuous/finite/degenerate/tie-break 契约；
- Controller/GT boundary test：相同 Controller 输入在改变隐藏 Ground Truth realization 后 pattern
  不变，oracle measurement 可变；
- identity test：每个 coefficient 影响项变化会失效 identity，pattern/B/NF/measurement noise 的
  非影响变化不会错误失效；
- 完整 pytest、三代 fast headless、Foundation provenance 和人工 call-graph review 通过。

## 风险与回退

| 风险 | 检测 | 安全回退 |
|---|---|---|
| 多点 simulator 与中心 Focus 相位分叉 | FND-T21/T22 | 阻断 Foundation；先做独立 migration |
| 为共享代码引入反向依赖 | import/call-graph review | 将纯 coefficient builder 放低层，不让 ris 依赖 simulation |
| efficiency/area 重复计入 | analytic single-patch test | 保持旧数值，修正因子所有权后再验收 |
| coefficient identity 漏项 | mutation matrix | 补 canonical dependency，不启用 cache |
| Ground Truth 泄漏 | model substitution tests | 恢复 Controller-only path，拒绝签署 |

## 文档影响

- [x] ADR-0011、requirements、Foundation plan、architecture、physics、optimization、API/data；
- [x] test/experiment/DoD/roadmap/status 与 FND-QA-AP 关系；
- [ ] code/tests：Planned，尚未实现；
- [ ] GUI/scene/results/cache：本工作项不修改。
