# FND-QA-CC Ready Review：D 独立决策（PERF-PREP-01 后续）

## 审查身份与范围

- Reviewer：D（性能工程准备与独立集成复核）
- Reviewed commit：`dcf25b61507ac0d6712994b3d19a6aa435e554d8`
- Parent/base：`87d2dea8c3ca40774f754271d7b21743cefcc133`
- Review checkout：`D:\Projects\AirMirror-Future-fnd-qa-cc-review-d`
- Checkout state：detached HEAD，未修改 C 提交中的文件
- Review environment：Windows NT 10.0.26200.0，Python 3.11.4，Git 2.55.0.windows.5；
  本 worktree 未安装 pytest（`python -m pytest` 返回 `No module named pytest`）
- Participation conflict：none；D 未参与 coefficient builder、Focus migration 或该提交实现

本记录只对 C 提交的 Ready candidate 做边界复核，不把候选稿当作生产实现，不重复开放式全量审计，
不重跑 PERF-PREP benchmark，也不改变任何正式状态。

## 实际复核命令与结果

在上述 worktree 中执行：

```text
git status --short --branch
git rev-parse HEAD
git rev-parse HEAD^
git diff --check origin/main...HEAD
python --version
git --version
[Environment]::OSVersion.VersionString
python -m json.tool configs/foundation_0_1_1/fnd_qa_cc_ready_contract_candidate_v1.json
python -m pytest -q tests/test_documentation.py
```

结果：

- `HEAD` 精确为 `dcf25b61507ac0d6712994b3d19a6aa435e554d8`；父提交精确为
  `87d2dea8c3ca40774f754271d7b21743cefcc133`。
- `git status --short --branch` 仅显示 `## HEAD (no branch)`；工作区干净。
- `git diff --check origin/main...HEAD` 通过。
- JSON 语法检查通过。
- 文档测试命令未能在该独立 worktree 启动：环境缺少 pytest（原始错误：
  `No module named pytest`）。没有安装依赖或修改环境；该项作为复核环境限制记录，不能写成测试 PASS。

## 已覆盖的契约边界

复用既有 QA-CC 边界复核并针对本精确提交阅读三项新增交付：

- pure coefficient source 的层级、控制单元/子点顺序、依赖方向以及 Controller/GT 分离边界已明确；
- legacy public RIS-only API 与新 scene-aware 路径的兼容范围、Coherent objective、candidate ordering、
  strict comparison、first-wins 和退化语义均有文字冻结；
- identity 层明确区分 transfer、baseline、commanded Gamma、GT realization、oracle、metrics 与 coverage，
  并列出 canonicalization、mutation 和 no-leak 验证计划；
- FND-T21/T22、三代矩阵、independent formula oracle、forward-error bound、provenance 与文档均被列为
  实施前验证项，而非已完成证据；
- candidate JSON 明确 `p1a_authorized: false`、`production_modified: false`，且禁止把
  `fnd_qa_ap_candidate/1` 当成 production identity。

## Blocking findings

### 设计阻断（1）

**RIS-only finite-bit 语义与既有公共 offset 契约不一致。** C 候选第 5.2 节把 scene-aware
production RIS-only finite-bit 候选族冻结为 singleton `{Q(base_phase + delta) | delta=0}`，并把
common-offset 搜索定义为需要另行 ADR 的新 objective。现有 `docs/adr/0006-coherent-target-focus-objective.md`
和 `docs/adr/0011-controller-coefficient-focus-consistency.md` 明确要求 finite-bit 在量化前加入公共
offset，并使用同一 Controller simulator objective 比较公共 offset 可达候选族；该约束也承载在 QA-CC
Work Item。C 文档虽保留 Coherent 的 common-offset 搜索，却改变了 RIS-only production 语义，不能在
Ready 阶段默默冻结。必须由维护者/ADR 明确：保持公共 offset 契约，或批准并记录新的 RIS-only objective
及兼容迁移。未决前不得进入 Ready/实施。

## External owner dependencies（非设计阻断）

1. **QA-AP owner / maintainer：** 签署 production M8 对应的 canonical
   `quadrature_policy_id/version`。禁止复用 `fnd_qa_ap_candidate/1`；在签署前 coefficient identity
   只能保持 candidate/partial。
2. **FND-PHY-NB owner / maintainer：** 现有代码与技术测试证据为 PASS，但 roadmap、Foundation plan 和
   Work Item 的 authoritative closure/status 仍待 owner 或维护者做正式决定。D 不自行改 Verified 或移除
   pending contract。

上述依赖属于外部签署/状态决策，不等同于 C 候选设计本身的阻断；但二者都必须在维护者授权 P1A 前
闭合。

## Non-blocking implementation gates (not evidence of completion)

- pure coefficient builder 及唯一 source 尚未实现；
- FND-T21/T22、identity mutation matrix、Ground Truth no-leak 和完整 migration evidence 尚未实现；
- 当前 production Focus 仍是既有 center-path，尚未切换到 M8-derived coefficient；
- P1A 的 A matrix、`A @ Gamma`、cache、chunking 与 incremental Greedy 均未授权且本轮不启动。

## Formal decision

**Decision: HOLD（不签署 Ready）。**

理由是上述 1 项设计阻断，加上 2 项必须由外部 owner/维护者签署的 closure 依赖。该结论不修改
`DEVELOPMENT_STATUS.md`、QA-CC/PHY-NB/QA-AP 状态，也不构成 approve、merge 或 P1A 授权。

## 最小返工/复核要求

维护者完成 finite-bit RIS-only 语义决策并取得 canonical M8 identity、PHY-NB closure 决策后，C 需
更新候选稿；随后由未参与核心 builder 实现的独立 reviewer 重新核对相关差异，并补齐 FND-T21/T22、
identity mutation/no-leak、三代 headless、provenance/docs 与完整回归证据，才可重新请求 Ready。
