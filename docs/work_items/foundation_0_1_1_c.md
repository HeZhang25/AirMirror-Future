# Work Item：Foundation 0.1.1C PropagationProfile and Minimum Provenance

- 层级：L3 Deliverable（含可独立评审的 C1/C2）
- Task IDs：FND-ARCH-01、FND-EXP-01
- Requirement IDs：AMF-SIM-005、AMF-EXP-006
- 状态：In Progress（C1 Implemented，待独立审查；C2 Ready）
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

后续 C1 implementation 独立审查授权的 environment-ID compatibility closure 补充了下述数据
边界：除 duplicate wall ID 外，Wall/Obstacle/RISSurface ID 也必须是 non-empty string。审计与实现证据见
文末 closure；不改变 Profile 契约、路径距离接受域或 C2 scope。

本节记录的 Ready Review 只冻结 C1/C2 的实现边界、接口、数据、错误和验收条件；当时没有修改 Python、
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
- reflecting-wall self-exclusion、duplicate wall ID / Wall-Obstacle-RIS non-empty ID 拒绝和因子唯一应用测试；
- C2 provenance schema v1、legacy 分类、pending-contract 标记和 no-overwrite 输出目录；
- `FND-T13..T15` 自动测试、三代 headless 兼容回归和人工 ownership/provenance review。

不包含：

- 选择或迁移 production quadrature policy，或实现最终 `a_n` coefficient builder；
- 签署 `FND-QA-AP`、`FND-PHY-NB`、`FND-QA-CC` 所拥有的 future identities；
- P1A cache/key 实现、矩阵化、增量 Greedy 或性能重写；
- 新传播路径、新场景、高阶/混合反射、逐 patch 遮挡、PathEnsemble、fading、delay、Doppler、
  frequency-selective channel 或 OFDM；
- GUI、Scene JSON v1 字段/结构、历史结果内容或完整历史迁移工具；duplicate wall ID 和
  Wall/Obstacle/RISSurface non-empty ID 仅作有记录、不升 schema version 的 validation tightening。

## C1：PropagationProfile

### C1.1 模块与精确 Protocol

实现位于 `airmirror_future.simulation.profiles`。以下名称、字段和签名已冻结；除修正明显的
typing 拼写外不得在实现中另行发明同义接口：

```python
PropagationPathRole = Literal[
    "direct",
    "reflection_before",
    "reflection_after",
    "ris_incident",
    "ris_scattered",
]

CanonicalParameter = bool | int | float | str | None
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
组合不一致；engine 在创建 context 前拒绝引用不存在或不唯一的 wall/RIS；RIS 引用匹配/歧义
仍由既有 commanded-pattern 边界校验。C1 对既有输入接受域的收紧为 duplicate wall ID 拒绝及
经审查授权的 Wall/Obstacle/RISSurface non-empty string ID 数据边界 closure；不扩展 TX/RX
或新增 RIS/global uniqueness enforcement。
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

Wall/Obstacle `id` 同时必须为 non-empty string（`len(id)>0`）：实体构造和 loader 拒绝空字符串
及非字符串，Scene 构造和 engine channel/map 在任何 working-world/Profile/physics 求值前复核，
包括可变实体/list 被事后修改、墙反射或遮挡关闭的情况。`ValueError` 包含实体类型、实际 ID 和
显式赋名指引。不得 trim、规范化、自动赋名或过滤 blocker ID；不新增 obstacle/global uniqueness
enforcement。经受支持 Scene/内建场景/tests/Git 历史兼容审计，该 closure 保持 schema v1，
但不承诺外部旧 reader 曾接受的空 ID 继续可用；外部文件必须显式赋名。Profile context 和
blocker non-empty contract、self-exclusion 及传播公式保持不变。

同源的 RIS ID closure 将 `RISSurface.id` 从 truthiness 校验收紧为 non-empty string：构造/loader
拒绝 truthy non-string，Scene 构造与 engine preflight 复核事后 mutation，且不依赖 enabled 或
是否有 pattern。错误同样含实体类型、实际 ID 和显式赋名指引；不转换为字符串或放宽 context。
RIS uniqueness 仍仅在既有 pattern 引用边界检查，不新增 Scene-wide enforcement；TX/RX 不变。

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

所有 task 保持 0.5–2 天且可独立 code review；2026-09-04 C1 已实现，C2 尚未开始：

| Task | Deliverable | 状态 | 完成输出 |
|---|---|---|---|
| `FND-ARCH-01A` Protocol/context/identity types | C1 | Implemented | `simulation.profiles`、canonical identity tests |
| `FND-ARCH-01B` default environment modifier | C1 | Implemented | immutable deterministic Profile、五 role contract tests |
| `FND-ARCH-01C` reflection factor split | C1 | Implemented | carrier-only path helper、Gamma/before/after once-only tests |
| `FND-ARCH-01D` engine integration and environment-ID guards | C1 | Implemented | constructor injection、all-role routing、duplicate wall / non-empty Wall-Obstacle-RIS ID validation |
| `FND-ARCH-01E` C1 compatibility/ownership closure | C1 | Implemented | component references、three-generation headless、manual call graph review |
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
  调用前失败；Wall/Obstacle 空 ID 在 constructor/loader 拒绝，Scene 构造及 engine channel/map
  preflight 防御事后修改；RISSurface truthy non-string ID 同样在数据边界拒绝，不到 world/Profile
  求值才失败；不新增 RIS uniqueness enforcement；
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

## C1 implementation evidence

2026-09-04：以独立远端 Ready PASS commit `9fad9b05273fd0d15569d8307e50321d40d05c4a` 为 parent
完成 `FND-ARCH-01A..01E`，C1 / `AMF-SIM-005` 为 **Implemented，待独立审查**。C 整体和 Foundation
仍为 In Progress；C2 / `AMF-EXP-006` 仍为 Ready，未实现、未产生 C2 provenance 或实验输出。

### 实现与 ownership audit

- `simulation.profiles` 实现冻结类型、默认 immutable Profile 和 canonical identity helper；
  `CanonicalParameter` 仅修正 Python union 的拼写为 `bool | int | float | str | None`，值域不变；
- `physics.reflections.single_wall_reflection_path` 只计算有效点、总距离与 carrier，旧聚合函数移除；
  engine 唯一组合 `carrier * Gamma_wall * before * after`；零名义反射幅值按 v0.1 继续跳过；
- engine 的 channel/map 共用五类 context 路由，blocker IDs 只进入诊断，RIS modifier 保持 center
  scalar；context 没有新增最小段长拒绝；
- Scene 构造/loader 和 engine preflight 共用 duplicate wall-ID guard；schema v1 字段未变；
- import/call-graph 审计确认 Profile 不导入 optimizer/GUI/Ground Truth 私有实现；仅消费显式
  working geometry，不接收 Model/seed/sigma/error callback；GT RIS phase/efficiency 仍仅由
  scattering 消费，没有最终 coefficient builder、cache 或新路径；
- `tests/test_wall_geometry.py` 的旧探针改为注入 Profile / carrier helper；新增探针限定被测
  engine/fixture。全量测试曾暴露跨测试 GUI worker/timer 生命周期问题，
  `tests/test_gui_smoke.py` 仅补取消、等待和销毁的 teardown，不改产品 GUI 或跳过断言。

### 自动测试

```text
python -m pytest tests/test_profiles.py tests/test_profile_integration.py tests/test_profile_compatibility.py tests/test_wall_geometry.py tests/test_blockage_reflection.py tests/test_scene_engine.py tests/test_pattern_contract.py
188 passed

python -m pytest tests/test_documentation.py
9 passed

python -m pytest
275 passed

git diff --check
PASS
```

- FND-T13：`tests/fixtures/c1_v01_components.json` 在修改 production 前采集；已确认 parent 的
  `src/` 与 `d9ab04a502055af3b519a781629e6e83f0ded9d8` 相同。三代 + 定向 reflection/blockage
  各含 nominal/GT，共 8 组；LOS、每条 wall、wall sum、RIS、total 满足 `rtol=1e-12, atol=1e-15`，
  路径集合、几何点和 blocker IDs 不变。fixture 是单元测试 reference，不是 C2/formal provenance；
- FND-T13b：channel/map role direction/ID/count、disabled/uncommanded RIS 和无效反射遗漏规则通过；
- FND-T13c：Gamma、before、after 独立零/幅值/相位扰动与五 role 复数缩放通过，无重复乘法；
- FND-T13d：反射墙 ID self-exclusion、其他 blocker、duplicate 构造/loader/可变 list 防御通过；
- FND-T14：frozen default、canonical literal payload/type mutation、两个独立进程、非法 context/
  output、异常透传、Reflection identity 分层与 GT 隔离通过；不含最终 world/coefficient identity。

### 三代 fast headless

对每代执行 `python -m airmirror_future --headless --scene scenes/smart_room.json --generation
<Current|Advanced|Future> --quality fast`；均 exit 0，grid `80×60`。改动前后下列指标完全一致，
共同 baseline 为 `-55.275335808122435 dBm`；runtime 只作运行记录，不是物理回归判据。

| Generation | Focused power dBm | Target RIS Gain dB | SNR dB | Coverage % |
|---|---|---|---|---|
| Current | -46.5879005740162 | 8.687435234106232 | 40.4120994259838 | 77.10416666666666 |
| Advanced | -30.125714151404196 | 25.14962165671824 | 56.874285848595804 | 78.52083333333333 |
| Future | -19.31176972053484 | 35.963566087587594 | 67.68823027946516 | 82.5625 |

未修改 `results/`、版本化 Scene、GUI 产品代码、实验 runner、Focus 或 scattering 公式；未签署
C / Foundation Verified、FND-QA-AP、FND-PHY-NB、FND-QA-CC 或 P1A gate。独立审查是下一步，
本交付停止于 C1 Implemented。

## C1 environment-ID compatibility closure

2026-09-04，针对独立审查的唯一 C1 compatibility blocker，parent 为
`a641b0d2c1c37e80d2c423d32ddbe239b61a9640`。C1 保持 Implemented，fix 待独立审查；C2 Ready、
C / Foundation In Progress，不开始其他工作项。

### Compatibility audit / schema decision

- 开始时工作树干净，HEAD 与审查 SHA 一致。审计本地 `git rev-list --all` 的 22 个可达提交，
  对 `src/`、`tests/` 的 Python 和 `scenes/` JSON 去重后检查 92 个 `(blob,path)` revision；
- 唯一受支持 Scene `scenes/smart_room.json` 在这些历史中只有一个 blob
  `e4e57225a7d1dec7195a6e499c456e1a73957b6c`：wall IDs 始终为
  `north/south/west/east/partition`，obstacle ID 为 `cabinet`。Current/Advanced/Future 内建场景
  复用这套环境实体，documentation test 继续验证内建与版本化 Scene 一致；
- AST 检查上述历史源码/tests 共 25 处 Wall/Obstacle 构造调用：23 处 literal ID 均为非空字符串，
  仅两处动态输入是 loader 的 `item["id"]`；未发现空 ID 赋值或受支持 JSON 中的空/非字符串 ID。
  相关 wall geometry、blockage/reflection、Scene、Profile tests 均不依赖合法空 ID；
- 旧构造器/loader 确实曾接受空 ID；不能把新限制误写为旧代码已有行为。审计未发现仓库内合法
  依赖，因此按审查授权冻结 non-empty string 并保持 Scene v1：无字段/类型/必需性/结构变化，
  有效场景传播公式、路径集合与数值不变。未知外部文件不在审计证明范围，空 ID 须显式赋名，
  不自动修复或过滤。无需更改 ADR ownership decision 或建立新插件/迁移机制。

### Focused fix / verification

- Wall/Obstacle 构造器共享 non-empty string validator；loader 原样通过构造器拒绝非法 ID，
  无新 JSON 字段或 coercion。Scene 构造及两个 engine 入口复核可变实体/list；保留 duplicate wall
  guard，不新增 obstacle/global uniqueness，不更改 Profile context/blocker contract；
- 新增 `tests/test_environment_ids.py`：修复前 `22 failed, 2 passed`，修复后 `24 passed`。
  覆盖实体/Scene 构造、v1 loader、channel/map rename/append preflight、无反射/遮挡墙也拒绝空 ID，
  以及非空 Unicode/空白原样 round-trip；全部归入 FND-T13d；
- C1 targeted：原 implementation evidence 的 7 个测试文件加 `tests/test_environment_ids.py`
  → `212 passed`；FND-T13..T14 的 numeric/path/ownership/identity 断言未放宽；
- `python -m pytest tests/test_documentation.py` → `9 passed`；
- `python -m pytest` → `299 passed`；`git diff --check` → PASS；
- 再跑上述三代 fast headless（`80×60`），均 exit 0；共同 baseline
  `-55.275335808122435 dBm`，focused power / gain / SNR / coverage 与上表完全一致；
- focused consistency search 已同步 C Ready 的输入收紧措辞、data model、Scene schema、test strategy、
  limitations、public API、architecture 和状态迁移说明；不再声称 C1 唯一输入收紧是 duplicate wall ID。
  未修改 Profile/physics/GT/Focus、C2、GUI product、版本化 Scene 或 results；停止等待独立审查。

## C1 RIS-ID compatibility closure

2026-09-04，第二轮独立审查确认 Wall/Obstacle blocker 已关闭；以
`3081c6a3a006db827f402d496e1f1e2c21a7a4ff` 为 parent，仅闭合剩余 RIS ID blocker。
旧 RIS constructor/loader 的 truthiness 校验会接受 `id=1`，`{1: pattern}` 也可通过引用匹配，
直到 C1 context 才失败；本次正式记录并提前执行 non-empty string 数据边界，不把它描述为旧行为。

- `RISSurface.__post_init__` 复用现有 ID validator；Scene 构造及 engine 两个入口复用的
  preflight 增加 RIS ID 检查，无需修改 loader 格式或 engine 传播流程；
- 受支持 Scene 与三代 preset 使用 `ris-1`，现有直接 RIS 构造 fixtures 使用 `ris`；schema v1
  字段/类型/必需性/结构不变，正常字符串 ID 无数值迁移。外部非字符串 ID 必须显式赋名并
  更新 pattern key，不自动转换。未知外部数据不在仓库兼容证据范围；
- 不放宽 context，不新增 TX/RX、RIS/global uniqueness 校验；既有 pattern 引用歧义校验不变。
  Profile ownership、公式、C2、QA-AP/PHY-NB/QA-CC、coefficient/cache、GUI、Scene/results 均未改动；
- `tests/test_environment_ids.py` 新增 26 项 RIS tests：constructor/loader、Scene mutation、
  channel/map 在 world/Profile/physics 前拒绝 mutation（含整数 pattern key、disabled、uncommanded、
  append），并保护 Unicode/空白 ID 与既有 uniqueness 范围；该文件共 `50 passed`，归入 FND-T13d；
- C1 targeted 沿用上一轮 8 个测试文件 → `238 passed`；FND-T13..T14 继续通过；
- `python -m pytest tests/test_documentation.py` → `9 passed`；
- `python -m pytest` → `325 passed`；`git diff --check` → PASS；
- 三代 fast headless（`80×60`）均 exit 0，baseline / focused power / gain / SNR / coverage 与
  C1 implementation evidence 数值表完全一致；
- focused consistency search 已将当前 C1 input-tightening 列表补齐为 duplicate wall ID 及
  Wall/Obstacle/RISSurface non-empty string ID；前轮审计/测试数字仍保留为历史证据。

C1 保持 Implemented、C2 Ready、C / Foundation In Progress；此 fix 等待独立审查，不进入 C2。
