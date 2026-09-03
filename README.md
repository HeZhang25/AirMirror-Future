# AirMirror Future

面向未来电子信息基础设施的可编程电磁空间仿真平台。项目以 RIS
（Reconfigurable Intelligent Surface）为核心，展示传播环境如何成为可感知、
可计算、可配置和可优化的信息基础设施组成部分。

> 本软件是 **System-level electromagnetic approximation**，不是 CST/HFSS
> 或完整三维 Maxwell 全波求解器。

## 文档与开发一致性

工程规格从 [docs/README.md](docs/README.md) 开始。该索引定义文档优先级、需求编号、
冲突处理、变更影响矩阵和防漂移规则；[docs/requirements.md](docs/requirements.md) 将每项
能力映射到实现与测试证据，[docs/definition_of_done.md](docs/definition_of_done.md) 统一各层级
完成门禁。参与开发前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

原始 `项目说明提示词.md` 是历史愿景输入；当前开发不能只凭聊天内容或提示词静默改变
规范性 API、物理公式、数据格式或阶段范围。

当前 `v0.1` Smart Space 已验证。进入性能缓存和新场景前，项目将先执行
[Foundation 0.1.1 物理模型契约计划](docs/foundation_0_1_1_plan.md)，校准 Focus objective、
RIS 网格语义、Commanded Pattern 硬件约束、优化搜索分辨率、GUI 状态和传播 Profile。
在 Foundation final exit/P1A 缓存前还必须完成
[FND-QA-AP 最小孔径求积有效性门禁](docs/work_items/foundation_0_1_1_qa_ap.md)，冻结待缓存
control-level coefficient 的 quadrature policy；随后依次关闭
[Wall 几何](docs/work_items/foundation_0_1_1_wall_geometry_closure.md)、
[中心频率窄带语义](docs/work_items/foundation_0_1_1_narrowband_contract.md) 和
[Controller coefficient/Focus 一致性](docs/work_items/foundation_0_1_1_coefficient_consistency.md)。
Foundation 当前为 In Progress：A1、A2 与 A3 已 Verified；B1/B2/B3 已达到 implementation-level
（待独立审查），C 和上述 cross-cutting gates 尚未
完成。未达到
Implemented 的计划项不得描述为当前功能。

## 安装

需要 Python 3.11 或更高版本。建议在虚拟环境中安装：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

程序完全离线运行，不依赖在线 API 或 CUDA。

## 启动

桌面应用：

```powershell
python -m airmirror_future
```

Headless Smart Space 验证：

```powershell
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Current --quality fast
python -m airmirror_future --headless --scene scenes/smart_room.json --generation Future --quality balanced
```

运行测试：

```powershell
python -m pytest
```

## v0.1 Smart Space

当前可运行垂直切片是一个 `10 m × 8 m × 3 m` 智能空间，包含 TX、可拖动
RX、内部阻挡墙、吸收障碍物和一块有限孔径 RIS。界面可以：

- 比较无 RIS 与 Physics Focus 后的接收功率、SNR 和 RIS Gain；
- 切换 Current、Advanced、Future 代表性代际，并继续手动修改所有关键参数；
- 显示接收功率、SNR 或 RIS Gain 热力图，以及 Coverage/Dead Zone；
- 查看 commanded 和带误差的 actual 相位图；
- 使用 Physics Focus、Feedback Greedy 或 Physics-Guided Feedback；
- 保存和加载版本化 JSON 场景；
- 在后台计算场图和优化，支持取消并拒绝过期结果。

Smart Space 默认以 `SNR ≥ 35 dB` 定义 coverage，使内部墙后的弱覆盖区域在演示中可见；
该阈值是场景指标，并不代表统一通信制式门限。

Future 参数始终显示 `Future Scenario Assumption`，不表示当前产品能力。

## 物理模型简介

- LOS 使用保留传播相位的复数 Friis 信道；
- 墙体使用有限线段 image method 一次镜面反射；
- 墙体和矩形障碍物通过几何求交施加场幅衰减；
- RIS 使用面积归一化的有限孔径双基地散射模型；
- 所有路径在复数域相加，然后由 `Pr = Pt |h|²` 得到接收功率；
- 热噪声为 `-174 + 10log10(B) + NF` dBm；
- 界面容量指标仅代表 Shannon 理论上界。

更准确地说，当前 `frequency_hz` 是中心频率 `fc`，引擎只计算 `h(fc)` 并假定其在
`bandwidth_hz` 内平坦；带宽用于接收噪声和 flat-channel Shannon upper bound，不表示已实现
OFDM 或频率选择性信道。当前所有场景仍使用同一固定传播编排，Foundation 的
environment-only PropagationProfile 尚未接入。

详细公式与适用边界见 [docs/physics_model.md](docs/physics_model.md)。

## RIS 技术代际

| Preset | 孔径 | Equivalent Patch 网格 | 相位 | 效率 | 更新率 |
|---|---:|---:|---:|---:|---:|
| Current | 0.8×0.8 m | 8×8 | 1-bit | 0.70 | 10 Hz |
| Advanced | 1.6×1.2 m | 24×24 | 3-bit | 0.85 | 100 Hz |
| Future | 3.0×2.0 m | 64×48 | continuous | 0.95 | 1000 Hz |

网格表示系统级等效可控孔径 patch，不是真实 meta-atom 布局。三组 preset 都是可编辑的
代表性仿真假设，不是对所有现实 RIS 的统一规格声明。

## 3–5 分钟 Demo

1. 启动应用，观察内部墙后方的 No RIS 基线与接收指标。
2. 保持 Current，点击 `Optimize`，查看 Physics Focus 相位和目标点变化。
3. 依次切换 Advanced、Future，观察孔径、效率和相位精度如何改变场分布。
4. 拖动 RX 到另一位置；目标指标立即更新，热力图在后台重新计算，热点随目标移动。
5. 增大 `Phase Error σ`，选择 `Physics-Guided Feedback`，观察反馈对模型误差的补偿。
6. 切换接收功率、SNR、RIS Gain 三种图，查看 Coverage 与 Dead Zone。

## 实验

相位分辨率实验会保持实体孔径不变，输出 CSV 和 PNG：

```powershell
python -m airmirror_future.experiments.phase_bits --output results/phase_bits
```

孔径、相位误差、RIS 数量和动态用户实验属于后续里程碑，目前未提供假入口。

## 四个目标场景与路线图

1. **Future Smart Space**：v0.1 已实现。
2. **XR / Spatial Computing**：计划加入人体遮挡、移动和 outage 时间序列。
3. **Future Smart Factory**：计划加入多 RX、多 RIS 和 max-min SNR。
4. **Future City / Low-Altitude Network**：计划加入建筑遮挡、立面 RIS 和电磁走廊。

随后考虑宽带 RIS、STAR-RIS、active RIS、感知定位、安全和无线能量传输；这些能力
必须先有明确物理模型，才会成为可用功能。

## 当前局限

项目暂不包含全波求解、衍射、高阶多次反射、互耦、复杂极化、材料色散、真实天线
全波方向图、PIN 二极管非线性、完整 OFDM/MIMO 或 5G 协议栈。完整列表见
[docs/limitations.md](docs/limitations.md)。

当前 production RIS 孔径积分为每个 equivalent control patch 一个中心点。A2 已验证 patch
语义，但独立 quadrature accuracy 尚未验证；三代精确 dBm 应理解为 current scalar
center-point model 的输出，而不是 full-wave/测量真值。

Scene v1 Wall 已收紧为 floor-anchored/XY-only：endpoint z 仅接受 `1e-9 m` 绝对容差，Ground
Truth 只施加刚体 XY 平移；悬空/倾斜墙仍不支持。A1 已验证现有 Focus objective，但在最终
quadrature/Profile 下的 coefficient 一致性仍须 FND-QA-CC 证明。
