# 架构决策登记册

| 属性 | 值 |
|---|---|
| 文档状态 | Normative index |
| 基线版本 | v0.1 + Foundation ADR-0006..0012 |

ADR 一经 Accepted 不直接改写结论。若决定变化，创建新 ADR 标记 supersedes，被替代 ADR
保留历史。讨论或聊天不能替代 ADR。

| ADR | 决定 | 状态 | 影响范围 |
|---|---|---|---|
| [0001](adr/0001-area-normalized-ris.md) | RIS 使用面积线性、孔径归一化散射 | Accepted | physics、tests、experiments |
| [0002](adr/0002-layered-python-architecture.md) | Python 分层、dataclass 公共模型和 src layout | Accepted | 全工程 |
| [0003](adr/0003-controller-ground-truth-boundary.md) | Controller/Ground Truth 通过 MeasurementOracle 隔离 | Accepted | simulation、optimization、experiments |
| [0004](adr/0004-versioned-background-work.md) | GUI 耗时任务使用可取消、版本化 worker | Accepted | GUI、performance |
| [0005](adr/0005-scene-json-v1.md) | Scene 使用显式版本化 JSON v1，不保存 pattern | Accepted | data、CLI、GUI |
| [0006](adr/0006-coherent-target-focus-objective.md) | 区分 RIS-only 与 nominal Coherent Target Focus | Accepted | ris、optimization、tests |
| [0007](adr/0007-equivalent-controllable-aperture-patches.md) | `nx/ny` 表示系统级等效可控孔径 patch | Accepted | core、ris、GUI、tests |
| [0008](adr/0008-minimum-aperture-quadrature-validity-gate.md) | A2 保持 Verified；在 Foundation final exit/P1A 前完成最小独立求积有效性门禁 | Accepted | Foundation、ris、QA、cache sequencing、experiments |
| [0009](adr/0009-environment-modifier-propagation-profile.md) | 历史 Profile 决定；因错误合并 `Gamma_wall` 所有权被 ADR-0012 完整取代 | Superseded | simulation、physics、scenarios、provenance、future cache |
| [0010](adr/0010-narrowband-center-frequency-flat-channel.md) | `frequency_hz` 是中心频率，`h(fc)` 在 `bandwidth_hz` 内按平坦窄带处理 | Accepted | physics、noise、GUI labels、experiments |
| [0011](adr/0011-controller-coefficient-focus-consistency.md) | Focus 与 Controller simulator 共享最终 control-level coefficient 定义 | Accepted | ris、simulation、optimization、quadrature QA、future cache |
| [0012](adr/0012-wall-reflection-coefficient-ownership.md) | Profile 仅拥有环境 modifier；`Gamma_wall` 由 Wall/Reflection Model 唯一拥有并与反射两段 modifier 分离 | Accepted | reflection、simulation、Profile、Ground Truth、provenance、future cache |

必须新建 ADR 的变化包括：物理公式/相位符号/能量标度、公共层依赖反转、schema major、
Ground Truth 隔离改变、优化 objective 语义、active RIS、宽带/频率模型、多 RIS ownership 和动态时间
模型。普通 bugfix、内部重命名、等价性能优化不需要 ADR，但仍需测试和文档同步。
