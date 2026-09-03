# ADR-0010：中心频率窄带平坦信道与容量语义

- 状态：Accepted
- 日期：2026-09-03
- Supersedes：无；澄清 v0.1 的隐含频率/带宽语义
- 关联需求：AMF-PHY-003、AMF-PHY-007
- 关联工作项：[FND-PHY-NB](../work_items/foundation_0_1_1_narrowband_contract.md)

## 背景

当前代码只在 `Scene.frequency_hz` 处计算一个复信道 `h`，而 `bandwidth_hz` 只用于热噪声和
`B*log2(1+SNR)`。这与中心频率窄带链路预算相符，但文档此前只写“窄带”和“Shannon 上界”，
没有明确 `frequency_hz` 是中心频率、`h(fc)` 被假定在带宽内平坦，容易被误读为已对整个
100 MHz 逐频点建模。

未来 OFDM、beam squint、材料色散和 frequency-selective multipath 都会改变这一含义，因此
必须先为当前结果建立稳定且可追踪的模型身份。

## 决定

### 1. 频率和带宽

- `Scene.frequency_hz` 是中心频率 `fc`；每次计算自动使用 `lambda=c/fc`、`k=2*pi/lambda`；
- `Scene.bandwidth_hz` 是等效占用/接收噪声带宽 `B`；
- `Transmitter.power_w` 是该等效带宽内的总发射功率，不是 W/Hz 功率谱密度；当前不解析带内
  power allocation；
- propagation/RIS channel 只在 `fc` 评价一次，并假定该复响应在 `B` 内平坦：

```text
h(f) ≈ h(fc),  f in [fc-B/2, fc+B/2]
```

- 修改 `fc` 必须重新计算所有波长、传播相位、方向/孔径诊断和信道分量；
- 仅修改 `B` 不改变 `h(fc)`，但必须重新计算 noise、SNR、capacity 和 coverage。

### 2. 噪声与容量标签

当前指标定义为：

```text
N_dBm = -174 dBm/Hz + 10*log10(B_Hz) + NF_dB
SNR(fc) = Pr(fc)/N
C_flat_upper = B*log2(1+SNR(fc))
```

`ChannelResult.shannon_capacity_bps` 字段为兼容保留，但其准确名称是：

> Center-frequency flat-channel Shannon upper bound

它不是 OFDM sum-rate、频率积分容量、调制编码吞吐量、协议吞吐量或实测速率。GUI、实验与
对外报告凡显示该字段，都必须使用“平坦信道 Shannon 理论上界”或等价明确措辞。

### 3. 稳定模型身份

Foundation 新 provenance 使用：

```text
channel_frequency_model_id = "narrowband_center_frequency_flat_v1"
```

该 ID 是运行/结果元数据，不加入 Scene JSON v1。legacy 结果缺失此字段时标记 legacy，不反向
伪造。未来频率选择性实现必须使用新 ID，并通过 ADR 说明比较/迁移规则。

### 4. 有效域与升级触发

Foundation 不以单一 `B*Delta_tau`、`B/fc` 或固定百分比建立自动 PASS/FAIL，因为当前一次
反射/RIS 系统级模型还没有正式 delay-spread 输出和场景校准。使用者必须把平坦信道视为
显式假设，而不是由软件自动证明的事实。

出现以下任一研究目标时，必须建立 wideband/PathEnsemble 新 capability：

- OFDM subcarrier、frequency-selective fading 或 delay spread；
- RIS beam squint、`Gamma_n(f)`、材料/墙系数色散；
- 带内增益/相位起伏、脉冲响应、ISI 或真实吞吐量；
- 不同频点共同优化或跨频段结果。

## 后果

- 当前数值公式和 Scene v1 不变，但带宽/容量的含义不再含糊；
- `B` 增大可能同时线性增加公式前因子并降低 SNR，不能把容量变化简单解释为 RIS 增益；
- 未来 Profile v1 仍是中心频率环境 modifier，不能通过它偷偷加入未记录的频率选择性；
- Foundation 需要补标签、provenance 和缓存失效契约测试，但不实现 OFDM。

## 候选与否决理由

- **把当前公式称为宽带容量**：否决。没有子载波或频率积分信道。
- **删除 bandwidth/capacity**：否决。它们在明确平坦信道假设下仍是有用的链路预算指标。
- **立即实现 OFDM**：否决。超出 Foundation，并依赖 delay/path/frequency-dependent RIS 模型。
- **用一个固定 `B/fc` 阈值拒绝输入**：否决。不能替代与 delay spread、材料和硬件带宽有关的
  场景化有效性判断。

## 验证

- FND-T20 验证改变 `fc` 会改变波长/信道，改变 `B` 不改变 `h(fc)` 但会改变 noise/SNR/capacity；
- GUI/Model Info 与 experiment schema 人工检查准确显示 flat-channel upper-bound 标签；
- Foundation provenance 包含 `channel_frequency_model_id`，legacy 文件不被回填；
- limitations 和 Definition of Done 明确 wideband 升级触发条件。
