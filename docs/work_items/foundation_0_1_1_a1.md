# Work Item：Foundation 0.1.1A / A1 Focus Objective

- 层级：L3 Deliverable
- Requirement IDs：AMF-RIS-008
- 状态：Implemented
- 父项：Foundation 0.1.1A — Physics and Algorithm Contract
- 依赖：v0.1 Verified、ADR-0001、ADR-0003、ADR-0006

## 目标与用户结果

新开发者和上层模块能够明确选择 RIS-only 或 Coherent Target Focus，并能用自动测试证明新
算法在 nominal 单目标链路上执行的是总接收功率目标，而不是把建议误当成现有能力。

## In / Out

包含：两个具名算法、连续公共 offset、有限 bit 公共 offset 候选与稳定 tie-break、退化规则、
公共 API、性质/集成测试和 A1 规范闭环。

不包含：A2 equivalent patch、A3 commanded validator、B 阶段 hardware/search 分离、GUI 默认
算法和 Pattern Source、PropagationProfile、实验 provenance、新场景、MIMO、fading 或性能
缓存。

## 接口与数据

- 输入：`Scene`、`ControllerModel`、单 TX/RX、单 enabled `RISSurface`、SI 频率和弧度相位；
- 输出：shape `[ris.cell_count]` 的有限 NumPy commanded phase array；
- objective：Controller Model 下 `received_power_w`，等价排序可显示为 dBm；
- 错误：非法 phase/offset、Ground Truth、未知/禁用/歧义 RIS 均为 `ValueError`；
- schema：不变；GUI/CLI 默认：不变；历史实验：不覆盖。

## 物理/算法约束

公式、相位符号、退化容差、finite-bit 边界枚举、适用域和禁止外推结论以
[ADR-0006](../adr/0006-coherent-target-focus-objective.md) 为准。新策略只能通过公开 Scene、
Controller Model 和 SimulationEngine 结果工作，不读取 Ground Truth 私有误差。

## Tasks

- [x] 冻结 ADR、术语、物理和 optimization objective；
- [x] 保留并显式命名 RIS-only API；
- [x] 实现纯 offset helper 和 Coherent Target Focus 策略；
- [x] 实现 FND-T01..T05 及候选覆盖/模型边界补充测试；
- [x] 同步 requirements、public API、test strategy 和 development status；
- [x] 运行完整 pytest 与三代 v0.1 headless 回归。

## 验收证据

- `tests/test_coherent_focus.py`：FND-T01..T05、候选覆盖和 Ground Truth 拒绝；
- `tests/test_ris.py`：既有 focus/random、孔径和方向性质；
- `python -m pytest`；
- Current/Advanced/Future fast headless 命令；
- Smart Space continuous 测试是实际版本化场景，不使用占位 channel。

本机 Windows / Python 3.14.3 验收为 `46 passed`；三代 fast headless 均通过。Coherent 单目标
运行记录为 Current 123 candidates / `0.083 s`、Advanced 4609 / `3.571 s`、Future continuous
/ `0.003 s`。完整数值见 [DEVELOPMENT_STATUS.md](../../DEVELOPMENT_STATUS.md) 的 A1 验收
快照；绝对秒数只作本机参考，不是跨机器硬门禁。

## 风险与回退

- finite-bit 边界候选最坏随 `N*2^bits` 增长；检测候选数和单目标运行时间，GUI 接入前另做
  等价优化，不删减 `delta=0` 或真实性质；
- 新算法改变 target dBm；旧 GUI/CLI/实验继续使用显式保留的 RIS-only 行为作为安全回退；
- 相位近零分量不稳定；统一回退 `delta=0`，以 FND-T05 防回归。

## 文档影响

- [x] requirements
- [x] public API
- [x] physics / optimization / glossary
- [x] test strategy
- [x] ADR / decisions index
- [x] development status / Foundation plan
- [ ] GUI spec（B 阶段）
- [ ] experiment provenance（C2 阶段）
