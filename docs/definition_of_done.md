# Definition of Ready / Done

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 |

## 1. 为什么需要统一门禁

项目同时包含物理、算法、数据、GUI 和研究实验。若以“代码文件写完”作为共同完成定义，
会把不同颗粒度工作混在一起。以下门禁分别作用于 Task、Deliverable、Capability 和 Release。

## 2. Definition of Ready

一个 Deliverable 进入 In Progress 前必须满足：

- 有稳定 requirement ID，目标和非目标明确；
- 输入、输出、单位、shape、异常和状态所有者明确；
- 物理近似及适用边界已写入规格；
- 依赖 capability 已 Verified 或有明确 mock 边界；
- 自动测试和人工验收条件已先写清；
- 随机功能已定义 seed、重复次数和统计口径；
- 数据变化已决定 schema version/迁移策略；
- GUI 功能已有 headless capability，不依赖占位数据；
- 预计工作能拆成 0.5–2 天的同层级 tasks；
- 有未决高影响选择时，状态保持 Proposed/Planned，不进入实现。

## 3. Task Done

Task 是一个可独立评审的最小工程变更，例如“实现 2-bit quantization”或“增加 schema
version 拒绝测试”。完成要求：

- 代码、类型提示、核心 docstring 完成；
- 新/改测试通过；
- 没有吞掉异常、全局状态或临时经验常数；
- 不引入反向依赖；
- 对应文档链接/字段同步；
- 没有生成缓存、调试文件或不相关改动留在交付目录。

Task 完成不自动意味着 Capability 完成。

## 4. Deliverable Done

Deliverable 是用户或上层模块可验证的结果，例如“单 RIS Focus headless 链路”。完成要求：

- 所含 tasks 全部 done；
- 公共 API、数据模型和错误契约完成；
- 单元、性质和集成测试通过；
- 至少一个真实场景运行，不使用占位数据；
- 运行时间和已知限制记录；
- requirements 状态从 Ready/In Progress 更新为 Implemented；
- `DEVELOPMENT_STATUS.md` 更新。

## 5. Capability Verified

Capability 是一个完整能力，例如 Smart Space 或 XR Dynamic Link。完成要求：

- 所有 Deliverables done，requirement 追踪无空白；
- headless 垂直切片先通过；
- GUI 如在 scope 内，完成 worker、取消、错误和人工交互验收；
- 物理不变量和对照实验通过；
- 数据可保存/重放，随机结果可复现；
- README/demo/limitations 与实际一致；
- 不存在指向未实现逻辑的可用按钮；
- 状态由 Implemented 经人工验收提升为 Verified。

## 6. Release Done

- release 内所有 Capability Verified 或明确 Deferred；
- `python -m pip install -e ".[dev]"`、完整 pytest、headless demo、必需 experiments 通过；
- 文档结构校验和本地链接校验通过；
- 需求矩阵没有无证据的 Implemented；
- ADR/迁移/已知问题完整；
- GUI 截图和 3–5 分钟 demo 复核；
- 清理缓存与临时文件；
- `DEVELOPMENT_STATUS.md` 有准确的已完成、限制、下一阶段；
- 发布说明不能包含 Planned 能力。

Release 达到以上门禁并经项目维护者确认后，还必须完成 GitHub 交付闭环：

- 提交只包含本版本已验收范围，不夹带无关工作区修改；
- 将验收分支推送到配置的 `origin`，并核对远端 commit；
- 向维护者报告版本、分支、commit hash、主要变更、测试/人工验收、兼容或迁移影响、已知
  限制和下一阶段；
- tag、GitHub Release、PR、合并和历史改写不由“版本完成”自动授权，必须按工作项明确执行；
- 远端同步失败时保留可恢复的本地状态并报告阻塞，不 force push 或绕过分支保护。

## 7. 物理模型变更附加门禁

改变相位符号、散射幅值、方向图、阻挡、反射、误差采样或 dB 转换时额外要求：

1. ADR 记录旧模型、动机、新公式和预期影响；
2. 单位/量纲复核；
3. energy/aperture sanity check；
4. 现有性质测试先运行并解释变化；
5. 新测试覆盖被改变的性质；
6. Smart Space Current/Advanced/Future 基准重新生成；
7. 实验结果明确标注 model version，不能与旧结果直接混合。

## 8. 禁止用作“完成”的证据

- GUI 有按钮但没有物理实现；
- 一次手动运行没有报错；
- 只有截图，没有输入配置和数值；
- 只在单 seed 上表现更好；
- TODO 被移到文档但仍在当前 scope；
- 测试通过是因为降低物理阈值或跳过测试；
- 用 Future preset 的高参数掩盖错误模型；
- 代码完成但 schema、API 和限制文档仍是旧版本。
