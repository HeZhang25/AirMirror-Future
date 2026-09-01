# ADR-0005：显式版本化 Scene JSON v1

- 状态：Accepted
- 日期：2026-09-01
- 关联：AMF-DATA-001

## 背景

场景必须可读、离线、可版本控制和可重放。pickle 不安全且与代码结构强耦合，无版本 dict
会导致字段含义漂移。

## 决定

使用 UTF-8 JSON、`schema_version=1`、显式实体结构和 SI 单位。reader 验证 dataclass，
拒绝未知 schema major；为前向容忍可忽略未知字段。v1 不保存 pattern、Ground Truth 会话
误差、GUI 状态或热图。

## 后果

- scene 可人工审阅和 diff；
- 保存/加载重建受验证对象；
- 未知字段写回会丢失，不能用它保存关键扩展；
- 轨迹、多用户目标、pattern 持久化等结构性变化触发 v2 和迁移器。

