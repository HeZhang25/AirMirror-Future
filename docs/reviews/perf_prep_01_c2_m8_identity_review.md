# PERF-PREP-01 独立复核：QA-AP / C2 production M8 identity

- 审查基线：`87d2dea8c3ca40774f754271d7b21743cefcc133`
- 环境：Windows build 26200，Python 3.11.4，NumPy 2.4.6；BLAS 线程基线固定为 1
- 审查角色：D；未参与 M8 production migration 实现

## 读取对象

- QA-AP Work Item、signed preregistration 和 reference-resolution configs；
- production migration commit `350fcba72c8d771fa9bfdf2b7aabb6519689d815`；
- `ris/quadrature.py`、`physics/ris_scattering.py`、`simulation/engine.py`；
- C2 `experiments/provenance.py` 和 tests；
- `tests/test_production_quadrature.py`、QA-AP/provenance focused evidence。

## 独立结果

- PASS：production rule 是 midpoint 8×8 per control patch；control count、pattern shape 和
  `parent_control_index = repeat(arange(control_count), 64)` 保持 canonical mapping；
- PASS：field-map 一次 call 只构造一份 M8 sample table 并复用；
- PASS：receiver×sample intermediate pair count 受 `_MAX_POINT_SAMPLE_PAIRS=262144` 约束；
- PASS：Current/Advanced/Future production M8 channel 均有限；
- PASS：C2 新结果保持 schema v1、no-overwrite/pending owner 边界；不猜 legacy；
- PASS：focused tests 与 documentation tests 通过。

## 发现与边界

QA-AP Work Item 已记录 Verified 和 signed M8 policy，production migration 也已完成；但
`results/README.md` 仍有“QA-AP Planned / 尚无正式结果”的旧文本。该差异不影响代码测量，
但应由独立文档/status 任务校正，不能在性能 PR 中混改。

本审查不签署 `coefficient_model_identity`：QA-CC 尚未完成，共享 coefficient source 和完整
identity/invalidation matrix 仍是后续 owner 工作；不得将 M8 policy ID 当作 coefficient identity。
