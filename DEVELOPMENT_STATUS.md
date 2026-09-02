# AirMirror Future Development Status

| 属性 | 值 |
|---|---|
| 状态快照 | 2026-09-02 |
| 当前 release | v0.1 |
| release 状态 | Verified |
| 规范基线 | [docs/README.md](docs/README.md) |
| 当前 Capability | Foundation 0.1.1A Physics and Algorithm Contract（In Progress） |

## Foundation 0.1.1A / A2 实现快照

Deliverable A2（RIS aperture patch semantic contract）已达到 **Implemented**，等待维护者最终
复核；尚未签署为 Verified：

- `nx/ny` 已冻结为 system-level equivalent controllable aperture patches，不表示真实
  meta-atoms；实体 `width_m/height_m` 仍是孔径尺寸的唯一事实源；
- 新增只读 `EquivalentPatchDiagnostics` 与 `equivalent_patch_diagnostics()`，派生 effective
  pitch、运行波长和 `pitch/wavelength`，不修改 Scene/RIS、不参与传播；
- 改变 operating frequency 只改变波长和比例，不自动缩放实体孔径；
- ratio 仅作透明度信息，不实现 `lambda/2` pass/fail；A2 明确不输出未验证的 phase-span；
- `RISSurface` 现在拒绝非有限孔径尺寸、bool/小数/非正 patch count；
- ADR-0007 冻结未来拆分 control/quadrature/physical layout 的触发条件；GUI 只读接入留在
  B 阶段，因此 `AMF-RIS-009` 仍为 In Progress。

本机 Windows / Python 3.14.3 实现门禁：

| 门禁 | 结果 |
|---|---|
| A2 + RIS 定向 pytest | `19 passed` |
| 完整 pytest | `74 passed in 2.18s` |
| Current v0.1 fast headless | `-46.5879 dBm`，RIS Gain `+8.6874 dB`，场图 `2.845 s` |
| Advanced v0.1 fast headless | `-30.1257 dBm`，RIS Gain `+25.1496 dB`，场图 `3.401 s` |
| Future v0.1 fast headless | `-19.3118 dBm`，RIS Gain `+35.9636 dB`，场图 `8.553 s` |

三代目标数值与 A1 基线一致；运行时间波动不构成数值变化。A2 没有修改散射核心算法、GUI、
A3、PropagationProfile、缓存或实验逻辑。状态边界保持：A1 Verified；A2 Implemented；
Foundation 0.1.1A、AMF-RIS-009 和 Foundation 0.1.1 均为 In Progress。

## Foundation 0.1.1A / A1 最终验收快照

Deliverable A1（Focus objective）已完成最终人工验收并达到 **Verified**：

- 验收依据：closure commit `87495ec91a490d5cd5331ad9c4a0a2e863c10b40`；
- Gate 结果：G0–G8 全部 PASS；
- blocking issues：0；
- 状态边界：Foundation 0.1.1A、AMF-RIS-008 和 Foundation 0.1.1 仍为 In Progress。

- 新增显式 `RIS-only Phase-Conjugate Focus`，兼容函数 `generate_focus_pattern()` 输出不变；
- 新增 `Coherent Target Focus`，continuous 使用 nominal baseline 解析相位对齐，finite-bit
  枚举公共 offset 可达的量化 pattern 并以 nominal target power 选择；
- `delta=0` 是 finite-bit 首个候选，平局稳定保留旧命令；零/近零分量确定性回退；
- 新策略只接受 Controller Model，拒绝 Ground Truth，不改变 GUI、CLI 和历史实验默认语义；
- 规范由 [ADR-0006](docs/adr/0006-coherent-target-focus-objective.md) 冻结，工作范围与证据见
  [A1 Work Item](docs/work_items/foundation_0_1_1_a1.md)。

验收环境为 Windows、Python 3.14.3；本机结果：

| 门禁 | 结果 |
|---|---|
| A1 定向 pytest | `30 passed`（verification closure 全绿） |
| 完整 pytest | `61 passed`（closure 自动回归全绿；待最终差异审查） |
| Current v0.1 fast headless | `-46.5879 dBm`，RIS Gain `+8.6874 dB`，场图 `1.248 s` |
| Advanced v0.1 fast headless | `-30.1257 dBm`，RIS Gain `+25.1496 dB`，场图 `1.545 s` |
| Future v0.1 fast headless | `-19.3118 dBm`，RIS Gain `+35.9636 dB`，场图 `6.628 s` |
| A1 Coherent 单目标 | Current 123 candidates / `0.083 s`；Advanced 4609 / `3.571 s`；Future continuous / `0.003 s` |

headless 仍故意运行 v0.1 RIS-only 默认算法，因此上述三代值是兼容回归，不是 Coherent
Target 新默认。A2 已 Implemented，A3 commanded pattern hardware boundary 尚未实现，
因此 Foundation 0.1.1A 仍不能标为 Implemented/Verified。

## 已完成（v0.1）

- Python 可编辑安装、模块入口和离线 headless 命令；
- SI 数据模型、参数校验、场景 JSON 保存/加载；
- 复数 Friis LOS、阻挡衰减、一次墙面反射、噪声、SNR、Shannon 上界；
- 有限孔径 RIS、前向方向图、相位量化、Physics Focus；
- Current / Advanced / Future 代表性参数；
- Smart Space 目标链路、热力图、RIS Gain、Coverage、Dead Zone；
- Controller Model、Ground Truth、测量 oracle；
- tile-based Feedback Greedy 和 Physics-Guided Feedback；
- 中文 PySide6 GUI、拖动交互、参数面板、相位图、后台计算、取消和版本控制；
- Phase Resolution headless 实验；
- 物理、序列化、集成、优化和 GUI 烟雾测试。
- 产品基线、术语、需求追踪、架构、数据/API/Schema、GUI、优化、实验、测试、DoD、
  roadmap、ADR 和贡献流程文档；
- 文档结构、链接、需求编号和 Implemented 证据自动校验。

## 已知问题

- GUI、CLI、Physics-Guided 和 legacy experiment 当前仍使用 RIS-only Physics Focus；A1 的
  Coherent Target Focus 已有 headless Python API，但默认接入属于后续 B 阶段；
- `nx/ny` 的 equivalent patch 语义已冻结，但仍同时承担控制与中心点求积；GUI 尚未接入
  A2 只读 pitch/波长诊断，严格求积收敛留在 P1C；
- Phase Bits 尚未在传播入口验证 commanded hardware states；
- continuous hardware 与反馈优化的 8-state search 尚未在接口/UI 中拆分；
- GUI Generation 立即应用、普通参数等待 Apply，但没有 pending/customized 状态提示；
- 所有场景仍共用固定传播编排，尚无 PropagationProfile identity；
- 高质量 `200×160` 场图在 Future 64×48 网格下计算较慢，但运行于后台且可取消；
- 当前场图采用逐评价点计算，尚未建立跨点 RIS 系数矩阵缓存；
- 墙面反射是二维平面几何加三维路径高度检查，不是完整材料/极化模型；
- 反馈算法是 v0.1 教学型 tile coordinate descent，尚未实现增量复场更新。

## 尚未实现

- XR、Factory、City 场景；
- 多 RIS 联合优化和 max-min 用户目标；
- 衍射、双 RIS 连续反射、宽带、active/STAR/space-time RIS；
- Aperture、Phase Error、RIS Count、Dynamic User 四组批量实验。

## 下一阶段

1. 复核 A2 implementation，然后按 [Foundation 0.1.1 计划](docs/foundation_0_1_1_plan.md)
   完成 A3 commanded pattern hardware boundary；
2. 完成 optimizer/GUI 语义和实验 provenance；
3. 建立最小 PropagationProfile，冻结 cache identity；
4. 再进入 P1A 几何系数缓存与矩阵求值；
5. 随后完成相位误差和孔径统计实验，再扩展 XR/Factory/City。

阶段顺序、entry/exit gate 和工作颗粒度以 [docs/roadmap.md](docs/roadmap.md) 为准。本页只
记录状态，不新增需求或改变优先级。
