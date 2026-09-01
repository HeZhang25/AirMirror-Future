# 实验与结果数据规格

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 |
| 当前实验 | Phase Resolution |

## 1. 可复现性规则

每次实验必须固定并记录：scene、frequency、geometry、generation、algorithm、Ground Truth
sigma、random seed、控制变量、评价指标和 runtime。对照组只能改变声明的控制变量；改变
孔径和 cell 数的实验不能被称为“纯相位位数对比”。

输出目录由 `--output` 指定，同名 CSV/PNG 可覆盖。正式研究结果应使用新的带日期/配置
名称目录，不能依赖覆盖后的 `results/phase_bits` 作为永久档案。

## 2. Phase Resolution v0.1

入口：

```text
python -m airmirror_future.experiments.phase_bits --output results/phase_bits
```

固定条件：Smart Space、Advanced 几何、`1.6×1.2 m`、`24×24`、效率 0.85、同一 TX/RX、
Controller Model、Physics Focus、seed 20260901。控制变量依次为 1、2、3、4、continuous。

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
| `nx`,`ny` | int | 网格 |
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

