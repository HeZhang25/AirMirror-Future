# Work Item：XR Dynamic Room MVP

## Prototype positioning

Non-release prototype / vertical slice，用于尽快验证第一个可运行 XR 场景。它不修改正式
release gate，不表示 Foundation、P1A 或 formal v0.2 entry gate 已满足。

## Entry condition

- FND-QA-AP 已 Verified，production quadrature policy 已 signed/frozen 为每个既有 RIS control
  patch 内 midpoint `8×8`；
- M8 production migration 已完成并通过其独立门禁；
- P1A formal gate 可继续 closed，FND-PHY-NB / FND-QA-CC 可仍为 Planned。

## Scope

- 1 indoor room、1 TX、1 RIS、1 moving RX/user；
- deterministic `position(t)`；
- No RIS / Static RIS；
- Adaptive RIS 仅在容易复用当前接口时纳入，不作为第一版必需项；
- 复用现有 Scene / SimulationEngine / RIS / Pattern / metrics。

## Deferred items

- FND-PHY-NB — Planned / **deferred for scene-first MVP**；
- FND-QA-CC — Planned / **deferred for scene-first MVP**；
- Foundation Final Verification — **deferred for scene-first MVP**；
- P1A（formal gate remains closed）、P1B、P1C — **deferred for scene-first MVP**；
- full human EM model、head orientation、28/60 GHz formal support、fading / Doppler、wideband /
  OFDM、multi-RIS、Factory / City、P1A cache、full GUI animation — **deferred for scene-first MVP**。

以上阶段或能力不得因本 prototype 标记为 Completed/Verified。

## Outputs

- received power(t)；
- SNR(t)；
- headless CSV；
- PNG result。

## Non-goals

- 不实现 formal v0.2 XR release capability 或解除其 entry gate；
- 不建立第二套 propagation engine 或 coefficient system；
- 不实现 deferred items，也不修改 Foundation/P1 的正式状态与顺序。

## Exit condition

同一确定性轨迹可用现有引擎重放 No RIS 与 Static RIS，输出完整 CSV 和 PNG，received power(t)
与 SNR(t) 可比较并可重复；Adaptive RIS 若未能直接复用现有接口可保持延期。
Foundation overall 仍为 In Progress，P1A formal gate 仍 closed，formal v0.2 gate not satisfied。
