# RIS 代际与未来假设

| 属性 | 值 |
|---|---|
| 文档状态 | Informative，默认值由代码/scene 提供 |
| 基线版本 | v0.1 |

## 1. 使用原则

代际 preset 用于把器件参数的演进映射为空间级结果，不是对行业产品的统计结论。用户可以
修改全部参数；实验记录必须保存最终数值，不能只记录 generation 名称。

Future 仍遵守与 Current 相同的传播公式、孔径归一化、效率上限和噪声。任何“Future
增益”都必须来自显式参数，不存在额外 multiplier。

## 2. v0.1 代表性 preset

| 参数 | Current | Advanced | Future |
|---|---:|---:|---:|
| Width × Height | 0.8×0.8 m | 1.6×1.2 m | 3.0×2.0 m |
| Equivalent Patch Nx × Ny | 8×8 | 24×24 | 64×48 |
| Phase | 1-bit | 3-bit | continuous |
| Reflection efficiency | 0.70 | 0.85 | 0.95 |
| Update rate | 10 Hz | 100 Hz | 1000 Hz |
| Self sensing | No | Yes | Yes |
| `future_assumption` | false | false | true |

权威构造器是 `generation_preset`。表格变化必须与代码同一次变更，并重新运行 phase/aperture
和 Smart Space 基准。

## 3. 参数解释

- **Aperture**：真实物理面积，直接影响捕获和重辐射尺度；不是显示尺寸；
- **Nx/Ny**：系统级 equivalent controllable aperture patch 数，同时承担控制和中心点求积；
  不是实际 meta-atom 数，固定孔径细分测试只证明面积归一化不发散；
- **Phase bits**：命令相位状态数；continuous 仍会受 Ground Truth phase error；
- **Efficiency**：反射功率效率，passive 始终 `≤1`；
- **Update rate**：控制能力元数据；v0.1 静态场图不自动把 Hz 转为吞吐或增益；
- **Self sensing**：未来系统能力标志；v0.1 不因 true 自动知道 Ground Truth。

因此代际比较同时改变多个控制变量，适合产品演示但不适合单因素科学归因。科学实验必须
使用单变量 sweep。

## 4. 允许的未来外推

在独立 requirement/ADR 后可探索：建筑融合大孔径、tile aggregation、多 RIS 协同、更快
更新、低损耗、高精度相位、宽带、自感知、通信感知定位融合。大规模实现不能创建百万
Python cell objects，应使用等效孔径/tiles/矩阵分块，并验证与细网格基准的一致性。

## 5. 尚未允许的外推

- passive efficiency `>1`；
- 不建外部功率和 noise figure 的 active gain；
- 不建透射路径的 STAR-RIS；
- Future 直接乘固定倍数；
- update rate 或 self sensing 自动变成 RF gain；
- 将 Shannon 上界称为真实 throughput；
- 将 Privacy spatial suppression 称为 encryption；
- 将概念性 Electromagnetic Corridor 画成不经过引擎的覆盖带。

## 6. 对外表达模板

推荐：

> Future preset 是物理约束下的场景假设，用更大孔径、更高相位精度、更低损耗和更快控制
> 探索潜在系统收益，不代表这些组合参数已形成现实部署产品。

禁止：

> Future RIS 能固定提升 36 dB。

具体 gain 依赖 scene、目标位置、频率、遮挡、相位和与其他路径的干涉，甚至可以为负。
