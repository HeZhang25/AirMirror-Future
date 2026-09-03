# 产品与工程基线

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 |
| 变更方式 | ADR + requirements 更新 + 测试证据 |

## 1. 产品定义

AirMirror Future 是“物理约束的系统级 RIS 数字孪生与未来场景推演平台”。它要让用户
直观看见传播环境 `H` 如何随 RIS 配置状态 `S` 变为 `H(S)`，从而理解从
Programmable Network 到 Programmable Electromagnetic Space 的可能演进。

产品不是 RIS 参数计算器，也不是通过美术效果展示“信号变强”的动画。任何热力图、
路径和指标都必须来自明确的传播模型。

## 2. 目标用户与核心任务

| 用户 | 核心任务 | v0.1 支持 |
|---|---|---|
| 学生/教师 | 理解相位、干涉、孔径、量化和遮挡 | 是 |
| RIS 研究人员 | 快速验证系统级趋势和优化先验 | 部分；窄带、单 RIS |
| 产品/规划人员 | 比较 Current/Advanced/Future 假设 | 是，明确标注假设 |
| 全波仿真工程师 | 替代 CST/HFSS 获得器件级精度 | 否，明确非目标 |

首要用户旅程：打开 Smart Space → 看见遮挡弱区 → 启用/优化 RIS → 拖动 RX →
观察复场和热点重构 → 改变代际或误差 → 比较指标。

## 3. 方法论不变量

以下约束高于界面效果、运行速度和演示叙事：

1. Maxwell 基本规律、相位演化和复场叠加不能被绕过；
2. 所有内部量使用 SI，显示层负责单位换算；
3. 无源 RIS `0 ≤ η ≤ 1`，不得使用隐藏增益常数；
4. 单元总有效面积不得超过实体孔径；固定孔径细分不得产生无界 patch-count gain；严格数值
   收敛声明必须固定 control/pattern、只细化独立 quadrature，并通过 successive/cross-rule 证据；
5. LOS、墙反射和 RIS 路径先在复数域相加，再计算功率；
6. 多次传播或反射必须带来相应距离和效率损耗；
7. Future 只能通过显式孔径、效率、相位精度、更新率等参数表达；
8. 随机模型必须有固定 seed，实验可重放；
9. Controller Model 与 Ground Truth 必须隔离，反馈算法只读 measurement oracle；
10. Shannon 容量只能称为中心频率平坦信道理论上界；系统模型不能冒充宽带、协议或全波结果；
11. model-based Focus 必须优化 Controller simulator 使用的同一 nominal coefficient，不能读取
    Ground Truth coefficient；
12. 场景环境 modifier、Wall/Reflection Model 的 `Gamma_wall`、RIS device response 和
    Controller/Ground Truth uncertainty 必须保持独立所有权；任何反射/器件因子只应用一次。

违反任一项属于 P0 缺陷，不允许通过放宽测试阈值掩盖。

## 4. v0.1 固定范围

### In scope

- Python 3.11+、CPU、离线、Windows 优先；
- 三维实体位置与二维俯视显示；
- 中心频率平坦窄带复数 Friis LOS、几何阻挡、一次墙面镜面反射；
- 单次 `TX → RIS → RX`、有限孔径和前向方向图；
- continuous 与 1/2/3/4-bit 相位、Physics Focus；
- Current/Advanced/Future 可编辑代表性 preset；
- Smart Space 场景、场图、功率、SNR、RIS Gain、Coverage、Dead Zone；
- Controller/Ground Truth、Feedback Greedy、Physics-Guided Feedback；
- JSON 场景、headless 命令、phase-bits 实验、PySide6 GUI；
- 后台执行、取消、过期结果丢弃。

### Out of scope

- 完整三维全波、衍射、高阶反射、极化、互耦和材料色散；
- active RIS、STAR-RIS、space-time modulation；
- 宽带 OFDM、MIMO 和真实协议栈；
- XR、Factory、City 的可运行实现；
- 多 RIS 联合优化、双 RIS 连跳和多用户 max-min；
- 将 Shannon 上界称为真实吞吐量或 Privacy Mode 称为加密替代品。

## 5. v0.1 质量目标

| 维度 | 验收基线 |
|---|---|
| 可安装 | `python -m pip install -e ".[dev]"` 成功 |
| 可启动 | `python -m airmirror_future` 打开 Smart Space GUI |
| Headless | 指定场景、代际、质量后输出结构化指标 |
| 正确性 | `requirements.md` 中所有 Implemented 条目有自动或人工证据 |
| 物理合理性 | 必需物理测试、孔径不发散/独立求积门禁和 focus/random 对照通过；不把内部参考称全波真值 |
| 稳定性 | 非法参数明确报错，不产生未处理 NaN/Inf |
| 交互性 | 场图/优化不阻塞 GUI；可取消；旧任务不覆盖新场景 |
| 可信度 | UI 显示模型定位、Future 假设和限制 |
| 文档性 | 本目录链接、需求编号和实现状态校验通过 |

性能不以单一机器上的绝对秒数作为规范，因为 CPU 和 NumPy 构建差异很大。门禁是 GUI
线程持续响应、任务可取消，同时 `DEVELOPMENT_STATUS.md` 记录实测参考时间。

## 6. 默认 Smart Space 基线

权威数据文件是 `scenes/smart_room.json`：

- 房间 `10 × 8 × 3 m`，评价高度 `1.2 m`；
- `f=5 GHz`、`Pt=20 dBm`、`B=100 MHz`、`NF=7 dB`；
- TX `(1,4,2.4)`，RX `(8.5,4,1.2)`；
- 内墙 `x=5, y=2..6`，LOS 衰减 `30 dB`；
- RIS 中心 `(5,7.9,1.5)`，法向朝向房间；
- Coverage 定义为 `SNR ≥ 35 dB`，是演示阈值而非通信标准。

默认值改变属于行为变化，必须更新场景 JSON、实验基准、README、requirements 和 ADR。

## 7. 发布原则

一个版本只能承诺已经实现并验证的能力。Planned 页面不进入场景选择器；disabled
placeholder 只有在能准确表达路线且不会被误认为可用功能时才允许出现。任何新场景先
完成 headless 垂直切片和物理验收，再加入 GUI。
