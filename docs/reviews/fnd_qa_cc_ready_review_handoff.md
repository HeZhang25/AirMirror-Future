# FND-QA-CC Ready Review 交接说明

本文件只定义真正独立 D 如何取得并复核 C 的阶段一候选稿。它不是 D 的结论，也不表示 Ready
已通过。

## 可核验交付渠道

交付渠道为 GitHub 仓库 `HeZhang25/AirMirror-Future` 的远端 task branch：

```text
task/fnd-qa-cc/fnd-qa-cc-ready-contract-aplupie66
```

该 branch 从 `origin/main@87d2dea8c3ca40774f754271d7b21743cefcc133` 创建。真正 D 应在与 C
不同的电脑或至少独立 clone/worktree、独立 Codex session 中执行：

```powershell
git fetch origin
git worktree add <new-empty-path> `
  origin/task/fnd-qa-cc/fnd-qa-cc-ready-contract-aplupie66
cd <new-empty-path>
git status --short --branch
git rev-parse HEAD
git diff --check origin/main...HEAD
python -m json.tool configs/foundation_0_1_1/fnd_qa_cc_ready_contract_candidate_v1.json
python -m pytest -q tests/test_documentation.py
```

reviewer 不应运行或修改 C 本机的 `d_*` 目录，也不能把同一 Codex 根任务的子代理回复作为身份
证明。D 的正式回复至少记录：电脑/OS、checkout 绝对路径、Python/Git 版本、reviewed commit、
实际命令和完整输出、blocking findings、最终 `PASS` 或 `HOLD`。

## 本次需要阅读的 diff

- `docs/reviews/fnd_qa_cc_ready_contract_candidate.md`：职责、签名、所有权、Focus migration、identity、
  T21/T22 和 tolerance 候选；
- `configs/foundation_0_1_1/fnd_qa_cc_ready_contract_candidate_v1.json`：机器可读冻结候选；
- 本交接说明。

历史前置审计包不在 Git branch 中，仍固定于旧 base `275fedfe6a8a4a1d8a45d3045cf6334e4d4202e2`。
若维护者另行安全传输给 D，必须同时传递 `HANDOFF_CORRECTION.md`，并明确其中旧 D 段落已失效。
历史包只能帮助理解风险，不能替代本 branch 的基线审查。

## 聚焦审查清单

1. 低层 pure reduction 是否避免第二公式和反向依赖；
2. `a^C/Gamma_cmd/a^GT/Gamma_actual/baseline` 因子是否有唯一 owner；
3. legacy public RIS-only 与 scene-aware production migration 是否兼容 ADR-0006/0011；
4. ADR-0013 方案 A 的 RIS-only `P_RIS` common-offset search 与 Coherent total-power search 是否分层正确；
5. identity 是否正确区分 coefficient、baseline、Gamma、Pt/link metrics、coverage、GT physical
   realization 和 measurement oracle；
6. entity ID、custom Profile、relevant/irrelevant environment mutation 是否完整；
7. T21/T22 的三代 production grids、独立 formula oracle 和 dynamic forward-error bounds 是否足以
   在实现前冻结；
8. PR #23 已签署的 production canonical `midpoint_8x8_per_control_patch/1` 是否被准确消费。

## 回复模板

```text
Reviewer: <real project D identity>
Reviewed commit: <full SHA>
Independent environment: <computer/OS/path/Python/Git>
Commands/log location: <durable path or PR attachment>
Decision: PASS | HOLD
Blocking findings: <number and list>
Non-blocking findings: <list>
Implementation participation conflict: none | explain
```

只有真正 D 对同一 commit 返回 `PASS`、blocking findings 为 0，且维护者明确授权后，C 才能进入
阶段二。D 若参与核心 builder 实施，则必须更换另一名非作者 reviewer。
