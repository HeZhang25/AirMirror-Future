# Work Item：Foundation 0.1.1C PropagationProfile and Minimum Provenance

- 层级：L3 Deliverable（含可独立评审的 C1/C2）
- Task IDs：FND-ARCH-01、FND-EXP-01
- Requirement IDs：AMF-SIM-005、AMF-EXP-006
- 状态：Ready
- 父项：Foundation 0.1.1
- 依赖：Foundation 0.1.1A Verified、FND-FIX-WALL Verified、Foundation 0.1.1B Verified、
  A/B Interim Checkpoint PASS、ADR-0011/0012 Accepted
- Ready 基线：`d9ab04a502055af3b519a781629e6e83f0ded9d8`
- 不属于：FND-QA-AP、FND-PHY-NB、FND-QA-CC、production quadrature migration、P1A cache、
  coefficient builder、新场景、mixed wall-RIS path、per-patch blockage、PathEnsemble/fading/OFDM

## Definition of Ready / Ready Review

2026-09-03 Ready Review 结论：**Ready / blocking ambiguity 0**。

2026-09-04 对 `950e1466661bc73773cb483e2fec1930bcfb354f` 的独立审查意见完成 focused correction：
修正历史结果分类、FND-T14 范围、path-specific 距离有效性所有权及 version/seed 类型文字。
C1/C2 保持 Ready，blocking ambiguity 0；不改变 ADR-0012 ownership 或进入实现。

本 Work Item 只冻结 C1/C2 的实现边界、接口、数据、错误和验收条件；本次评审没有修改 Python、
tests、results、GUI 或 Scene，也不构成 C1/C2 Implemented/Verified 证据。ADR-0011 已冻结
`geometry/environment -> a^GT`、`RIS phase/efficiency error -> Gamma_actual`，ADR-0012 已冻结
Profile/Reflection 的因子所有权；以下决定只把两份 Accepted ADR 明确留给 C Ready Review 的
类型、序列化和 provenance 细节闭合，不实现最终 coefficient builder。

未发现需要新 ADR 的高影响选择。若实现发现必须改变下列任一项，应停止 C、建立新 ADR 并重新
执行 Ready Review：Profile 返回 full transfer/path ensemble、`Gamma_wall` 归属、Scene v1
持久化、Controller/Ground Truth 隔离、反射路径集合或默认 v0.1 数值行为。

## 目标与用户结果

C1 完成后，所有现有确定性环境路径都通过一个最小、可注入、可识别的 environment-only
`PropagationProfile`，且默认实现可解释地复现基线。C2 完成后，每个新的 Foundation 实验运行
都能说明实际使用的 Focus/Profile/Reflection/world model，并诚实标记尚未由后续工作项签署的
identity；历史结果保持原样且不会被覆盖。

## In / Out

包含：

- C1 Protocol/context、五个固定 path roles、默认不可变 Profile 和跨进程稳定 identity；
- direct、两段 reflection、两段 RIS environment modifier 的统一 engine 编排；
- `single_wall_reflection` 的几何/carrier 与 coefficient/modifier 拆分；
- reflecting-wall self-exclusion、duplicate wall ID 拒绝和因子唯一应用测试；
- C2 provenance schema v1、legacy 分类、pending-contract 标记和 no-overwrite 输出目录；
- `FND-T13..T15` 自动测试、三代 headless 兼容回归和人工 ownership/provenance review。

不包含：

- 选择或迁移 production quadrature policy，或实现最终 `a_n` coefficient builder；
- 签署 `FND-QA-AP`、`FND-PHY-NB`、`FND-QA-CC` 所拥有的 future identities；
- P1A cache/key 实现、矩阵化、增量 Greedy 或性能重写；
- 新传播路径、新场景、高阶/混合反射、逐 patch 遮挡、PathEnsemble、fading、delay、Doppler、
  frequency-selective channel 或 OFDM；
- GUI、Scene JSON v1 字段/结构、历史结果内容或完整历史迁移工具；duplicate wall ID 仅作不升
  schema version 的 validation tightening。

## C1：PropagationProfile

### C1.1 模块与精确 Protocol

实现目标位于 `airmirror_future.simulation.profiles`。以下名称、字段和签名已冻结；除修正明显的
typing 拼写外不得在实现中另行发明同义接口：

```python
PropagationPathRole = Literal[
    "direct",
    "reflection_before",
    "reflection_after",
    "ris_incident",
    "ris_scattered",
]

CanonicalParameter = None | bool | int | float | str
CanonicalParameters = tuple[tuple[str, CanonicalParameter], ...]

@dataclass(frozen=True, slots=True)
class PropagationPathContext:
    role: PropagationPathRole
    start: Vec3
    end: Vec3
    reflecting_wall_id: str | None = None
    ris_id: str | None = None

@dataclass(frozen=True, slots=True)
class PropagationModifier:
    value: complex
    blocker_ids: tuple[str, ...] = ()

@runtime_checkable
class PropagationProfile(Protocol):
    @property
    def profile_id(self) -> str: ...

    @property
    def profile_version(self) -> str: ...

    @property
    def canonical_parameters(self) -> CanonicalParameters: ...

    def environment_modifier(
        self,
        *,
        scene: Scene,
        context: PropagationPathContext,
    ) -> PropagationModifier: ...

def profile_identity(profile: PropagationProfile) -> str: ...
```

`SimulationEngine` 的唯一新增构造边界为：

```python
SimulationEngine(profile: PropagationProfile | None = None)
```

`None` 必须在构造时解析为一个新的 `IndoorDeterministicProfile()`；engine 之后只通过只读
`profile`/`profile_identity` 属性暴露该快照，不提供运行中 setter。`compute_channel` 和
`compute_field_map` 的参数、`ris_patterns` shape 与 `ChannelResult`/`FieldMapResult` 保持不变。
Protocol、context、modifier result、默认 Profile 和 identity helper 是模块级公共构造接口；本阶段
不建立 entry-point、动态 import、注册中心、配置 DSL 或 Profile 插件生命周期。

### C1.2 Context 与五类 path role

`scene` 是 engine 为本次 Controller 或 Ground Truth 计算显式选定的 working-scene 快照；Profile
只可读取环境阻挡所需的 wall/obstacle 几何、`attenuation_db`、`fully_blocking` 和 `blocks_los`。
Profile 不接收 `ControllerModel`/`GroundTruthModel`、seed、sigma、position-delta/RIS-error callback、
nominal/actual 标签或 MeasurementOracle，也不得读取/生成隐藏 realization。engine 负责先建立
working scene；Profile 对显式给定的相同 scene/context 做纯确定性求值，不能选择 world model。

| role | `start -> end` | 必需 identity | 禁止 identity | 调用时机 |
|---|---|---|---|---|
| `direct` | working TX -> working RX | 无 | wall/RIS ID | 每个 link 恰好一次 |
| `reflection_before` | working TX -> reflection point | `reflecting_wall_id` | RIS ID | 每条有效一次反射路径恰好一次 |
| `reflection_after` | reflection point -> working RX | `reflecting_wall_id` | RIS ID | 每条有效一次反射路径恰好一次 |
| `ris_incident` | working TX -> working RIS center | `ris_id` | wall ID | 每块 enabled 且有 validated pattern 的 RIS 恰好一次 |
| `ris_scattered` | working RIS center -> working RX | `ris_id` | wall ID | 与 incident 成对调用一次 |

`PropagationPathContext.__post_init__` 必须拒绝未知 role、非有限坐标、空 ID 和 role/ID
组合不一致；engine 在创建 context 前拒绝引用不存在或不唯一的 wall/RIS；RIS ID 校验沿用既有
commanded-pattern 边界，C1 对既有输入接受域只新增 duplicate wall ID tightening。
Context 不统一检查 `start.distance_to(end)`：direct 距离和 reflection 总路径长度继续由既有
`complex_free_space_channel` 校验，RIS 的 TX/RX-to-cell 最小距离继续由 scattering kernel 校验。
不得新增 reflection 单 leg 或 RIS center environment leg 的 `MIN_DISTANCE_M` 拒绝，包含零长度
在内的路径有效性仍按既有 physics kernels 决定。无有效反射点、disabled
RIS 或没有 commanded pattern 的 RIS 不创建对应 context，也不调用 Profile。RIS 两段保持 v0.1
的面板中心标量 modifier；不得按 patch 或 quadrature sample 调用 Profile。

### C1.3 输出、异常与 finite contract

- 返回值必须是 frozen `PropagationModifier`。`value` 是无量纲 complex scalar；默认纯幅度衰减
  必须显式返回 `complex(a, 0.0)`；
- `value.real/imag` 必须 finite；零允许，幅值不在 Protocol 层施加无来源的统一上界；
- `blocker_ids` 只作诊断，必须是 non-empty string 的 tuple；它不触发第二次衰减或任何乘法。
  默认 Profile 保持当前 wall-then-obstacle traversal order，使 LOS/RIS `path_details` 可继续报告
  相同 blocker IDs；自定义 Profile 可以返回空 tuple；
- Profile 不得在返回值中包含 Friis 距离/相位、TX/RX gain、`Gamma_wall`、RIS aperture/direction/
  efficiency/phase、noise 或 link metric；
- 非法 Profile ID/version/canonical parameter 或非法 context 抛 `ValueError`；不支持五个必需 role
  中任一个属于实现不合约，必须明确失败，不能回退为 `1+0j`；
- engine 将 `value` 规范成 Python `complex` 并复核 finite，同时验证 `blocker_ids`；错误的 result
  类型、非标量、不可转换、NaN/Inf 或非法 blocker tuple 以包含 `profile_id` 和 role 的
  `ValueError` 失败；
- Profile 自身抛出的异常不被静默吞掉、替换或降级；既有 `SimulationCancelled`、active-RIS
  `NotImplementedError` 和 physics `ValueError` 契约保持不变。

### C1.4 默认 Profile、determinism 与 immutability

`IndoorDeterministicProfile` 冻结为 `@dataclass(frozen=True, slots=True)`，无可变字段、RNG、时钟、
全局状态或缓存副作用：

```text
profile_id = "indoor_deterministic"
profile_version = "1"
canonical_parameters = ()
```

硬编码的 v0.1 blocker 算法和 fully-blocking `300 dB` 行为由 `profile_version="1"` 版本化，不伪装成
用户参数；未来改变该算法必须提升 version。scene 中的墙/障碍物几何和衰减值是本次 world 输入，
不属于 `canonical_parameters` 或 `profile_identity`。

默认输出精确复用当前 `path_attenuation_amplitude` 的 `(attenuation, blockers)` 语义：命中墙/
障碍物的 dB 值相加后转换为 `PropagationModifier.value`，blocker list 转为 tuple；reflection roles
另外排除反射墙自身。相同显式 scene/context 在同一受支持运行时重复调用必须逐位一致；跨平台
只承诺下述数值容差，不承诺不同数学库的 bitwise equality。

数值兼容 reference 固定为 Ready 基线 `d9ab04a502055af3b519a781629e6e83f0ded9d8`。Current、Advanced、
Future 及定向 reflection/blockage fixture 的 `los_channel`、每条 wall contribution、`wall_channel`、
`ris_channel` 和 `total_channel` 必须满足 `rtol=1e-12, atol=1e-15`，路径集合和 blocker IDs 不变。
这只证明职责抽取没有数值迁移，不签署 quadrature accuracy 或 coefficient consistency。

### C1.5 Stable canonical identity

`profile_identity()` 由公共 helper 计算，不能信任对象地址、类名、显示名、`repr()` 或 Python
`hash()`。ID、version 和 parameter key 必须匹配 ASCII
`[a-z0-9][a-z0-9_.-]*`；parameter tuple 按 key 升序且 key 唯一。

canonical scalar 使用带类型标签的 JSON array：

| Python 值 | canonical form |
|---|---|
| `None` | `["null",null]` |
| `bool` | `["bool",true|false]` |
| `int`（bool 除外） | `["int","<base-10>"]` |
| finite `float` | `["float64_hex","<value.hex()>"]` |
| `str` | `["str","<exact Unicode string>"]` |

payload 固定为：

```text
[
  "airmirror_profile_identity", 1,
  ["str", profile_id],
  ["str", profile_version],
  [[parameter_key, tagged_value], ...]
]
```

使用 `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"))` 的 UTF-8 bytes，
输出 `profile_identity = "sha256:" + sha256(payload_bytes).hexdigest()`。不做 Unicode normalization；
字符串的精确 code points 属于参数语义。`-0.0` 与 `0.0` 保持不同；若某 Profile 认为二者等价，
应在构造阶段规范化。此有限 scalar tuple 是 Foundation v1 的有意边界；需要嵌套结构时先版本化
identity schema，不在各 Profile 中自行序列化。

ID/version/任一参数的类型或值改变必须改变 identity；相同输入跨独立 Python 进程产生相同 identity。
`Gamma_wall`、scene geometry、world realization、frequency 和 quadrature 不进入
`profile_identity`，但未来总体 coefficient/world-model identity 仍必须包含它们。

### C1.6 Reflection 拆分与 self-exclusion

现有 `single_wall_reflection()` 不再同时查询 blocker 并返回聚合后的 wall channel。C1 冻结以下
内部拆分：

```python
@dataclass(frozen=True, slots=True)
class WallReflectionPath:
    point: Vec3
    total_distance_m: float
    carrier: complex

def single_wall_reflection_path(
    scene: Scene,
    tx: Transmitter,
    rx: Receiver,
    wall: Wall,
) -> WallReflectionPath | None: ...
```

该 helper 只负责有效有限墙反射点、总路径长度和一次 `h_FS(L_reflection)`；不接收/应用
`Gamma_wall`，不调用 Profile，也不查询 blocker。engine 对每条有效 path 按固定顺序取得
`Gamma_wall = model.wall_coefficient(wall)`、before modifier、after modifier，并只在一个编排点计算：

```text
wall_contribution = path.carrier * Gamma_wall * m_before_env * m_after_env
```

每个因子只出现一次；不得保留另一个仍会乘 blocker 或 `Gamma_wall` 的聚合入口。该 helper 不是
新的顶层稳定 API，也不生成 mixed path 或 coefficient builder。

`reflecting_wall_id` 是 self-exclusion 的唯一键。默认 Profile 对两个 reflection roles 都只排除该
ID 对应的反射墙；其他 ID 的墙及所有障碍物仍按各自 leg 求交。对象地址、list index、坐标相等或
名称猜测都不能替代 ID。

Scene v1 继续不新增字段，但 `walls[*].id` 从“应唯一”收紧为必须唯一：
`Scene.__post_init__`/loader 拒绝重复值；由于 `Scene.walls` 当前仍是可变 list，engine 还必须在
任何 Profile/reflection 求值前做 defensive preflight。重复 ID 抛包含重复值的 `ValueError`。
不采用“排除所有同 ID 墙”、自动改名、首项获胜或 object-identity fallback。仓库内建/版本化
scene 和现有 tests 已审计为无 duplicate wall ID，因此该收紧不要求 schema version 升级；外部
歧义输入必须显式改名。

### C1.7 Controller / Ground Truth / Profile ownership

- Controller/Ground Truth 唯一拥有 nominal-vs-truth realization；engine 创建 working geometry；
- Reflection Model 在该 world 下取得唯一有效 `Gamma_wall`；
- Profile 只对 engine 显式给出的 working geometry/context 应用同一环境规则，不知道也不选择
  Controller/GT，不访问 actual RIS error 或 MeasurementOracle；
- Ground Truth position/environment 可以改变未来 `a^GT`，RIS phase/efficiency error 只进入
  `Gamma_actual`；C1 不实现或最终化这两个 coefficient；
- model-based Focus 继续只接受 Controller Model。改变隐藏 GT seed/sigma/realization 不得改变
  Profile identity、Profile selection 或 nominal Focus；oracle result 可以改变；
- `profile_identity` 只描述规则，`reflection_model_id/version` 只描述反射算法契约；两者都不是
  完整 world/coefficient identity。

### C1.8 Minimum Reflection Model identity

C1 只增加两个稳定常量，不建立 Reflection Protocol、factory 或插件系统：

```text
reflection_model_id = "finite_wall_single_bounce_image"
reflection_model_version = "1"
```

它标识当前“floor-anchored finite wall + image specular point + total-length Friis carrier + 所选
world 的一次 `Gamma_wall`”算法与因子所有权。改变反射几何、bounce count、`Gamma_wall` 公式或
应用次数必须提升 version；改变某个 Scene 的 wall 坐标/幅相不提升 version，而由 scene/world/
future coefficient identity 记录。C1 不定义动态选择、hash 型 `reflection_model_identity` 或缓存键。

## C2：Minimum Experiment Provenance

### C2.1 Schema v1

Foundation 新实验行使用以下稳定 schema：

```text
provenance_schema_id = airmirror_experiment_provenance
provenance_schema_version = 1
provenance_status = partial | complete
```

在现有物理量/结果字段之外，每行至少包含：

| 字段 | 类型/空值 | 契约 |
|---|---|---|
| `provenance_schema_id` | non-empty str | 固定值 `airmirror_experiment_provenance` |
| `provenance_schema_version` | int | 固定值 `1`；未知版本拒绝 |
| `provenance_status` | enum | `partial` 或 `complete`；新输出不得写 `legacy` |
| `pending_contracts_json` | JSON array[str] | 尚未签署的 owner Work Item IDs，升序、无重复 |
| `run_id` | str | 等于 no-overwrite run 目录 basename |
| `software_version` | str | 实际 package version，不从目标版本猜测 |
| `focus_mode_id`,`focus_mode_version` | str | 实际调用的具名 Focus；不以 display label 代替 |
| `search_levels` | int/empty | 仅 continuous feedback search 适用；不适用为空，不填 0 |
| `profile_id`,`profile_version` | str | 来自实际注入的 C1 Profile |
| `profile_parameters_json` | canonical JSON | C1 identity payload 中的 tagged parameter array |
| `profile_identity` | `sha256:<hex>` | 由 C1 helper 计算，不接受调用者自报 hash |
| `reflection_model_id`,`reflection_model_version` | str | C1 的最小反射契约常量 |
| `world_model_id`,`world_model_version` | str | `controller_nominal/1` 或 `ground_truth_stochastic/1` |
| `world_model_parameters_json` | JSON object | 实际六个 sigma；Controller 使用空对象；key 排序、compact JSON、禁止 NaN/Inf |
| `random_seed` | int/empty | 实际使用或显式声明的整数 seed；不适用为 CSV 空单元格；0 仅表示实际 seed 0 |
| `channel_frequency_model_id` | str/empty | 由 FND-PHY-NB 拥有；未接入时不得从 ADR 目标值回填 |
| `quadrature_policy_id`,`quadrature_policy_version` | str/empty | 由 FND-QA-AP 拥有；未签署时不得伪造 production default |
| `coefficient_model_identity` | str/empty | 由 FND-QA-CC 拥有；builder/identity 未完成时保持空 |

已由 A1 验证的 Focus provenance 值冻结为
`ris_only_phase_conjugate/1` 与 `coherent_target/1`。world model ID 只说明本次调用选择，不把
`GroundTruthModel` 暴露给 Profile，也不替代 seed/sigma 或未来 world/coefficient identity。
Ground Truth parameter object 的六个固定 key 为 `ris_phase_error_sigma_rad`、
`ris_efficiency_sigma_fraction`、`wall_amplitude_error_sigma_fraction`、
`wall_phase_error_sigma_rad`、`position_error_sigma_m`、`measurement_noise_sigma_db`；不得只记录
当前 sweep 恰好改变的一项。

`pending_contracts_json` 是防止 future identity 被伪造的强制字段。C2 首次实现时至少列出仍未
签署的 `FND-PHY-NB`、`FND-QA-AP`、`FND-QA-CC`；对应字段保持空。后续 runner 若正在评估一个
明确 candidate，可记录 candidate ID/version，但 owner ID 仍必须留在 pending list，不能称
Verified/default production provenance。只有 pending list 为空、所有本 run 必需 identity 均由其
owner closure 实际签署且字段非空时，`provenance_status` 才能为 `complete`；否则必须为 `partial`。

字段缺失、空值和“不适用”不能用 0、`default`、目标 ADR 值或当前类名猜测。C2 只冻结最小共同
schema；FND-QA-AP 可增加 QA 专用列，但必须复用这些字段和 pending 规则。

### C2.2 Legacy contract

- 只有已确认的 `results/phase_bits/` v0.1 历史输出派生为 `legacy_v0_1_unversioned`；缺少 schema
  本身不能证明 v0.1 来源；
- `results/checkpoints/foundation_0_1_1_ab_checkpoint_20260903/` 保持
  `checkpoint / non-formal provenance`，缺少 C2 schema 不把它重分类为 v0.1 legacy；
- Foundation 新 run（含默认目录及显式 `--output`）缺少或空置 C2 schema ID/version 任一字段时，
  必须按 malformed provenance 明确失败，不能降级为 legacy；
- 未知来源的 schema-less 文件保持未分类，拒绝作为 Foundation provenance，不自动猜为 v0.1 legacy；
- legacy 是 reader/report 和 `results/README.md` 的派生标签，不向旧 CSV/PNG 回写新列，不计算
  guessed Profile/Reflection/channel/quadrature/coefficient identity；
- 未知的非空 schema ID/version 明确拒绝，不能降级为 legacy；
- legacy/checkpoint 结果仍可展示其原有字段，但不能相互重分类或与 `partial/complete` Foundation
  行拼接成一个无标签 aggregate，也不能作为 Foundation formal provenance evidence。

### C2.3 No-overwrite contract

Foundation Phase Resolution 新输出根目录冻结为：

```text
results/foundation_0_1_1/phase_bits/<run_id>/
```

默认 `run_id` 格式为 UTC `YYYYMMDDTHHMMSS.ffffffZ-<8 lowercase uuid4 hex>`。显式 `--output DIR`
把 `DIR` 视为完整 run directory。无论默认或显式目录，目标必须不存在，并以 exclusive create
建立；已存在即在计算/写文件前抛 `FileExistsError`。C2 不提供 `--force`，不删除、清空、合并
或改写旧目录。repo 内解析后的 `results/phase_bits/` 是保留路径，即使不存在也拒绝作为
Foundation `--output`。每个 run 的 CSV/PNG 共处一目录，以 CSV 的 run-level provenance 解释
PNG。

失败留下的 partial run directory 不被下次运行复用；调用者使用新 run ID，人工检查后再按独立
授权清理。完整历史迁移、索引、artifact store 和统计报告治理留给 P1B。

## Tasks

所有 task 保持 0.5–2 天且可独立 code review；状态在本次 Ready Review 后为 Ready，尚未开始：

| Task | Deliverable | 状态 | 完成输出 |
|---|---|---|---|
| `FND-ARCH-01A` Protocol/context/identity types | C1 | Ready | `simulation.profiles`、canonical identity tests |
| `FND-ARCH-01B` default environment modifier | C1 | Ready | immutable deterministic Profile、五 role contract tests |
| `FND-ARCH-01C` reflection factor split | C1 | Ready | carrier-only path helper、Gamma/before/after once-only tests |
| `FND-ARCH-01D` engine integration and duplicate-ID guard | C1 | Ready | constructor injection、all-role routing、wall-ID validation |
| `FND-ARCH-01E` C1 compatibility/ownership closure | C1 | Ready | component references、three-generation headless、manual call graph review |
| `FND-EXP-01A` provenance schema/model metadata | C2 | Ready | schema v1 fields、pending/partial validation |
| `FND-EXP-01B` versioned no-overwrite runner | C2 | Ready | new run directory、CSV/PNG、existing-target failure |
| `FND-EXP-01C` legacy classification and docs | C2 | Ready | read-only legacy marker、results README、FND-T15 tests |

C1 和 C2 分两个 focused implementation reviews；C2 依赖 C1 实际 Profile/reflection metadata，不能
先填默认字符串模拟依赖完成。任一 task 超过两天时必须继续拆分，不扩大本 Work Item scope。

## 验收证据

### C1 automatic

- `FND-T13`：基线 SHA 的 direct、每条 wall、RIS 和 total complex components 在冻结容差内等价；
- `FND-T13b`：spy Profile 验证五个 role、方向、ID 和调用次数；RIS 仍为 center scalar；
- `FND-T13c`：分别只缩放 `Gamma_wall`、before、after，wall amplitude 恰好一次缩放；
- `FND-T13d`：反射墙只从自身两个 legs 排除，其他 blocker 仍生效；duplicate wall ID 在 Profile
  调用前失败；
- `FND-T14`：默认 Profile frozen/deterministic；ID/version/typed parameter mutation 改变 identity；
  两个独立 Python 进程 identity 一致；非法/non-finite output 和 context 明确失败；Reflection
  ID/version 独立于 Profile identity，改变墙系数不改变 `profile_identity`。wall/world state 对总体
  coefficient/world identity 的 mutation matrix 留给 FND-QA-CC，不是 C1 测试或实现前置项。

### C2 automatic

- `FND-T15`：schema ID/version、Focus/Profile/Reflection/world/search 字段来自实际运行；C1
  canonical parameters 与 identity 一致；
- `FND-T15b`：FND-PHY-NB/FND-QA-AP/FND-QA-CC 未签署时保持 `partial`、列入 pending，相关
  identity 为空或显式 candidate，绝不伪造 Verified/default；
- `FND-T15c`：按 C2.2 区分 v0.1 legacy、A/B checkpoint、malformed Foundation run 与未知来源；
  legacy/checkpoint bytes/mtime 不变；新 run 缺 schema、未知 schema 明确失败，不降级 legacy；
- `FND-T15d`：已存在 run directory 在计算前 `FileExistsError`，legacy CSV/PNG hash 不变；新
  run 的 CSV/PNG 在唯一目录中生成且 `run_id` 一致。

### Integration and manual

- `python -m pytest`、Current/Advanced/Future fast headless、documentation tests 和
  `git diff --check` 全部通过；
- 人工 call-graph review 确认每个 carrier、`Gamma_wall`、Profile modifier、RIS response 只有一个
  owner/application site，Profile 没有 import optimizer/GUI/Ground Truth 私有实现；
- 人工 provenance review 确认 partial/candidate/complete/legacy 不会被展示为同一可信等级；
- Scene v1 round-trip 无新 Profile/Reflection Python class 字段，旧 results 未修改。

## C1/C2 Exit 与状态边界

C1/C2 implementation 完成只能把各自状态提升为 Implemented；独立 review 与上述证据完成后才可
提升 C。C 的 Ready/Implemented/Verified 均不签署 FND-QA-AP、FND-PHY-NB、FND-QA-CC，不解除
Foundation/P1A gate，也不把 `partial` provenance 宣称为 final Foundation evidence。

## 风险与回退

| 风险 | 检测 | 安全回退 |
|---|---|---|
| Profile 绕过某类 path | spy role/call-count tests | C 保持 In Progress，补统一 engine 路由 |
| carrier/Gamma/modifier 重复或遗漏 | 三个因子独立扰动 | 恢复基线顺序，修正唯一编排点 |
| duplicate ID 排除多堵墙 | preflight duplicate test | 明确 `ValueError`，不做 object fallback |
| Profile 读取 GT 私有状态 | import/call-graph 与 seed mutation test | 收回 Model/callback 输入，保留显式 working geometry |
| identity 随进程或类型漂移 | subprocess golden/mutation tests | 只使用冻结 tagged JSON + SHA-256 helper |
| future identity 被提前写成默认 | pending-contract/schema tests | 保持空/candidate + `partial`，等待 owner closure |
| 新实验覆盖 legacy/已有 run | hash + existing-target tests | exclusive create，无 force/删除路径 |
| C 膨胀到 coefficient/cache/new physics | diff/scope review | 停止并移回相应 Work Item/ADR |

## 文档影响

- [x] Foundation plan、roadmap、requirements、DEVELOPMENT_STATUS：C Ready 状态与依赖；
- [x] architecture、public API、data/physics：Protocol、ownership、reflection split 和 identity；
- [x] experiment/test/DoD/limitations：schema、legacy、pending、no-overwrite、FND-T15；
- [x] ADR：复核 ADR-0011/0012，确认无需新增；
- [ ] code/tests/results/GUI/Scene 与 results README：Ready Review 不修改，implementation 后另行
  更新证据。

## Ready Review evidence

- 事实源审计：计划列出的 Markdown 与当前 engine/reflection/blockage/ground-truth/RIS/focus/
  phase-bits 调用图已核对；
- documentation tests：`python -m pytest tests/test_documentation.py -q` → `9 passed`；
- whitespace：`git diff --check` → PASS；
- scope audit：提交只允许 Markdown，且不修改 `results/` 下任何文件。
