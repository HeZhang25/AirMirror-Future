# Future Intelligent Workspace 双 Future RIS 演示

这是一个独立于 `future_dual_ris_demo.json` 的科研汇报场景。它使用 Scene v1
已有的 Wall/Obstacle、有限孔径 RIS、复数信道相干求和和 prepared 双 RIS 接口，
没有新增材料、门窗、曲面或第二套物理后端。

## 场景与传播关系

- 房间：`12 × 9 × 3 m`，`5 GHz`、`100 MHz`、`z_eval=1.2 m`。
- TX：`tx-workspace=(1.3, 2.1, 2.4) m`；RX：`rx-workspace=(10.5, 7.0, 1.2) m`。
- 7 道 Wall：4 道外边界，`meeting-partition`、`lab-partition`、`cross-partition` 三道内部隔断。
- 5 个 Obstacle：协作桌、实验台、仪器架、会议控制台、东侧储物柜；它们都进入现有阻挡/衰减模型。
- `ris-west-service=(1.2,5.0,1.6) m`，yaw `0`，法向 `+X`，服务西侧和隔断过渡区。
- `ris-east-service=(10.8,6.8,1.6) m`，yaw `π`，法向 `−X`，服务东侧工作/会议区。
- 两块 RIS 均为 `3×2 m`、`64×48`、连续相位、效率 `0.95`、Future、启用。

路线有 8 个控制点、`0–11.3 s` 单调到达时间、`0.5 s` 采样间隔，共 27 个采样时刻。
它依次经过 TX 直达服务区、会议隔断边缘、中央弱覆盖走廊和东 RIS 服务区。
路线使用 `airmirror_xr_route_experiment/1` 的连续 Wall/Obstacle 碰撞检查；当前
报告为 0 collisions、0 warnings。

## 可复现验证

在仓库根目录运行：

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
python tools/run_future_intelligent_workspace_demo.py
```

默认输出为 `results/demos/future_intelligent_workspace_dual_ris_1x1.json`。脚本只使用：

- `FAST_1X1_RIS_COEFFICIENT_MODEL`；
- `generate_dual_ris_coordinated_patterns`；
- `evaluate_dual_ris_command`；
- `prepare_controller_dual_ris_link`；
- `prepare_controller_dual_ris_field`（8×6）。

manifest 记录 No RIS、第一块 RIS、第二块 RIS、双 RIS 四种配置的复信道、功率、SNR、
完整合法相位命令摘要/哈希，以及 prepared coefficient identities。它还记录路线身份、
场景身份、机器、Python、模型身份和 8×6 构建计时；不复用旧场景性能数字。

本机一次验证（Windows 11、Python 3.14.3、Intel64）中，双 RIS 8×6 FAST 1×1
prepared field 的系数矩阵占 `4,718,592 bytes`，冷构建约 `1.17 s`。这不是完整 M8
benchmark；本演示不重复昂贵的 `48×36` M8 冷构建。

代表性目标点的现象保留真实结果：point-2 主要由西 RIS 服务，point-8 主要由东 RIS
服务；point-4/5 穿过隔断后有明显衰减；在 point-8 双 RIS 相比东 RIS 单独配置的
功率提升约 `1.05 dB`。其他点若双 RIS 不优于单 RIS，manifest 原样保留，不添加校准常数。

## GUI 操作（约 3 分钟）

1. 启动：`$env:PYTHONPATH=(Resolve-Path src).Path; python -m airmirror_future`。
2. Scenario 选择 `XR Scene & Route Editor · Prototype`。
3. 模板下拉框可选 `Future Intelligent Workspace · dual RIS demo`，或点击 `Load Scene`
   打开 `scenes/future_intelligent_workspace_demo.json`。
4. 点击 `Load Route`，打开 `scenes/future_intelligent_workspace_route.json`；检查状态为
   `Route valid`，路线控制点位于隔断与障碍物之间。
5. 保持 `高速 1×1 · prepared`、`8×6 · quick Windows gate`，点击
   `Build route fields · fast 1×1 · 8×6`。该入口会一次准备双 RIS 系数矩阵，并缓存
   Static/Adaptive 路线场图；不是旧的 `Run 3 Modes` 单 RIS 后端。
6. 结果完成后切换 `No RIS`、`Static RIS`、`Adaptive RIS`，拖动时间轴观察服务区切换；
   右侧 RIS pattern 面板可选择两块 RIS，查看独立命令。

原始 `scenes/future_dual_ris_demo.json`、原 manifest、原测试和历史结果不被此演示覆盖。
