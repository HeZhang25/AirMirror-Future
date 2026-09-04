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

## Collaboration Governance v1

多人协作采用“roadmap 阶段串行、Work Item 内部并行”的流程。`main` 只接受已通过验收的
变更；复杂 Work Item 使用临时 `integration/<work-item>`，简单且低耦合的任务可以直接以
task branch 创建 PR 到 `main`。integration 分支不是永久第二主干，Work Item 完成并合并到
`main` 后删除对应 integration/task branches。

### Branch and working-tree rules

- 禁止直接在 `main` 或受保护的 integration 分支开发、push、force push、删除或改写历史。
- task branch 命名为 `task/<work-item>/<task-id>-<short-slug>-<user>`；例如
  `task/c2/FND-EXP-01A-provenance-alice`。bootstrap 使用
  `chore/collaboration-governance-v1`，C2 集成线使用 `integration/c2`。
- task branch 从当前 Work Item integration HEAD 创建；没有 integration 时从最新 `main` 创建。
- 每个开发者使用独立 clone/worktree、独立 Codex session、GitHub 账号和凭据；同一 working
  tree 同时只允许一个 active coding agent。
- 开始任务先执行并报告：

  ```powershell
  git status --short --branch
  git branch --show-current
  git rev-parse HEAD
  git fetch origin
  ```

  如果工作区不干净、branch/base 不正确或发现已有用户修改，停止并报告；不得自行
  `stash`、`reset --hard`、`clean`、覆盖用户改动或切换到其他分支。
- 已 push 分支默认用 `git fetch` + `git merge origin/<branch>` 同步，不用 rebase 或 force push。
  语义冲突必须交给文件 owner、Integration Owner 和维护者依据规范解决，不能盲选 ours/theirs。

### Codex scope and evidence

每个 Codex 任务必须在 prompt 和 PR 中写明 Work Item/Task ID、base SHA、目标与非目标、
owned/forbidden paths、阶段边界和停止条件。Codex prompt 只是 scope 指令，不是权限系统；
真实边界由 branch protection、CI、PR review、changed-path inspection 和人工操作规程保证。

Codex 不得自行：

- 修改其他 owner 的文件或扩大 Work Item/roadmap 阶段；
- push `main`、force push、改写历史、merge 或 approve PR；
- 把 Requirement、Work Item、Capability、Foundation 或 P1A 标为 Verified；
- 读取、写入或提交 token、SSH key、API key 等凭据；
- 把实验生成物、缓存或截图加入 PR，除非 Work Item 明确授权。

任务开始前如果发现跨 owner 依赖或 seam 不明确，应停止并报告 dependency，不顺手扩大范围。
任务完成后，Task Owner 在 PR 中提供原始测试命令、结果、未执行项和风险；不直接竞争修改共享
status 文档。

### Ownership and single-writer policy

同一轮一个热点文件只有一个 writer。共享 requirements、status 和集成事实源由 Work Item
指定的 Integration/Status Owner 统一更新；Task Owner 只在 PR 中提供状态证据。实现者不得
批准自己的 PR。`Implemented` 需要集成验收和维护者确认；`Verified` 需要 Independent Review
与 Maintainer 共同签署。

C2 的具体 owner、内部 integration seam 和 `results/README.md` owner 记录在
[C Work Item](docs/work_items/foundation_0_1_1_c.md)；其中 `results/README.md` 由 C 维护，
`phase_bits.py`、`tests/test_documentation.py`、`DEVELOPMENT_STATUS.md`、
`docs/requirements.md` 和 C Work Item 状态/集成段落由 D/维护者单写。`results/phase_bits/`
及 A/B checkpoint 只读。

### Pull requests and integration lifecycle

日常协作默认通过 PR，不需要为“创建 PR”单独请求授权。每个 PR 必须使用仓库 PR template，
目标明确为 `integration/<work-item>` 或 `main`，并通过 CI 与至少一名非作者 reviewer；作者
不能批准自己的 PR。PR 创建是协作流程，merge、status promotion、release 和 Verified 仍需
对应 Work Item/Integration Owner/Maintainer 授权。

对于活动 integration 分支，D 按串行顺序合并 task PR。若 integration 在该 task 最近一次
CI 之后发生变化，task owner 必须先 fetch 并 merge 最新 `origin/integration/<work-item>`，
重新 push 并通过 CI，才能合并。每次 merge 后 D 在最新 integration 上运行完整 pytest 和
受影响的 headless/实验回归；最后再创建 integration 到 `main` 的 final PR。若合并前发现
integration 再次变化，取消本次合并并重新检查。

GitHub 上的保护规则由维护者配置：`main` 和活动 integration 至少要求 PR、稳定 CI checks、
一名非作者 approval、conversation resolution、禁止 force push 和 protected branch deletion。
v1 暂不强制 `Require branch up to date`，以上述 stale-base 人工门禁和每次 merge 后回归替代；
C2 retrospective 后再决定是否启用。`Do not allow bypassing` 按当前 GitHub ruleset 能力配置，
不是代码 bootstrap 的自动条件。团队成员使用独立账号、最小权限和 2FA；2FA 是团队操作要求，
不作为仓库内自动化验收项。

### Generated results and status boundaries

开发阶段实验结果默认写入仓库外临时目录；若必须写入仓库内，必须使用 Work Item 允许的唯一
目录，且默认不提交。不得修改、覆盖、重分类或回写 tracked legacy/checkpoint 结果。C2 新 run
必须遵守其 exclusive no-overwrite 和 `partial`/pending provenance 契约。

任何 Codex 或 Task Owner 都不能因为代码完成、局部测试通过或 PR 合并而自动提升状态。状态
转移仍按 `docs/definition_of_done.md` 和对应 Work Item 的证据要求执行。

### Governance v1 boundary and backlog

本次 Governance v1 只建立 branch/PR/CI、integration 生命周期、ownership/single-writer、
Codex preflight/scope、C2 seam 和结果治理规则；不改变物理、simulation、GUI、Scene、C2
实现或 tracked results。

后续治理 backlog：

| 目标阶段 | 内容 |
|---|---|
| Governance v1.1 / C2 retrospective 后 | 根级 `AGENTS.md`、更完整 RACI、状态/evidence registry、Issue/Projects 评估、results CI guard |
| Foundation Final 前 | release/hotfix/revert 流程、版本与 tag 规则 |
| P1A 前后 | dependency constraints/lock、source/environment provenance 扩展 |
| Later maturity | `.gitattributes`、CODEOWNERS、安全自动化、仓库备份与 hygiene audit |

## 工作流程

1. 在 `docs/requirements.md` 找到稳定 ID；没有则先以 Planned 添加。
2. 用 `docs/templates/work_item.md` 确认工作层级、输入输出和验收。
3. 检查是否触发 ADR；物理、频率/带宽语义、Profile 所有权、coefficient 因子分解、schema
   major、层依赖、objective 和时间模型通常会触发。
4. 先增加/更新测试，再实现最小 headless 纵向结果。
5. GUI 只在 headless capability 通过后接入 worker。
6. 同一变更的 requirements 证据、相关规格和 DEVELOPMENT_STATUS 由对应 owner 更新；多人
   Work Item 的共享 requirements/status 文档由指定的 Integration/Status Owner 统一同步，
   Task Owner 在 PR 中提供所需证据。
7. 运行自动测试、headless/demo/实验中受影响的命令。
8. 按 Definition of Done 复核并清理缓存/临时文件。

Foundation 0.1.1 开发还必须遵守 [主计划](docs/foundation_0_1_1_plan.md) 的顺序和独立 Work
Item 边界。尤其不得把 FND-QA-AP 的 runner、条件性 production migration、FND-QA-CC 或 P1A
cache 合并成一个不可审查变更。

## 编码规则

- 公共函数有 type hints；核心类和公式有 docstring；
- 代码标识符英文，UI 默认中文+必要英文术语；
- 无全局 scene/pattern/random state；使用 `default_rng(seed)`；
- 内部 SI，UI 边界换算；
- GUI 不写物理公式；optimizer 不读 Ground Truth 私有参数；
- Profile 不重复自由空间 carrier/RIS device；model-based Focus 不读取 Ground Truth coefficient；
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
