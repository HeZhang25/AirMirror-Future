# 模型限制、影响与升级触发条件

| 属性 | 值 |
|---|---|
| 文档状态 | Normative boundary |
| 基线版本 | v0.1 + Foundation physics/algorithm closure boundaries |

以下限制定义模型适用域，不是通过 UI 平滑或调大 Future 参数可以修复的问题。

| 未包含能力 | 对结果的影响 | 当前安全解释 | 升级触发条件 |
|---|---|---|---|
| 完整 3D 全波 | 不解析细尺度电流/边缘/腔体模式 | 系统级趋势 | 需器件/近场精度时接全波或校准 |
| 材料色散 | 墙系数不随频率/角度自动变化 | 用户配置复系数 | 宽带/材料库需求 |
| 天线全波方向图 | TX/RX 仅线性标量 gain | 近似各向/固定 gain | 方向/极化研究 |
| 衍射 | 几何阴影可能过深 | 只计衰减和反射 | 城市拐角/低频 NLoS 定量需求 |
| 高阶多反射 | 不包含两次以上墙反射 | 一次镜面路径 | 工厂/城市多径精度需求 |
| RIS mutual coupling | 等效 patch 独立孔径采样 | 大尺度趋势 | 高密度/器件设计 |
| patch 内场积分 | 当前 production 每个等效 patch 只取 `1×1` midpoint，且假定满填充 | 系统级面积归一化近似；A2 semantic Verified，不代表精度 Verified | FND-QA-AP 在 final exit/P1A 前冻结最小 policy；P1C 扩大研究 |
| 控制/求积网格分离 | `nx/ny` 同时决定控制自由度和中心采样 | 现有细分测试只解释为不发散/稳定趋势 | FND-QA-AP 内部拆分；生产迁移需独立 Work Item/ADR |
| 复杂极化 | 不跟踪 Jones/vector field | 标量复信道 | 偏振 RIS/天线研究 |
| PIN diode 非线性 | 不建幅相耦合和功率依赖 | eta+phase error | 硬件校准/高功率 |
| 严格近场 | 面积模型不保证近孔径精度 | 避免 cell 零距离 | 超大孔径近距离用户 |
| 宽带/OFDM | 只在中心频率计算 `h(fc)`，并假定在 B 内平坦 | 平坦信道 Shannon 上界；不是 OFDM/真实吞吐 | 频率选择性、delay spread、波束偏斜或 `Gamma(f)` 需求 |
| MIMO/protocol | 无流、调制、调度、HARQ | Shannon 上界 | 真实系统吞吐/链路层 |
| active RIS | 无外部功率、gain、NF、budget | 明确拒绝 active | 提出独立 active model ADR |
| STAR/time modulation | 无透射/时间谐波 | 不提供入口 | 明确波形与能量模型 |
| 多 RIS 连跳 | 仅每块单跳 TX-RIS-RX | 可相加多个单跳贡献 | Factory 双跳研究 |
| 动态控制时延 | update_rate 目前是元数据 | 静态重配置 | XR 时间步和 latency |
| Profile v1 路径集合 | Foundation Profile 只计划提供 environment modifier，不生成 delay/angle/Doppler 多径集合 | 默认确定性路径编排 | fading/wideband/dynamic multipath 需要独立 PathEnsemble ADR |
| Wall z/vertical placement | v1 只支持地面锚定竖直墙，不支持悬空/倾斜墙或墙底高度误差 | endpoint z 在 `1e-9 m` 容差内为 0，占据 `[0,height]`；Ground Truth 只消费刚体 XY delta | 悬空/倾斜/楼层墙需求触发 schema v2 与独立 ADR |
| Focus/coefficient future migration | 当前 1×1 中中心路径相位等价；未来复杂 Profile/多点求积可能破坏等价 | A1 objective 已验证，不代表未来 policy 自动一致 | FND-QA-CC；需要时先做独立 production migration |

## 数值边界

- 极小功率在 dBm 边界 floor 到 `1e-30 W`；这限制显示下界，不改变复场计算；
- 完全阻挡以 300 dB 表示数值近零，不是数学绝对零；
- 评价点过近 RIS cell 会拒绝，而不是给出发散结果；
- 场图有限网格可能漏掉非常窄的干涉峰/谷；改变质量会改变 coverage 采样误差；
- A2 的 `pitch/wavelength` 只提供模型透明度，不是 `lambda/2` 合规或栅瓣判定；
- A2 不输出 patch 内相位跨度、pass/fail 或 warning severity；这些需要先拆分 control 与
  quadrature grid 并建立有来源的适用域验证；
- 一次 `16×16` 或更细结果不是 electromagnetic truth；只有 successive refinement 和独立规则
  支持后，才可在声明适用域内称 internal refined numerical reference；
- 当前 RIS blockage 使用 TX→RIS center、RIS center→RX 的统一衰减；增加 quadrature samples
  不会自动得到 partial-aperture/spatially resolved blockage；
- FND-QA-AP 完成前，三代精确 dBm 差值只能标为 current scalar center-point model 输出；允许
  展示系统级趋势，不应宣称精确到四位小数或推广到所有场图位置；
- Future 64×48、High 200×160 可能计算较慢，后台运行不等于模型更精确；
- `bandwidth_hz` 不会让引擎计算多个频点；当前 100 MHz 只进入 noise/flat-channel capacity，
  软件没有自动证明该带宽对任意几何都满足窄带条件；
- Field Map 对所有网格点使用同一 fixed RIS pattern，不是逐像素最优聚焦包络；
- PropagationProfile 已在 C1 Implemented（待独立审查），最小 provenance 仍为 C2 Ready、未实现；
  `channel_frequency_model_id` 与 coefficient consistency 仍是后续 Planned contract，不得在现有
  结果中声称已经实现。Profile 只拥有环境 modifier；当前及
  目标模型中的墙面 `Gamma_wall` 均属于 Wall/Reflection Model，不得在 C1 中重复迁入 Profile。
- C1 支持 environment-only complex modifier，但只签入默认 Profile 的 v0.1 数值兼容；自定义
  复相位规则与最终 Focus/coefficient consistency 仍须 FND-QA-CC/必要 migration，不能凭注入
  Protocol 就声称已通过最终算法/物理门禁。
- C1 的输入收紧包括 duplicate wall ID 和 Wall/Obstacle non-empty string ID 数据边界 closure。
  仓库受支持 Scene/内建场景/tests/可达 Git 历史无合法空 ID 依赖，故保持 schema v1；外部旧文件
  的空 ID 仍须显式赋名，不自动改名、过滤 blocker 或放宽 Profile contract。审计不覆盖未知外部
  数据，详见 [C Work Item](work_items/foundation_0_1_1_c.md#c1-environment-id-compatibility-closure)。
- C2 schema Ready 不使现有 `results/phase_bits` 获得 Profile/Reflection/channel/quadrature/
  coefficient identity；这些文件仍是只读 `legacy_v0_1_unversioned`，不得回填。C2 初始新结果也
  必须对未签署的 FND-PHY-NB/FND-QA-AP/FND-QA-CC 保持 partial/pending。

## 使用限制

结果可用于教学、系统架构对比、参数趋势和算法原型，不应直接用于法规合规、安全许可、
健康暴露评估、真实网络 SLA 或硬件采购保证。需要定量工程结论时，应与测量或全波模型
校准，并记录 model version 和校准参数。

## 报告要求

引用结果时至少报告：频率、TX power/gains、带宽/NF、场景几何、RIS 实体尺寸/等效 patch
网格/phase/eta、算法、Ground Truth sigma、seed、coverage threshold、channel frequency model、
Profile、coefficient/quadrature identity（若可用）和本限制文档版本；不得把等效 patch 数量或
effective pitch 报告成真实 meta-atom 布局。若
结果仍使用当前 1×1 policy，应明确标注 `current scalar center-point model`。
