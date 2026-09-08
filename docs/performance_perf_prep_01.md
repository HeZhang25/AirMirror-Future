# PERF-PREP-01：可复现性能基线与 P1A 准备

状态：性能准备 / 非 P1A 实施。本文和配套 JSON 只描述当前 main 的实测；不提升
Foundation、QA-CC、PHY-NB 或 P1A 状态，也不构成正式性能门禁。

## 固定基线与命令

- 仓库：`HeZhang25/AirMirror-Future`，HEAD / `origin/main`：
  `87d2dea8c3ca40774f754271d7b21743cefcc133`。
- 分支：`task/perf-prep-01`；工作树在 `D:\Projects\AirMirror-Future-main-baseline`。
- 硬件/OS：Windows 10 build 26200，Intel64 Family 6 Model 198，24 logical CPUs，
  16.51 GB physical memory（完整环境快照在 JSON）。
- Python：3.11.4，项目保留 `.venv`；NumPy 2.4.6；BLAS/NUMEXPR 线程均固定为 1。
- 场景：`create_smart_space_scene(generation)`，10×8×3 m，TX `(1,4,2.4)` m，
  RIS center `(5,7.9,1.5)` m，RX `(8.5,4,1.2)` m，5 GHz，100 MHz，
  `ControllerModel`，seed `20260901`，`IndoorDeterministicProfile`。
- production RIS：midpoint 8×8 per control patch，单 control 命令继承到 64 个
  subpoints；不改变公式、不构造 A、不启用 coefficient/cache/incremental Greedy。
- 命令（在基线 worktree）：

  ```powershell
  $env:PYTHONDONTWRITEBYTECODE='1'
  $env:PYTHONPATH='src'
  $env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'
  $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
  D:\Projects\AirMirror-Future\.venv\Scripts\python.exe -B `
    tools/perf_prep_01.py `
    --output results/performance/perf_prep_01_87d2dea_windows_single_thread_final.json `
    --repeats 3 --timeout-s 900
  ```

默认矩阵只对 Current 执行 Fast 80×60；Advanced 使用 16×12、Future 使用 8×6 的
`representative_probe`。Future Fast 80×60 必须显式加 `--future-fast`；Advanced Fast
必须显式加 `--full-fast`。这避免把未经测量的高成本结果写成基线，也不运行 QA-AP 全矩阵。

## 实测结果

数值来自配套 JSON，时间单位为秒，RSS 为独立子进程的 Windows working-set 峰值。

| generation | controls / M8 samples | phase bits | Focus candidates | single RIS channel (median) | Coherent Focus total | field grid / label | field time | peak RSS delta |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| Current | 64 / 4,096 | 1 | 123 | 0.00730 | 0.89027 | 80×60 / Fast | 3.75741 | 1.99 MB |
| Advanced | 576 / 36,864 | 3 | 4,609 | 0.06647 | 293.81605* | 16×12 / probe | 0.95394 | 11.52 MB |
| Future | 3,072 / 196,608 | continuous | analytic (1) | 0.35088 | 0.34994 | 8×6 / probe | 1.84507 | 52.11 MB |

`*` Advanced Focus 是一次完整有限比特候选 sweep（4,610 次含 unshifted evaluation），
不是 3 次重复；其余小项按 warmup=1、repeat=3。Focus 候选生成本身只有约 0.000036 s
(Current) / 0.000135 s (Advanced)，瓶颈是候选逐个调用完整 `compute_channel`。

Current Fast field 的 `FieldMapResult` 数组只有约 0.15 MB，但 production RIS 批处理和
临时数组使峰值 RSS 增长约 1.99 MB；Advanced/Future probe 的峰值分别约 11.52/52.11 MB。
不要将结果数组大小当作物理计算峰值内存。

## 瓶颈排序与 GUI/XR 观察

1. **有限比特 Coherent Focus**：Advanced 的 4,609 个公共 offset 候选 × 每次 0.0665 s
   channel evaluation，合计 293.8 s；Current 同结构为 123 × 0.00730 s，约 0.89 s。
   cProfile 的 Current 代表 case 还显示 123 次 `_production_quadrature_spec` / `midpoint_quadrature`
   累计约 1.03/1.23 s，即每个候选重复构造相同 M8 sample table。复用生命周期涉及
   production coefficient/Focus 边界，交 C/维护者协调，当前不改。
2. **场图生产散射**：每个 map 点都会执行 TX/RX、墙和 RIS M8 求积；Current Fast 4,800
   点约 3.76 s。Future probe 每点约 0.0384 s，随 196,608 subpoints 和临时广播数组增长。
   Future 8×6 cProfile 中 `_ris_aperture_point_contributions` 约占 1.60/2.22 s，M8 table
   一次构造约 0.44 s；范数、复指数/归约和广播临时数组是场图主成本。
3. **XR adaptive link 播放**：11 个轨迹点 × No/Static/Adaptive 共 33 条 link 的真实
   预计算为 10.04 s，但其中 channel evaluation runtime 总和只有 0.144 s；约 9.90 s
   来自每个 adaptive sample 重算 Focus（Current 1-bit 候选 sweep）。这解释了播放启动等待，
   不是 GUI 绘制时间。
4. **XR field/cache**：Current Static Fast 实测 2.67 s；选取第二个 adaptive sample
   的 cache miss 实测 2.66 s。精确 cache-key 构造约 0.000104 s，dict miss/hit 查找均为
   微秒级；命中不执行物理，miss 在 GUI 中串行交给 `XRAdaptiveFieldWorker`。
5. **metrics 与数组分配**：80×60 `coverage_percent` + `outage_probability` 的中位
   时间约 11 µs，输入数组 38.4 KB；相对 Focus/field 可忽略。PatternView 的 NumPy→QImage
   双图转换与 offscreen event processing 也已单独测量：Current/Advanced/Future 中位约
   0.14/0.16/0.26 ms，相对物理时间可忽略。真实窗口 compositor 与 SceneView heatmap
   redraw 仍需 A 在 GUI 侧 profiling，本报告不以 offscreen 结果替代交互体验。

真实 QThreadPool `MapWorker` 取消测量：Current Fast，进入物理约 6.7 ms；发出取消后
   runnable 约 41.0 ms 返回。取消检查位于 field-map 每完成一行的边界，正在执行的单点不会
   被中断；这是当前 GUI 排队/取消等待语义，不是承诺的上界。

## P1A 准备清单（未授权实施）

- [ ] FND-PHY-NB 正式 closure：当前代码/测试已接入
  `narrowband_center_frequency_flat_v1`，但路线图/Work Item 仍标记 Planned；不能自行提升。
- [ ] C2 canonical production quadrature identity：确认 M8 `midpoint_8×8`、parent ordering、
  policy/version 和 coefficient identity 的单一来源与失效矩阵；当前 benchmark 只记录实际
  M8，不创建第二套 source。
- [ ] FND-QA-CC：完成 ADR-0011 的 Controller coefficient / Focus 一致性、GT 隔离和
  identity mutation 复核；当前仍 Planned，不能把本报告当 closure。
- [ ] Foundation Final Verification：在上述 owner closure、focused tests、documentation/
  diff-check 和同机 Fast smoke 通过后，由维护者明确开放 P1A。
- [ ] P1A 设计先冻结 identity/invalidation 矩阵：scene/geometry、frequency model、Profile/
  reflection、M8 policy、control grid/flatten、efficiency/gain/direction/blockage；pattern、
  Gamma、metrics、coverage、oracle 各自分层，GT/measurement noise 不进入 nominal coefficient。
- [ ] 内存预算：以 M8 subpoint 临时广播和分块上限为基线；Future probe 已显示约 52.1 MB
  峰值增量。正式 P1A 必须先给出多点分块 A 的 chunk budget，不能以单个中心系数替代。
- [ ] 数值等价 gate：先复用 C 验收的 coefficient source，验证 `A @ Gamma` 与当前 scalar/
  production path 在声明容差内一致，再测同机 Fast 性能；没有等价证据不得宣称加速比例。

### Identity / invalidation 准备矩阵

| layer | 必须影响 identity / invalidate | 不应影响该 layer identity |
|---|---|---|
| coefficient `a_n^C` / future A | TX/RX/RIS 几何与 IDs、frequency model + `fc`、Profile identity、Reflection Model、M8 policy/order/parent mapping、control grid/flatten、gain/direction/blockage、nominal efficiency ownership | commanded pattern/Gamma、B、NF、coverage threshold、map quantity、measurement RNG/noise、GT phase error |
| commanded Gamma | validated phase float64 snapshot、hardware phase bits、control shape/order、nominal efficiency（按最终 QA-CC ownership） | RX map grid、B/NF、coverage、measurement RNG |
| link metrics | total complex channel、TX power、B、NF、metric formula/version | plot colors、GUI selection、worker version |
| coverage/field result | coefficient + Gamma identities、map x/y/z grid、threshold、quantity semantics、Controller/GT world identity | GUI compositor、timeline selection；quantity-only redraw若复用同一完整 field arrays 不重算物理 |
| measurement/oracle | GT world identity、seed、measurement noise model、command snapshot、sample index/order | nominal coefficient/Focus identity；oracle 不得反向污染 Controller Focus |

正式 key 的字段名、canonical encoding 和 coefficient source 必须由 QA-CC/C 接受后再冻结；本表仅列
失效责任，不创建 hash、共享 cache 或 production A。

### 数值等价锚点

最终机器 JSON 对三代固定 RIS-only command 保存：command float64 big-endian SHA-256、
LOS/wall/RIS/total 复分量、power/SNR，以及默认 bounded field grid 的四组 float64 big-endian
数组 SHA-256 和 coverage。P1A 必须在同一输入上先比较复数值与数组（声明 rtol/atol），hash
仅用于 exact-regression 诊断，不能取代容差比较或跨 NumPy/平台的数值验收。

## 独立 Foundation 复核记录

- **FND-PHY-NB**：PR #19 已合并（merge `99cde97`，实现提交 `62a1c7b`，后续测试提交
  `99fd49d`/`895bb13`）。`tests/test_narrowband_frequency.py` 覆盖 fc 重算、固定 command
  频率依赖、B 仅影响 noise/link metrics、canonical model ID；provenance 默认 pending
  目前为 `FND-PHY-NB` 与 `FND-QA-CC`。文档事实源仍写 Planned/deferred，故本审查不签署 closure。
- **QA-AP / C2 / M8**：QA-AP Work Item 记录 Verified 和 signed midpoint 8×8 policy；
  production migration 提交 `350fcba` 已由 `SimulationEngine` 在 field-map call 内复用一份
  M8 sample table，并由 `tests/test_production_quadrature.py` 检查 parent mapping、bounded
  pair count 和三代有限输出。`results/README.md` 仍保留旧的 Planned 描述，是文档同步问题，
  不在本性能 PR 中回填。
- **QA-CC**：Work Item `foundation_0_1_1_coefficient_consistency.md` 仍为 Planned/deferred；
  ADR-0011 Accepted 只冻结关系和边界，不表示共享 builder、FND-T21/T22 或 identity tests
  已完成。本报告未修改 production coefficient、Focus、cache 或 status。

## 保留边界

本分支只新增 benchmark、机器 JSON 和本报告/契约测试；不修改项目生产代码，不创建功能 PR，
不 merge、不 approve、不改变 Verified 状态、不启动正式 P1A。历史 `results/phase_bits` 和
旧 D 审计仍只作历史参考，未被用于当前 SHA 的测量结论。
