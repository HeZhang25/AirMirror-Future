# Smart Space GUI 行为规格

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation planned semantics/labels |
| 对应需求 | AMF-UI-001..008、AMF-PHY-007、AMF-SIM-006 |

## 1. 页面组成

| 区域 | 固定职责 |
|---|---|
| 顶部 | 产品名、系统级近似副标题、Future 假设徽标 |
| 左侧 | 已实现场景、文件操作、显示层、Model Info |
| 中央 | Smart Space 俯视几何、场图、实体和显式路径 |
| 右侧 | 代际、RF/RIS/误差参数、优化、场图质量、phase pattern |
| 底部 | Power、SNR、RIS Gain、Coverage、Dead Zone、Runtime |
| 状态栏 | 当前任务开始/进度/完成/取消/失败 |

场景选择器只包含可运行的 Future Smart Space。XR、Factory、City 只在不可交互路线文字
中出现，直到各自通过 release gate。

## 2. 主画布

- x 向右、y 向上；Qt 屏幕 y 在显示边界翻转，模型坐标不变；
- TX 红色圆点、RX 绿色圆点、RIS 紫色线段、墙灰白、障碍物橙色；
- TX/RX/RIS 可拖动并限制在 room 平面范围内，z 保持原值；
- 拖动任一实体立即使旧 task version 失效，重新计算目标 Physics Focus、目标指标并
  debounce 新场图；
- 直接射线和 RIS 两段射线只表示模型显式计算的主要路径，不生成装饰射线；
- 场图 y 轴只在图像显示时翻转；数组和保存数据维持数值升序。

### 显示层

| 开关 | 行为 |
|---|---|
| Show Field | 显示/隐藏当前 quantity 热力图，不重新计算 |
| Show Rays | 重绘显式 LOS 与 RIS 中心路径 |
| Show RIS Pattern | 显示/隐藏 commanded/actual tabs |
| Show Coverage | 以场景 SNR threshold 叠加透明覆盖/红色 dead-zone |
| Show Labels | 重绘 TX/RX/RIS 标签 |

显示开关不得改变物理结果或 metrics。

## 3. 参数契约

### RF

| 控件 | UI 单位 | 范围 | 应用到 |
|---|---|---:|---|
| Frequency | GHz | 0.1..300 | `Scene.frequency_hz` |
| TX Power | dBm | -30..80 | `Transmitter.power_w` |
| Bandwidth | MHz | 0.001..5000 | `Scene.bandwidth_hz` |
| Noise Figure | dB | 0..30 | `Receiver.noise_figure_db` |
| Coverage SNR | dB | -30..100 | `Scene.coverage_threshold_db` |

Foundation FND-PHY-NB 的目标文案：Frequency 明确标为中心频率；Bandwidth 明确标为等效占用/
接收噪声带宽。Model Info 必须说明 `h(fc)` 在 `B` 内按平坦处理，任何容量显示必须写“平坦信道
Shannon 理论上界”，TX Power 是该带宽内总功率而非 PSD；不能写 OFDM 容量或真实吞吐。该标签
更新仍为 Planned。

### RIS

| 控件 | 范围/状态 | 行为 |
|---|---|---|
| Width/Height | 0.05..20 m | 改变实体孔径并使 pattern 失效 |
| Nx/Ny | 1..256 | 等效可控孔径 patch 数；改变控制/中心采样网格并重新生成 pattern |
| Phase Bits | 1/2/3/4/continuous | Focus 输出按新状态量化 |
| Efficiency | 0..1 | 无源功率效率 |
| Update Rate | 0.1..1e6 Hz | 元数据；v0.1 静态计算不模拟控制时延 |
| Self Sensing | bool | 元数据；不自动降低误差或改变算法 |

当前字段 `Nx/Ny` 不得标注为真实 meta-atoms、antenna elements 或制造单元。Foundation A2
提供 `equivalent_patch_diagnostics()`，供 B 阶段以只读形式显示 effective pitch、运行波长和
`pitch/lambda`；这些值不得带“通过/失败”或 `lambda/2` 合规提示。A2 本身不改变当前 GUI
状态机，也不新增可点击入口。频率变化不得自动改写 Width/Height 或 Nx/Ny。

Foundation B 的 Model Info/结果说明还必须标注当前 production aperture integration 为
`1×1 midpoint per equivalent control patch`，并把精确 dBm 解释为 current scalar
center-point model 输出。FND-QA-AP Verified 前不得显示“quadrature converged”“EM accurate”或
把小数位数当作物理精度；GUI 不新增 quadrature order 可编辑控件，除非后续 production policy
Work Item 明确授权。

### Ground Truth

GUI v0.1 暴露 phase error、measurement noise 和 position error sigma；点击 Apply 才创建新
GroundTruthModel。未暴露的效率/墙误差通过 headless API 配置。

Position Error 为各实体生成三维 delta；FND-FIX-WALL 已冻结 engine 消费语义：TX/RX/RIS/
obstacle 按各自三维模型处理，floor-anchored wall 只使用同一个刚体 XY 偏移。B3 接线后的准确
tooltip 必须使用该措辞，不得声称墙体存在 vertical position error。

Apply 使用 dataclass replace 重建并校验对象。任何错误用对话框明确显示，旧 scene 保持
有效。Apply 后自动生成 Physics Focus，即使算法下拉框仍显示 Feedback；用户若需要反馈
结果必须再次点击 Optimize。

## 4. 技术代际

切换 Current/Advanced/Future 时：

1. 保留 RIS id、position、yaw 和整个 room scene；
2. 用 `generation_preset` 替换孔径、网格、相位、效率、更新率、自感知；
3. 同步控件；
4. 生成 Physics Focus；
5. 更新目标指标并后台重算场图；
6. Future 显示 `Future Scenario Assumption`。

代际不是主题颜色，不允许额外乘增益。

## 5. 优化交互

| 选择 | 点击 Optimize 后 |
|---|---|
| Physics Focus | 主线程快速生成 pattern，随后后台重算场图 |
| Feedback Greedy | worker 从全零 pattern 开始，仅用 oracle 测量 |
| Physics-Guided Feedback | worker 从 Physics Focus 开始反馈细化 |

Feedback 显示 tile 进度和当前 dBm，Cancel 设置 worker cancellation。完成后 pattern、目标
metrics 和场图更新；取消结果不覆盖现有 pattern。

## 6. 场图和任务状态机

质量映射在 GUI 与 headless 统一：

| Quality | Grid |
|---|---:|
| Fast | 80×60 |
| Balanced | 120×90 |
| High | 200×160 |

```text
Idle
 -> Start(version N, deep-copied inputs)
 -> Running
    -> Cancel/parameter change: invalidate N -> Idle/debounced next task
    -> Error at current N: show error -> Idle
    -> Result at old N: discard silently
    -> Result at current N: render + metrics -> Idle
```

quantity 在 Power/SNR/RIS Gain 间切换只重绘已有 `FieldMapResult`，不触发物理重算。

当前 Field Map 将同一组 fixed RIS commanded pattern 用于所有评价点；它表示“固定配置下的空间
分布”，不是每个像素分别重新聚焦后的最优包络。Coverage/Dead Zone 必须沿用这一解释。

## 7. 场景保存和加载

- Save 只保存 Scene v1，不保存 current pattern、algorithm、Ground Truth sigma、窗口状态或
  heatmap；
- Load 校验 v1，要求 GUI 至少有一个 TX、RX 和 RIS；
- Load 后同步 RF/RIS 控件、重建 Physics Focus 并重算；
- 若未来需要保存控制状态，必须升级 schema，不能偷偷加入 GUI 私有字段。

## 8. 人工验收清单

1. 启动后中文正常、模型标签可见，场图完成时 UI 可继续拖动；
2. 拖 RX，旧图不会在新位置后覆盖；
3. Current→Future 时 scene 不移动，Future 徽标出现且参数真实变化；
4. Show Field/Rays/Pattern/Coverage/Labels 各自只影响显示；
5. Phase Error 后 commanded 与 actual 图不同；
6. Feedback 可显示进度并取消；
7. Save/Load 后 scene 数值往返一致，pattern 重新生成；
8. Model Info 正确声明系统级近似、Shannon 上界、当前 `1×1` center-point policy、A2 semantic
   与 discretization accuracy 的状态边界，以及 partial-aperture blockage 未实现。
9. Foundation 完成时，Model Info 同时声明中心频率平坦信道、固定 pattern 场图和 wall 仅 XY
   误差；这些计划文案不得在对应实现/测试完成前误标为 Verified。
