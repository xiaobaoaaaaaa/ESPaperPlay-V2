# 旧工程 AUDIO 页审查

日期：2026-11-01。范围为用户提供的 `.epro2` 归档中的有效 AUDIO 页，不代表当前核心板搭建的实物。用户已说明当前固件运行在核心板上，归档 PCB 与当前运行硬件不同。本次不修改电路或固件，不冻结新版器件。

## 证据与范围

- 原件及哈希见 [旧工程接收记录](../legacy-project.md)。AUDIO 页 UUID 为 `fe8b1fc3c060782a`。
- 已目视检查归档嵌入的同名 WebP 全页原理图，核对 U4/U5/U6、R29–R33、FB1–FB3、H2 的关键连接；并与 PCB `PAD_NET` 记录交叉核对。下文 `L...` 均为解包后 `ESPaperPlay.epru` 的原始行号。
- 固件参照原 ESPaperPlay 仓库固定提交的 [板级配置](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/board/include/espaperplay_config.h)、[音频驱动](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/drivers/audio/src/espaperplay_audio.c)、[电源服务](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/services/power/src/espaperplay_power.c)。软件配置相符不等于已上板验证。
- 本次不包含全板走线/铺铜检查、EMI、热测试、音质或实测功耗；封装焊盘网络只证明归档网络分配，不证明实际铜线已正确连接。

## 已确认的设计事实

| 电路 | 原理图与 PCB 证据 | 评价 |
| --- | --- | --- |
| 独立音频电源 | U6 `TLV62569DBVR`，VIN 接 `VRAW`，SW 经 L3 1µH 到 `AUDIO_3V3`；R29=453kΩ、R30=100kΩ 反馈；C28=10µF、C29=22µF。器件 L11398、L11467；网络 L19855–L19860、L19480–L19482、L19681–L19689 | 有独立开关控制；标称设定 `0.6 × (1 + 453/100) = 3.318 V`，为计算值，未测量 |
| 电源默认关闭 | U6 EN=`AUDIO_PWR_EN`，R31 100kΩ 下拉；MCU U3 pin4 对应 GPIO4。L19693–L19695、L19860、L19772 | 保留复位默认关闭的意图 |
| 麦克风供电 | FB1 `BLM18AG601SN1D` 串接 `AUDIO_3V3 → MIC_3V3`；前端 C30 10µF/C31 100nF，后端 C32 1µF/C33 100nF。L19285–L19305、L19396–L19398 | 是磁珠滤波，不是独立开关或直流隔离；不能单独关闭麦克风 |
| 麦克风接口 | U4 `ICS-43434`：pin1 WS、pin4 SCK、pin5 VDD、pin6 SD；LR pin2 和 GND pin3 接地。L19821–L19830 | 输出左槽；与驱动读取左槽、24-bit 左对齐后取高16位的约定一致 |
| 功放 | U5 `MAX98357AETE+T`：VDD pin7/8=`AUDIO_3V3`，GAIN_SLOT pin2 接 GND，SD_MODE pin4 经 R32 2kΩ 到 GPIO6，并由 R33 100kΩ 下拉。L19834–L19851、L19699–L19707 | 原厂表8对应12dB增益；SD_MODE同时承担关断与声道选择 |
| I²S | BCLK=GPIO12、WS=GPIO7，U4/U5共享；MIC_DOUT=GPIO11、SPK_DIN=GPIO43。U3 L19775、L19787–L19788、L19805；U4/U5网络如上 | 与板级宏一致；没有发现此处脚位对调证据 |
| 扬声器 | U5 OUTP/OUTN 分别经 FB2/FB3 到 H2 pin1/2；C34/C35 各100pF对地，H2 pin3/4为接地辅助焊盘。L19402–L19410、L19309–L19317、L22178–L22182 | 是差分扬声器接口；信号端未直接接地。磁珠和电容是否适合最终线长仍待EMI与音频测试 |

## 修改与验证清单

### A1：声道说明与实际接法不一致（已确认，需修改说明/接口约定）

[板级配置第193行](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/board/include/espaperplay_config.h#L193)写“内部混为单声道”，驱动第265行附近也按混音描述。按归档 R32/R33 和芯片内部典型100kΩ下拉，GPIO高电平为3.3V时，SD_MODE计算约为 `3.3 × (100k || 100k) / (2k + (100k || 100k)) = 3.17 V`。这对应**左声道选择**，并非左右平均；原厂也将约2kΩ串阻作为左声道模式的限流示例。[ADI 数据手册，p17–18、表5](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)

当前驱动把同一个单声道样本复制到两个槽，因此此差异不必然导致当前播放失败。新版应明确“软件混音后送左槽”或其他声道策略，再决定电阻；验证用左/右不同测试音，不能只用双槽相同音频。

### A2：3.3V稳压及“3W功放”不是整段电池范围的保证（事实加条件性风险）

U6 是降压器；输入最低2.5V，输出最高为输入电压，低压差时满足 `VIN(min) = VOUT + IOUT × (RDS(on) + RL)` 才能保持稳压。因此 `VRAW` 接近或低于3.318V时，不能继续把音频轨当作恒定3.3V。归档文字 L12835 的“3.3V/2A”是目标/器件能力描述，不能替代低电量负载验证。[TI 数据手册，p4、p6、§7.3.2](https://www.ti.com/lit/ds/symlink/tlv62569.pdf)

L12838 写“功放3W”；ADI 的3.2W标称具有5V、4Ω及指定失真条件，不能移用于本板约3.3V供电。应先确定扬声器阻抗、额定功率、最低电量和可接受失真，再测输出能力，不据此直接否定MAX98357A。[ADI 产品说明](https://www.analog.com/en/products/max98357a.html)

### A3：关断及电压下降时的跨电源域信号需要验证（风险推断，需修改契约并实测）

U4 的 WS/SCK 直接连接 MCU，无信号隔离；原厂数字输入绝对最大值随麦克风 VDD 变化。若 MIC_3V3 已降至低电压/零，而 MCU 仍输出高电平，可能超过输入限制。低电量下是否发生同类情况还取决于主3.3V与音频轨的相对下降，不能只凭音频轨掉压断言已经倒灌。[TDK 数据手册，p8 表6](https://product.tdk.com/en/search/set_distributor?back_url=%2Fsystem%2Ffiles%2Fdam%2Fdoc%2Fproduct%2Fsw_piezo%2Fmic%2Fmems-mic%2Fdata_sheet%2Fds-000069-ics-43434-v1.2.pdf&ref_disty=mouser)

现有驱动第210–221行先 SD_MODE 拉低、延时、停用/删除 I²S、再关轨，方向可保留；但没有显式定义关轨后的 BCLK/WS 静态电平或高阻，也未验证冷启动、初始化失败、复位及睡眠时的波形。检查本机 IDF 6.1 的 `i2s_del_channel()` 及 `i2s_output_gpio_revoke()` 只发现时钟/资源释放，不能把删除通道当成有证明的断电隔离。

新版需定义开轨、接管引脚、关断、复位的顺序；根据测量决定是否加隔离。不能把 U5 的 BCLK/LRCLK/DIN 与 U4 一概而论：ADI 为这些数字输入给出了独立于VDD的绝对最大范围，SD_MODE则有不同限制且本板已串2kΩ限流。

### A4：MIC_DOUT 缺少原厂建议的外部下拉（已确认，建议补足/验证）

归档中 `MIC_DOUT` 的器件端点只有 U4 pin6 和 U3 pin19，AUDIO/MCU 图中未见该线外部下拉。TDK 建议 SD 配100kΩ下拉以释放三态期间的线电荷（p10表8）。当前仅采左槽并丢弃右槽会减轻无效槽数据的影响，但不等于具备此硬件条件；新版预留/配置相应下拉，并验证空闲电平和启动噪声。

### A5：共享采样率需要明确白名单（已确认的软件接口缺口）

驱动 `start()` 第95–98行仅拒绝0；本板同时给麦克风和功放供时钟，不能任意接受媒体文件原始采样率。MAX98357A原厂明确不支持11.025/12/22.05/24kHz；ICS-43434也只在规定的低功耗/高性能频率区间工作。[ADI 数据手册，p16](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)、[TDK 数据手册，p6](https://product.tdk.com/en/search/set_distributor?back_url=%2Fsystem%2Ffiles%2Fdam%2Fdoc%2Fproduct%2Fsw_piezo%2Fmic%2Fmems-mic%2Fdata_sheet%2Fds-000069-ics-43434-v1.2.pdf&ref_disty=mouser)

旧器件组合可从8/16/32/44.1/48kHz的交集建立验证集合；默认16kHz、32-bit双槽属于合理起点。新版应限制接口或重采样，并验证启动过渡数据丢弃。`MIC_WARMUP_MS=50` 是软件固定等待，不能据此宣称全部采样率的首包已有效。本次未运行实际录放音。

### A6：麦克风生命周期与连接器注释需更新（已确认）

- U4 仍是 ICS-43434；截至本次检查，TDK InvenSense产品页标为 **EOL**。旧库存可用于参考验证，新版长期BOM应另选在产器件并重核接口、时序、声孔和封装。[原厂产品页](https://www.invensense.tdk.com/en-us/products/microphone/ics-43434)
- H2 的实际器件属性是 `WAFER-MX1.25-2PWB`（L12854），但图中文字 L12839 写 `PH2.0-2P`。这是装配说明冲突，应按实际器件图纸/样品统一，不按注释购买线束。

## 保留项与上板验收

保留独立音频域、默认关闭下拉、SD_MODE提前静音、共享I²S时钟与左右数据分离、麦克风电源滤波及差分扬声器接口的设计意图。器件和被动件数值不因此自动进入新版BOM。

开发验证板至少应完成：最低/最高电池电压和USB插拔下的音频轨瞬态；复位/启动失败/停止/睡眠时的 MIC_3V3、BCLK、WS、SD_MODE时序及关断电流；左/右独立测试音；批准采样率的录音首包与持续稳定性；规定扬声器负载下的功率、失真、温升和爆音；Wi-Fi/刷屏/SD并发时底噪与EMI。FB1两侧有去耦不证明布局距离合格，U5去耦、地回路和声孔仍需布局阶段复核。

## 原厂资料版本

- ADI `MAX98357A/MAX98357B`，Rev.16，2026-02；本机只读下载位于 `build/legacy-review/audio-datasheets/max98357a.pdf`。
- TI `TLV62569/TLV62569P`，SLVSDG1C，2017-10修订；本机只读下载位于同目录 `tlv62569.pdf`。这两份下载的大小和SHA-256见该目录 `sources.json`，不进入项目许可。
- TDK `DS-000069 ICS-43434`，Rev.1.2；通过原厂PDF入口的网页抽取核对 p6、p8、p10、p15，直接文件下载本次未成功；未把第三方转载作为上述结论来源。
