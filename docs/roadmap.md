# 路线图、阶段门禁与工作颗粒度

| 属性 | 值 |
|---|---|
| 文档状态 | Operational / Normative for sequencing |
| 当前 release | v0.1 Verified，P1 性能与误差实验准备中 |

## 1. 统一规划层级

| 层级 | 大小 | 示例 | 状态汇报方式 |
|---|---|---|---|
| L0 Vision | 多 release | Programmable Electromagnetic Space | 不报告百分比 |
| L1 Release | 多个 capability | v0.2 Dynamic XR | 以 capability gate 汇总 |
| L2 Capability | 完整用户/研究能力 | Phase Error Robustness | Proposed→Verified |
| L3 Deliverable | 可独立验收纵向结果 | 三算法共享 seed 的 CSV | 入口/输出/验收 |
| L4 Task | 0.5–2 天工程工作 | 实现 phase sigma sweep CLI | done/not done |

状态页同一列表只能放同一层级。禁止把“实现一个函数”和“完成 Future City”放成并列步骤；
禁止用文件数或代码行数表示 capability 完成度。

## 2. 依赖路线

```text
v0.1 Smart Space (Verified)
  -> P1A geometry coefficient cache
  -> P1B phase-error statistical experiment
       -> v0.2 XR dynamic engine
            -> v0.3 Factory multi-user/multi-RIS
                 -> v0.4 City geometry and corridor
  -> P1C aperture experiment (may run after cache)
```

后续场景不能越过依赖门禁。尤其 Factory 的多 RIS 和 City 的立面网络依赖统一的多 RIS
pattern ownership；不能各自实现不兼容版本。

## 3. v0.1 Smart Space — Verified

已交付 capabilities：

- C01 Core SI Geometry and Scene v1；
- C02 Complex LOS/Blockage/One-bounce Wall；
- C03 Finite Passive RIS and Physics Focus；
- C04 Smart Space Headless + FieldMap；
- C05 Interactive GUI and Background Workers；
- C06 Controller/Ground Truth + Feedback；
- C07 Phase Resolution Experiment；
- C08 Documentation and Traceability Baseline。

已知技术债不回写为“未完成 v0.1”：矩阵缓存未启用、反馈非增量、高质量 Future 较慢、
id 错误异常待统一。这些进入 P1 tasks。

## 4. P1：性能与模型误差研究

### Capability P1A — Geometry Cache and Matrix Evaluation

Deliverables：

1. 规范 geometry/cache key 和 invalidation；
2. 预计算单点 `a_n` 和多点分块 A；
3. pattern 更新只执行 `A @ Gamma`；
4. Greedy 单 tile 使用复场增量；
5. Current/Advanced/Future 性能、内存和数值等价基准。

Exit gate：与 v0.1 scalar/reference 结果在声明容差内一致；全部失效测试通过；同机 Fast
基准显著改善或给出为何不采用的 ADR。

### Capability P1B — Phase Error Robustness

Deliverables：多 seed runner、Physics/Feedback/Physics-Guided 公平对照、median/quantile CSV、
PNG、运行配置元数据、研究结论和限制。

Exit gate：三算法共享每个 seed 的 truth；结果可完全重放；不以单 seed 下结论。

### Capability P1C — Aperture Sweep

Deliverables：定义固定 cell density/固定 cell count 两类实验、孔径适用域警告、target gain
与 coverage 输出、异常趋势检查。

## 5. v0.2：XR / Spatial Computing

Entry gate：P1A Verified；动态状态和轨迹 schema ADR 完成。

Deliverables：人体吸收体、`position(t)`/head orientation、28/60 GHz preset、No/Static/Adaptive
RIS、SNR(t)、outage probability、更新率和 heatmap cadence、headless dynamic experiment、GUI
Play/Pause。

Exit gate：转身遮挡造成模型产生的链路下降；adaptive 依据明确更新策略重构；outage 定义和
轨迹可重放；GUI 不逐帧强制高分辨率场图。

## 6. v0.3：Future Smart Factory

Entry gate：多 RX API、objective ADR、多 RIS pattern ownership 完成。

Deliverables：20×12 m、金属遮挡、3 AGV、2–3 RIS、所有 RIS 单跳复场、average/min-user
SNR、No/Single/Multi/Cooperative 对照、RIS Count 实验。

双 RIS 连跳不是 release 必需项；若加入，需单独建模额外传播、效率和计算复杂度。

## 7. v0.4：Future City / Low-Altitude Network

Entry gate：Factory 多 RIS Verified；城市几何性能预算完成。

Deliverables：建筑、BS、vehicle/UAV、facade RIS、轨迹、NLoS、No/Single/Multi/Cooperative、
coverage corridor 指标与动态场图。Electromagnetic Corridor 必须由路径模型和阈值连续性
定义，不能手绘。

## 8. Future Extensions — Proposed

宽带、STAR、active、space-time、communication+sensing、localization、WPT、physical-layer
security 和应急 RIS 均为 Proposed。每项独立 ADR 和物理模型；不共享一个“Future mode”
开关绕过建模。

## 9. 每轮开发计划模板

每轮最多选择一个 L2 Capability，拆成 3–7 个 L3 Deliverables；每个 Deliverable 再拆
0.5–2 天 L4 Tasks。计划必须列 requirement IDs、输入/输出、测试、依赖、风险和 exit gate。
模板见 [templates/work_item.md](templates/work_item.md)。

