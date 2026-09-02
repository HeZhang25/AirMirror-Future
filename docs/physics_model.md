# 物理模型规范

| 属性 | 值 |
|---|---|
| 文档状态 | Normative |
| 基线版本 | v0.1 + Foundation 0.1.1A/A1-A2 |
| 模型标签 | System-level electromagnetic approximation |
| 对应 ADR | ADR-0001、ADR-0003、ADR-0006、ADR-0007 |

## 1. 适用范围

模型用于窄带、系统级、实时/准实时趋势仿真。坐标是三维的，但场图是在固定高度的二维
采样。模型能表达距离损耗、传播相位、复场干涉、有限孔径、方向性、一次反射、几何
阻挡、相位量化和器件误差。

它不提供器件级电流分布、严格近场全波、互耦、极化、材料色散、衍射、高阶反射或协议
栈结果。完整边界见 [limitations.md](limitations.md)。

## 2. 坐标、符号和复数约定

- `x,y` 为地面平面，`z` 为高度，单位 m；
- `RISSurface.position` 是孔径几何中心；
- `yaw_rad` 是 RIS 正面法向相对 +x 的方位角；
- 时间/传播相位使用 `exp(-j*k*L)`；
- 反射/控制系数使用 `exp(+j*phi)`；
- 天线增益为线性功率增益；
- 所有 dB 值只能在明确边界转换，不能参与复数求和。

```text
c = 299792458 m/s
lambda = c/f
k = 2*pi/lambda
```

## 3. 自由空间信道

对于正距离 `d`：

```text
h_FS(d) = sqrt(Gt*Gr) * lambda/(4*pi*d) * exp(-j*k*d)
```

`h` 是无量纲窄带复信道。接收功率：

```text
Pr_W = Pt_W * |h_total|²
Pr_dBm = 10*log10(max(Pr_W, MIN_POWER_W)) + 30
```

`MIN_POWER_W` 只避免对零取对数，不能在求和前把小路径清零。远区 Friis 下距离加倍，
接收功率约下降 6.0206 dB；传播一个波长，相位增加 `2π`（模 `2π` 后等价）。

## 4. 阻挡

### 墙体

墙体是从 `start` 到 `end` 的竖直有限线段，高度为 `height_m`。TX-RX 的二维线段交点
参数为 `t`，交点高度：

```text
z_hit = z_start + t*(z_end-z_start)
```

只有 `0<t<1` 且 `0≤z_hit≤height` 时命中。命中后：

```text
a_block = 10^(-attenuation_db/20)
```

多个阻挡的 dB 衰减相加，等价于幅度比相乘。`blocks_los=false` 的边界墙不阻挡室内
路径，但仍可产生一次反射。

### 矩形障碍物

障碍物为轴对齐三维包围盒，使用 segment/AABB slab 算法。`fully_blocking=true` 在 v0.1
以 300 dB 数值衰减表示，保持有限结果。人体在未来 XR 中复用同一接口，但需单独定义
姿态、材料和时间更新契约。

## 5. 一次墙面镜面反射

墙复反射系数：

```text
Gamma_wall = rho * exp(j*phi_wall), 0≤rho≤1
```

步骤：

1. 将 TX 关于墙所在无限竖直平面镜像；
2. 镜像点到 RX 的线与有限墙段相交，得到反射点；
3. 反射点必须在墙宽度和高度范围内；
4. 总长度 `L=d_TX-reflection+d_reflection-RX`；
5. 以 `h_FS(L)*Gamma_wall` 计算；
6. 反射前后路径受到除反射墙本身外的其他阻挡衰减。

v0.1 不叠加反射角 Fresnel 极化系数；`rho,phi` 是场景可配置系统级系数。

## 6. RIS 几何

RIS 是宽 `W`、高 `H` 的竖直矩形平面。水平切向量和法向量：

```text
n = [cos(yaw), sin(yaw), 0]
t = [-sin(yaw), cos(yaw), 0]
```

`Nx*Ny` 个中心均匀位于实体孔径内：

```text
A_cell = W*H/(Nx*Ny)
sum(A_cell) = W*H
```

v0.1 中同一 `Nx*Ny` 网格同时决定独立 commanded phase 和中心点求积采样；这些点是系统级
等效控制 patch，不是经过器件校准的真实 meta-atom。当前模型按满填充孔径处理，没有 patch
内积分、fill factor、互耦或真实单元子结构。

数组展开顺序是先生成 `u`（宽度/Nx）和 `v`（高度/Ny）的 meshgrid，再以 C-order
flatten；pattern 必须使用同一顺序，reshape 形状为 `[Ny,Nx]`。

### 等效 pitch 与运行波长诊断

实体宽高始终由 `RISSurface.width_m/height_m` 决定。对于 operating frequency `f`，A2 只派生：

```text
pitch_x = W/Nx
pitch_y = H/Ny
lambda  = c/f
r_x     = pitch_x/lambda
r_y     = pitch_y/lambda
```

改变 `Nx/Ny` 不改变实体孔径；改变 `f` 只改变传播波长、波数和上述比例，也不自动缩放孔径。
`r_x/r_y` 是模型透明度信息，不是物理阵元间距合规检查；尤其 `pitch/lambda > 0.5` 不会使
当前系统级模型自动失效。A2 不提供 patch 内 phase-span 数值或硬阈值，因为当前尚未独立
定义 control grid 与 quadrature grid。严格求积收敛按 P1C 触发条件处理，完整决定见
[ADR-0007](adr/0007-equivalent-controllable-aperture-patches.md)。

## 7. RIS 双基地散射

对第 n 个单元：

```text
d1_n = |TX-cell_n|
d2_n = |cell_n-RX|
u_in  = (TX-cell_n)/d1_n
u_out = (RX-cell_n)/d2_n

cos_in  = max(dot(u_in,n),0)
cos_out = max(dot(u_out,n),0)
D_n = (cos_in*cos_out)^(q/2), q=1 default

h_n = sqrt(Gt*Gr*eta_n)
      * A_cell/(4*pi*d1_n*d2_n)
      * D_n
      * exp[-j*k*(d1_n+d2_n) + j*(phi_command_n+epsilon_phi_n)]

h_RIS = sum_n(h_n)
```

方向图中的平方根表示从功率方向因子转为场幅因子。任一方向位于背面时贡献为零。
TX-RIS 和 RIS-RX 的中心路径可受几何阻挡；v0.1 不逐 cell 计算不同阻挡边缘。

### 孔径归一化不变量

场幅与 `A_cell` 线性相关，因此固定 `W,H,eta` 和连续相位时，网格从 8×8 加密到
16×16、32×32 不得随 patch 数量产生无界增益，并应表现出稳定细分趋势。由于当前细分同时
增加求积点和独立控制自由度，该测试保护面积归一化/不发散，不证明较粗 control patch 已达到
物理或求积收敛。真正的求积有效性测试需要固定 control grid 和 commanded pattern，只细化
patch 内 integration grid。增大实体孔径通常增加理想聚焦能力，但最终总信道可能因与 LOS/墙
路径相消而在个别点下降。

模型没有任意校准常数。若未来需要与实测/全波校准，应新增具名、带单位和来源的模型
参数，并通过 ADR 说明，不允许添加“RIS gain dB”。

## 8. 相位命令和量化

单元总路径：

```text
L_n = d1_n+d2_n
phi_ideal_n = k*L_n mod 2*pi
```

量化状态数 `M=2^b`，步长 `Delta=2π/M`，使用最近状态并在 `2π` 处回绕：

```text
phi_q = (round(phi/Delta) mod M)*Delta
```

- 1-bit：`{0,π}`；
- 2-bit：`{0,π/2,π,3π/2}`；
- 3/4-bit：均匀 8/16 状态；
- `phase_bits=None`：continuous，不量化。

### RIS-only Phase-Conjugate Focus

`generate_ris_only_focus_pattern()` 将上述 `phi_ideal_n` 直接按 hardware `phase_bits` 量化，
只让 RIS patch 在目标点互相相干。兼容函数 `generate_focus_pattern()` 保持相同语义。它不读取
`h_LOS+h_wall` 的复相位，因此不是总接收功率目标。

### Coherent Target Focus

定义 nominal baseline 与未偏置 RIS 场：

```text
h_b  = h_LOS + sum(h_wall)
h_r0 = h_RIS(phi_ideal)
```

continuous 单 RIS 使用公共相位偏移：

```text
delta = [arg(h_b)-arg(h_r0)] mod 2*pi
phi_command_n = [phi_ideal_n+delta] mod 2*pi
```

当两个分量均非退化且相位不改变 RIS 幅度时，Controller Model 下应满足
`|h_total|≈|h_b|+|h_RIS|`。若任一分量相对另一分量小于 `64*machine_epsilon`，确定性使用
`delta=0`，不对近零复数作不稳定相位判断。

有限 bit 必须先加 offset 再使用同一个量化器。算法评价所有由公共 offset 量化边界划分出的
不同候选区间，并将精确 `delta=0` 作为第一候选，以 Controller Model 的
`Pt*|h_b+h_RIS|²` 选择最佳命令。它只保证不差于同一 nominal objective 下的 unshifted 候选，
且只是在公共 offset 可达 pattern 族内最优；不是任意逐 patch 离散组合的全局最优。

完整符号、候选构造、tie-break、退化行为和兼容决定见
[ADR-0006](adr/0006-coherent-target-focus-objective.md)。两种算法都不保证在 Ground Truth
误差、幅相耦合、多用户或带约束目标下全局最优。

## 9. 总信道、基线与 RIS Gain

```text
h_baseline = h_LOS + sum(h_wall)
h_total    = h_baseline + sum(h_RIS)

P_baseline = Pt*|h_baseline|²
P_with_RIS = Pt*|h_total|²
RIS_Gain_dB = P_with_RIS_dBm-P_baseline_dBm
```

RIS Gain 可以为负，这是物理相消的合法结果。任何将负值强制截为零的显示或算法都违反
规范。

## 10. 噪声、SNR、Coverage 和容量

```text
N_dBm = -174 + 10*log10(B_Hz) + NF_dB
SNR_dB = Pr_dBm-N_dBm
C_upper = B*log2(1+10^(SNR_dB/10))
```

Coverage 是当前场图网格中 `SNR≥scene.coverage_threshold_db` 的比例；Dead Zone 为其补集。
阈值是场景参数，结果记录必须携带阈值。`C_upper` 只能显示为 Shannon 理论上界。

## 11. Controller Model 与 Ground Truth

Controller Model 返回零位置/相位误差、单位效率缩放和名义墙系数。Ground Truth 通过
`seed + stable CRC32(key)` 为每类实体建立独立随机流，避免 Python hash 随进程变化。

支持的 v0.1 误差：

| 参数 | 分布/处理 |
|---|---|
| RIS phase | `N(0,sigma_phase²)`，每 cell 固定 realization |
| RIS efficiency | 以 `N(1,sigma_eff²)` 缩放并裁剪到有效效率范围 |
| Wall amplitude | 名义幅值乘 `N(1,sigma_wall_amp²)` 后裁剪 `[0,1]` |
| Wall phase | 名义相位加 `N(0,sigma_wall_phase²)` |
| Position | 同一实体使用固定三维 `N(0,sigma_pos²)` 平移 |
| Measurement | 每次 oracle 调用加入时序 `N(0,sigma_measure²)` dB 噪声 |

相同 seed、场景和调用顺序必须产生相同结果。baseline/with-RIS 比较使用相同 realization。

## 12. 数值与模型有效性检查

- 频率、带宽、距离、孔径、网格和更新率必须为正；
- 无源效率和墙幅值必须在 `[0,1]`；
- pattern 长度必须严格等于 `Nx*Ny`；
- TX/RX 与 cell 距离小于 `MIN_DISTANCE_M` 时拒绝；
- 任何输出数组必须是有限值；
- active RIS 在完整功率与噪声模型建立前拒绝；
- 非法 scene schema 拒绝加载。

改变公式、相位符号、方向图、面积标度或误差采样策略必须新增 ADR，更新物理性质测试和
实验基准，不能只修改 docstring。
