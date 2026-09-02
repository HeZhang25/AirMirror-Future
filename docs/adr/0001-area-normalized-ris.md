# ADR-0001：面积归一化的有限孔径 RIS

- 状态：Accepted
- 日期：2026-09-01
- 决策者：项目维护者
- 关联：AMF-RIS-001、005、006
- 后续解释：[ADR-0007](0007-equivalent-controllable-aperture-patches.md) 与
  [ADR-0008](0008-minimum-aperture-quadrature-validity-gate.md) 将“固定孔径细分收敛”严格限定为
  面积归一化下不产生无界 patch-count gain 和当前几何的稳定趋势；它不是独立 quadrature
  convergence 或 EM truth

## 背景

若每 cell 场幅只与 `sqrt(A_cell)` 成正比，固定实体孔径增加离散单元时 coherent sum 会随
`sqrt(N)` 增长，造成单元数量凭空创造能量。项目要求 Future 参数通过物理孔径和效率进入，
不能使用经验增益。

## 决定

每 cell 场幅与 `A_cell` 线性相关，总 RIS 信道是孔径积分的离散近似；前后方向采用余弦
功率图的幅度平方根。完整公式以 `physics_model.md` 为唯一声明点。

## 后果

- 固定孔径按面积归一化后细分不得产生无界增益；当前 control-grid 细分提供稳定趋势，但严格
  quadrature convergence 需要固定 control/pattern、只细化独立 integration grid；
- 增大实体孔径通常提高理想 focus；
- 模型适合系统级趋势，不声称严格近场/互耦精度；
- 未来校准需要具名物理参数和新 ADR，不添加固定 dB gain。

## 否决方案

- “开启 RIS +10 dB”：无路径/相位/能量依据；
- `sqrt(A_cell)` 的独立点散射直接求和：固定孔径不收敛；
- 为每代乘比例因子：混淆器件假设和传播模型。
