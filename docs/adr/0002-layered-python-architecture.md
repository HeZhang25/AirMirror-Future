# ADR-0002：分层 Python src 架构与 dataclass 模型

- 状态：Accepted
- 日期：2026-09-01
- 关联：AMF-CORE-001、AMF-ENG-001、002

## 背景

项目需同时支持 headless 研究、桌面交互和后续场景。若把计算写在 Qt 事件中，测试、实验
复用和模型审计都会失效；若全用 dict，单位和字段容易漂移。

## 决定

使用 Python 3.11+、`src/airmirror_future` layout、core→physics/ris→scene→simulation→
optimization→gui/experiments 单向依赖。公共实体和结果使用带验证的 dataclass。GUI 只调用
simulation/optimization 公共 API。

`Scene.save/load` 允许局部 import serialization，作为便利 API 与循环依赖之间的受控例外。

## 后果

- 核心可在无 Qt 环境测试；
- 数据字段、单位和范围集中定义；
- 新功能先做 headless vertical slice；
- 变更公共 dataclass 字段需要同步 schema 和迁移策略。

