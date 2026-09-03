# Results

Headless experiments write reproducible CSV and PNG artifacts below this directory.

`phase_bits/`（如存在）属于 v0.1 RIS-only/current scalar center-point model 的 legacy 输出；
小数位数不代表已验证的 aperture quadrature accuracy。

Foundation `FND-QA-AP` 当前为 Planned，本目录尚无正式 aperture quadrature validity 结果。未来
QA 必须写入新的 versioned/no-overwrite run 目录，并记录 model/Profile/pattern/quadrature
policy identity。不得把一次临时复算或固定 16×16 输出标为 Ground Truth/EM truth。

2026-09-03 的 `checkpoints/foundation_0_1_1_ab_checkpoint_20260903/` 是 Foundation 0.1.1
A/B Interim Checkpoint 的隔离输出，仅标记为 checkpoint / non-formal provenance。它不是正式
Foundation experiment，不覆盖 `phase_bits/` legacy，也不回填 C2 尚未完成的 provenance 字段。
