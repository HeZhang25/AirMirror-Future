# Future 双 RIS 可复现场景

该演示基于仓库当前 `main`（PR #25 后的 `028b881a353a05972f8fcc3f398abd01d2fd3196`），不包含或依赖重复的 prepared 模块 `2767ffdfe75e74e48f976fda51e49a58e642779f`。

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
