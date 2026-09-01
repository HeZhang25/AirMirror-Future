# 术语、符号与状态词

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 |

## 产品术语

| 术语 | 统一含义 | 禁止混用 |
|---|---|---|
| AirMirror Future | 本项目和应用名称 | 不缩写成另一个产品名 |
| RIS | Reconfigurable Intelligent Surface，可重构智能表面 | 不等同“固定反射板” |
| Smart Space | v0.1 唯一可运行场景 | 不称 Smart Home，以免缩小范围 |
| Physics Focus | 根据名义几何计算相位共轭 pattern | 不称全局最优 |
| Feedback Greedy | 仅通过 measurement oracle 的 tile coordinate descent | 不读取 Ground Truth 参数 |
| Physics-Guided Feedback | Physics Focus 初始化 + feedback refinement | 不简称“AI 优化” |
| Controller Model | 控制器相信的名义世界 | 不包含隐藏真实误差 |
| Ground Truth Model | 仿真中的真实世界及可复现误差 | 不等同实测硬件 |
| Field Map | 固定 `z_eval` 高度的规则网格结果 | 不称完整 3D 场 |
| RIS Gain | `P_with_RIS_dBm - P_without_RIS_dBm` | 不是器件固定增益 |
| Coverage | 网格中 `SNR ≥ threshold` 的比例 | 阈值必须随场景记录 |
| Dead Zone | `100% - Coverage` | 不表示绝对无信号 |
| Future Scenario Assumption | 超出当前代表性能力的显式假设 | 不表示当前已部署能力 |
| System-level electromagnetic approximation | 本系统的模型定位 | 不称 full-wave solver |

## 坐标与单位

| 符号/字段 | 含义 | 内部单位 |
|---|---|---|
| `x, y` | 地面平面坐标 | m |
| `z` | 离地高度 | m |
| `position` | 实体中心三维坐标 | m |
| `yaw_rad` | RIS 正面法向相对 +x 的方位角 | rad |
| `z_eval_m` | 场图评价高度 | m |
| `f` / `frequency_hz` | 载波频率 | Hz |
| `B` / `bandwidth_hz` | 接收带宽 | Hz |
| `Pt`, `Pr` | 发射/接收功率 | W；UI 可显示 dBm |
| `Gt`, `Gr` | 天线功率增益 | linear ratio |
| `NF` | 接收机噪声系数 | dB |
| `lambda` | 自由空间波长 | m |
| `k` | 波数 | rad/m |
| `h` | 无量纲窄带复信道 | complex |
| `phi` | RIS 相位命令 | rad，规范化到 `[0,2π)` |
| `eta` | 单元反射功率效率 | `[0,1]` |
| `A_cell` | 单元物理面积 | m² |

角度 API 默认弧度；仅 UI 明确带 `°` 的输入使用度并在边界转换。dB 衰减作用在功率比，
进入复场前使用 `10^(-A_dB/20)` 转为幅度比。

## 相位约定

- 时间谐波和传播约定统一使用 `exp(-j*k*L)`；
- RIS 命令系数使用 `exp(+j*phi)`；
- 因此 Physics Focus 为 `phi=kL mod 2π`；
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

