# FND-QA-CC Ready：D 最终独立决策

## 审查身份与精确候选

- Reviewer：D（独立集成与 Ready 复核）
- Reviewed commit：`86fb9ceaad07a03a653b2b8016f8af75b35805f7`
- Candidate branch：`task/fnd-qa-cc/fnd-qa-cc-ready-contract-aplupie66`
- Integrated baseline：`origin/main@a7271648d3d6d98d6af953eadcc4784b7776222f`
- PR #23 merge：`6bc64c5d36b12905d4d6c89f9f89f91cbb05aa76`
- Review checkout：`D:\Projects\AirMirror-Future\_review_qa_cc_86fb9ce`
- Environment：Windows NT 10.0.26200.0；Python 3.11.4；Git 2.55.0.windows.5
- Implementation participation conflict：none；D 未参与 coefficient builder、Focus migration
  或候选设计修正的实现。

本轮是对最终 Ready 差异的聚焦复核，不重复开放式审计。旧候选
`dcf25b61507ac0d6712994b3d19a6aa435e554d8` 的 HOLD 仅为历史结论，不用于阻断本候选。

## 复核范围与证据

本轮核对：

- `docs/adr/0013-ris-only-scene-aware-finite-bit-clarification.md`；
- `docs/reviews/fnd_qa_cc_ready_contract_candidate.md`；
- `configs/foundation_0_1_1/fnd_qa_cc_ready_contract_candidate_v1.json`；
- `docs/reviews/fnd_qa_cc_ready_review_handoff.md`；
- 与 ADR-0006、ADR-0011、PR #23 已签署 NB/M8 契约的对应关系；
- Ready 后 FND-T21/T22、oracle、identity mutation、GT no-leak、兼容性和完整回归计划。

实际检查：

```text
git rev-parse HEAD
git diff --check origin/main...HEAD
python -m json.tool configs/foundation_0_1_1/fnd_qa_cc_ready_contract_candidate_v1.json
python -m pytest -q tests/test_documentation.py
```

结果：候选 SHA 与上述值一致；`git diff --check` 通过；机器 JSON 语法检查通过；
documentation tests `13 passed`。未运行阶段二 FND-T21/T22、三代 headless 或完整回归，因为它们
属于 implementation closure，当前候选没有生产实现变化。

## 最终边界判断

1. **逐元素零系数：PASS。** ADR-0013 与 Ready 契约均规定 `a_n^C == 0` 时在量化前使用
   `base_phase_n=0.0`，不调用 `arg(0)`、不引入容差，也不改变其他非零元素。该规则是命令的
   确定性规范，不把无贡献元素错误提升为 aggregate 退化。
2. **aggregate degenerate：PASS。** aggregate RIS 合成项以及 ADR-0006 已定义的退化条件继续使用
   既有精确 `0.0` fallback；它与逐元素 zero policy 分层明确，没有改变 ADR-0006 的相对退化、
   candidate ordering、strict-better 或 first-wins 契约。
3. **非有限值：PASS。** coefficient、phase、channel 或 offset 中的 NaN/Inf 必须经既有校验抛
   `ValueError`，禁止静默替换或归零。后续 FND-T21/T22 计划明确覆盖非有限输入。
4. **legacy/new callable：PASS。** legacy `generate_focus_pattern()`、
   `generate_ris_only_focus_pattern()`、`generate_unquantized_ris_only_focus_pattern()` 的签名、
   shape、异常、A3 合法状态和 center-path phase-array 语义保持不变。新的 scene-aware RIS-only
   路径必须是独立、具名且不顶层导出的 production callable，使用 `a^C` 与独立的 `P_RIS`
   objective；它不得伪装为 legacy 数组兼容。
5. **finite-bit objective：PASS。** 新路径复用 ADR-0006 common-offset candidate generator，
   `delta=0` 首项，保持候选顺序、strict-better 与 first-wins；RIS-only 只比较 `P_RIS`，Coherent
   继续比较包含 baseline 的 total power。两种 objective 分离且均不读取 Ground Truth。
6. **NB/M8 输入：PASS。** PR #23 已在 main 签署 FND-PHY-NB 与 production M8 identity
   `midpoint_8x8_per_control_patch/1`；候选准确消费该身份，并继续禁止以历史
   `fnd_qa_ap_candidate/1` 替代 production identity。

## Blocking findings

**0。** 未发现违反 ADR-0006、ADR-0011、ADR-0013 或 PR #23 已接受契约的 Ready 级冲突。

阶段二尚未实现 pure coefficient builder、FND-T21/T22、identity mutation、GT no-leak、三代
headless 和完整回归，不构成本次 Ready 阻断。这些项目继续作为 implementation closure 的强制
证据，不能因 Ready PASS 被提前声明为完成。

## 正式决策

**Decision：READY PASS。Blocking findings：0。**

本结论只签署 `86fb9ceaad07a03a653b2b8016f8af75b35805f7` 的阶段一设计契约已具备进入既定
FND-QA-CC 阶段二的条件。它不代签维护者决定，不提升 FND-QA-CC/Foundation 状态，不授权 P1A，
也不表示阶段二 implementation 或 closure 已完成。C 可在既有维护者授权范围内继续总控任务；
若核心契约发生实质变化，需对变化后的精确提交重新请求独立差异复核。
