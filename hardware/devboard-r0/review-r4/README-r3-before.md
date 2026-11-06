# ESPaperPlay 开发验证板：BOM 与封装审查 r3

更新日期：2026-11-02。**十页可编辑 KiCad 原理图：一张索引、九张功能页；r3 已完成首轮 BOM 与封装资料审查。** 共有222个实体器件位置（含6个DNP）、178条网络；215个位置有封装候选，184个位置有准确候选料号。目录沿用 `devboard-r0` 以保留工程路径。尚未布PCB、上电或冻结制造BOM，电池充电仍未批准装配。

本轮结果见[BOM与封装审查报告](../../docs/v2/hardware/bom-footprint-review-r3.md)、[逐位号审查数据](review-r3/bom-review.json)及[可筛选工作簿](../../outputs/espaperplay-bom-r3/ESPaperPlay_BOM_Review_r3.xlsx)。`Candidate_MPN` 是候选属性，不等于批准采购；38个位置的准确料号仍待定，其中包括2个DNP调谐电容。7个封装继续留空：J102/J103/J406/J601/J801、R602、U803。

## 打开与查看

打开 [ESPaperPlay_Devboard.kicad_pro](ESPaperPlay_Devboard.kicad_pro)，进入原理图，再双击根页功能框。也可直接打开[根原理图](ESPaperPlay_Devboard.kicad_sch)。

| 页 | 内容 |
| --- | --- |
| 1 | 工程索引、装配默认状态与当前边界 |
| 2 [POWER_INPUT_CHARGER](POWER_INPUT_CHARGER.kicad_sch) | BQ24074、保护后电池/NTC、默认禁充、输入档位、USB支路检测 |
| 3 [POWER_3V3_CONTROL](POWER_3V3_CONTROL.kicad_sch) | TPS63802、反馈与测流、TCA9539、MAX17048 |
| 4 [MCU_CORE](MCU_CORE.kicad_sch) | N16R8实际焊盘、去耦、EN/BOOT、正常电源/翻页键、功能调试头 |
| 5 [USB_INPUT](USB_INPUT.kicad_sch) | USB-C设备端、独立CC下拉、数据/CC保护、PTC/TVS、单跳帽选源 |
| 6 [POWER_DOMAINS](POWER_DOMAINS.kicad_sch) | EPD、SD、TOUCH、MIC、AMP五路TPS22918、测流断点与泄放 |
| 7 [TOUCH_ISOLATION](TOUCH_ISOLATION.kicad_sch) | TMUX1511四路隔离、GT911功能接口、上电/掉电和注电约束 |
| 8 [EPD_DISPLAY](EPD_DISPLAY.kicad_sch) | 原厂升压拓扑、24针FPC、五路写缓冲与BUSY返回 |
| 9 [STORAGE_SD](STORAGE_SD.kicad_sch) | microSD插座、六线隔离、卡侧上拉、检测和ESD保护 |
| 10 [AUDIO](AUDIO.kicad_sch) | I²S缓冲、施密特输出使能、MAX98357A、PUI麦克风候选 |

[本地十页PDF预览](output/pdf/ESPaperPlay_Devboard_BOM_r3.pdf)由当前原生工程导出，未纳入Git，可按下方命令重建。旧r0/r1/r2 PDF仅为前轮参考。

已用KiCad **10.0.7**解析、导出并检查。初始文件使用兼容格式，首次用编辑器保存时可能提示升级格式。**原生文件是后续手工编辑的工作源，不应运行生成器覆盖。** `tools/generate_power_schematic.py`保留最初r0两页草稿；其余生成脚本只生成各自分组草稿，均不是完整r2工程的再生成命令。实验输出必须放在空的临时目录。

## 电路与默认状态

| 项目 | 实际实现 / 初始状态 |
| --- | --- |
| 选源 | J502仅装一个跳帽：1–2 USB、2–3台架，拔除则断开充电器输入。断电后换档，不能短接两路源；不是自动电源切换电路 |
| USB输入 | J501→F501→USB_5V_PROTECTED→J502；D501从保护后节点到地。CC1/CC2各自5.1k下拉；无PD、Host、CC电流识别 |
| 台架输入 | 原J101接BENCH_5V，仅使用已知稳压、限流5 V电源。该支路不经过USB的PTC/TVS，不保证反接或错误电压保护 |
| USB数据 | D−=GPIO19/模组焊盘13，D+=GPIO20/焊盘14；两组正反插接点合并，22Ω串阻靠MCU；C501/C502为真实DNP调谐预留 |
| 电池 | J102接保护后的电池正负端，J103接实际NTC；均为功能接口，真实电池连接器/脚序待定 |
| 系统测流 | R102测整个BAT支路；R101分开SYS_RAW/SYS；R203分开3V3_REG/3V3_AON；8个电源测流连接采用Bourns CRF0805金属低阻跳线候选，整板电流和温升仍待核 |
| 充电禁止 | R108 `CHG_ARM` **DNP**；Q101栅极100k下拉。R106从芯片侧SYS_RAW上拉CE_N，拔R101不会撤掉禁充上拉 |
| 输入档位 | EN1/EN2外部下拉，默认00=100 mA；不能因VBUS有电或有CC下拉就升档。整口还要计入绕过BQ限流的检测/保护电流 |
| 充电参数 | R103=1.62k、R104=3k、R105=68k只是计算候选；约297 mA典型充电电流不等于电池参数已批准 |
| 主电源 | J202单跳帽1–2运行、2–3关闭；开路由R205默认关闭。关掉主稳压后不能靠GPIO21普通按键重新供电 |
| 维护恢复 | J105默认开放。只有合格电池/NTC、主电源及音频关闭、已知来源时才强制CE低；NTC/ISET/TMR仍有效 |
| 反馈 | C202、R201上臂、U201 VOUT均留在R203前，测流断开不会丢失反馈 |
| 扩展器 | TCA9539地址0x74，GPIO42独立控制RESET；P13为SD_IO_EN且10k下拉；P14–P17各100k下拉并保持输入；先写安全锁存再设输出方向 |
| 电量计 | MAX17048 VDD/CELL接BAT_PROT；R217/R218只是调试断开点，不能证明电池断开时Ioff合格或可靠判定电池存在 |
| USB检测 | R221取USB_5V_PROTECTED，即PTC之后、选源之前；Q201开漏拉低GPIO2表示USB支路有电。PTC跳脱可能撤掉指示，不等于检测物理插头；PGOOD表示选中输入有效 |
| 主控 | N16R8，GPIO35/36/37为内存保留，3/45/46不接外设；USB为默认调试通道，43/44已分配音频/按键，不能再常接UART0 |
| 用户按键 | GPIO21正常电源键，GPIO44/5翻页或音量；EN/BOOT是独立维护键，软件去抖/唤醒仍待固件实现和实测 |
| 音频默认 | GPIO4经R416=10k下拉使MIC与AMP两路默认关；GPIO6经R306=10k下拉默认静音。AMP取SYS，不使用5 V升压；录音时MIC和AMP供电会一起开启 |

ERC按逻辑连接工作，**不模拟DNP、跳帽状态、电源能力、时序、保护动作或温度**。R108、C501/C502及J301–303的DNP真实存在于KiCad属性和PDF中。原理图的PWR_FLAG只描述正常RUN且测流连接已装配状态，不是保护器件。

J201/J205含AON电源；外部3.3 V注入前断R203，不能并联核心板稳压器。J205依次为AON/GND/SDA/SCL/IOX_RESET/VBUS；J206为控制信号接口。J301/302/303在r2默认DNP，保留MCU侧高阻探测位置。板上EPD/SD/音频负载已连接，不得再接外设模块或通过这些接口注入电源。

## 分域测量与触摸隔离

| 域 | 输入 / 使能 | 输出 | 测流断点 | QOD泄放电阻 |
| --- | --- | --- | --- | --- |
| EPD | AON / IOX P00 | EPD_3V3 | R402 | R401 |
| SD | AON / IOX P01 | SD_3V3 | R405 | R404 |
| TOUCH | AON / IOX P02 | TOUCH_3V3 | R408 | R407 |
| MIC | AON / GPIO4 | MIC_3V3 | R411 | R410 |
| AMP | SYS / GPIO4 | AMP_SYS | R414 | R413 |

五路CT暂定4.7nF、QOD外阻330Ω，输入/输出电容仍需随实际负载校核。测流连接只计下游负载，不含上游开关自身静态电流。**QOD接在测流之后：仅拆0Ω并不完全隔离输出轨。** 外部注电须同时断开QOD并处理跨域信号；上游无电时也不能假定快速泄放有效。低压轨关断后1 s内低于0.2 V只是测试目标，不包含墨水屏高压节点。TPS22918不提供精确限流或反向电流阻断。

TMUX1511及触摸侧上拉/去耦全部在R408后；四个SEL均接TOUCH_IO_EN，由IOX P10控制，R215=10k默认拉低。隔离SDA、SCL、RESET、双向INT，J406六针功能顺序为GND/VCC/RESET/INT/SDA/SCL；**真实FPC封装、接触面和插座型号尚未指定**。AON侧4.7k与触摸侧10k在开关接通时约为3.20k，还要加上屏幕自带上拉与电容再核算。掉电先隔离再关轨；上电执行完整GT911选址/复位流程。

## 新增外设与时序

完整连接说明见[外设电路设计r2](../../docs/v2/hardware/peripheral-design-r2.md)。

- **EPD**：原厂p38升压，J601第18脚仅接内部稳压电容；五路写信号经EPD供电SN74LVC541A，BUSY经AON供电SN74LVC1G125返回。断电时BUSY低表示忙/无效。当前不支持SDI读回。
- **SD**：两个TMUX1511隔离六根总线，P01开供电、P13独立接通信号；CMD/DAT0–3均有卡侧10k上拉。上电先等供电稳定再接通；关闭先卸载、停总线、隔离再断电。400kHz初始化、4-bit 20MHz为验证目标。
- **音频**：明确采用有Ioff规格的Nexperia 74LVC125APW，不能直接换成TI同名系列；SN74LVC1G14施密特反相器驱动四个/OE。MAX98357A接左声道、6dB候选增益，BTL两根扬声器线均不接地。
- **麦克风**：PUI DMM-4026-B-I2S-R为3.3 V、7焊盘候选，生命周期/采购仍待确认。首测48kHz、双32-bit槽、64fs；旧16kHz配置不适用，现有固件没有改动。底部声孔与专用封装尚未建立。
- **复位默认**：R215/R223/R306/R416均改为10k，按多输入最坏漏电核算；使能高时每个约330µA，属于活动电流。新增两颗AON返回缓冲的静态电流须纳入睡眠实测。

这些缓冲/模拟开关的掉电规格不能替代电源坡度、残压、注入电流和热插拔验证。FPC接触面、SD卡座检测触点的实际位置、扬声器/电池连接器仍需对照样品。

## 符号、封装与资料

本地[符号库](ESPaperPlay.kicad_sym)含13种符号，覆盖电源、扩展器、模拟开关、显示接口与音频；按原厂物理引脚核对。[sym-lib-table](sym-lib-table)通过相对路径引用。其他符号嵌入标准库副本。MAX98357A的EP17按原厂定义作为接地散热焊盘；两个1G125符号仅绘图几何不同。

- [本地封装库](ESPaperPlay.pretty)含13种候选，经[fp-lib-table](fp-lib-table)相对引用。TPS63802已建立DLA0010A非对称10焊盘：8脚为宽PGND焊盘，没有第11脚中央EP；BQ24074、MAX98357A、TPD2E2U06、AO3400A、保险丝、电感、金属跳线及排针均有对应资料。
- TCA9539用PW24脚序；MAX17048用G+ TDFN8加EP9；TPS22918为DBV6，TMUX1511为PW14。所填封装为候选，PCB前还要核实实物/机械图。
- USB插座采用GCT USB4105-GF-A、按键采用Omron B3F-1002-G候选。屏幕/触摸FPC、麦克风声孔、电池/扬声器线束、R602脉冲额定和MLCC有效容量尚待闭合；这些选择尚未成为制造BOM。
- D601–603已改为单独核对过的onsemi MBR0530T1G，不能沿用旧MBR0530的数据手册。16个100nF位置选TDK C1608X7R1H104K080AA候选；6个4.7µF/50V高压电容改用1206候选，仍需DC偏压有效容量证据。
- F501在50°C时保持电流仅0.85A，低于R103对应约0.917–1.072A的可编程输入限流范围。默认输入档位仍是100mA，升档前须核对USB来源和热/电流预算，不能直接增大保险丝。
- Q101/Q201为AOS AO3400A NMOS，1G/2S/3D。D501为AOS单向SMAJ6.0A，KiCad焊盘1是阴极接USB保护后电压，2是阳极接地。
- [电源原厂资料与哈希](../reference/power/README.md)、[主控/USB原厂资料与哈希](../reference/mcu-usb/README.md)、[屏幕资料](../reference/good-display/README.md)、[新增外设资料与哈希](../reference/peripherals/README.md)。标准KiCad库采用CC-BY-SA 4.0及电子设计例外，见本机`/usr/share/licenses/kicad/LICENSE-symbols.md`。
- [r3原厂资料索引](../reference/bom-r3/README.md)含77个URL记录、12份新下载PDF及20份原有PDF引用；在线页面不冒充已归档原始文件。

## 验证与复现

- 十页原生文件解析、PDF/XML导出通过；**ERC 0错误、0警告、0排除项**。
- **658项关键物理引脚检查通过**，包含原r1的371项，以及新增外设285项和R223的2个引脚；检查器读取独立保存的物理引脚契约，不导入绘图生成器。
- r3全部215个已指定封装位置、32种封装经`pcbnew`原生加载，焊盘编号集合与符号引脚一致。222个器件UUID、6个DNP状态保留，r2/r3的178个电气网络连接集合完全一致。焊盘编号匹配不代表FPC适配、焊接工艺或电气额定已获验证。
- 对合并后网表单独复核SD的87个引脚和音频的86个引脚。原r1的USB59引脚独立审查记录保留，当前完整检查器继续覆盖该电路。
- 十页PDF已逐页渲染检查。EPD_SW统一使用页内标签，避免与电源页开关输出的同名局部标签混淆；不同页的同名局部网络互不相连。
- 尚未验证上电、充电/NTC、功耗、热、浪涌/ESD、USB启动/协议、GPIO复位保持、总线掉电和电池存在判据。

R221=10k/R222=47k，在USB选通且只计现有约4.8µF时名义RC约0.27 s；BENCH选源、电容容差/寄生、PTC状态会改变响应，不能把计算当实测插拔延迟。USB H05测试覆盖两种选源及保护动作。验证快照和源文件哈希见[verification.json](verification.json)。

从仓库根目录依次运行：

```sh
mkdir -p build/devboard-r3
kicad-cli sch erc --format json --severity-all --exit-code-violations \
  -o build/devboard-r3/erc.json hardware/devboard-r0/ESPaperPlay_Devboard.kicad_sch
kicad-cli sch export netlist --format kicadxml -o build/devboard-r3/peripheral.net.xml \
  hardware/devboard-r0/ESPaperPlay_Devboard.kicad_sch
python3 hardware/devboard-r0/tools/check_peripheral_netlist.py \
  build/devboard-r3/peripheral.net.xml --erc build/devboard-r3/erc.json
python3 hardware/devboard-r0/tools/check_bom_footprints.py \
  build/devboard-r3/peripheral.net.xml \
  --baseline hardware/devboard-r0/review-r3/electrical-baseline-r2.json \
  --output build/devboard-r3/bom-footprint-check.json
mkdir -p hardware/devboard-r0/output/pdf
kicad-cli sch export pdf -o hardware/devboard-r0/output/pdf/ESPaperPlay_Devboard_BOM_r3.pdf \
  hardware/devboard-r0/ESPaperPlay_Devboard.kicad_sch
```

基线XML属于本机前轮导出；仓库另保留[连接分组快照](review-r3/electrical-baseline-r2.json)，检查器可使用该JSON在其他机器复核。原生工程是编辑源，旧生成脚本不应覆盖它。

下一步先闭合FPC/麦克风/线束机械接口、MLCC有效容量、采样电阻和输入电流/温升预算，再进入开发板布局。电池容量、保护、NTC R–T/温区仍是充电装配的前置条件。
