# Future 双 RIS 可复现场景

该演示使用仓库现有的单一 prepared 实现，不包含或依赖第二套 prepared 模块。运行前应先
`git fetch origin main` 并核对当前分支与实际远端 `main`，不要把文档中的历史 SHA 当作最新基线。

场景文件为 [scenes/future_dual_ris_demo.json](../scenes/future_dual_ris_demo.json)，符合现有 Scene v1 格式。它包含：

- `tx-demo`、`rx-demo`，接收目标为 `(8.5, 4.0, 1.2) m`；
- `ris-north` 与 `ris-east` 两块独立 Future RIS，均为 `3.0 m × 2.0 m`、`64 × 48` 控制网格、连续相位、效率 `0.95`；
- 现有 10 m × 8 m 房间、partition 与 cabinet 几何，用于保留真实 Profile/blocker 计算。

运行：

```powershell
$env:PYTHONPATH='src'
python -B tools/run_future_dual_ris_demo.py
```

脚本显式选择 `FAST_1X1_RIS_COEFFICIENT_MODEL`，调用现有 `generate_dual_ris_coordinated_patterns` 与 `evaluate_dual_ris_command`，并将 No RIS、每个单 RIS、双 RIS 的合法命令和真实信道/功率/SNR 保存到 [results/demos/future_dual_ris_demo_1x1.json](../results/demos/future_dual_ris_demo_1x1.json)。Scene v1 不保存 patterns，因此命令保存在该结果 manifest 中。

结果仅是该几何、目标点、模型身份和命令下的可复现数值，不预设双 RIS 必然优于单 RIS；比较应使用 manifest 中的总复信道和总功率。

## Windows GUI 快速操作

请从准备运行的仓库目录启动；如果机器上保留了旧 checkout，先打印解释器、包路径、GUI
模块路径和 Git SHA，避免 editable install 或 `PYTHONPATH` 指向旧目录：

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
python -c "import sys, airmirror_future, airmirror_future.gui.main_window as gui; print(sys.executable); print(airmirror_future.__file__); print(gui.__file__)"
git rev-parse HEAD
python -m airmirror_future
```

在应用中：

1. 在 `Scenario` 选择 `XR Scene & Route Editor · Prototype`。
2. 点击 `Load Scene`，打开 `scenes/future_dual_ris_demo.json`。
3. 在画布中直接拖动 TX、RX、两块 RIS 或蓝色路线控制点；释放鼠标后坐标提交到模型并使旧场图失效。也可在左侧选择 `ris-north` / `ris-east` 后精确输入坐标并点击 `Apply selected RIS`。
4. 保持 `高速 1×1 · prepared` 和 `8×6 · quick Windows gate`，点击 `Build field · fast 1×1 · 8×6`。
5. 完成后切换 `No RIS`、`Static RIS`、`Adaptive RIS`。右侧 pattern 面板显示下拉框当前所选 RIS 的独立命令；单击画布中的 RIS 也会同步选择。
6. 要检查单 RIS 退化，在下拉框选择一块 RIS、取消 `Enabled` 并应用；重新计算前旧结果会被明确清除。双 RIS Future 使用 prepared 场图入口，旧的 `Run 3 Modes` 入口会保持禁用。

界面仍标记为 non-release XR Editor Prototype；8×6 是快速 Windows 验收网格，不代表完整
48×36 场图精度或正式产品能力。
