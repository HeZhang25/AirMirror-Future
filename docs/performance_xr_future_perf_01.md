# XR-FUTURE-PERF-01：单 Future 精确 M8 复用证据

状态：非发布性能实验；不是正式 P1A，不提升 Foundation、FND-QA-CC 或版本状态。

## 仓库与交接状态

- 实际远端 `origin/main`：`a7271648d3d6d98d6af953eadcc4784b7776222f`。
- C 的共享 M8/Focus 生产实现：`11f65a3b0762d738c8880901e00244ace3dd2a88`。
- 本分支依赖的 C 最新候选：`08c2d28fd0e749643ff29f269259980369d30f0c`。
- 测量实现 SHA：`27c1f8a8fb5e21daf95f4c75b99f824c8991a2d3`。
- 分支：`task/xr-future-perf-01`。
- PERF-PREP-01 保持在独立 worktree / `617cd602c5e7f791d0f8801145a29db471e727bb`；
  其 JSON、SHA 和工作区未修改、未重跑。

FND-QA-CC 阶段一 Ready 已由 D 在 `73fc59fa37ccc0668d3da9db2c46bae482b41d92`
给出 PASS；但 C 的阶段二生产实现文档仍明确标记为等待非作者 D 独立代码/证据复核与维护者
closure。本性能任务由 D 编写代码，因此 D 不再适合作为本分支或与本分支耦合后的独立作者外
审查人。阶段二剩余独立审查应交 B 或其他未参与 `11f65a3` / `27c1f8a` 实现的人，且不得由本
性能结果代签 FND-QA-CC closure。

## 实现

本轮没有重写 C 已完成的 Focus 内积。实际复用：

- `ris_control_coefficients()`：单点 production M8 control-level 复系数；
- `controller_focus_terms()`：Controller-only `a^C` 与 No-RIS baseline；
- C 已冻结的效率/相位 Gamma 所有权、Profile modifier、production quadrature identity 和
  coefficient identity。

新增最小 headless 接口：

- `prepare_controller_link()`：固定 Scene/Tx/Rx/RIS 一次构建 `a^C`，多合法 Pattern 只执行
  `dot(a, Gamma)`；
- `ris_control_coefficient_matrix()`：同一 C M8 contribution/reduction 的多接收点、接收点×
  aperture sample 双分块版本；
- `prepare_controller_field()`：固定网格构建 Controller-only `A` 和 No-RIS baseline，随后以
  `A @ Gamma` 热求值多个 Pattern。

接口显式拒绝 `GroundTruthModel`，不接触 MeasurementOracle。系数身份继续由 C 的
`controller_ris_coefficient_identity()` 给出：Scene 中影响路径 modifier 的环境、Tx/Rx/RIS
几何、频率、Profile、方向模型和 M8 policy 变化产生不同身份；Pattern、phase bits、效率、Pt、
B/NF、coverage 和 RNG 不进入系数身份。Pattern 与效率只进入 Gamma。没有全局隐藏缓存；prepared
对象具有明确生命周期和保存的 coefficient identity，物理输入改变时调用者必须使用新身份重新
prepare，不允许把旧矩阵当成新场景结果。

Future `48×36×3072×complex128` 系数矩阵为 84,934,656 bytes（81 MiB）。默认系数预算
128 MiB；超过预算在任何 M8 计算前抛 `MemoryError`。中间广播数组受
`max_point_sample_pairs=262144` 限制，未一次性分配所有接收点×196,608 aperture samples。

## 固定输入与命令

场景：`create_smart_space_scene("Future")`，Scene v1，10×8×3 m，5 GHz / 100 MHz，
`IndoorDeterministicProfile/1`，`ControllerModel`，seed `20260901`。Future RIS 保持 3×2 m、
64×48 controls、continuous phase、reflection efficiency 0.95、production
`midpoint_8x8_per_control_patch/1`；没有缩小 RIS、减少 controls 或修改公式。

Windows / Python 3.11.4 / NumPy 2.4.6；OMP、OpenBLAS、MKL、NumExpr 均固定为 1 线程。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='src'
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
D:\Projects\AirMirror-Future\.venv\Scripts\python.exe -B `
  tools/xr_future_perf_01.py `
  --output results/performance/xr_future_perf_01_20260908_27c1f8a_windows_single_thread `
  --grids 8x6,16x12

D:\Projects\AirMirror-Future\.venv\Scripts\python.exe -B `
  tools/xr_future_perf_01.py `
  --output results/performance/xr_future_perf_01_20260908_27c1f8a_48x36_windows_single_thread `
  --grids 48x36
```

每个 reference/prepared case 在独立子进程运行，峰值内存为 Windows
`PeakWorkingSetSize`。热 Pattern 取同一 prepared 对象连续 5 次的中位数。reference 与
prepared 使用相同 Pattern hash；单点覆盖 zero、scene-aware RIS-only、coherent 和固定 seed
random 四种合法连续相位命令。

## 结果

| case | 原始参考 | prepared 冷构建 | 热 Pattern | reference 峰值 | prepared 峰值 | 最大差异 |
|---|---:|---:|---:|---:|---:|---:|
| 单点 4 Pattern | 2.2926 s | 0.3557 s | 0.0000562 s / Pattern | 118.80 MiB | 115.70 MiB | complex channel 0 |
| 8×6 coherent 场图 | 1.8470 s | 1.2824 s | 0.0000908 s | 115.04 MiB | 116.45 MiB | 4.26e-14 dB |
| 16×12 coherent 场图 | 7.0290 s | 4.6097 s | 0.0002756 s | 115.25 MiB | 125.46 MiB | 9.95e-14 dB |
| 48×36 coherent 场图 | 67.9261 s | 43.2158 s | 0.0050979 s | 115.36 MiB | 197.26 MiB | 1.99e-13 dB |

声明容差：complex `rtol=2e-13, atol=1e-18`；power/SNR dB
`rtol=2e-13, atol=2e-12`。全部 case 通过，baseline 最大差异 `2.84e-14 dB`，coverage
差异为 0。

被消除的重复计算：

- 同一接收点的多个 Pattern 不再重复构造 M8 quadrature、TX/RX 距离、方向因子、传播相位、
  Profile modifier 和 control reduction；
- 同一固定网格的多个 Pattern 不再逐点重算上述 M8 几何，也不重复 No-RIS baseline；
- 热路径只保留 pattern validator、Gamma 构造、BLAS/NumPy 内积和 link metrics。

冷构建相对原始单 Pattern 场图也从 67.93 s 降到 43.22 s，来源是多接收点分块和共享入射侧
计算；本轮不预先把该比例定义为稳定门禁。真正的大幅收益来自第二个及后续 Pattern：48×36
热求值为 5.10 ms，而原始完整场图每个 Pattern 需约 68 s。

## 证据与停止条件

- `results/performance/xr_future_perf_01_20260908_27c1f8a_windows_single_thread/`
  包含 `evidence.json`、`summary.csv`、`timings.png`；
- `results/performance/xr_future_perf_01_20260908_27c1f8a_48x36_windows_single_thread/`
  包含独立 48×36 同类证据；
- 聚焦回归覆盖多 Pattern 等价、真实场图等价、Profile blocker modifier、identity
  mutation/exclusion、GT rejection、pair budget 和 coefficient memory budget。

本轮按范围停止：不做 GUI、双 RIS、GPU/CUDA、80×60、低阶 Preview 或通用持久缓存。
剩余瓶颈是精确 M8 的首次 `A` 构建（48×36 为 43.22 s）和 81 MiB 常驻矩阵。下一阶段优先继续
精确分块扩展：增加按网格 tile 的可消费/可释放接口、进一步向量化 baseline/Profile identity
检查，并由 A 在调用层明确管理 prepared identity。只有当交互冷启动预算仍无法接受、且精确
路径及独立审查已稳定后，再建立具有独立模型身份和 M8 误差对照的 Fast Preview。
