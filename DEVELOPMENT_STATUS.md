# AirMirror Future Development Status

| 属性 | 值 |
|---|---|
| 状态快照 | 2026-09-01 |
| 当前 release | v0.1 |
| release 状态 | Verified |
| 规范基线 | [docs/README.md](docs/README.md) |
| 下一 Capability | P1A Geometry Cache and Matrix Evaluation |

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

1. 对固定场景预计算 `a_n` 和分块 `A @ Gamma`，缩短 Future 场图与反馈时间；
2. 完成相位误差强度扫描，对比 Physics / Feedback / Physics-Guided；
3. 加入 XR 人体阻挡与动态 outage 时间序列；
4. 在 Smart Space 稳定后扩展多用户、多 RIS Factory。

阶段顺序、entry/exit gate 和工作颗粒度以 [docs/roadmap.md](docs/roadmap.md) 为准。本页只
记录状态，不新增需求或改变优先级。
