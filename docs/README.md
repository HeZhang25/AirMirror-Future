# 文档中心与治理规则

| 属性 | 值 |
|---|---|
| 文档状态 | Normative / 规范性 |
| 基线版本 | v0.1 |
| 最后复核 | 2026-09-02（ADR-0008 / FND-QA-AP aperture quadrature gate planning） |
| 维护责任 | 修改相关代码的开发者 |

本目录是 AirMirror Future 的工程事实源。根目录的 `项目说明提示词.md` 保存原始愿景和
完整需求背景；本目录将其转化为可实现、可测试、可追踪的当前基线。开发时不得只依据
原始提示词或聊天记录改变实现。

## 阅读顺序

新参与者应按以下顺序阅读：

1. [project_baseline.md](project_baseline.md)：产品目标、边界和不可破坏原则；
2. [glossary.md](glossary.md)：统一术语、坐标、单位和状态词；
3. [foundation_0_1_1_plan.md](foundation_0_1_1_plan.md)：当前基线之后的模型契约改进计划；
   其中最小孔径求积门禁详见
   [FND-QA-AP](work_items/foundation_0_1_1_qa_ap.md) 与
   [ADR-0008](adr/0008-minimum-aperture-quadrature-validity-gate.md)；
4. [requirements.md](requirements.md)：带稳定编号的需求与验收映射；
5. [architecture.md](architecture.md)：模块边界、依赖方向和数据流；
6. [data_model.md](data_model.md) 与 [public_api.md](public_api.md)：代码契约；
7. [physics_model.md](physics_model.md)：物理公式、约定、适用域和不变量；
8. [scene_schema.md](scene_schema.md)：持久化格式和兼容策略；
9. [gui_spec.md](gui_spec.md)、[optimization_spec.md](optimization_spec.md)、
   [experiment_spec.md](experiment_spec.md)：子系统行为；
10. [test_strategy.md](test_strategy.md) 与 [definition_of_done.md](definition_of_done.md)：
   验证和交付门禁；
11. [roadmap.md](roadmap.md)：阶段顺序和工作颗粒度；
12. [decisions.md](decisions.md) 与 [adr/](adr/)：不可静默改变的架构决定；
13. [../DEVELOPMENT_STATUS.md](../DEVELOPMENT_STATUS.md)：当前实现快照。

## 文档级别

| 级别 | 含义 | 文档 |
|---|---|---|
| Normative | 实现与测试必须遵守；修改需要变更记录 | baseline、requirements、architecture、data/API、physics、schema、DoD |
| Operational | 描述开发过程、阶段和当前状态 | Foundation 计划、roadmap、test strategy、development status、contributing |
| Informative | 帮助理解，不覆盖规范性契约 | README、scenarios、future assumptions、limitations |
| Historical | 保存输入与历史，不自动代表当前实现 | `项目说明提示词.md`、已替代 ADR |

## 冲突处理顺序

发现文档、代码或测试冲突时，按以下优先级处理，禁止私自选择最方便的一项：

1. 物理与安全不变量：`physics_model.md`、`project_baseline.md`；
2. 稳定需求及验收：`requirements.md`；
3. 对外契约：`data_model.md`、`public_api.md`、`scene_schema.md`；
4. 架构和子系统规格；
5. 测试和完成定义；
6. 路线图、状态页、README；
7. 原始提示词和历史讨论。

如果高优先级规范与已运行代码不一致，先记录为缺陷；不能通过悄悄修改规范来让测试
“通过”。若确需改变高优先级规范，必须添加 ADR、更新需求版本及所有下游文档和测试。

## 防漂移规则

1. **稳定编号**：需求使用 `AMF-域-序号`，ADR 使用四位序号；编号删除后不得复用。
2. **单一声明点**：公式只在物理规格中定义，JSON 字段只在场景 Schema 中定义，其他
   文档使用链接，不复制成不同版本。
3. **实现与计划分离**：`Implemented` 才能出现在可用功能清单；`Planned` 只能出现在
   roadmap，不得创建可点击假功能。
4. **同一变更闭环**：任何行为变化必须同时更新代码、测试、需求追踪和相关文档。
5. **颗粒度固定**：规划统一使用 Release → Capability → Deliverable → Task 四级，规则见
   `roadmap.md`；状态报告不得把一个代码文件与一个完整场景放在同一级。
6. **数值默认值唯一**：场景默认值来自 `scenes/smart_room.json`；代际默认值来自
   `ris/generations.py`；场图质量来自 `core/config.py`。文档只说明它们及其含义，改值时
   必须同步验证。
7. **日期不是完成度**：没有测试证据的功能不因排期或 UI 出现而被标为完成。

## 修改影响矩阵

| 改动类型 | 必须同步检查 |
|---|---|
| 物理公式/符号 | physics、requirements、ADR、单元测试、实验可比性 |
| 数值求积/精度声明 | physics、ADR、test/experiment、limitations、cache identity、provenance |
| 公共类/函数 | data model、public API、scene schema、调用方、兼容测试 |
| JSON 字段 | scene schema、schema version、迁移策略、round-trip 测试 |
| GUI 行为 | GUI spec、需求追踪、烟雾测试、截图/演示说明 |
| 优化目标/算法 | optimization spec、oracle 边界、随机种子、对照实验 |
| 默认参数 | assumptions、场景 JSON、README、基准输出、测试阈值 |
| 阶段状态 | roadmap、requirements status、DEVELOPMENT_STATUS |

## 文档自动校验

`tests/test_documentation.py` 检查：

- 必需文档是否存在；
- 本地 Markdown 链接是否有效；
- 需求编号是否唯一；
- 每个 `Implemented` 需求是否给出验证证据；
- 文档基线版本是否存在。

这只能发现结构漂移；物理和产品语义仍需按 Definition of Done 人工复核。
