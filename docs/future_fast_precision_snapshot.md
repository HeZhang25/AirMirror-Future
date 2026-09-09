# Future 高速 1×1 / M8 精度对照快照

本记录只服务 D/A 接口消费，不构成验收阈值、研究报告或 Foundation 状态变更。

测试分支：`codex/future-fast-dual-ris`；高速实现提交：`2f96f7f`；双 RIS 实现提交：`93c129a`。
每个 generation 使用同一 Scene、同一接收点和同一 commanded phase；分别由
`SimulationEngine(coefficient_model=FAST_1X1_RIS_COEFFICIENT_MODEL)` 与默认 M8 Engine 评价。
场图为 `6×4` 低分辨率代表性计算，未运行 Future 大场图。

| Generation | `|Δh_total|` | `|Δh_RIS|` | 聚焦功率 ΔdB (1×1−M8) | SNR ΔdB | 场图功率最大 ΔdB | 场图功率 RMSE dB | 场图 RIS-gain 最大 ΔdB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current | `6.3944399189e-05` | `6.3944399189e-05` | `+0.6381825453` | `+0.6381825453` | `2.7216329807` | `1.0290376435` | `2.7216329807` |
| Advanced | `1.5891234102e-04` | `1.5891234102e-04` | `+0.4036609475` | `+0.4036609475` | `4.2344631516` | `1.0185092664` | `4.2344631516` |

这些数值仅描述当前实现和该场景/命令下的实际差异；没有预设精度保证。1×1 与 M8 的物理
尺寸、控制 patch 数、传播距离/相位、方向因子、Profile 和 Gamma 所有权保持一致，差异仅来自
每个 control patch 的求积采样模型。

