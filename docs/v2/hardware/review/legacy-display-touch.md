# 旧板 EPD 与 TOUCH 审查

日期：2026-11-01。对象为用户提供的 `ProPrj_ESPaperPlay_2026-11-01.epro2` 中有效 EPD/TOUCH 页及 PCB1，结合原 ESPaperPlay 仓库的参考固件作交叉检查。本报告不证明归档设计就是当前运行实物；用户已说明当前固件运行于核心板，存在为板载资源调整的适配配置。

## 证据与边界

- 原件 SHA-256：`aa9540b138b95a9e4e70a56337f4366901f3e5233e9a12d55d852e55732ef614`，见 [旧工程记录](../legacy-project.md)。下文 `L` 为解包后的 `ESPaperPlay.epru` 行号。
- 有效 EPD 页 UUID：`6bc65f1bb9c7e213`；有效 TOUCH 页 UUID：`bd9d7bdc63743c49`。已目视核对归档内同 UUID 的完整 WebP 页面，并与器件记录、PCB `PAD_NET` 交叉核对关键连接。缓存截图不是原软件重新生成的网表，PCB 网络也不能单独证明所有原理图连接都已同步。
- 屏幕资料：[GDEY075T7-T01 规格书（原厂下载）](https://v4.cecdn.yun300.cn/100001_1909185147/GDEY075T7-T01.pdf) p6–7、p38；[GT911 Rev.10（屏厂提供的下载）](https://v4.cecdn.yun300.cn/100001_1909185147/GT911%20Datasheet_English%2020150625_Rev.10.pdf) p11–12；[原厂资料索引](../panel-reference.md)。当时已在本机渲染并目视核对 p38 参考电路及 GT911 时序图。PDF仅作为本地参考，不随Git发布；来源、版本与哈希见[sources.json](../../../../hardware/reference/good-display/sources.json)。
- 未做旧工程 ERC/DRC、实板测量、波形或刷新压力测试；下面的电气风险与“已测出故障”分开记录。没有修改电路或固件。

## 已确认、可保留的部分

### EPD 接口与升压拓扑

FPC1 器件记录是 `HYCW3D-05FPC24-200B`（原理图 L17629），PCB 有 24 个信号焊盘及 25/26 两个接地固定焊盘（L19414–19440）。关键脚序与屏厂资料一致：

| FPC1 脚 | 归档 PCB 网络/连接 | 原始行号 |
| --- | --- | --- |
| 1、4 | 空网络，图上 NC 标记 | L19437、L19440 |
| 2 GDR、3 RESE | Q1 栅极/源极及 R2 取样网络 | L19438–19439、L19493–19495 |
| 5 VSHR | `$3N50`，C1 4.7 µF 至 GND | L19436、L19112–19113 |
| 6 TSCL、7 TSDA | 空网络，外部温度接口未使用 | L19434–19435 |
| 8 BS1 | GND，选择 4-wire SPI | L19433 |
| 9 BUSY | BUSY → U3 模组脚 17 / GPIO9 | L19432、L19785 |
| 10 RES、11 D/C、12 CS | RES、D/C、CS → GPIO8、18、17 | L19429–19431、L19778–19780 |
| 13 SCL、14 SDA | SCLK、SDI → GPIO16、15；此处是 SPI | L19427–19428、L19776–19777 |
| 15 VDDIO、16 VCI | 同接 `3V3_PER` | L19425–19426 |
| 17 VSS | GND | L19424 |
| 18 VDD | `$3N63`，仅 C6 1 µF 去耦至 GND；未短接 3.3 V | L19423、L19142–19143 |
| 19 VPP | 空网络，图上 NC 标记 | L19422 |
| 20 VSH1、22 VSL | 分别通过 C7、C9 4.7 µF 去耦至 GND | L19419、L19421、L19148–19149、L19160–19161 |
| 21 VGH、23 VGL、24 VCOM | PREVGH、PREVGL、VCOM；分别有 C4/C8/C10 | L19417–19420、L19131、L19154、L19166 |

EPD 页中 L1=10 µH，Q1 标称 SI1308EDL，D1–D3 标称 MBR0530，R1=1 MΩ 栅极下拉，R2=0.47 Ω 电流取样；C1–C10 容值及正负升压连接与屏厂 p38 参考拓扑一致（L17666–17973；PCB L19356–19370、L19467–19495、L19513–19521）。因此保留该拓扑作为新板的核对基线，不能把裸屏当作仅接电源与 SPI 的成品模块。

容值与额定电压可交叉确认：4.7 µF 使用 `CL10A475KA8NQNC`，三星原厂页面为 25 V X5R；1 µF 使用 `CC0603KRX5R8BB105`，YAGEO 原厂规格为 25 V X5R。它们符合屏厂 p38 的名义耐压要求；工作偏压后的有效电容与纹波仍未测。[三星规格](https://product.samsungsem.com/cn/mlcc/CL10A475KA8NQN.do)、[YAGEO 规格](https://www.yageogroup.com/download/specsheet/CC0603KRX5R8BB105)

现有驱动将 BUSY 低电平视为忙，并在电源/刷新命令后等待，与面板定义相符。参考 [epd_wait_busy](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/drivers/epd/src/espaperplay_epd.c) 第 287–301 行；GPIO 宏也与上述归档网络一致。

### TOUCH 接口

FPC2 为 `LAIL-FPC-CDX01-6P0.5-GW`（L14505），其 1–6 脚依次为 GND、`3V3_PER`、RST、INT、SDA、SCL；7/8 为接地固定焊盘（L19894–19902）。此信号脚序与屏厂总成/触摸图一致。

RST、INT、SDA、SCL 分别接 GPIO14、3、10、13；PCB U3 模组脚 22、15、18、21 的网络记录位于 L19783、L19786、L19789–19790。R3/R4 将 SDA/SCL 以 10 kΩ 上拉到 `3V3_PER`，R5 将 RST 以 10 kΩ 上拉到同一轨；C11=100 nF、C12/C13=4.7 µF 去耦（L19171–19185、L19525–19539）。保留独立 RESET/INT 控制和外部上拉、就地去耦的设计思路；INT 在地址选择阶段必须允许 MCU 输出。

## 修改与待验证清单

### DT-01：高地址回退的 GT911 复位流程缺少 INT 低电平阶段

**已确认的软件差异，建议修改后测波形。** [gt911_hw_reset](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/drivers/touch/src/espaperplay_touch.c) 第 222–251 行先输出选择电平，保持 RESET 低 20 ms，释放 RESET 后维持该 INT 电平 60 ms，随后直接将 INT 改为输入。初始化第 988–1001 行在 `0x5D` 失败后尝试 `0x14`，运行恢复第 801–813 行同样调用此函数。

GT911 原厂 p12 的高地址时序明确包含：INT 高选择地址，RESET 释放后保持超过 5 ms，**再将 INT 拉低超过 50 ms，最后转输入**。当前 `gt911_hw_reset(1)` 缺少后面的低电平阶段。默认 `0x5D` 路径一直为低，其保持时间覆盖该阶段，但不能据此认为 `0x14` 路径也已符合时序。

建议分别实现地址选择保持与低电平同步阶段，并在 `0x5D`、`0x14` 两条路径上记录 RESET/INT 波形、产品 ID、首帧触摸及重复恢复。这里确认的是代码与规格不一致，未断言当前核心板已出现该故障；本轮没有改固件。

### DT-02：外设断轨前没有完整释放 EPD/TOUCH 信号

**关闭序列缺口已确认；倒灌与异常状态属于待测风险。** 归档的 EPD、触摸供电与触摸上拉均属于 `3V3_PER`，信号直连常供电 MCU，未见页内隔离器。现有驱动将 TOUCH_RST/EPD_RST 驱动高，将 TOUCH_INT/EPD_BUSY 设为输入上拉，并启用 I²C 内部上拉（touch 第 234–249、981 行，epd 第 167–177 行）。

[深睡流程](https://github.com/xiaobaoaaaaaa/ESPaperPlay/blob/0f6d7c349afdbbeb962a736d84036ce7f8487174/components/services/power/src/espaperplay_power.c) 第 850–872 行在 EPD 休眠后直接关闭外设轨并进入深睡，未在此路径停止触摸读取/恢复任务、拆除 I²C 或释放上述引脚。EPD 控制器睡眠命令不等于 MCU 引脚断电隔离。

建议新平台明确“停止访问 → 外设睡眠 → 释放/隔离信号 → 断轨”的顺序，并按外设逐一检查；触摸后台任务不能在断轨期间继续探测或复位。验收应测关闭前后 `3V3_PER` 电压、MCU→外设引脚电压、关断电流及重复上电恢复。未测量前不填写漏电数值，也不把 MCU 进入深睡后的默认状态当作过渡期间无倒灌的保证。

### DT-03：10 kΩ 上拉与 400 kHz 的裕量需要波形验证

**已确认参数，尚不能判为通信不合格。** R3/R4=10 kΩ；固件默认触摸 I²C=400 kHz，并行启用 MCU 内部上拉。GT911 p11 给出的 400 kbit/s 测试条件使用 2 kΩ，上拉值不能只按“有电阻”验收。

按 `tr = 0.8473 × Rp × Cb`，仅考虑 10 kΩ 外部上拉、Fast-mode 300 ns 上升时间上限时，总电容约需不超过 35 pF；内部并联上拉、触摸总成内部电路和实际 FPC 会改变结果。这个值是条件计算，不是测得的总线电容。[TI I²C 上拉计算，p3](https://www.ti.com/lit/an/slva689/slva689.pdf)

建议在实际 FPC、接插件和供电条件下测 SDA/SCL 的 30%–70% 上升时间、低电平和重试率，再决定上拉值与运行频率；同步计入低电平时的静态电流。

### DT-04：GPIO3 的触摸 INT 需要与启动绑定位区分

**归档连接已确认，启动故障未证实。** GPIO3 同时是 JTAG 来源选择的 strapping pin；其作用取决于 eFuse，默认 `STRAP_JTAG_SEL=0` 时不能简单断言 GT911 INT 电平会改变 JTAG 或导致启动失败。现有页没有外部 INT 上拉，运行时的 MCU 内部上拉也不等于硬复位时的确定电平。[Espressif JTAG 选择说明](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/jtag-debugging/configure-other-jtag.html)

新版按已讨论方案将正常触摸中断迁到合适的非 strapping GPIO；旧板调试记录实际 eFuse 状态、冷启动/仅 MCU 复位/触摸保持供电三种场景。无需为规避这一问题烧写不可逆 eFuse。

### DT-05：升压器件的完整厂家型号与原厂参考要求仍需核验

**归档库属性与参考要求存在未闭合项，不等于已判定器件失效。**

| 位号 | 归档的实际器件身份与声明 | 审查结论 |
| --- | --- | --- |
| Q1 | TECH PUBLIC（台舟）`SI1308EDL`，C7603347；库声明 30 V、150 mΩ@4.5 V、Qg 2.6 nC@4.5 V；DEVICE L11281 | 不能拿 Vishay 同名器件资料替代该供应商规格。应核对实际 GDR 电压下的导通、栅极负载、引脚和温升 |
| D1–D3 | R+O（宏嘉诚）`MBR0530`，C55068180；库声明 30 V、500 mA、470 mV@0.5 A；DEVICE L11251 | 屏厂 p38 写正向压降 ≤430 mV，但未在该表列同一测试条件。需要实际厂家规格统一测试条件再判断替代资格 |
| L1 | cjiang（长江微电）`FHD252012S-100MT`，C602018；库声明 10 µH、额定 1 A、Isat 1.35 A、DCR 435 mΩ；DEVICE L11241 | 数值为工程库声明，尚未核实该厂完整曲线；测刷新峰值电流、饱和与温升后再验收 |

同时检查 R2 的实际功率与脉冲负荷、各电容偏压降额、PREVGH/PREVGL/VCOM 电压及纹波。当前可保留升压原理，但不能仅因元件名称与参考图相同就冻结新 BOM。

### DT-06：图纸注释把固定焊脚计入 FPC 触点数

**已确认的文档问题。** EPD 注释 L18351 写 `HYCWD3D-056FPC22-200B(26PIN)`，与实际器件属性 `HYCW3D-05FPC24-200B` 不一致；TOUCH 注释 L14935 称 `FPC2 8PIN`。实际是 24/6 个信号触点加各两个固定焊盘，应分别标注，避免连接器采购与脚序核对误用。机械接触面、插入方向、锁扣和样品适配仍需按实际连接器图纸检查。

## 本轮结论

保留：EPD 参考升压拓扑、FPC 信号脚序、VDD18 单独去耦、BUSY 低有效、触摸 RESET/INT 可控及外部上拉/去耦。

修改：GT911 高地址复位阶段；新平台外设断轨的任务/引脚处理；FPC 位数与型号注释。GPIO3 迁移随新板 GPIO 规格统一处理。

待验证：实际核心板与归档板的差异、400 kHz 总线上升时间、掉电倒灌、两种地址及异常恢复、升压替代料完整规格和实测波形、FPC 机械适配。没有据本轮静态审查承诺实板稳定性或功耗结果。
