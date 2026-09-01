# ADR-0003：Controller Model 与 Ground Truth 隔离

- 状态：Accepted
- 日期：2026-09-01
- 关联：AMF-SIM-003、AMF-OPT-001、002

## 背景

若优化器读取仿真真实误差，所谓 feedback 只是使用隐藏答案，无法研究 physics prior 与
real feedback 的关系。

## 决定

Controller Model 仅提供名义世界；Ground Truth 生成固定 seed 的实际参数。反馈算法唯一
观测是 `MeasurementOracle.measure(patterns)->dBm`，measurement noise 有独立可重放序列。

## 后果

- Physics Focus 可按 controller 计算；
- feedback 在不知道误差的情况下修正；
- 算法测试/实验必须共享 truth realization；
- Python 属性可见不代表允许使用，code review 必须检查边界。

## 否决方案

- 将误差直接传给 optimizer：研究无效；
- 每次 channel 调用重新抽 truth：baseline 与对照不可比；
- 使用全局随机数：结果受其他代码调用影响。

