# 术语、符号与状态词

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation physics/algorithm contract terminology |

## 产品术语

| 术语 | 统一含义 | 禁止混用 |
|---|---|---|
| AirMirror Future | 本项目和应用名称 | 不缩写成另一个产品名 |
| RIS | Reconfigurable Intelligent Surface，可重构智能表面 | 不等同“固定反射板” |
| Smart Space | v0.1 唯一可运行场景 | 不称 Smart Home，以免缩小范围 |
| RIS-only Phase-Conjugate Focus | 根据名义几何使 RIS patch 在目标点互相同相；兼容名称 Physics Focus | 不称总信道或全局最优 |
| Coherent Target Focus | 以 Controller Model 的 nominal baseline 为参考，在公共 offset 族内最大化单目标总接收功率 | 不称 Ground Truth 或任意逐 patch 全局最优 |
| Feedback Greedy | 仅通过 measurement oracle 的 tile coordinate descent | 不读取 Ground Truth 参数 |
| Physics-Guided Feedback | v0.1 RIS-only Focus 初始化 + feedback refinement | 不简称“AI 优化” |
| Controller Model | 控制器相信的名义世界 | 不包含隐藏真实误差 |
| Ground Truth Model | 仿真中的真实世界及可复现误差 | 不等同实测硬件 |
| Field Map | 固定 `z_eval` 高度的规则网格结果 | 不称完整 3D 场 |
| RIS Gain | `P_with_RIS_dBm - P_without_RIS_dBm` | 不是器件固定增益 |
| Coverage | 网格中 `SNR ≥ threshold` 的比例 | 阈值必须随场景记录 |
| Dead Zone | `100% - Coverage` | 不表示绝对无信号 |
| Future Scenario Assumption | 超出当前代表性能力的显式假设 | 不表示当前已部署能力 |
| System-level electromagnetic approximation | 本系统的模型定位 | 不称 full-wave solver |
| Equivalent Controllable Aperture Patch | RIS 孔径上的系统级独立命令/中心采样区域 | 不称真实 meta-atom 或天线阵元 |
| Effective Pitch | 实体宽高除以对应 equivalent patch 数所得的派生尺寸/中心间距 | 不当作制造间距或 `lambda/2` 合规结论 |
| Physical Meta-atom | 需要器件布局、材料、互耦等模型支持的真实结构 | 当前模型尚未实现 |
| Control Grid | `nx×ny` equivalent patches 及其 commanded phase 自由度 | 不与 quadrature grid 或 physical layout 混用 |
| Quadrature Grid | 每个 control patch 内为数值积分生成的采样点与权重 | 当前 production 模型仍为每 patch `1×1` midpoint；不增加命令自由度 |
| Quadrature Policy | 求积规则、阶数、坐标/权重约定和版本的稳定身份 | 不只写“high quality”或省略版本 |
| Control-level RIS Coefficient (`a_n`) | 在指定 Controller/GT、Profile 与 quadrature policy 下，一个 control patch 对单位反射状态的复响应 | 不与 commanded phase、measurement 或缓存对象混用 |
| Reflection State (`Gamma_n`) | patch 的复反射状态；命令态含 nominal efficiency/phase，真实态可含效率和相位误差 | 不把 Ground Truth 状态反馈给 nominal Focus |
| PropagationProfile | Foundation 中只提供自由空间载波之外的 environment-only complex modifier | 不返回重复的距离/传播相位，也不等同未来 PathEnsemble |
| PathEnsemble | 未来可包含多路径 delay/angle/Doppler/statistics 的独立抽象 | 当前未实现，不用 Profile multiplier 冒充 |
| Center-frequency Flat-channel Shannon Upper Bound | 以 `h(fc)` 在带宽内平坦为假设的 `B log2(1+SNR)` | 不称 OFDM/频率选择性容量或真实吞吐量 |
| Floor-anchored Wall | v1 目标墙模型：端点 z=0、占据 `[0,height]`、误差只做刚体 XY 平移 | 不称悬空/倾斜墙 |
| Internal Refined Numerical Reference | 同一系统级标量模型内经 successive refinement 和交叉规则支持的内部参考 | 不称 Ground Truth、EM truth、full-wave 或 measurement |
| Spatially Resolved Blockage | 对 aperture subpoint/region 分别判定遮挡的模型 | 不等同当前 RIS center scalar attenuation，也不由 quadrature refinement 自动获得 |

## 坐标与单位

| 符号/字段 | 含义 | 内部单位 |
|---|---|---|
| `x, y` | 地面平面坐标 | m |
| `z` | 离地高度 | m |
| `position` | 实体中心三维坐标 | m |
| `yaw_rad` | RIS 正面法向相对 +x 的方位角 | rad |
| `z_eval_m` | 场图评价高度 | m |
| `fc` / `frequency_hz` | 中心频率；当前只在此频点评价复信道 | Hz |
| `B` / `bandwidth_hz` | 等效占用/接收噪声带宽；当前不生成频率轴 | Hz |
| `Pt`, `Pr` | 发射/接收功率 | W；UI 可显示 dBm |
| `Gt`, `Gr` | 天线功率增益 | linear ratio |
| `NF` | 接收机噪声系数 | dB |
| `lambda` | 自由空间波长 | m |
| `k` | 波数 | rad/m |
| `h` | 无量纲窄带复信道 | complex |
| `phi` | RIS 相位命令 | rad，规范化到 `[0,2π)` |
| `eta` | 单元反射功率效率 | `[0,1]` |
| `A_cell` | 等效可控孔径 patch 面积；旧代码名为兼容保留 | m² |

角度 API 默认弧度；仅 UI 明确带 `°` 的输入使用度并在边界转换。dB 衰减作用在功率比，
进入复场前使用 `10^(-A_dB/20)` 转为幅度比。

## 相位约定

- 时间谐波和传播约定统一使用 `exp(-j*k*L)`；
- RIS 命令系数使用 `exp(+j*phi)`；
- 因此 RIS-only Phase-Conjugate Focus 为 `phi=kL mod 2π`；
- Coherent Target Focus 在量化前再加入一个公共 offset；连续相位使 RIS 合成场与 nominal
  baseline 同相，有限 bit 在公共 offset 可达候选中比较 nominal target power；
- 不允许在单个模块中反转符号后依靠测试数据“调回来”。

## 状态词

| 状态 | 准确定义 |
|---|---|
| Proposed | 只有问题和候选方案，不允许作为开发承诺 |
| Planned | 需求已定义但未通过 Definition of Ready |
| Ready | 接口、边界、测试和依赖已明确，可进入实现 |
| In Progress | 正在实现，仍不得在 README 宣称可用 |
| Implemented | 代码存在且对应自动测试通过 |
| Verified | 实现、自动测试、人工验收和文档均通过 DoD |
| Deferred | 明确移出当前 release，保留编号和原因 |
| Rejected | 经 ADR 否决，不再作为默认路线 |

`DEVELOPMENT_STATUS.md` 使用上述状态，不能用“基本完成”“差不多”等不可验收描述。
