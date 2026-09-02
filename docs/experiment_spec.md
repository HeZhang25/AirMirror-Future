# 实验与结果数据规格

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation aperture QA plan |
| 当前实验 | Phase Resolution |

## 1. 可复现性规则

每次实验必须固定并记录：scene、frequency、geometry、generation、algorithm、Ground Truth
sigma、random seed、控制变量、评价指标、quadrature policy/version 和 runtime。对照组只能改变声明的控制变量；改变
孔径和 cell 数的实验不能被称为“纯相位位数对比”。

输出目录由 `--output` 指定，同名 CSV/PNG 可覆盖。正式研究结果应使用新的带日期/配置
名称目录，不能依赖覆盖后的 `results/phase_bits` 作为永久档案。

## 2. Phase Resolution v0.1

入口：

```text
python -m airmirror_future.experiments.phase_bits --output results/phase_bits
```

固定条件：Smart Space、Advanced 几何、`1.6×1.2 m`、`24×24`、效率 0.85、同一 TX/RX、
Controller Model、v0.1 RIS-only Physics Focus、seed 20260901。控制变量依次为
1、2、3、4、continuous。

每个点输出目标 RX power/SNR/RIS Gain，并用 Fast 80×60 场图计算 Coverage。PNG 横轴为
phase resolution，纵轴为 target RIS gain dB，用于观察收益递减。

## 3. CSV 最小字段

| 字段 | 单位/类型 | 说明 |
|---|---|---|
| `timestamp` | ISO-8601 UTC | 行生成时间 |
| `scenario` | str | 场景名 |
| `frequency_hz` | Hz | 载频 |
| `generation` | str | preset 标签 |
| `ris_count` | int | 场景 RIS 数 |
| `ris_width_m`,`ris_height_m` | m | 实体孔径 |
| `nx`,`ny` | int | 等效可控孔径 patch 网格；不表示真实 meta-atom 布局 |
| `phase_bits` | int/continuous | 控制变量 |
| `efficiency` | ratio | `[0,1]` |
| `phase_error_sigma_rad` | rad | Ground Truth 参数 |
| `algorithm` | str | 算法名 |
| `rx_x_m`,`rx_y_m`,`rx_z_m` | m | 目标位置 |
| `received_power_dbm` | dBm | 目标结果 |
| `ris_gain_db` | dB | 相对同一 realization baseline |
| `snr_db` | dB | 目标 SNR |
| `coverage_percent` | % | 带记录阈值的场图 coverage |
| `coverage_threshold_db` | dB | 场景 threshold |
| `iterations` | int | Focus 固定为 1 |
| `runtime_s` | s | 该行目标+场图计算时间 |
| `random_seed` | int | 重放 seed |

新增实验可增加列，不得删除这些共同追踪字段；不适用的指标应为空并在实验文档解释，
不能填零冒充测量值。

## 4. 统计比较规则

- 无随机误差的参数 sweep 可用单 seed，但仍记录 seed；
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

## 6. Foundation FND-QA-AP（Planned，非当前可运行实验）

FND-QA-AP 是 Foundation final exit evidence，不是 P1C 完整 Aperture experiment，也不是当前
已实现命令。正式入口、schema version 和输出目录在 Work Item 进入 Ready 时冻结；在此之前
不得在 README 提供可运行命令或生成占位结果。

唯一控制变量是每个 fixed control patch 内的 quadrature rule/order。一个 refinement series
必须固定 aperture、`nx/ny`、commanded pattern hash、frequency、geometry、Profile、Ground
Truth realization 和 baseline。禁止随 order 重新生成 Focus。

最小输出除第 3 节可复用字段外，还必须记录：

- `qa_schema_version`、`geometry_case`、实际 TX/RX/RIS 坐标；
- `profile_id/version`、`model_version`、`quadrature_policy_id/version`；
- `pattern_class/hash`、预登记 random seed；
- `quadrature_rule/order_x/order_y`；
- `h_RIS` real/imag、absolute/robust normalized error、magnitude/phase error；
- RIS-only/total power、RIS Gain 及 ill-conditioned/not-applicable reason；
- reference label、successive difference、runtime 和 peak memory。

正式结果写入新的版本化目录并默认 no-overwrite。reference 只能标为 internal refined numerical
reference，不得标为 Ground Truth/EM truth。一次隔离审计中的 `0.430–0.848 dB` 只用于说明
工作项必要性，不得回填为正式 CSV 或 PASS evidence。
