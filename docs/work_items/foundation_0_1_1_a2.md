# Work Item：Foundation 0.1.1A / A2 Aperture Patch Semantic Contract

- 层级：L3 Deliverable
- Requirement IDs：AMF-RIS-009
- 状态：Implemented
- 父项：Foundation 0.1.1A — Physics and Algorithm Contract
- 依赖：v0.1 Verified、A1 Verified、ADR-0001、ADR-0007

## 目标与用户结果

新开发者、GUI 和实验层能够把 `nx/ny` 正确解释为系统级等效可控孔径 patch，并能在不改变
实体几何的前提下读取 effective pitch、运行波长和 `pitch/wavelength`。任何结果都不会把
当前网格误报为真实 meta-atom 布局或严格数值收敛证明。

## In / Out

包含：`nx/ny` 术语冻结、孔径尺寸所有权、纯派生诊断 API、非法输入契约、A2 文档闭环和
FND-T09 回归。

不包含：A3 commanded pattern validator、GUI 状态机/只读面板接线、PropagationProfile、
独立 quadrature grid、phase-span、真实 meta-atom、互耦、fill factor、材料/频率响应、缓存、
新场景、MIMO 或 fading。

## 接口与数据

- 输入：合法 `RISSurface` 和 finite、positive operating `frequency_hz`；
- 输出：冻结 `EquivalentPatchDiagnostics`，字段全部为 SI 或无量纲 ratio；
- 几何事实源：仅 `RISSurface.width_m/height_m`；
- patch 计数：`nx/ny` 必须是正整数，bool 和小数均拒绝；
- 错误：非法频率、非有限/非正尺寸、非法 patch count 均为 `ValueError`；
- schema、传播算法、GUI/CLI 默认、代际 preset 数值和历史实验：不变。

## 物理/算法约束

规范语义、派生公式、advisory 边界、`design_frequency_hz` Deferred 决定和未来拆网格触发条件
以 [ADR-0007](../adr/0007-equivalent-controllable-aperture-patches.md) 为准。A2 的
`pitch/wavelength` 不构成 `lambda/2` 阵元合规判定；A2 不输出 phase-span 或 pass/fail。
现有 8/16/32 固定孔径测试继续只解释为面积归一化/不发散证据。

## Tasks

- [x] 冻结 ADR-0007、术语、孔径所有权和 Deferred 边界；
- [x] 实现只读 `EquivalentPatchDiagnostics` 和纯派生 helper；
- [x] 加强 RIS 实体尺寸 finite 校验和 `nx/ny` 正整数校验；
- [x] 实现 FND-T09、非法输入与三代 preset 诊断测试；
- [x] 同步 data/API/physics/limitations/GUI/experiment/assumption 文档；
- [x] 运行完整 pytest 与三代 v0.1 headless 回归；
- [x] 完成范围复核并创建 A2 implementation commit。

## 验收证据

- `tests/test_aperture_diagnostics.py`：FND-T09、精确 SI 字段、非法输入和三代 preset；
- `tests/test_ris.py`：固定孔径细分、孔径增大、背面方向图与既有 Focus；
- `tests/test_scene_engine.py`：频率与 Scene/传播集成回归；
- `python -m pytest`；
- Current/Advanced/Future fast headless 命令。

本机 Windows / Python 3.14.3 实现门禁：A2+RIS 定向 `19 passed`，完整回归 `74 passed`；
Current/Advanced/Future fast headless 的目标功率依次为 `-46.5879/-30.1257/-19.3118 dBm`，
RIS Gain 依次为 `+8.6874/+25.1496/+35.9636 dB`，与 A1 兼容基线一致。绝对运行时间只作
同机参考。自动测试通过只允许 A2 标为 Implemented；在维护者最终复核前不得标为 Verified，
且 Foundation 0.1.1A、AMF-RIS-009 和 Foundation 0.1.1 继续保持 In Progress。

## 风险与回退

- ratio 被误当真实阵元约束：API 不输出判断，规范禁止 `lambda/2` pass/fail；
- 更严格输入校验暴露旧非法对象：通过显式 `ValueError` 修正输入，不允许 NaN 几何进入传播；
- 诊断被错误接入传播：helper 保持纯函数，现有散射路径不导入它；
- 未来需要数值收敛：进入 P1C 拆分 control/quadrature grid，不在 A2 增加经验阈值。

## 文档影响

- [x] requirements / Foundation plan / roadmap
- [x] data model / public API
- [x] physics / limitations / glossary
- [x] GUI spec（只冻结术语和未来只读接线，不修改 GUI）
- [x] test strategy / assumptions / experiment schema wording
- [x] ADR / decisions index / docs index
- [x] development status
- [ ] experiment provenance（C2 阶段）
