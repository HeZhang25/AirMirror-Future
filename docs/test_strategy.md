# 测试与验证策略

| 属性 | 值 |
|---|---|
| 文档状态 | Normative / Operational |
| 基线版本 | v0.1 |
| 测试框架 | pytest 9+，pytest-qt |

## 1. 目标

测试不是为了冻结某组好看的 dBm，而是保护以下性质：公式约定、单位、能量/孔径标度、
随机可复现性、数据兼容、层间契约和交互并发。任何测试阈值都必须能解释其物理或工程
来源，不能在失败后反复放宽直到通过。

## 2. 测试层级

| 层级 | 目录/方式 | 目的 | 每次变更 |
|---|---|---|---|
| L1 纯函数单元 | physics/core/ris tests | 公式、量化、几何、校验 | 必跑 |
| L2 性质测试 | aperture/focus/seed | 不变量和趋势，不绑定偶然数值 | 必跑 |
| L3 集成 | scene + engine + optimizer | 层间数据与结果有限性 | 必跑 |
| L4 GUI smoke | Qt offscreen | 构造、取消、版本丢弃 | GUI 变更必跑 |
| L5 人工验收 | `gui_spec.md` 清单 | 拖动、视觉、文案、交互响应 | release 必跑 |
| L6 实验回归 | headless experiments | 研究输出格式与趋势 | 物理/算法 release 必跑 |

默认命令：

```powershell
python -m pytest
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast
python -m airmirror_future.experiments.phase_bits --output results/phase_bits
```

## 3. 必须保护的物理性质

| Test ID | 性质 | 容差/判据 | 当前测试 |
|---|---|---|---|
| PHY-T01 | Friis 距离加倍 | power `-6.0206±0.01 dB` | `test_distance_doubled...` |
| PHY-T02 | 一波长相位 | `kλ=2π` | `test_one_wavelength...` |
| PHY-T03 | 同相等幅 | amplitude 恰为 2 倍 | `test_complex_field_interference` |
| PHY-T04 | π 反相 | residual `<1e-12` | 同上 |
| PHY-T05 | passive eta | `>1` 构造失败 | `test_passive_efficiency...` |
| PHY-T06 | 1-bit states | 仅 0/π | `test_phase_quantization_states` |
| PHY-T07 | 2-bit states | 仅四均匀状态 | 同上 |
| PHY-T08 | Focus vs random | focus > 100 random median 的 4 倍 | `test_physics_focus...` |
| PHY-T09 | fixed seed | complex result 完全一致 | `test_fixed_ground_truth_seed...` |
| PHY-T10 | wall blockage | 幅度衰减换算为 `-30±0.01 dB` | `test_complete_los...` |
| PHY-T11 | fixed aperture | 8/16/32 spread `<0.5 dB` | subdivision test |
| PHY-T12 | aperture growth | larger focused amplitude > smaller | larger aperture test |
| PHY-T13 | back face | RIS contribution exactly zero | back side test |

若更换物理近似导致这些容差不再适用，必须先提交 ADR 解释新性质，并加入等价或更强的
测试；不得先删除失败测试。

## 4. 数据与 API 测试

- Scene 保存/加载后名称、几何、cell count 和默认语义一致；
- schema version 不支持时拒绝；后续应增加未知/缺失字段和重复 id tests；
- 所有公共参数边界至少有一个非法值测试；
- pattern shape、active RIS、空 TX/RX 和 id 不存在需要逐步补错误契约测试；
- FieldMap 四个数组形状一致，coverage+dead-zone 约 100%；
- public top-level exports 能导入。

JSON golden file 只用于结构兼容；物理数值不写入 golden JSON，以免默认场景变动与公式
回归混在同一次失败中。

## 5. 随机与优化测试

- 使用显式 `np.random.default_rng(seed)`，不依赖全局 NumPy RNG；
- 随机 patterns 数量和 seed 固定；
- Ground Truth 误差是固定 realization，measurement noise 是固定调用序列；
- 无噪声贪心的 accepted objective 不应下降；有噪声时允许 measured history 偏差；
- 测试不能读取 Ground Truth 后直接构造“最优”反馈结果；
- 算法比较应在同一组 seeds 上配对，报告分位数。

## 6. GUI 与并发测试

自动 smoke 使用 `QT_QPA_PLATFORM=offscreen`：

- MainWindow 可构造/关闭；
- Cancel 不抛未处理异常；
- stale version 结果不写 `latest_field`；
- CJK 字体加载属于人工/截图验收，因为 offscreen font database 依赖主机。

后续应补：拖动坐标 round-trip、worker cancellation latency、错误对话框、Save/Load 控件同步
和 coverage overlay。涉及 Qt 线程的测试必须等待明确 signal，禁止依赖固定 sleep 作为唯一
同步条件。

## 7. 性能测试

绝对秒数只记录为参考，不作为跨机器硬门禁。每个 release 记录：CPU/OS/Python/NumPy、
Current/Advanced/Future 的 Fast 场图时间、最大内存、feedback measurement 数。性能退化
超过同机基线 30% 时调查。

硬门禁是：GUI 主线程不运行场图/feedback；可取消；无单次 `N_points×N_cells` 全量矩阵
导致不可控内存。P1 矩阵优化应增加内存上界和 cache invalidation 测试。

## 8. 缺陷优先级

| 级别 | 示例 | 发布处理 |
|---|---|---|
| P0 | 违反无源能量约束、相位不计算、随机伪造成功、数据损坏 | 阻断所有发布 |
| P1 | stale 结果覆盖、seed 不可复现、JSON 不兼容、GUI 卡死 | 阻断当前 release |
| P2 | 标签/tooltip 缺失、非关键布局、性能轻微退化 | 可带记录延期 |
| P3 | 文案或内部清理 | 进入 backlog |

## 9. 合并证据格式

完成报告至少记录：测试命令、通过数量、headless 关键指标、人工验收项目、未跑项目及原因。
“测试应该能过”不构成证据。requirements 中的 Implemented 条目必须能定位到证据。

