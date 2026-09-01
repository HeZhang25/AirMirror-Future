# ADR-0004：可取消、版本化的 GUI 后台任务

- 状态：Accepted
- 日期：2026-09-01
- 关联：AMF-UI-003

## 背景

热图和 feedback 会随孔径/网格显著变慢。直接在 Qt 主线程运行会冻结 UI；仅使用线程仍
可能让旧任务在用户拖动后覆盖新状态。

## 决定

使用 QThreadPool/QRunnable；worker 获取 scene/pattern/model 深拷贝、cancel event 和单调
version。任何输入变化立即增加 version 并取消旧任务；只有当前 version 结果可应用。

## 后果

- UI 持续响应；旧结果安全丢弃；
- worker 不触碰 QWidget；
- cancellation 是协作式，计算内必须设置检查点；
- deep copy 成本可接受，未来若改不可变快照需新性能设计。

