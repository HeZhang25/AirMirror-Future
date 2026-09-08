# ADR-0013：Scene-aware RIS-only 有限 bit 语义澄清（待维护者决策）

- 状态：Proposed / Pending maintainer decision
- 日期：2026-09-08
- 关联：ADR-0006、ADR-0011、AMF-RIS-012、FND-QA-CC

## 背景与阻断

ADR-0006 保留了旧的公开 RIS-only API，同时定义了带公共 offset 的有限 bit
候选族；ADR-0011 要求未来 scene-aware Focus 使用 Controller control-level
coefficient `a^C`。C 的 Ready candidate 将新的 scene-aware RIS-only 有限 bit
路径收窄为 singleton `delta=0`，而 D 独立复核确认这与既有公共 offset 契约不
一致。此文件只澄清语义，不授权生产迁移或改变任何已接受 ADR。

## 不变的兼容边界

1. `generate_focus_pattern()`、`generate_ris_only_focus_pattern()` 和
   `generate_unquantized_ris_only_focus_pattern()` 的签名、返回 shape、异常、
   A3 合法状态及 v0.1 center-path phase-array 语义保持不变。
2. 这些 legacy API 不读取 baseline、Ground Truth realization 或 measurement
   oracle，也不因本 ADR 自动改名或改行为。
3. 新 scene-aware 路径必须是独立的内部/具名 production callable；不得以
   legacy API 的数组兼容性掩盖 coefficient basis 的迁移。

## 待决策的 scene-aware RIS-only 语义

两项方案如下，维护者必须明确选择其一：

### 方案 A（建议：保持公共 offset 契约）

- continuous 命令：`phi_n = wrap(-arg(a_n^C))`。
- finite-bit 候选族：对 `base_phase_n = wrap(-arg(a_n^C))` 使用
  ADR-0006 的公共 offset 候选生成器；首项严格为 `delta=0`，随后为唯一量化
  边界排序及环形区间中点，保持既有候选顺序。
- RIS-only objective：仅最大化
  `P_RIS(delta) = Pt * |sum_n a_n^C * Gamma_cmd,n(delta)|^2`。
  不加入 `h_baseline^C`，不使用 Coherent 的 total-power objective。
- 仅当候选功率相对 incumbent 严格超过既有数值比较规则时替换；相等时
  first-wins。`delta=0` 因为是首项而在平局时保留。
- 若 `a^C` 或 RIS 合成项触发 ADR-0006 的退化/非有限输入规则，则保持其
  精确 fallback、错误类型和命令验证语义，不新增容差。

### 方案 B（保持 singleton，但需显式改约）

- continuous 命令同方案 A。
- finite-bit 候选族仅为 `{Q(base_phase + 0)}`。
- 目标仍为 `P_RIS`，而非 total received power；singleton 内不执行 offset
  比较，因此不得宣称对公共 offset 可达族最优。
- 该方案视为对 ADR-0006/QA-CC Work Item 公共 offset 要求的受控例外，必须由
  新的获批准 ADR 明确记录兼容迁移、验收范围和调用方影响后方可使用。

在维护者选择并批准前，Ready 状态保持 HOLD；不得把任一方案写成已批准的
production 语义。

## Coherent 语义（不变）

- continuous：`phi_n = wrap(arg(h_baseline^C) - arg(a_n^C))`。
- finite-bit：沿用 ADR-0006 的 total received-power objective
  `Pt * |h_baseline^C + h_RIS^C(delta)|^2`，使用同一公共 offset 候选族、
  `delta=0` 首项、既有候选顺序、严格比较、first-wins 及退化 fallback。
- 不得把该 total-power objective 直接套用于 RIS-only。

## Ready 与实施边界

本 ADR 仅是 Ready 设计决策输入。FND-T21/T22、independent oracle、identity
mutation、GT no-leak、三代 headless 及完整回归属于阶段二实施后的 closure 证据；
它们不因本文件而提前报告为通过。维护者批准后，C 才可更新 Ready Markdown、
机器 JSON 和测试计划；生产 source/Focus migration 仍需另行授权。

## 决策记录（留空）

- Maintainer decision: **pending**
- Decision date: pending
- Rationale / approved option: pending
