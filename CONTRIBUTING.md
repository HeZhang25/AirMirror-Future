# Contributing to AirMirror Future

本项目把物理可信度和文档一致性视为代码质量的一部分。开始修改前先阅读
[docs/README.md](docs/README.md) 规定的顺序。

## 开发环境

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

## 工作流程

1. 在 `docs/requirements.md` 找到稳定 ID；没有则先以 Planned 添加。
2. 用 `docs/templates/work_item.md` 确认工作层级、输入输出和验收。
3. 检查是否触发 ADR；物理、schema major、层依赖、objective 和时间模型通常会触发。
4. 先增加/更新测试，再实现最小 headless 纵向结果。
5. GUI 只在 headless capability 通过后接入 worker。
6. 同一变更更新 requirements 证据、相关规格和 DEVELOPMENT_STATUS。
7. 运行自动测试、headless/demo/实验中受影响的命令。
8. 按 Definition of Done 复核并清理缓存/临时文件。

## 编码规则

- 公共函数有 type hints；核心类和公式有 docstring；
- 代码标识符英文，UI 默认中文+必要英文术语；
- 无全局 scene/pattern/random state；使用 `default_rng(seed)`；
- 内部 SI，UI 边界换算；
- GUI 不写物理公式；optimizer 不读 Ground Truth 私有参数；
- 不吞掉校验错误，不用 NaN/零值伪装“不适用”；
- 不增加未经命名和说明的 dB gain、future multiplier 或绘制热点；
- 保持 NumPy 数组 shape 契约，避免大量 cell Python objects。

## 文档规则

- 规范文档使用当前行为和“必须/不得”；roadmap 使用 Planned；
- 不复制公式、schema 字段或默认值到多个无链接的事实源；
- 删除 requirement 时保留编号并标 Deferred/Rejected；
- 修改默认参数必须更新 JSON、测试基准、README 和 assumptions；
- README 只列用户可运行能力，详细契约链接到 docs；
- 任何本地 Markdown 链接必须通过 documentation test。

## 提交前检查

```powershell
python -m pytest
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast
```

物理/优化改动还需运行受影响实验。GUI 改动执行 `gui_spec.md` 人工清单。报告准确的通过
数量和未执行项；不得写“应该没问题”。

## 版本验收与 GitHub 同步

项目已配置 GitHub 远端。每次 release 或明确的版本更新完成后，按以下顺序收尾：

1. 先满足对应 Capability/Release 的 Definition of Done，并记录自动测试、headless、实验和
   人工验收证据；
2. 由项目维护者确认本次版本可以发布；未经确认的 In Progress、仅文档草案或局部测试通过
   不得当作已验收版本推送；
3. 检查工作区和目标分支，只提交本版本范围内的文件，不夹带用户未授权或无关改动；
4. 使用能说明版本目标的提交信息提交，并将已验收分支同步到已配置的 GitHub `origin`；
5. 推送后核对远端分支/提交，向项目维护者报告：版本、分支、commit hash、主要更新、测试与
   验收结果、兼容/迁移说明、已知限制和下一步；
6. 若凭据、网络、分支保护或远端状态阻止同步，保留本地提交，准确报告阻塞原因，不使用
   force push、历史改写或降低验收标准绕过问题。

默认不自动创建 tag、GitHub Release、PR 或改写远端历史；这些操作需要在对应版本工作项中
明确约定。同步 GitHub 是已验收版本的交付步骤，不是替代验收的证据。
